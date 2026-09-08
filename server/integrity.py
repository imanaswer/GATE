"""Post-hoc integrity signals.

Read the design spec §1.2 before extending this. Browser signals — tab switches,
fullscreen exits — catch a student who alt-tabs on the same device and nothing
else. They cannot see a second device, a phone, a shared screen or a person
sitting next to them, and no amount of client-side cleverness changes that.

The two signals here carry more information than the browser ones, because both
are computed server-side from data the student cannot edit:

  fast_response  a correct answer to a hard question returned implausibly fast
  pattern_match  two students whose entire answer sequence is identical

Neither disqualifies anyone. They produce a list for a human to look at.
"""
import logging

from server.settings import settings

log = logging.getLogger("tech-arena")

# A hard debugging question cannot be read, understood and answered in eight
# seconds. Advisory: response_ms is client-reported and therefore spoofable —
# which only matters in one direction, since spoofing it *slower* is what
# someone cheating would do, and that removes them from this list rather than
# adding them.
FAST_MS = {"hard": 8000, "medium": 5000, "easy": 3000}
MIN_FAST_ANSWERS = 4


def scan(cur) -> dict:
    """Idempotent: re-running replaces this scan's flags rather than piling up
    duplicates, so it is safe on a schedule and safe to trigger by hand.

    Scoped to the active event. On an hourly cron an unscoped version would
    re-hash every answer ever recorded, forever — 750,000 rows sorted every hour
    to recompute a result that only changes when new attempts finish — and it
    would also delete flags belonging to a previous event nobody asked it to
    touch."""
    cur.execute("select id from exam_events where slug = %s", (settings.event_slug,))
    event = cur.fetchone()
    if not event:
        log.warning("integrity scan: no event %r", settings.event_slug)
        return {"fast_response": 0, "pattern_match": 0}
    event_id = event["id"]

    cur.execute(
        """
        delete from suspicious_activity
        where type in ('fast_response','pattern_match')
          and attempt_id in (select id from exam_attempts where event_id = %s)
        """,
        (event_id,),
    )

    fast = _flag_fast_responses(cur, event_id)
    patterns = _flag_duplicate_patterns(cur, event_id)
    return {"fast_response": fast, "pattern_match": patterns}


def _flag_fast_responses(cur, event_id) -> int:
    """One quick answer is luck. A paper where several hard questions came back
    correct in seconds is a different claim."""
    cur.execute(
        """
        with quick as (
          select a.id as attempt_id, a.user_id,
                 count(*) as quick_answers,
                 min(ans.response_ms) as fastest_ms
          from exam_attempts a
          join attempt_questions aq on aq.attempt_id = a.id
          join questions q on q.id = aq.question_id
          join answers ans on ans.attempt_question_id = aq.id
          where a.event_id = %s
            and a.status in ('submitted','expired')
            and ans.is_correct
            and ans.response_ms is not null
            and ans.response_ms < case q.difficulty
                                    when 'hard' then %s
                                    when 'medium' then %s
                                    else %s
                                  end
          group by a.id, a.user_id
          having count(*) >= %s
        )
        insert into suspicious_activity (attempt_id, user_id, type, detail)
        select attempt_id, user_id, 'fast_response',
               jsonb_build_object('quick_answers', quick_answers,
                                  'fastest_ms', fastest_ms)
        from quick
        """,
        (event_id, FAST_MS["hard"], FAST_MS["medium"], FAST_MS["easy"], MIN_FAST_ANSWERS),
    )
    return cur.rowcount


def _flag_duplicate_patterns(cur, event_id) -> int:
    """Two students in the same slot with byte-identical answer sequences.

    A GROUP BY on a hash of the ordered sequence, not a pairwise comparison: at
    slot capacity the naive version is 12.5 million comparisons and this is one
    pass. Note that papers are individually selected, so an identical sequence
    across *different* papers means little — the hash therefore covers the
    question and the chosen option, not the position alone."""
    cur.execute(
        """
        with sequences as (
          select a.id as attempt_id, a.user_id,
                 md5(string_agg(aq.question_id::text || ':' ||
                                coalesce(ans.selected_option_id::text, '-'),
                                ',' order by aq.question_id)) as fingerprint
          from exam_attempts a
          join attempt_questions aq on aq.attempt_id = a.id
          left join answers ans on ans.attempt_question_id = aq.id
          where a.event_id = %s and a.status in ('submitted','expired')
          group by a.id, a.user_id
          -- An all-blank paper is not a conspiracy; several students who never
          -- answered anything would otherwise all match each other.
          having count(ans.selected_option_id) > 0
        ),
        dupes as (
          select fingerprint, count(*) as n from sequences
          group by fingerprint having count(*) > 1
        )
        insert into suspicious_activity (attempt_id, user_id, type, detail)
        select s.attempt_id, s.user_id, 'pattern_match',
               jsonb_build_object('fingerprint', s.fingerprint, 'group_size', d.n)
        from sequences s join dupes d on d.fingerprint = s.fingerprint
        """,
        (event_id,),
    )
    return cur.rowcount
