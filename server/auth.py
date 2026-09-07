from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient

from server.settings import settings

# Cached across warm invocations; refetching JWKS on every request would add a
# round-trip to Supabase on the hot path.
_jwks_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            f"{settings.supabase_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
    return _jwks_client


class Identity:
    """What Google told us, verified. Trusted for identity; nothing else."""

    def __init__(self, sub: str, email: str, name: str):
        self.id = sub
        self.email = email.lower()
        self.name = name


def _decode(token: str) -> dict:
    unverified = jwt.get_unverified_header(token)
    alg = unverified.get("alg", "")

    if alg.startswith("HS"):
        if not settings.supabase_jwt_secret:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unsupported token")
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
        )

    key = _jwks().get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        key,
        algorithms=["ES256", "RS256"],
        audience=settings.jwt_audience,
    )


def current_identity(
    authorization: Annotated[str | None, Header()] = None,
) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = _decode(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    email = claims.get("email")
    if not claims.get("sub") or not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing identity")

    meta = claims.get("user_metadata") or {}
    name = meta.get("full_name") or meta.get("name") or email.split("@")[0]
    return Identity(claims["sub"], email, name)


CurrentIdentity = Annotated[Identity, Depends(current_identity)]
