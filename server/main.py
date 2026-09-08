import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from server import attempts, certificates, db, students

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tech-arena")

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open()
    yield
    db.pool.close()


app = FastAPI(
    title="Tech Arena API",
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
