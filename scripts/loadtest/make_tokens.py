#!/usr/bin/env python3
"""Mint access tokens for throwaway load-test students.

    .venv/bin/python scripts/loadtest/make_tokens.py 1000 > /tmp/tokens.json

Requires ALLOW_HS256_JWT and SUPABASE_JWT_SECRET, which means it only works
against a **scratch** Supabase project — settings.py refuses the symmetric path
in production outright. That refusal is doing exactly its job here: you should
not be able to point this at the real event.
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import jwt  # noqa: E402

from server import db  # noqa: E402

REG = {"name": "Load Test", "phone": "9000000000"}


def main() -> int:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        print("SUPABASE_JWT_SECRET is required, and this must be a scratch project.",
              file=sys.stderr)
        return 1

    db.pool.open()
    try:
        with db.cursor() as cur:
            cur.execute(
                "insert into colleges (name) values ('Load Test College') "
                "on conflict (lower(name)) do update set name = excluded.name returning id"
            )
            college = cur.fetchone()["id"]
            cur.execute(
                "insert into locations (name) values ('Load Test City') "
                "on conflict (lower(name)) do update set name = excluded.name returning id"
            )
            location = cur.fetchone()["id"]

        tokens = []
        for i in range(count):
            sub = str(uuid.uuid4())
            email = f"load-{i}-{sub[:8]}@loadtest.invalid"
            with db.cursor() as cur:
                cur.execute("insert into auth.users (id, email) values (%s, %s)", (sub, email))
                cur.execute(
                    """
                    insert into users (id, email, name, phone, college_id,
                                       location_id, student_id, registered_at)
                    values (%s, %s, %s, %s, %s, %s, %s, now())
                    """,
                    (sub, email, f"Load Test {i}", REG["phone"], college,
                     location, f"LT{i:06d}"),
                )
            tokens.append(jwt.encode(
                {"sub": sub, "email": email, "aud": "authenticated",
                 "user_metadata": {"full_name": f"Load Test {i}"}, "exp": 9999999999},
                secret, algorithm="HS256",
            ))
        json.dump(tokens, sys.stdout)
    finally:
        db.pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
