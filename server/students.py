import json
import re

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from server import db, ratelimit
from server.auth import CurrentIdentity, Identity
from server.settings import settings

router = APIRouter()

PHONE_RE = re.compile(r"\D")


class RegistrationIn(BaseModel):
    # Name and email are NOT accepted from the client: they come from the verified
    # Google token. A student cannot register under someone else's name.
    phone: str
    college_id: str | None = None
    college_name: str | None = Field(default=None, max_length=160)
    location: str = Field(min_length=2, max_length=120)
    # Optional. It is the only signal behind the duplicate-register-number flag
    # (spec §1.1), so it is still asked for — but a student who does not know
    # theirs must not be blocked from sitting the exam over it.
    student_id: str | None = Field(default=None, max_length=60)

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, v: str) -> str:
        digits = PHONE_RE.sub("", v)
        if not 10 <= len(digits) <= 15:
            raise ValueError("phone must have 10 to 15 digits")
        return digits

    @field_validator("student_id", "location")
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return " ".join(v.split()) or None


def ensure_user(identity: Identity) -> dict:
    """First authenticated request for a Google account creates the shell row.
    ON CONFLICT rather than SELECT-then-INSERT: two tabs racing must not both insert."""
    return db.fetch_one(
        """
        insert into users (id, email, name) values (%s, %s, %s)
        on conflict (id) do update set email = excluded.email, updated_at = now()
        returning *
        """,
        (identity.id, identity.email, identity.name),
    )


def _attempt_summary(user_id: str) -> dict | None:
    return db.fetch_one(
        """
        select a.id, a.status, a.started_at, a.expires_at, a.submitted_at,
               a.score, d.slug as domain_slug, d.name as domain_name
        from exam_attempts a
        join domains d on d.id = a.domain_id
        join exam_events e on e.id = a.event_id
        where a.user_id = %s and e.slug = %s
        """,
        (user_id, settings.event_slug),
    )


def _profile(user: dict) -> dict:
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "phone": user["phone"],
        "college_id": str(user["college_id"]) if user["college_id"] else None,
        "college_name": user.get("college_name"),
        "location": user.get("location_name"),
        "student_id": user["student_id"],
        "registered": user["registered_at"] is not None,
    }


@router.get("/me")
def me(identity: CurrentIdentity):
    ensure_user(identity)
    user = db.fetch_one(
        """
        select u.*, c.name as college_name, l.name as location_name
        from users u
        left join colleges c on c.id = u.college_id
        left join locations l on l.id = u.location_id
        where u.id = %s
        """,
        (identity.id,),
    )
    attempt = _attempt_summary(identity.id)
    if attempt:
        attempt["id"] = str(attempt["id"])
    return {"profile": _profile(user), "attempt": attempt}


@router.get("/colleges")
def list_colleges(q: str = Query(default="", max_length=120)):
    """Autocomplete for the registration form. Free-text entry is still allowed —
    the point is to stop 'ABC College' and 'A.B.C. college' becoming two rows in
    the analytics, not to constrain the student."""
    if q.strip():
        rows = db.fetch_all(
            "select id, name, city from colleges where name ilike %s order by name limit 20",
            (f"%{q.strip()}%",),
        )
    else:
        rows = db.fetch_all("select id, name, city from colleges order by name limit 50")
    return [{"id": str(r["id"]), "name": r["name"], "city": r["city"]} for r in rows]


@router.get("/locations")
def list_locations(q: str = Query(default="", max_length=120)):
    """Autocomplete over places students have already entered. Free text is still
    accepted — this exists so one city does not arrive spelled four ways."""
    if q.strip():
        rows = db.fetch_all(
            "select id, name from locations where name ilike %s order by name limit 20",
            (f"%{q.strip()}%",),
        )
    else:
        rows = db.fetch_all("select id, name from locations order by name limit 50")
    return [{"id": str(r["id"]), "name": r["name"]} for r in rows]


@router.get("/domains")
def list_domains():
    rows = db.fetch_all(
        """
        select id, slug, name, icon, description
        from domains where is_active order by position
        """
    )
    return [{**r, "id": str(r["id"])} for r in rows]


@router.post("/register")
def register(payload: RegistrationIn, identity: CurrentIdentity):
    # Keyed on the user, not the IP: an entire college sits behind one NAT
    # address, and a shared budget there would lock out real students.
    ratelimit.check("register", identity.id, limit=5, per_seconds=60)
    user = ensure_user(identity)

    # Once the exam has started, identity data is frozen — otherwise a student
    # could sit the exam and then re-badge the attempt to a different college.
    if _attempt_summary(str(user["id"])):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Your exam has already started; registration details can no longer be changed.",
        )

    if not payload.college_id and not payload.college_name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "college is required")

    with db.transaction() as cur:
        if payload.college_id:
            cur.execute("select id from colleges where id = %s", (payload.college_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown college")
            college_id = row["id"]
        else:
            # Trust-boundary write: free-text college names let an authenticated
            # student insert rows into a permanent analytics dimension, and this
            # endpoint is callable repeatedly until their attempt starts.
            # Bounded by the exam-started freeze below; a per-user rate limit
            # lands with the rest of them in Phase 7.
            name = " ".join(payload.college_name.split())
            cur.execute(
                """
                insert into colleges (name) values (%s)
                on conflict (lower(name)) do update set name = colleges.name
                returning id
                """,
                (name,),
            )
            college_id = cur.fetchone()["id"]

        # Same trust-boundary reasoning as the college name above: an
        # authenticated student writes into a permanent analytics dimension, so
        # it is normalised and deduplicated on the way in.
        cur.execute(
            """
            insert into locations (name) values (%s)
            on conflict (lower(name)) do update set name = locations.name
            returning id
            """,
            (payload.location,),
        )
        location_id = cur.fetchone()["id"]

        cur.execute(
            """
            update users set
              phone = %s, college_id = %s, location_id = %s, student_id = %s,
              registered_at = coalesce(registered_at, now()), updated_at = now()
            where id = %s
            returning *
            """,
            (payload.phone, college_id, location_id, payload.student_id, identity.id),
        )
        updated = cur.fetchone()

        # Deliberately NOT a rejection. See docs/.../design.md §1.1 — a mistyped
        # register number must never lock out the student who owns it. Flag it and
        # let an admin resolve it.
        clashes = []
        if payload.student_id:
            cur.execute(
                """
                select id, name, email from users
                where college_id = %s and student_id = %s and id <> %s
                """,
                (college_id, payload.student_id, identity.id),
            )
            clashes = cur.fetchall()
        if clashes:
            cur.execute(
                """
                insert into suspicious_activity (user_id, type, detail)
                values (%s, 'duplicate_student_id', %s)
                """,
                (
                    identity.id,
                    json.dumps(
                        {
                            "student_id": payload.student_id,
                            "college_id": str(college_id),
                            "clashes_with": [str(c["id"]) for c in clashes],
                        }
                    ),
                ),
            )

    user = db.fetch_one(
        """
        select u.*, c.name as college_name, l.name as location_name
        from users u
        left join colleges c on c.id = u.college_id
        left join locations l on l.id = u.location_id
        where u.id = %s
        """,
        (identity.id,),
    )
    return {"profile": _profile(user), "flagged_duplicate_student_id": bool(clashes)}
