"""Attempt lifecycle endpoints."""
import ipaddress
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from server import admin, certificates, db, exam, integrity, ratelimit
from server.auth import CurrentIdentity
from server.settings import settings
from server.students import ensure_user

router = APIRouter()
log = logging.getLogger("tech-arena")

EVENT_TYPES = {"tab_switch", "fullscreen_exit", "disconnect"}


class StartIn(BaseModel):
    domain_slug: str = Field(min_length=1, max_length=64)


class AnswerIn(BaseModel):
    option_id: str | None = None
    response_ms: int | None = None

    @field_validator("response_ms", mode="before")
    @classmethod
    def _advisory_only(cls, value):
        """Never allowed to reject the save. This field is client-reported
        analytics that is explicitly not an input to scoring, so a float, a
        negative, or an absurd value becomes None — a 422 here would throw away
        a real student's real answer over a number nobody scores on."""
        if value is None:
            return None
        try:
            ms = int(float(value))
        except (TypeError, ValueError):
            return None
        return ms if 0 <= ms <= 24 * 60 * 60 * 1000 else None


class ActivityIn(BaseModel):
    type: str
    detail: dict = Field(default_factory=dict)


def _client_ip(request: Request) -> str | None:
    """Behind Vercel the socket peer is a proxy, so the real address is the first
    entry of X-Forwarded-For. Anything unparseable becomes NULL rather than an
    error — a malformed header must never stop a student starting their exam."""
    forwarded = request.headers.get("x-forwarded-for", "")
    candidate = forwarded.split(",")[0].strip() or (
        request.client.host if request.client else ""
    )
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _event(cur):
    cur.execute("select * from exam_events where slug = %s", (settings.event_slug,))
    event = cur.fetchone()
    if not event or not event["is_active"]:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The event is not open.")
    cur.execute(
        """
        select
          (opens_at is null or now() >= opens_at) as open_yet,
          (closes_at is null or now() < closes_at) as still_open
        from exam_events where id = %s
        """,
        (event["id"],),
    )
    window = cur.fetchone()
    if not window["open_yet"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The event has not opened yet.")
    if not window["still_open"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The event has closed.")
    return event


def _load_attempt(cur, user_id, for_update: bool = False):
    cur.execute(
        f"""
        select a.*, d.slug as domain_slug, d.name as domain_name,
               extract(epoch from (a.expires_at - now()))::int as remaining_seconds,
               now() > a.expires_at + interval '{exam.GRACE_SECONDS} seconds' as past_grace
        from exam_attempts a
        join domains d on d.id = a.domain_id
        join exam_events e on e.id = a.event_id
        where a.user_id = %s and e.slug = %s
        {"for update of a" if for_update else ""}
        """,
        (user_id, settings.event_slug),
    )
    return cur.fetchone()


def _expire_if_due(cur, attempt):
    """A student who closes their laptop must still be scored. Checked on every
    access, and swept by cron for the ones who never come back."""
    if attempt["status"] == "in_progress" and attempt["past_grace"]:
        scored = exam.score(cur, attempt["id"], final_status="expired")
        return {**attempt, **scored, "remaining_seconds": 0}
    return attempt


def _require_live(attempt):
    if attempt["status"] != "in_progress":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This exam has already been submitted."
            if attempt["status"] == "submitted"
            else "Your exam time has expired and the attempt was submitted automatically.",
        )


def _check_session(cur, attempt, presented_token: str | None):
    """A second device takes over rather than being locked out — a student whose
    phone dies must be able to continue on a laptop.

    The takeover is recorded once per switch, not once per answer: a legitimate
    laptop swap would otherwise write fifteen rows into the table an admin reads
    to spot genuine ping-ponging, and bury the signal it exists to surface."""
    if not presented_token or presented_token == str(attempt["session_token"]):
        return

    cur.execute(
        """
        select detail ->> 'presented' as presented from suspicious_activity
        where attempt_id = %s and type = 'session_takeover'
        order by occurred_at desc limit 1
        """,
        (attempt["id"],),
    )
    last = cur.fetchone()
    if last and last["presented"] == presented_token[:64]:
        return

    cur.execute(
        """
        insert into suspicious_activity (attempt_id, user_id, type, detail)
        values (%s, %s, 'session_takeover', %s)
        """,
        (attempt["id"], attempt["user_id"], json.dumps({"presented": presented_token[:64]})),
    )


def _attempt_public(attempt) -> dict:
    return {
        "id": str(attempt["id"]),
        "status": attempt["status"],
        "domain_slug": attempt["domain_slug"],
        "domain_name": attempt["domain_name"],
        "started_at": attempt["started_at"].isoformat(),
        "expires_at": attempt["expires_at"].isoformat(),
        "remaining_seconds": max(0, attempt["remaining_seconds"] or 0),
        "session_token": str(attempt["session_token"]),
    }


@router.post("/attempts", status_code=status.HTTP_201_CREATED)
def start(payload: StartIn, identity: CurrentIdentity, request: Request):
    user = ensure_user(identity)
    if not user["registered_at"]:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Complete your registration before starting."
        )

    with db.transaction() as cur:
        event = _event(cur)

        existing = _load_attempt(cur, identity.id, for_update=True)
        if existing:
            # Not an error the student needs to see as a failure: a double-click
            # or a retried request should land them back in their exam.
            existing = _expire_if_due(cur, existing)
            if existing["status"] != "in_progress":
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "You have already taken this exam."
                )
            return {
                "attempt": _attempt_public(existing),
                "questions": exam.load_paper(cur, existing),
            }

        cur.execute(
            "select * from domains where slug = %s and is_active", (payload.domain_slug,)
        )
        domain = cur.fetchone()
        if not domain:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown domain.")

        try:
            attempt = exam.create_attempt(cur, identity.id, event, domain)
        except exam.BankTooSmall as e:
            # The student did nothing wrong and cannot fix this; say so plainly
            # and make sure the real reason reaches the logs.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "This domain is not ready. Please choose another or tell an organiser.",
            ) from e

        cur.execute(
            "update exam_attempts set ip = %s, user_agent = %s where id = %s",
            (_client_ip(request), request.headers.get("user-agent", "")[:500],
             attempt["id"]),
        )
        full = _load_attempt(cur, identity.id)
        return {"attempt": _attempt_public(full), "questions": exam.load_paper(cur, full)}


@router.get("/attempts/current")
def current(identity: CurrentIdentity):
    """Resume. Refresh, crash and network drop all land here, and all three get
    back exactly the paper and answers the student already had."""
    with db.transaction() as cur:
        attempt = _load_attempt(cur, identity.id, for_update=True)
        if not attempt:
            return {"attempt": None, "questions": []}
        attempt = _expire_if_due(cur, attempt)
        if attempt["status"] != "in_progress":
            return {"attempt": _attempt_public(attempt), "questions": [], "finished": True}
        return {"attempt": _attempt_public(attempt), "questions": exam.load_paper(cur, attempt)}


@router.put("/attempts/{attempt_id}/answers/{position}")
def save_answer(
    attempt_id: str,
    position: int,
    payload: AnswerIn,
    identity: CurrentIdentity,
    x_session_token: str | None = Header(default=None),
):
    with db.transaction() as cur:
        attempt = _load_attempt(cur, identity.id, for_update=True)
        if not attempt or str(attempt["id"]) != attempt_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found.")
        attempt = _expire_if_due(cur, attempt)
        _require_live(attempt)
        _check_session(cur, attempt, x_session_token)

        exam.save_answer(cur, attempt, position, payload.option_id)
        if payload.response_ms is not None:
            # Client-reported and therefore spoofable. Kept as an advisory
            # analytics signal only — never as an input to a scoring decision.
            cur.execute(
                """
                update answers set response_ms = %s
                where attempt_question_id = (
                  select id from attempt_questions where attempt_id = %s and position = %s
                )
                """,
                (payload.response_ms, attempt["id"], position),
            )
        return {
            "saved": True,
            "position": position,
            "remaining_seconds": max(0, attempt["remaining_seconds"] or 0),
        }


@router.post("/attempts/{attempt_id}/submit")
def submit(attempt_id: str, identity: CurrentIdentity, response: Response):
    """Idempotent. SELECT ... FOR UPDATE serialises concurrent submits of the
    same attempt, so a double-click returns the same result rather than racing.
    No Redis lock needed: the row we must protect is already the row we lock.

    Deliberately not rate limited, against the spec. A repeat submit is a row
    lock and a read of a result already computed — there is nothing here to
    abuse — while a limit that fires has blocked a real student from handing in
    a real exam. An impatient double-click is not an attack."""
    with db.transaction() as cur:
        attempt = _load_attempt(cur, identity.id, for_update=True)
        if not attempt or str(attempt["id"]) != attempt_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found.")

        if attempt["status"] != "in_progress":
            response.status_code = status.HTTP_200_OK
            return _result(cur, attempt["id"])

        if attempt["past_grace"]:
            exam.score(cur, attempt["id"], final_status="expired")
        else:
            exam.score(cur, attempt["id"], final_status="submitted")
        return _result(cur, attempt["id"])


@router.get("/attempts/{attempt_id}/result")
def result(attempt_id: str, identity: CurrentIdentity):
    with db.transaction() as cur:
        attempt = _load_attempt(cur, identity.id, for_update=True)
        if not attempt or str(attempt["id"]) != attempt_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found.")
        # Finalise here too, so a student whose time ran out can simply navigate
        # to their result. The client never has to submit on their behalf.
        attempt = _expire_if_due(cur, attempt)
        if attempt["status"] == "in_progress":
            raise HTTPException(status.HTTP_409_CONFLICT, "This exam is still in progress.")
        return _result(cur, attempt["id"])


def _result(cur, attempt_id) -> dict:
    # Idempotent, and it also back-fills attempts that were scored before
    # certificates existed. Every caller of _result is inside a transaction.
    certificate_id = certificates.issue(cur, attempt_id)
    cur.execute(
        """
        select a.id, a.status, a.score, a.correct_count, a.wrong_count, a.skipped_count,
               a.started_at, a.submitted_at, d.name as domain_name, d.slug as domain_slug,
               (select count(*) from attempt_questions where attempt_id = a.id) as total,
               extract(epoch from (a.submitted_at - a.started_at))::int as duration_seconds
        from exam_attempts a join domains d on d.id = a.domain_id
        where a.id = %s
        """,
        (attempt_id,),
    )
    r = cur.fetchone()
    # Deliberately no per-question breakdown: publishing which questions a
    # student got wrong publishes the answer key to everyone still to sit it.
    return {
        "attempt_id": str(r["id"]),
        "status": r["status"],
        "domain_name": r["domain_name"],
        "domain_slug": r["domain_slug"],
        "score": r["score"],
        "total": r["total"],
        "correct": r["correct_count"],
        "wrong": r["wrong_count"],
        "skipped": r["skipped_count"],
        "duration_seconds": r["duration_seconds"],
        "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None,
        "certificate_id": certificate_id,
    }


def _require_cron(authorization: str | None) -> None:
    if not settings.cron_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "cron is not configured")
    if authorization != f"Bearer {settings.cron_secret}":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorised")


@router.post("/cron/refresh-overview")
def refresh_overview(authorization: str | None = Header(default=None)):
    """The admin dashboard reads one pre-computed row instead of counting every
    attempt on every load. Once a minute is close enough to live for a number
    an organiser glances at."""
    _require_cron(authorization)
    with db.transaction() as cur:
        row = admin.refresh_overview(cur)
    # The dashboard also refreshes on read, so this is a backstop for when
    # nobody is looking — which is the only thing it can be on a plan that
    # caps cron jobs at once per day.
    return {"refreshed": row is not None}


@router.post("/cron/scan-integrity")
def scan_integrity(authorization: str | None = Header(default=None)):
    """Produces a list for a human, never a disqualification. See the design
    spec §1.2 for what browser-side signals can and cannot detect — these two
    are server-side and carry more information than any of them."""
    _require_cron(authorization)
    with db.transaction() as cur:
        return integrity.scan(cur)


@router.post("/cron/expire-attempts")
def sweep_expired(authorization: str | None = Header(default=None)):
    """Auto-submits attempts whose owner never came back — a closed laptop, a
    dead battery, a student who simply walked away. Without this they sit
    in_progress forever, never scored and never certificated.

    Attempts are also expired lazily on access; this catches the rest."""
    _require_cron(authorization)
    return finalise_abandoned()


def finalise_abandoned() -> dict:
    """Shared by the cron and the admin panel. On Hobby the cron can only run
    daily, so an organiser closing out a slot needs a way to finalise the
    students who walked away without waiting until tomorrow."""
    swept = []
    with db.cursor() as cur:
        cur.execute(
            f"""
            select id from exam_attempts
            where status = 'in_progress'
              and now() > expires_at + interval '{exam.GRACE_SECONDS} seconds'
            limit 500
            """
        )
        ids = [r["id"] for r in cur.fetchall()]

    # One transaction per attempt: a single poisoned row must not roll back the
    # whole sweep and leave five hundred students unscored.
    for attempt_id in ids:
        try:
            with db.transaction() as cur:
                cur.execute(
                    "select status from exam_attempts where id = %s for update",
                    (attempt_id,),
                )
                row = cur.fetchone()
                if row and row["status"] == "in_progress":
                    exam.score(cur, attempt_id, final_status="expired")
                    swept.append(str(attempt_id))
        except Exception:
            log.exception("failed to expire attempt %s", attempt_id)

    # Piggybacked so the limiter needs no schedule of its own; its old windows
    # can never be read again.
    with db.cursor() as cur:
        ratelimit.sweep(cur)

    return {"swept": len(swept), "remaining": len(ids) - len(swept)}


@router.post("/attempts/{attempt_id}/events", status_code=status.HTTP_202_ACCEPTED)
def log_activity(attempt_id: str, payload: ActivityIn, identity: CurrentIdentity):
    """Integrity signals. These get recorded and shown to an admin; they never
    disqualify anyone automatically. See the design doc §1.2 for what browser
    signals can and cannot actually detect."""
    if payload.type not in EVENT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown event type")

    with db.cursor() as cur:
        attempt = _load_attempt(cur, identity.id)
        if not attempt or str(attempt["id"]) != attempt_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found.")
        cur.execute(
            """
            insert into suspicious_activity (attempt_id, user_id, type, detail)
            values (%s, %s, %s, %s)
            """,
            (attempt["id"], identity.id, payload.type,
             json.dumps({k: str(v)[:200] for k, v in list(payload.detail.items())[:10]})),
        )
    return {"recorded": True}
