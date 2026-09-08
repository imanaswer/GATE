"""Exam engine: selection, timer, autosave, submission, scoring.

Everything in here assumes the client is hostile and the network is unreliable,
because at 50,000 students both are true somewhere. Three rules the rest of the
module exists to enforce:

  1. The correct answer never leaves the server.
  2. The clock the exam runs on is the database's, never the browser's.
  3. A student has exactly one attempt, and no sequence of retries, refreshes,
     duplicate tabs or lost connections can produce a second one.
"""
import random
from collections import defaultdict

from fastapi import HTTPException, status

GRACE_SECONDS = 30
"""Absorbs network lag on a final answer. Thirty seconds cannot be gamed into a
meaningful advantage on a twenty-minute exam, and without it a student on a slow
connection loses the answer they submitted in time."""


class BankTooSmall(Exception):
    """A domain cannot serve its blueprint. Loud on purpose: silently handing a
    student 12 questions instead of 15 is an unfair exam, not a degraded one."""


def select_questions(cur, domain_id, blueprint: dict[str, int]) -> list[dict]:
    """Pick questions per the difficulty blueprint, spread across topics.

    Not `ORDER BY random() LIMIT 15`: that ignores difficulty entirely and
    happily returns five questions on the same topic. This draws each difficulty
    tier separately and round-robins across shuffled topics, so a student gets
    the intended difficulty mix *and* a spread of subject matter.
    """
    cur.execute(
        """
        select id, topic, difficulty from questions
        where domain_id = %s and status = 'active'
        """,
        (domain_id,),
    )
    by_tier: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in cur.fetchall():
        by_tier[row["difficulty"]][row["topic"]].append(row["id"])

    chosen: list[dict] = []
    for difficulty, quota in blueprint.items():
        topics = by_tier.get(difficulty, {})
        available = sum(len(v) for v in topics.values())
        if available < quota:
            raise BankTooSmall(
                f"domain needs {quota} active {difficulty} questions but has {available}"
            )

        buckets = list(topics.values())
        for bucket in buckets:
            random.shuffle(bucket)
        random.shuffle(buckets)

        picked: list = []
        # Round-robin: take one per topic before taking a second from any.
        while len(picked) < quota:
            for bucket in buckets:
                if bucket:
                    picked.append(bucket.pop())
                    if len(picked) == quota:
                        break
        chosen.extend({"id": qid, "difficulty": difficulty} for qid in picked)

    # Shuffle the final order so difficulty is not readable from position.
    random.shuffle(chosen)
    return chosen


def create_attempt(cur, user_id, event, domain) -> dict:
    """One short transaction: insert the attempt, pick questions, freeze the
    option order. No PDF, no email, no analytics — this runs under whatever peak
    concurrency the event produces, and UNIQUE(user_id, event_id) serialises
    concurrent starts for the same student."""
    selected = select_questions(cur, domain["id"], event["blueprint"])

    cur.execute(
        """
        insert into exam_attempts (user_id, event_id, domain_id, expires_at)
        values (%s, %s, %s, now() + make_interval(secs => %s))
        returning *
        """,
        (user_id, event["id"], domain["id"], event["duration_seconds"]),
    )
    attempt = cur.fetchone()

    for position, item in enumerate(selected, start=1):
        cur.execute(
            "select id from question_options where question_id = %s order by position",
            (item["id"],),
        )
        option_ids = [r["id"] for r in cur.fetchall()]
        # Frozen once, here. Reshuffling on every render would look like a bug to
        # the student and would break the position-based answer they already gave.
        random.shuffle(option_ids)
        cur.execute(
            """
            insert into attempt_questions (attempt_id, question_id, position, option_order)
            values (%s, %s, %s, %s)
            """,
            (attempt["id"], item["id"], position, option_ids),
        )

    return attempt


def load_paper(cur, attempt) -> list[dict]:
    """The student's questions, in their frozen order, with their frozen option
    order — and without `is_correct`, which is never selected anywhere on this
    path. Saved answers come back too, so a refresh restores exactly what was
    on screen."""
    cur.execute(
        """
        select aq.position, aq.option_order, aq.id as attempt_question_id,
               q.type, q.body, q.code_snippet, q.language, q.topic, q.difficulty,
               a.selected_option_id
        from attempt_questions aq
        join questions q on q.id = aq.question_id
        left join answers a on a.attempt_question_id = aq.id
        where aq.attempt_id = %s
        order by aq.position
        """,
        (attempt["id"],),
    )
    rows = cur.fetchall()
    if not rows:
        return []

    option_ids = [oid for r in rows for oid in r["option_order"]]
    cur.execute(
        "select id, body from question_options where id = any(%s)", (option_ids,)
    )
    bodies = {r["id"]: r["body"] for r in cur.fetchall()}

    return [
        {
            "position": r["position"],
            "type": r["type"],
            "body": r["body"],
            "code": r["code_snippet"],
            "language": r["language"],
            "topic": r["topic"],
            "difficulty": r["difficulty"],
            "options": [
                {"id": str(oid), "body": bodies[oid]} for oid in r["option_order"]
            ],
            "selected_option_id": str(r["selected_option_id"])
            if r["selected_option_id"]
            else None,
        }
        for r in rows
    ]


def save_answer(cur, attempt, position: int, option_id: str | None) -> None:
    """Idempotent by construction: UNIQUE(attempt_question_id) makes this an
    upsert, so the client can retry as often as the network demands. A null
    option means the student deliberately cleared their answer."""
    cur.execute(
        "select id, option_order from attempt_questions where attempt_id = %s and position = %s",
        (attempt["id"], position),
    )
    aq = cur.fetchone()
    if not aq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such question in this attempt")

    # The option must belong to *this* question in *this* attempt. Without this
    # check a student could post any option id and have it scored.
    if option_id is not None and option_id not in {str(o) for o in aq["option_order"]}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "option does not belong to this question"
        )

    cur.execute(
        """
        insert into answers (attempt_id, attempt_question_id, selected_option_id, answered_at)
        values (%s, %s, %s, now())
        on conflict (attempt_question_id) do update
          set selected_option_id = excluded.selected_option_id,
              answered_at = now()
        """,
        (attempt["id"], aq["id"], option_id),
    )


def score(cur, attempt_id, final_status: str = "submitted") -> dict:
    """Grade server-side, in one transaction, from the database's own record of
    which option is correct. Runs for both a real submission and a timed-out
    attempt, so a student who closes their laptop is still scored and
    certificated rather than left in limbo."""
    cur.execute(
        """
        update answers a
        set is_correct = o.is_correct
        from question_options o
        where a.selected_option_id = o.id and a.attempt_id = %s
        """,
        (attempt_id,),
    )
    # A cleared or never-given answer is a skip, not a wrong answer.
    cur.execute(
        "update answers set is_correct = null where attempt_id = %s and selected_option_id is null",
        (attempt_id,),
    )
    cur.execute(
        """
        update exam_attempts set
          status = %s,
          submitted_at = now(),
          correct_count = c.correct,
          wrong_count = c.wrong,
          skipped_count = c.total - c.correct - c.wrong,
          score = c.correct
        from (
          select
            (select count(*) from attempt_questions where attempt_id = %s) as total,
            (select count(*) from answers
              where attempt_id = %s and is_correct) as correct,
            (select count(*) from answers
              where attempt_id = %s and is_correct = false) as wrong
        ) c
        where exam_attempts.id = %s
        returning *
        """,
        (final_status, attempt_id, attempt_id, attempt_id, attempt_id),
    )
    return cur.fetchone()
