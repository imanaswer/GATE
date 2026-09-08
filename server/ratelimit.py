"""Request rate limiting.

Applied to the paths where abuse is cheap and damage is real: admin sign-in
(brute force), the batch export (ten seconds of CPU per call), registration, and
the public certificate lookup.

**Deliberately not applied to answer saving.** That is the hot path — roughly
110 writes a second at slot capacity — and an autosave is an idempotent upsert
onto a single row that a student cannot use to do harm. Limiting it would double
the write load on the one path that cannot be degraded on event day, to prevent
nothing. See the README.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

from server import db

log = logging.getLogger("tech-arena")


def client_ip(request: Request) -> str:
    """Behind Vercel the socket peer is a proxy. Falls back to a constant rather
    than raising, which means an unparseable header shares one bucket with every
    other unparseable header — conservative, and never an error."""
    forwarded = request.headers.get("x-forwarded-for", "")
    candidate = forwarded.split(",")[0].strip()
    if not candidate and request.client:
        candidate = request.client.host
    return candidate[:64] or "unknown"


def _window(per_seconds: int):
    now = datetime.now(timezone.utc)
    return now, now - timedelta(seconds=now.timestamp() % per_seconds)


def _too_many(per_seconds: int, now) -> HTTPException:
    retry_after = int(per_seconds - (now.timestamp() % per_seconds)) or 1
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many requests. Please wait a moment and try again.",
        headers={"Retry-After": str(retry_after)},
    )


def check(bucket: str, subject: str, limit: int, per_seconds: int) -> None:
    """Count this request and raise 429 if the caller is over. For volume: every
    call counts, whether or not it succeeded.

    Fails **open** on a database error. An outage in the limiter must never be
    able to stop students sitting the exam; these paths are protective, not
    load-bearing."""
    now, window = _window(per_seconds)
    try:
        row = db.fetch_one(
            """
            insert into rate_limits (bucket, subject, window_start, count)
            values (%s, %s, %s, 1)
            on conflict (bucket, subject, window_start)
              do update set count = rate_limits.count + 1
            returning count
            """,
            (bucket, subject[:200], window),
        )
    except Exception:
        log.exception("rate limiter unavailable for %s", bucket)
        return
    if row["count"] > limit:
        raise _too_many(per_seconds, now)


def guard(bucket: str, subject: str, limit: int, per_seconds: int) -> None:
    """Read-only half of the failure-counting limiter. Called *before* the
    expensive work so an attacker over the limit never reaches the KDF."""
    now, window = _window(per_seconds)
    try:
        row = db.fetch_one(
            "select count from rate_limits where bucket = %s and subject = %s "
            "and window_start = %s",
            (bucket, subject[:200], window),
        )
    except Exception:
        log.exception("rate limiter unavailable for %s", bucket)
        return
    if row and row["count"] >= limit:
        raise _too_many(per_seconds, now)


def record_failure(bucket: str, subject: str, per_seconds: int) -> None:
    """Write half. Only failures count towards a brute-force budget: an admin
    signing in from a phone and a laptop is not an attack, and locking them out
    for it would be the limiter causing the incident it exists to prevent."""
    _, window = _window(per_seconds)
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                insert into rate_limits (bucket, subject, window_start, count)
                values (%s, %s, %s, 1)
                on conflict (bucket, subject, window_start)
                  do update set count = rate_limits.count + 1
                """,
                (bucket, subject[:200], window),
            )
    except Exception:
        log.exception("rate limiter unavailable for %s", bucket)


def sweep(cur, older_than_seconds: int = 3600) -> int:
    """Old windows can never be read again. Folded into the attempt-expiry cron
    so this needs no schedule of its own."""
    cur.execute(
        "delete from rate_limits where window_start < now() - make_interval(secs => %s)",
        (older_than_seconds,),
    )
    return cur.rowcount
