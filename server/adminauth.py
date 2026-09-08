"""Admin authentication — a separate world from student auth.

Students authenticate against Supabase/Google. Admins do not: an admin account
must not depend on an external OAuth app whose verification status is itself a
project risk (spec §10), and it must be revocable by us alone.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, status

from server import db
from server.settings import settings

COOKIE = "admin_session"
SESSION_HOURS = 8

# scrypt is in the standard library and is a real password KDF. bcrypt/argon2
# would be a dependency for no gain at the handful of admin accounts this has.
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, expected = stored.split("$")
        if kind != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt),
            n=int(n), r=int(r), p=int(p), dklen=len(expected) // 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), expected)


# A real hash to check against when the email is unknown, so a missing account
# costs the same time as a wrong password and login is not an email oracle.
_DUMMY = hash_password(secrets.token_urlsafe(32))


def authenticate(email: str, password: str) -> dict | None:
    row = db.fetch_one(
        "select id, email, name, role, password_hash from admin_users where lower(email) = %s",
        (email.strip().lower(),),
    )
    if not row:
        verify_password(password, _DUMMY)
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return row


def _secret() -> str:
    if not settings.admin_secret:
        # Signing an admin session with an empty default would be a full
        # compromise, so refuse to issue one rather than fall back to anything.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "admin access is not configured"
        )
    return settings.admin_secret


def issue_token(admin: dict) -> str:
    return jwt.encode(
        {
            "sub": str(admin["id"]),
            "email": admin["email"],
            "name": admin["name"],
            "role": admin["role"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS),
        },
        _secret(),
        algorithm="HS256",
    )


class Admin:
    def __init__(self, claims: dict):
        self.id = claims["sub"]
        self.email = claims["email"]
        self.name = claims.get("name", "")
        self.role = claims.get("role", "viewer")


def current_admin(admin_session: Annotated[str | None, Cookie()] = None) -> Admin:
    if not admin_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "admin sign-in required")
    try:
        claims = jwt.decode(admin_session, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "admin session expired")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid admin session")
    return Admin(claims)


CurrentAdmin = Annotated[Admin, Depends(current_admin)]


def require_writer(admin: CurrentAdmin) -> Admin:
    """Viewers can read the whole dashboard and change nothing. The event has
    more people who need to watch it than people who should edit questions."""
    if admin.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this action needs an admin role")
    return admin


CurrentWriter = Annotated[Admin, Depends(require_writer)]
