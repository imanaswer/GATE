"""Admin API.

Deliberately plain. Spec §8: "6 is mostly post-event work and a bare student
list covers event day." The effort here goes into the auth boundary, the export
paths and the analytics queries — not into a designed dashboard.

Every endpoint below is behind `CurrentAdmin`; writes are behind `CurrentWriter`.
"""
import csv
import io
import json
import zipfile
from datetime import datetime, timezone

from fastapi import (
    APIRouter, Header, HTTPException, Query, Request, Response, status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server import certificates, db, exam, integrity, questions, ratelimit
from server.adminauth import (
    COOKIE,
    SESSION_HOURS,
    Admin,
    CurrentAdmin,
    CurrentWriter,
    authenticate,
    issue_token,
)
from server.settings import settings

router = APIRouter(prefix="/admin")

PAGE_SIZE = 50
MAX_BATCH_PDF = 500


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


# ------------------------------------------------------------------ auth

@router.post("/login")
def login(payload: LoginIn, response: Response, request: Request):
    # Both keys, because either alone is evadable: one address trying a thousand
    # accounts, or a thousand addresses trying one account. Checked before the
    # KDF runs, so being over the limit costs an attacker nothing of ours.
    ip, email = ratelimit.client_ip(request), payload.email.strip().lower()
    ratelimit.guard("admin_login_ip", ip, limit=10, per_seconds=300)
    ratelimit.guard("admin_login_email", email, limit=5, per_seconds=300)

    admin = authenticate(payload.email, payload.password)
    if not admin:
        ratelimit.record_failure("admin_login_ip", ip, per_seconds=300)
        ratelimit.record_failure("admin_login_email", email, per_seconds=300)
        # One message for "no such account" and "wrong password". The timing is
        # equalised in authenticate(); saying which one it was would undo that.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    token = issue_token(admin)
    with db.cursor() as cur:
        cur.execute("update admin_users set last_login_at = now() where id = %s", (admin["id"],))

    # HttpOnly so a script on the page cannot read it; SameSite=Lax so a form on
    # another site cannot POST with it, which is the CSRF defence this needs.
    response.set_cookie(
        COOKIE, token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return {"email": admin["email"], "name": admin["name"], "role": admin["role"]}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def whoami(admin: CurrentAdmin):
    return {"email": admin.email, "name": admin.name, "role": admin.role}


# ------------------------------------------------------------------ overview

# How stale the counters may get before a dashboard read recomputes them.
OVERVIEW_MAX_AGE_SECONDS = 60


@router.get("/overview")
def overview(admin: CurrentAdmin):
    """Recomputes on read when the cached row has aged out, rather than relying
    on the cron to be frequent. Vercel's Hobby plan caps cron jobs at once per
    day, and a dashboard showing yesterday's numbers during the event is worse
    than no dashboard. The guarded UPDATE means concurrent admins recompute at
    most once a minute between them — the same cost the cron had, and the cron
    stays as a backstop for when nobody is looking."""
    with db.transaction() as cur:
        refresh_overview(cur, max_age_seconds=OVERVIEW_MAX_AGE_SECONDS)
        cur.execute("select * from admin_overview where id")
        row = cur.fetchone()
    return {
        **{k: v for k, v in row.items() if k not in ("id", "refreshed_at", "average_score")},
        "average_score": float(row["average_score"]) if row["average_score"] is not None else None,
        "refreshed_at": row["refreshed_at"].isoformat(),
        "stale_seconds": int(
            (datetime.now(timezone.utc) - row["refreshed_at"]).total_seconds()
        ),
    }


def refresh_overview(cur, max_age_seconds: int | None = None) -> dict | None:
    """One pass over the attempt table, instead of a COUNT(*) per dashboard
    load. Everything here is a single scan the planner can do cheaply; it is not
    meant to be exact to the second.

    With `max_age_seconds` the UPDATE only fires if the row is older than that.
    The predicate is re-checked after the row lock is taken, so two concurrent
    readers cannot both recompute — the loser simply matches no rows."""
    guard = "and refreshed_at < now() - make_interval(secs => %s)" if max_age_seconds else ""
    cur.execute(
        f"""
        update admin_overview set
          students      = (select count(*) from users),
          registered    = (select count(*) from users where registered_at is not null),
          attempts      = (select count(*) from exam_attempts),
          in_progress   = (select count(*) from exam_attempts where status = 'in_progress'),
          submitted     = (select count(*) from exam_attempts where status = 'submitted'),
          expired       = (select count(*) from exam_attempts where status = 'expired'),
          certificates  = (select count(*) from certificates),
          colleges      = (select count(*) from colleges),
          flagged       = (select count(distinct attempt_id) from suspicious_activity),
          average_score = (select round(avg(score), 2) from exam_attempts
                           where status in ('submitted','expired')),
          by_domain     = coalesce((
            select jsonb_agg(x order by x ->> 'name')
            from (
              select jsonb_build_object(
                       'slug', d.slug, 'name', d.name,
                       'attempts', count(a.id),
                       'average_score', round(avg(a.score), 2)
                     ) as x
              from domains d
              left join exam_attempts a
                on a.domain_id = d.id and a.status in ('submitted','expired')
              group by d.id, d.slug, d.name
              -- A retired domain still belongs here while it has attempts to
              -- account for; once it has none it is just noise on every load.
              having d.is_active or count(a.id) > 0
            ) t), '[]'::jsonb),
          refreshed_at  = now()
        where id {guard}
        returning refreshed_at
        """,
        (max_age_seconds,) if max_age_seconds else (),
    )
    return cur.fetchone()


@router.post("/attempts/finalise-abandoned")
def finalise_abandoned(admin: CurrentWriter):
    """Scores and certificates every attempt whose owner never came back.
    Also on a daily cron; exposed here because on Hobby that cron cannot run
    more than once a day, and an organiser closing out a slot should not have
    to wait until tomorrow for those students to get their certificates."""
    from server.attempts import finalise_abandoned as sweep

    return sweep()


@router.post("/integrity/scan")
def rescan_integrity(admin: CurrentWriter):
    """Also on an hourly cron. Exposed here so an organiser can re-run it the
    moment a slot finishes rather than waiting for the schedule."""
    with db.transaction() as cur:
        return integrity.scan(cur)


@router.get("/integrity/flags")
def integrity_flags(admin: CurrentAdmin, limit: int = Query(default=200, ge=1, le=1000)):
    rows = db.fetch_all(
        """
        select sa.type, sa.detail, sa.occurred_at, u.id as user_id, u.name, u.email,
               co.name as college_name, a.score
        from suspicious_activity sa
        join users u on u.id = sa.user_id
        left join colleges co on co.id = u.college_id
        left join exam_attempts a on a.id = sa.attempt_id
        order by sa.occurred_at desc limit %s
        """,
        (limit,),
    )
    return {
        "flags": [
            {
                "type": r["type"], "detail": r["detail"],
                "occurred_at": r["occurred_at"].isoformat(),
                "user_id": str(r["user_id"]), "name": r["name"], "email": r["email"],
                "college_name": r["college_name"], "score": r["score"],
            }
            for r in rows
        ]
    }


# ------------------------------------------------------------------ students

def _student_filters(q, college_id, domain, attempt_status):
    """Shared by the list and the CSV export so the export always covers exactly
    what the screen showed. Two copies of this would drift, and an organiser
    would export a different set than they filtered."""
    where, params = ["1=1"], []
    if q:
        where.append(
            "(u.name ilike %s or u.email ilike %s or u.student_id ilike %s "
            "or lo.name ilike %s)"
        )
        params += [f"%{q}%"] * 4
    if college_id:
        where.append("u.college_id = %s")
        params.append(college_id)
    if domain:
        where.append("d.slug = %s")
        params.append(domain)
    if attempt_status == "none":
        where.append("a.id is null")
    elif attempt_status:
        where.append("a.status = %s")
        params.append(attempt_status)
    return " and ".join(where), params


STUDENT_SELECT = f"""
    select u.id, u.name, u.email, u.phone, u.student_id,
           u.registered_at, u.created_at,
           co.name as college_name, lo.name as location_name,
           a.id as attempt_id, a.status as attempt_status, a.score,
           a.correct_count, a.wrong_count, a.skipped_count,
           a.started_at, a.submitted_at,
           {exam.DURATION_SECONDS_SQL} as duration_seconds,
           d.name as domain_name, d.slug as domain_slug,
           c.certificate_id, c.verify_hash, c.issued_at
    from users u
    left join colleges co on co.id = u.college_id
    left join locations lo on lo.id = u.location_id
    left join exam_attempts a on a.user_id = u.id
    left join domains d on d.id = a.domain_id
    left join certificates c on c.attempt_id = a.id
"""


@router.get("/students")
def students(
    admin: CurrentAdmin,
    q: str = Query(default="", max_length=120),
    college_id: str | None = None,
    domain: str | None = None,
    attempt_status: str | None = None,
    cursor: str | None = Query(default=None, description="last_created_at,last_id"),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=200),
):
    """Keyset, not OFFSET. `OFFSET 40000` on the student list is a table scan,
    and the student list is the page an organiser refreshes all day."""
    where, params = _student_filters(q, college_id, domain, attempt_status)
    if cursor:
        try:
            created_at, last_id = cursor.split(",", 1)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "malformed cursor")
        where += " and (u.created_at, u.id) > (%s, %s)"
        params += [created_at, last_id]

    rows = db.fetch_all(
        f"{STUDENT_SELECT} where {where} order by u.created_at, u.id limit %s",
        (*params, limit + 1),
    )
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "students": [_student_row(r) for r in rows],
        "next_cursor": (
            f"{rows[-1]['created_at'].isoformat()},{rows[-1]['id']}" if more and rows else None
        ),
    }


def _student_row(r) -> dict:
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "email": r["email"],
        "phone": r["phone"],
        "student_id": r["student_id"],
        "college_name": r["college_name"],
        "location": r["location_name"],
        "registered": r["registered_at"] is not None,
        "attempt_status": r["attempt_status"],
        "domain_name": r["domain_name"],
        "score": r["score"],
        "certificate_id": r["certificate_id"],
        "started_at": r["started_at"].isoformat() if r["started_at"] else None,
        "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None,
        # Wall clock on the paper. For an expired attempt this is the cap, not
        # an achievement — attempt_status is what says which.
        "duration_seconds": r["duration_seconds"],
    }


@router.get("/students/{student_id}")
def student_detail(student_id: str, admin: CurrentAdmin):
    row = db.fetch_one(f"{STUDENT_SELECT} where u.id = %s", (student_id,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such student.")

    flags = db.fetch_all(
        """
        select type, detail, occurred_at from suspicious_activity
        where user_id = %s order by occurred_at desc limit 200
        """,
        (student_id,),
    )
    breakdown = db.fetch_all(
        """
        select aq.position, q.topic, q.difficulty, ans.is_correct,
               ans.response_ms, ans.selected_option_id is null as skipped
        from attempt_questions aq
        join questions q on q.id = aq.question_id
        left join answers ans on ans.attempt_question_id = aq.id
        where aq.attempt_id = %s order by aq.position
        """,
        (row["attempt_id"],),
    ) if row["attempt_id"] else []

    return {
        **_student_row(row),
        "attempt_id": str(row["attempt_id"]) if row["attempt_id"] else None,
        "correct": row["correct_count"],
        "wrong": row["wrong_count"],
        "skipped": row["skipped_count"],
        # Admin-side only. This is the per-question view deliberately withheld
        # from the student's own result page, because publishing it there
        # publishes the answer key to everyone still to sit the exam.
        "questions": [
            {
                "position": b["position"], "topic": b["topic"],
                "difficulty": b["difficulty"], "is_correct": b["is_correct"],
                "skipped": b["skipped"], "response_ms": b["response_ms"],
            }
            for b in breakdown
        ],
        "flags": [
            {"type": f["type"], "detail": f["detail"],
             "occurred_at": f["occurred_at"].isoformat()}
            for f in flags
        ],
    }


# ------------------------------------------------------------------ questions

class QuestionIn(BaseModel):
    domain_slug: str = Field(min_length=1, max_length=64)
    type: str = Field(pattern="^(mcq|code_output|debug|scenario|logic)$")
    body: str = Field(min_length=5, max_length=4000)
    code_snippet: str | None = Field(default=None, max_length=4000)
    topic: str = Field(min_length=1, max_length=120)
    difficulty: str = Field(pattern="^(easy|medium|hard)$")
    explanation: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="active", pattern="^(draft|active|retired)$")
    options: list[str] = Field(min_length=2, max_length=6)
    correct_index: int = Field(ge=0, le=5)


@router.get("/questions")
def list_questions(
    admin: CurrentAdmin,
    q: str = Query(default="", max_length=200),
    domain: str | None = None,
    difficulty: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, le=2000),
    limit: int = Query(default=PAGE_SIZE, ge=1, le=200),
):
    where, params = ["1=1"], []
    if q:
        where.append("(qs.body ilike %s or qs.topic ilike %s)")
        params += [f"%{q}%"] * 2
    for column, value in (("d.slug", domain), ("qs.difficulty", difficulty),
                          ("qs.status", status_filter)):
        if value:
            where.append(f"{column} = %s")
            params.append(value)
    clause = " and ".join(where)

    total = db.fetch_one(
        f"select count(*) as n from questions qs join domains d on d.id = qs.domain_id "
        f"where {clause}", tuple(params))["n"]
    # OFFSET is fine here and only here: the bank is ~1,000 rows and an admin
    # browsing it wants page numbers, not an opaque cursor.
    rows = db.fetch_all(
        f"""
        select qs.id, qs.body, qs.code_snippet, qs.topic, qs.difficulty, qs.type,
               qs.status, qs.explanation, d.slug as domain_slug, d.name as domain_name
        from questions qs join domains d on d.id = qs.domain_id
        where {clause} order by d.slug, qs.difficulty, qs.topic, qs.id
        limit %s offset %s
        """,
        (*params, limit, (page - 1) * limit),
    )
    ids = [r["id"] for r in rows]
    options = db.fetch_all(
        "select id, question_id, body, is_correct, position from question_options "
        "where question_id = any(%s) order by position", (ids,)) if ids else []
    by_question = {}
    for o in options:
        by_question.setdefault(o["question_id"], []).append(
            {"id": str(o["id"]), "body": o["body"], "is_correct": o["is_correct"]}
        )

    return {
        "total": total,
        "page": page,
        "pages": max(1, -(-total // limit)),
        "questions": [
            {
                "id": str(r["id"]), "body": r["body"], "code": r["code_snippet"],
                "topic": r["topic"], "difficulty": r["difficulty"], "type": r["type"],
                "status": r["status"], "explanation": r["explanation"],
                "domain_slug": r["domain_slug"], "domain_name": r["domain_name"],
                "options": by_question.get(r["id"], []),
            }
            for r in rows
        ],
    }


def _write_question(cur, payload: QuestionIn, question_id=None) -> str:
    if payload.correct_index >= len(payload.options):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "correct_index is outside the options"
        )
    cur.execute("select id from domains where slug = %s", (payload.domain_slug,))
    domain = cur.fetchone()
    if not domain:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown domain.")

    if question_id:
        cur.execute(
            """
            update questions set domain_id = %s, type = %s, body = %s, code_snippet = %s,
                   topic = %s, difficulty = %s, explanation = %s, status = %s,
                   version = version + 1
            where id = %s returning id
            """,
            (domain["id"], payload.type, payload.body, payload.code_snippet,
             payload.topic, payload.difficulty, payload.explanation, payload.status,
             question_id),
        )
        if not cur.fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such question.")
        # Replacing the options wholesale keeps the one-correct-option index
        # satisfiable; editing them in place cannot be done without transiently
        # violating it.
        cur.execute("delete from question_options where question_id = %s", (question_id,))
    else:
        cur.execute(
            """
            insert into questions (domain_id, type, body, code_snippet, topic,
                                   difficulty, explanation, status)
            values (%s, %s, %s, %s, %s, %s, %s, %s) returning id
            """,
            (domain["id"], payload.type, payload.body, payload.code_snippet,
             payload.topic, payload.difficulty, payload.explanation, payload.status),
        )
        question_id = cur.fetchone()["id"]

    for i, body in enumerate(payload.options):
        cur.execute(
            "insert into question_options (question_id, body, is_correct, position) "
            "values (%s, %s, %s, %s)",
            (question_id, body, i == payload.correct_index, i),
        )
    return str(question_id)


@router.post("/questions", status_code=status.HTTP_201_CREATED)
def create_question(payload: QuestionIn, admin: CurrentWriter):
    with db.transaction() as cur:
        return {"id": _write_question(cur, payload)}


@router.put("/questions/{question_id}")
def update_question(question_id: str, payload: QuestionIn, admin: CurrentWriter):
    with db.transaction() as cur:
        return {"id": _write_question(cur, payload, question_id)}


@router.delete("/questions/{question_id}")
def retire_question(question_id: str, admin: CurrentWriter):
    """Retire, never delete. A question that has been sat is part of the record
    of every attempt that contains it; deleting it would rewrite history and
    cascade away the attempt_questions rows that explain a student's score."""
    with db.cursor() as cur:
        cur.execute(
            "update questions set status = 'retired' where id = %s returning id",
            (question_id,),
        )
        if not cur.fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such question.")
    return {"retired": question_id}


@router.post("/questions/import")
async def import_questions(request: Request, admin: CurrentWriter,
                           x_dry_run: str | None = Header(default=None)):
    """Same parser the CLI import uses, so a CSV that passes `pnpm bank:import`
    behaves identically here. Dry-run by default would be safer still, but the
    parser already refuses the whole file if any row is bad."""
    text = (await request.body()).decode("utf-8-sig", errors="replace")
    with db.transaction() as cur:
        cur.execute("select slug from domains")
        known = {r["slug"] for r in cur.fetchall()}
        report = questions.parse_csv(text, known)
        if report.errors:
            return {"ok": False, "errors": report.errors[:100],
                    "rows": len(report.rows)}
        if x_dry_run:
            return {"ok": True, "dry_run": True, "rows": len(report.rows)}
        report = questions.apply(report, cur)
    return {"ok": True, "created": report.created, "updated": report.updated}


# ------------------------------------------------------------------ analytics

@router.get("/analytics/questions")
def question_analytics(
    admin: CurrentAdmin,
    domain: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    """The number that matters is the correct rate. A question everyone gets
    wrong is usually a broken question, not a hard one — and one everyone gets
    right is measuring nothing. Both need a human to look."""
    where = "where a.status in ('submitted','expired')"
    params: list = []
    if domain:
        where += " and d.slug = %s"
        params.append(domain)
    rows = db.fetch_all(
        f"""
        select q.id, q.body, q.topic, q.difficulty, q.status,
               d.slug as domain_slug,
               count(*) as seen,
               count(*) filter (where ans.selected_option_id is not null) as answered,
               count(*) filter (where ans.is_correct) as correct,
               count(*) filter (where ans.selected_option_id is null) as skipped,
               round(avg(ans.response_ms) filter (where ans.response_ms is not null)) as avg_ms
        from attempt_questions aq
        join questions q on q.id = aq.question_id
        join domains d on d.id = q.domain_id
        join exam_attempts a on a.id = aq.attempt_id
        left join answers ans on ans.attempt_question_id = aq.id
        {where}
        group by q.id, q.body, q.topic, q.difficulty, q.status, d.slug
        having count(*) filter (where ans.selected_option_id is not null) > 0
        -- Rate is over questions actually attempted. Counting a skip as a wrong
        -- answer would conflate "nobody could answer this" with "nobody tried",
        -- and those two want different fixes.
        order by (count(*) filter (where ans.is_correct))::float
                 / count(*) filter (where ans.selected_option_id is not null),
                 count(*) desc
        limit %s
        """,
        (*params, limit),
    )
    return {
        "questions": [
            {
                "id": str(r["id"]),
                "body": r["body"][:200],
                "topic": r["topic"], "difficulty": r["difficulty"],
                "status": r["status"], "domain_slug": r["domain_slug"],
                "seen": r["seen"], "answered": r["answered"],
                "correct": r["correct"], "skipped": r["skipped"],
                "correct_rate": round(r["correct"] / r["answered"], 3) if r["answered"] else None,
                "avg_ms": int(r["avg_ms"]) if r["avg_ms"] is not None else None,
            }
            for r in rows
        ]
    }


@router.get("/analytics/colleges")
def college_analytics(admin: CurrentAdmin, limit: int = Query(default=200, ge=1, le=1000)):
    rows = db.fetch_all(
        """
        select co.id, co.name, co.city,
               count(distinct u.id) as students,
               count(distinct a.id) filter (where a.status in ('submitted','expired')) as completed,
               round(avg(a.score) filter (where a.status in ('submitted','expired')), 2) as average_score,
               max(a.score) as top_score
        from colleges co
        left join users u on u.college_id = co.id
        left join exam_attempts a on a.user_id = u.id
        group by co.id, co.name, co.city
        order by count(distinct u.id) desc, co.name
        limit %s
        """,
        (limit,),
    )
    return {
        "colleges": [
            {
                "id": str(r["id"]), "name": r["name"], "city": r["city"],
                "students": r["students"], "completed": r["completed"],
                "average_score": float(r["average_score"]) if r["average_score"] is not None else None,
                "top_score": r["top_score"],
            }
            for r in rows
        ]
    }


# ------------------------------------------------------------------ exports

CSV_COLUMNS = [
    "name", "email", "phone", "student_id", "college_name", "location",
    "domain_name", "attempt_status", "score", "correct",
    "wrong", "skipped", "started_at", "submitted_at", "duration_seconds",
    "certificate_id",
]


@router.get("/export/csv")
def export_csv(
    admin: CurrentAdmin,
    q: str = Query(default="", max_length=120),
    college_id: str | None = None,
    domain: str | None = None,
    attempt_status: str | None = None,
):
    """Constant memory at any row count, and — importantly — it does not hold a
    connection open for the whole stream. A server-side named cursor would, and
    with a pool of 2 that means one export starves the exam path on event day.
    Batched keyset pagination gets the same constant memory without the hold."""
    where, params = _student_filters(q, college_id, domain, attempt_status)

    def rows():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_COLUMNS)
        yield buffer.getvalue()

        cursor = None
        while True:
            clause, args = where, list(params)
            if cursor:
                clause += " and (u.created_at, u.id) > (%s, %s)"
                args += list(cursor)
            batch = db.fetch_all(
                f"{STUDENT_SELECT} where {clause} order by u.created_at, u.id limit 1000",
                tuple(args),
            )
            if not batch:
                return
            buffer.seek(0), buffer.truncate(0)
            for r in batch:
                writer.writerow([
                    r["name"], r["email"], r["phone"], r["student_id"],
                    r["college_name"], r["location_name"],
                    r["domain_name"], r["attempt_status"], r["score"],
                    r["correct_count"], r["wrong_count"], r["skipped_count"],
                    r["started_at"].isoformat() if r["started_at"] else "",
                    r["submitted_at"].isoformat() if r["submitted_at"] else "",
                    r["duration_seconds"] if r["duration_seconds"] is not None else "",
                    r["certificate_id"],
                ])
            yield buffer.getvalue()
            cursor = (batch[-1]["created_at"], batch[-1]["id"])

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        rows(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="tech-arena-{stamp}.csv"'},
    )


@router.get("/export/pdf")
def export_pdf(
    request: Request,
    admin: CurrentAdmin,
    q: str = Query(default="", max_length=120),
    college_id: str | None = None,
    domain: str | None = None,
):
    """A ZIP of certificate PDFs, streamed straight back — no job row, no queue,
    no object storage. The spec called for a background job on the assumption
    that rendering is expensive; it is ~20ms, so 500 of them is ten seconds
    inside a 300s timeout. `jobs` stays unused, and that is the point.

    The cap is not about cost. Nobody reads a 50,000-certificate archive; above
    this many, CSV is what you actually wanted."""
    # No attempt_status filter: an attempt that timed out is certificated on
    # exactly the same terms as one that was submitted, and an export that
    # silently dropped those students would be the cruellest possible bug.
    # Ten seconds of CPU per call at the cap, so this one is limited by admin.
    ratelimit.check("admin_export_pdf", admin.id, limit=5, per_seconds=3600)
    where, params = _student_filters(q, college_id, domain, None)
    rows = db.fetch_all(
        f"{STUDENT_SELECT} where {where} and c.certificate_id is not null "
        f"order by u.created_at, u.id limit %s",
        (*params, MAX_BATCH_PDF + 1),
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No certificates match that filter.")
    if len(rows) > MAX_BATCH_PDF:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"That filter matches more than {MAX_BATCH_PDF} certificates. "
            f"Narrow it, or use the CSV export instead.",
        )

    base = settings.site_url or ""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            cert = {
                "certificate_id": r["certificate_id"],
                "student_name": r["name"],
                "college_name": r["college_name"],
                "domain_name": r["domain_name"],
                "issued_at": r["issued_at"].date().isoformat(),
                "verify_code": r["verify_hash"][:12].upper(),
            }
            zf.writestr(
                f"{r['certificate_id']}.pdf",
                certificates.render(cert, f"{base}/verify/{r['certificate_id']}"),
            )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        archive.getvalue(), media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="certificates-{stamp}.zip"',
        },
    )
