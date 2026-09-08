#!/usr/bin/env python3
"""Create and manage admin accounts.

There is no self-service admin signup and there should not be — this is the
only way an account comes into existence, and it needs shell access to the
project to run.

    pnpm admin:create you@example.com --role admin
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")

from server import db  # noqa: E402
from server.adminauth import hash_password  # noqa: E402


def create(args) -> int:
    password = args.password or getpass.getpass("Password: ")
    if not args.password and password != getpass.getpass("Confirm: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    if len(password) < 12:
        print("Use at least 12 characters. This account can read every "
              "student's record.", file=sys.stderr)
        return 1

    with db.cursor() as cur:
        cur.execute(
            """
            insert into admin_users (email, name, role, password_hash)
            values (%s, %s, %s, %s)
            on conflict (lower(email)) do update
              set password_hash = excluded.password_hash,
                  name = excluded.name,
                  role = excluded.role
            returning id, email, role
            """,
            (args.email.strip().lower(), args.name or args.email.split("@")[0],
             args.role, hash_password(password)),
        )
        row = cur.fetchone()
    print(f"{row['email']} ({row['role']}) is ready.")
    return 0


def listing(_) -> int:
    with db.cursor() as cur:
        cur.execute("select email, name, role, last_login_at from admin_users order by email")
        rows = cur.fetchall()
    if not rows:
        print("No admin accounts. Create one with: pnpm admin:create you@example.com")
        return 0
    for r in rows:
        seen = r["last_login_at"].strftime("%Y-%m-%d %H:%M") if r["last_login_at"] else "never"
        print(f"{r['email']:<40} {r['role']:<8} last login: {seen}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="create or reset an admin account")
    c.add_argument("email")
    c.add_argument("--name", default="")
    c.add_argument("--role", choices=("admin", "viewer"), default="admin")
    c.add_argument("--password", default="", help="skips the prompt; avoid, it lands in your shell history")
    c.set_defaults(func=create)

    sub.add_parser("list", help="list admin accounts").set_defaults(func=listing)

    args = parser.parse_args()
    db.pool.open()
    try:
        return args.func(args)
    finally:
        db.pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
