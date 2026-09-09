#!/usr/bin/env python3
"""Seed-data soak.

Drives many complete exams through the real HTTP API — start, answer, submit —
and then asserts the invariants that matter afterwards. It is not a performance
test (see scripts/loadtest for that); it is a check that nothing drifts when the
system is used a lot: no student gets two attempts, every finished attempt is
scored and certificated, no certificate ID collides, and the scores the database
holds still agree with the answers it holds.

    .venv/bin/python scripts/soak.py --students 300 --base-url http://localhost:8100
"""
import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jwt  # noqa: E402

from server import db  # noqa: E402

DOMAINS = ["full-stack", "cybersecurity", "data-science", "ai-ml", "cloud-devops"]


def call(base, path, token=None, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=body, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.status, json.loads(res.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def make_student(secret, college_id, location_id, index):
    sub = str(uuid.uuid4())
    email = f"soak-{index}-{sub[:8]}@soak.invalid"
    with db.cursor() as cur:
        cur.execute("insert into auth.users (id, email) values (%s, %s)", (sub, email))
        cur.execute(
            """
            insert into users (id, email, name, phone, college_id, location_id,
                               student_id, registered_at)
            values (%s, %s, %s, '9000000000', %s, %s, %s, now())
            """,
            (sub, email, f"Soak {index}", college_id, location_id, f"SOAK{index:06d}"),
        )
    return jwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated",
         "user_metadata": {"full_name": f"Soak {index}"}, "exp": 9999999999},
        secret, algorithm="HS256",
    )


def sit_exam(base, token, index):
    status, body = call(base, "/attempts", token, "POST",
                        {"domain_slug": DOMAINS[index % len(DOMAINS)]})
    if status not in (200, 201):
        return ("start_failed", status, body)

    attempt, questions = body["attempt"], body["questions"]

    # A second start must return the same attempt, never a new one. This is the
    # one-attempt rule, checked from the outside rather than trusted.
    _, again = call(base, "/attempts", token, "POST", {"domain_slug": "ai-ml"})
    if again.get("attempt", {}).get("id") not in (attempt["id"], None):
        return ("second_attempt_created", attempt["id"], again["attempt"]["id"])

    for q in questions:
        if random.random() < 0.15:
            continue  # some students skip
        option = random.choice(q["options"])
        call(base, f"/attempts/{attempt['id']}/answers/{q['position']}", token, "PUT",
             {"option_id": option["id"], "response_ms": random.randint(3000, 90000)})

    status, result = call(base, f"/attempts/{attempt['id']}/submit", token, "POST")
    if status != 200:
        return ("submit_failed", status, result)
    return ("ok", result["certificate_id"], result["score"])


def invariants() -> list[str]:
    """Each of these is a way a student could be treated unfairly, checked in
    the database rather than inferred from the API responses that produced it."""
    problems = []
    with db.cursor() as cur:
        cur.execute("""
            select count(*) as n from (
              select user_id, event_id from exam_attempts
              group by user_id, event_id having count(*) > 1
            ) t
        """)
        if cur.fetchone()["n"]:
            problems.append("a student holds more than one attempt")

        cur.execute("""
            select count(*) as n from exam_attempts a
            left join certificates c on c.attempt_id = a.id
            where a.status in ('submitted','expired') and c.id is null
        """)
        if (n := cur.fetchone()["n"]):
            problems.append(f"{n} finished attempts have no certificate")

        cur.execute("""
            select count(*) as n from exam_attempts
            where status in ('submitted','expired')
              and (score is null or correct_count is null or submitted_at is null)
        """)
        if (n := cur.fetchone()["n"]):
            problems.append(f"{n} finished attempts were never scored")

        cur.execute("""
            select count(*) as n from (
              select certificate_id from certificates
              group by certificate_id having count(*) > 1
            ) t
        """)
        if cur.fetchone()["n"]:
            problems.append("certificate IDs collided")

        # The stored score must still equal the answers it was computed from.
        cur.execute("""
            select count(*) as n from exam_attempts a
            join (
              select attempt_id, count(*) filter (where is_correct) as correct
              from answers group by attempt_id
            ) t on t.attempt_id = a.id
            where a.status in ('submitted','expired') and a.score <> t.correct
        """)
        if (n := cur.fetchone()["n"]):
            problems.append(f"{n} stored scores disagree with the stored answers")

        cur.execute("""
            select count(*) as n from exam_attempts a
            where a.status in ('submitted','expired')
              and a.correct_count + a.wrong_count + a.skipped_count
                  <> (select count(*) from attempt_questions where attempt_id = a.id)
        """)
        if (n := cur.fetchone()["n"]):
            problems.append(f"{n} attempts have counts that do not add up")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost:8100"))
    args = parser.parse_args()

    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        print("SUPABASE_JWT_SECRET is required; this must be a scratch project.",
              file=sys.stderr)
        return 1

    db.pool.open()
    try:
        with db.cursor() as cur:
            cur.execute("insert into colleges (name) values ('Soak Test College') "
                        "on conflict (lower(name)) do update set name = excluded.name "
                        "returning id")
            college = cur.fetchone()["id"]
            cur.execute("insert into locations (name) values ('Soak City') "
                        "on conflict (lower(name)) do update set name = excluded.name "
                        "returning id")
            location = cur.fetchone()["id"]

        print(f"minting {args.students} students…")
        tokens = [make_student(secret, college, location, i) for i in range(args.students)]

        print(f"sitting {args.students} exams against {args.base_url}…")
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            results = list(pool.map(
                lambda it: sit_exam(args.base_url, it[1], it[0]), enumerate(tokens)))

        failures = [r for r in results if r[0] != "ok"]
        certs = {r[1] for r in results if r[0] == "ok"}
        print(f"  completed: {len(results) - len(failures)}/{len(results)}")
        print(f"  distinct certificate IDs: {len(certs)}")
        for f in failures[:10]:
            print(f"  ! {f}")

        print("checking invariants…")
        problems = invariants()
        for p in problems:
            print(f"  ✗ {p}")
        if not problems and not failures:
            print("✓ soak clean")
            return 0
        return 1
    finally:
        db.pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
