"""End-to-end check of Phase 1 against a real Postgres.

Run: pnpm api:test  (creates and drops a scratch database)

Covers the thing Phase 1 exists to prove: a Google account can register once,
and the *database* — not application logic, not the browser — is what stops a
second attempt.
"""
import os
import subprocess
import uuid

import jwt
import pytest

SECRET = "test-secret-not-used-anywhere-real"
DB = f"tech_arena_api_test_{os.getpid()}"


def _psql(*args):
    subprocess.run(["psql", "-q", "-v", "ON_ERROR_STOP=1", "-d", DB, *args], check=True)


@pytest.fixture(scope="module", autouse=True)
def database():
    subprocess.run(["dropdb", "--if-exists", DB], check=False)
    subprocess.run(["createdb", DB], check=True)
    _psql("-c", "create extension if not exists pgcrypto;")
    _psql("-f", "supabase/test/00_auth_shim.sql")
    for name in sorted(os.listdir("supabase/migrations")):
        _psql("-f", f"supabase/migrations/{name}")
    os.environ.update(
        DATABASE_URL=f"postgresql:///{DB}",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET=SECRET,
        EVENT_SLUG="tech-arena-2026",
    )
    yield
    subprocess.run(["dropdb", "--if-exists", DB], check=False)


@pytest.fixture(scope="module")
def client(database):
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as c:
        yield c


def make_student(email: str, name: str) -> str:
    """Create the auth.users row Supabase would have created, return a bearer token."""
    sub = str(uuid.uuid4())
    subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1", "-d", DB, "-c",
         f"insert into auth.users (id, email) values ('{sub}', '{email}')"],
        check=True,
    )
    token = jwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated",
         "user_metadata": {"full_name": name}, "exp": 9999999999},
        SECRET, algorithm="HS256",
    )
    return f"Bearer {token}"


REG = {
    "phone": "+91 98765 43210",
    "college_name": "ABC College of Engineering",
    "course": "Computer Science",
    "academic_year": 3,
    "student_id": "CS21001",
}


def test_health(client):
    assert client.get("/api/v1/health").json() == {"ok": True}


def test_rejects_unauthenticated(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/register", json=REG).status_code == 401


def test_rejects_forged_token(client):
    bad = jwt.encode({"sub": str(uuid.uuid4()), "email": "x@y.z", "aud": "authenticated"},
                     "wrong-secret", algorithm="HS256")
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_first_login_creates_shell_profile(client):
    auth = make_student("asha@example.edu", "Asha Menon")
    body = client.get("/api/v1/me", headers={"Authorization": auth}).json()
    assert body["profile"]["name"] == "Asha Menon"      # from Google, not the client
    assert body["profile"]["email"] == "asha@example.edu"
    assert body["profile"]["registered"] is False
    assert body["attempt"] is None


def test_registration_completes_and_normalises(client):
    auth = make_student("ravi@example.edu", "Ravi Kumar")
    r = client.post("/api/v1/register", json=REG, headers={"Authorization": auth})
    assert r.status_code == 200, r.text
    p = r.json()["profile"]
    assert p["registered"] is True
    assert p["phone"] == "919876543210"                  # punctuation stripped
    assert p["college_name"] == "ABC College of Engineering"
    assert r.json()["flagged_duplicate_student_id"] is False


def test_client_cannot_spoof_name_or_email(client):
    auth = make_student("real@example.edu", "Real Name")
    client.post(
        "/api/v1/register",
        json={**REG, "student_id": "CS21099", "name": "Somebody Else",
              "email": "attacker@example.edu"},
        headers={"Authorization": auth},
    )
    p = client.get("/api/v1/me", headers={"Authorization": auth}).json()["profile"]
    assert p["name"] == "Real Name"
    assert p["email"] == "real@example.edu"


def test_invalid_payloads_rejected(client):
    auth = make_student("bad@example.edu", "Bad Input")
    h = {"Authorization": auth}
    assert client.post("/api/v1/register", json={**REG, "phone": "123"}, headers=h).status_code == 422
    assert client.post("/api/v1/register", json={**REG, "academic_year": 9}, headers=h).status_code == 422
    assert client.post("/api/v1/register", json={**REG, "course": ""}, headers=h).status_code == 422
    no_college = {k: v for k, v in REG.items() if k != "college_name"}
    assert client.post("/api/v1/register", json=no_college, headers=h).status_code == 422


def test_duplicate_student_id_is_flagged_not_blocked(client):
    """The whole point of §1.1: a typo must not lock anyone out."""
    auth = make_student("typo@example.edu", "Typo Student")
    r = client.post("/api/v1/register", json=REG, headers={"Authorization": auth})
    assert r.status_code == 200                          # registration SUCCEEDS
    assert r.json()["flagged_duplicate_student_id"] is True
    assert r.json()["profile"]["registered"] is True

    out = subprocess.run(
        ["psql", "-tA", "-d", DB, "-c",
         "select count(*) from suspicious_activity where type='duplicate_student_id'"],
        capture_output=True, text=True, check=True,
    )
    assert int(out.stdout.strip()) >= 1                  # and an admin can see it


def test_colleges_are_deduplicated_by_name(client):
    auth = make_student("dedupe@example.edu", "Dedupe")
    client.post(
        "/api/v1/register",
        json={**REG, "college_name": "  abc college OF engineering ", "student_id": "CS21500"},
        headers={"Authorization": auth},
    )
    out = subprocess.run(
        ["psql", "-tA", "-d", DB, "-c",
         "select count(*) from colleges where lower(name) like 'abc college%'"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "1"


def test_domains_listed(client):
    rows = client.get("/api/v1/domains").json()
    assert {r["slug"] for r in rows} == {
        "ai-ml", "data-science", "full-stack", "cybersecurity", "cloud-devops"}


def test_profile_frozen_once_exam_starts(client):
    auth = make_student("started@example.edu", "Started Already")
    client.post("/api/v1/register", json={**REG, "student_id": "CS21777"},
                headers={"Authorization": auth})
    me = client.get("/api/v1/me", headers={"Authorization": auth}).json()

    subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1", "-d", DB, "-c",
         f"""insert into exam_attempts (user_id, event_id, domain_id, expires_at)
             select '{me["profile"]["id"]}', e.id, d.id, now() + interval '20 min'
             from exam_events e, domains d
             where e.slug='tech-arena-2026' and d.slug='ai-ml'"""],
        check=True,
    )

    r = client.post("/api/v1/register", json={**REG, "student_id": "CHANGED"},
                    headers={"Authorization": auth})
    assert r.status_code == 409                          # cannot re-badge after starting

    # …and the database refuses a second attempt outright.
    second = subprocess.run(
        ["psql", "-v", "ON_ERROR_STOP=1", "-d", DB, "-c",
         f"""insert into exam_attempts (user_id, event_id, domain_id, expires_at)
             select '{me["profile"]["id"]}', e.id, d.id, now() + interval '20 min'
             from exam_events e, domains d
             where e.slug='tech-arena-2026' and d.slug='full-stack'"""],
        capture_output=True, text=True,
    )
    assert second.returncode != 0
    assert "duplicate key" in second.stderr
