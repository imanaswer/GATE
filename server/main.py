import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from server import admin, attempts, certificates, db, students
from server.settings import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tech-arena")

if settings.sentry_dsn:  # pragma: no cover - needs a real DSN to exercise
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        # Traces off by default: at slot capacity a 10% sample of the autosave
        # path is millions of spans nobody reads. Turn it on deliberately.
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        # Student phone numbers and emails pass through these requests. Errors
        # are for debugging, not for copying the roster into another vendor.
        send_default_pii=False,
    )

# Optional settings whose absence degrades something silently. Warned about at
# boot so a misconfigured deploy says so on the first log line, rather than on
# event day when someone tries to sign in.
for _name, _value, _effect in (
    ("ADMIN_SECRET", settings.admin_secret, "the admin panel will refuse every sign-in"),
    ("SITE_URL", settings.site_url, "certificate QR codes fall back to request headers"),
    ("CRON_SECRET", settings.cron_secret, "scheduled sweeps and counters will not run"),
):
    if not _value:
        log.warning("%s is not set — %s", _name, _effect)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open()
    yield
    db.pool.close()


app = FastAPI(
    title="GATE API",
    lifespan=lifespan,
    # No public schema. The API surface is documented in docs/, not served to
    # anyone who wants to enumerate it.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Log the detail, return none of it. Stack traces and SQL fragments in an
    # error body are a gift to anyone probing the API.
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        {"detail": "Something went wrong. Please try again."},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.get("/api/v1/health")
def health():
    db.fetch_one("select 1 as ok")
    return {"ok": True}


app.include_router(students.router, prefix="/api/v1")
app.include_router(attempts.router, prefix="/api/v1")
# Public: no identity. Verification has to work for an employer
# holding a printed certificate and no account.
app.include_router(certificates.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
