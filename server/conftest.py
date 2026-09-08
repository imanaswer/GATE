"""Scratch-database fixtures. Each test module gets a real Postgres with the
migrations applied — the constraints are the thing under test, so a mock would
test nothing."""
import os
import subprocess
import uuid

import jwt
import pytest

SECRET = "test-secret-not-used-anywhere-real"
DB = f"tech_arena_test_{os.getpid()}"


def psql(*args, check=True):
    return subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1", "-d", DB, *args],
        check=check, capture_output=True, text=True,
    )


def scalar(sql: str) -> str:
    return subprocess.run(["psql", "-tA", "-d", DB, "-c", sql],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture(scope="session", autouse=True)
def database():
    subprocess.run(["dropdb", "--if-exists", DB], check=False)
    subprocess.run(["createdb", DB], check=True)
    psql("-c", "create extension if not exists pgcrypto;")
    psql("-f", "supabase/test/00_auth_shim.sql")
    for name in sorted(os.listdir("supabase/migrations")):
        psql("-f", f"supabase/migrations/{name}")
    os.environ.update(
        DATABASE_URL=f"postgresql:///{DB}",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET=SECRET,
        EVENT_SLUG="tech-arena-2026",
        CRON_SECRET="test-cron-secret",
    )
    yield
    subprocess.run(["dropdb", "--if-exists", DB], check=False)


@pytest.fixture(scope="session")
def client(database):
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def conn(database):
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(f"postgresql:///{DB}", row_factory=dict_row) as c:
        yield c


def make_student(email: str, name: str) -> str:
    """Create the auth.users row Supabase would have created; return a bearer token."""
    sub = str(uuid.uuid4())
    psql("-c", f"insert into auth.users (id, email) values ('{sub}', '{email}')")
    token = jwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated",
         "user_metadata": {"full_name": name}, "exp": 9999999999},
        SECRET, algorithm="HS256",
    )
    return f"Bearer {token}"
