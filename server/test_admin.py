"""Admin API. The boundary tests here matter more than the feature tests: this
panel reads every student's phone number and can rewrite the question bank.
"""
import io
import zipfile

import pytest

from server.conftest import DB, make_student, psql, scalar
# Same real 1,000-question bank the exam tests use: the analytics and export
# queries are only meaningful against a populated one.
from server.test_exam import seed_bank  # noqa: F401  (module-scoped autouse)

ADMIN_PW = "correct-horse-battery-staple"


@pytest.fixture(scope="module", autouse=True)
def admin_env(database):
    import os

    os.environ["ADMIN_SECRET"] = "test-admin-secret"
    from server import db as dbmod
    from server.adminauth import hash_password
    from server.settings import settings

    settings.admin_secret = "test-admin-secret"
    os.environ["DATABASE_URL"] = f"postgresql:///{DB}"
    dbmod.pool.open()
    with dbmod.cursor() as cur:
        for email, role in (("boss@arena.test", "admin"), ("watcher@arena.test", "viewer")):
            cur.execute(
                """
                insert into admin_users (email, name, role, password_hash)
                values (%s, %s, %s, %s)
                on conflict (lower(email)) do update set password_hash = excluded.password_hash
                """,
                (email, email.split("@")[0], role, hash_password(ADMIN_PW)),
            )


def signin(client, email="boss@arena.test", password=ADMIN_PW):
    r = client.post("/api/v1/admin/login", json={"email": email, "password": password})
    return r


@pytest.fixture
def admin(client):
    signin(client)
    yield client
    client.cookies.clear()


# ------------------------------------------------------------------ passwords

def test_password_hashes_are_salted_and_verify():
    from server.adminauth import hash_password, verify_password

    a, b = hash_password("same-password"), hash_password("same-password")
    assert a != b, "identical passwords must not produce identical hashes"
    assert verify_password("same-password", a)
    assert not verify_password("same-password ", a)
    assert not verify_password("", a)


def test_a_corrupt_stored_hash_fails_closed():
    """A truncated or hand-edited row must deny the login, never raise a 500 that
    an attacker can use to tell that account apart from the others."""
    from server.adminauth import verify_password

    for junk in ("", "garbage", "scrypt$x$8$1$aa$bb", "bcrypt$1$2$3$4$5"):
        assert verify_password("anything", junk) is False


# ------------------------------------------------------------------ the boundary

def test_every_admin_endpoint_refuses_an_anonymous_caller(client):
    """The whole point of the phase. Enumerated explicitly rather than trusting
    that the dependency was remembered on each new route."""
    client.cookies.clear()
    for method, path in [
        ("get", "/api/v1/admin/me"),
        ("get", "/api/v1/admin/overview"),
        ("get", "/api/v1/admin/students"),
        ("get", "/api/v1/admin/students/00000000-0000-0000-0000-000000000000"),
        ("get", "/api/v1/admin/questions"),
        ("post", "/api/v1/admin/questions"),
        ("put", "/api/v1/admin/questions/00000000-0000-0000-0000-000000000000"),
        ("delete", "/api/v1/admin/questions/00000000-0000-0000-0000-000000000000"),
        ("post", "/api/v1/admin/questions/import"),
        ("get", "/api/v1/admin/analytics/questions"),
        ("get", "/api/v1/admin/analytics/colleges"),
        ("get", "/api/v1/admin/export/csv"),
        ("get", "/api/v1/admin/export/pdf"),
    ]:
        r = getattr(client, method)(path)
        assert r.status_code == 401, f"{method.upper()} {path} returned {r.status_code}"


def test_a_student_token_is_not_an_admin_session(client):
    """Different auth worlds. A valid Supabase JWT must buy nothing here."""
    client.cookies.clear()
    token = make_student("sneaky@example.edu", "Sneaky")
    r = client.get("/api/v1/admin/students", headers={"Authorization": token})
    assert r.status_code == 401


def test_a_forged_session_cookie_is_refused(client):
    import jwt

    client.cookies.clear()
    forged = jwt.encode({"sub": "x", "email": "e@x", "role": "admin", "exp": 9999999999},
                        "not-the-secret", algorithm="HS256")
    r = client.get("/api/v1/admin/me", cookies={"admin_session": forged})
    assert r.status_code == 401
    client.cookies.clear()


def test_login_is_not_an_email_oracle(client):
    """A wrong password and a nonexistent account must be indistinguishable, or
    the endpoint tells you which of your guesses are real admins."""
    client.cookies.clear()
    wrong = signin(client, "boss@arena.test", "wrong-password")
    missing = signin(client, "nobody@arena.test", "wrong-password")
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]


def test_the_session_cookie_is_httponly(client):
    """A cookie readable from JavaScript is one XSS away from being an admin."""
    client.cookies.clear()
    r = signin(client)
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "samesite=lax" in r.headers["set-cookie"].lower()
    client.cookies.clear()


def test_login_refuses_to_issue_a_session_without_a_configured_secret(client):
    """Absent ADMIN_SECRET must mean no admin sessions at all — never one signed
    with an empty default that anybody could forge."""
    from server.settings import settings

    client.cookies.clear()
    settings.admin_secret = None
    try:
        assert signin(client).status_code == 503
    finally:
        settings.admin_secret = "test-admin-secret"


def test_a_viewer_can_read_everything_and_write_nothing(client):
    client.cookies.clear()
    assert signin(client, "watcher@arena.test").json()["role"] == "viewer"
    assert client.get("/api/v1/admin/students").status_code == 200
    assert client.get("/api/v1/admin/questions").status_code == 200

    blocked = client.post("/api/v1/admin/questions", json={
        "domain_slug": "tech", "type": "mcq", "body": "Should not be created?",
        "topic": "x", "difficulty": "easy", "options": ["a", "b"], "correct_index": 0,
    })
    assert blocked.status_code == 403
    client.cookies.clear()


def test_logout_clears_the_session(client):
    client.cookies.clear()
    signin(client)
    assert client.get("/api/v1/admin/me").status_code == 200
    client.post("/api/v1/admin/logout")
    assert client.get("/api/v1/admin/me").status_code == 401
    client.cookies.clear()


# ------------------------------------------------------------------ data

@pytest.fixture(scope="module")
def sat_exam(client, admin_env):
    """One student who has actually sat and submitted, so the read endpoints are
    exercised against a real attempt rather than an empty table."""
    from server.test_exam import register, start

    auth = register(client, "adminfixture@example.edu", "Admin Fixture", "AD10001")
    attempt = start(client, auth).json()["attempt"]
    pos1 = scalar(f"""
        select o.id from attempt_questions aq
        join question_options o on o.question_id = aq.question_id
        where aq.attempt_id = '{attempt['id']}' and aq.position = 1 and o.is_correct
    """)
    client.put(f"/api/v1/attempts/{attempt['id']}/answers/1",
               json={"option_id": pos1, "response_ms": 4000},
               headers={"Authorization": auth})
    result = client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                         headers={"Authorization": auth}).json()
    client.cookies.clear()
    return {"email": "adminfixture@example.edu", **result}


def test_overview_reads_a_precomputed_row_not_a_live_count(admin, sat_exam):
    """A dashboard doing COUNT(*) over every attempt on each load would be the
    slowest thing in the system, so the counters are refreshed by cron."""
    before = admin.get("/api/v1/admin/overview").json()
    assert "refreshed_at" in before and before["stale_seconds"] >= 0

    admin.post("/api/v1/cron/refresh-overview",
               headers={"Authorization": "Bearer test-cron-secret"})
    after = admin.get("/api/v1/admin/overview").json()
    assert after["students"] > 0
    assert after["submitted"] >= 1
    assert after["certificates"] >= 1
    assert {d["slug"] for d in after["by_domain"]}


def test_the_overview_refresh_needs_the_cron_secret(client):
    client.cookies.clear()
    assert client.post("/api/v1/cron/refresh-overview").status_code == 401


def test_the_student_list_paginates_by_keyset_not_offset(admin):
    first = admin.get("/api/v1/admin/students?limit=2").json()
    assert len(first["students"]) <= 2
    if first["next_cursor"]:
        second = admin.get(
            f"/api/v1/admin/students?limit=2&cursor={first['next_cursor']}").json()
        seen = {s["id"] for s in first["students"]}
        assert not (seen & {s["id"] for s in second["students"]}), "pages overlapped"


def test_a_malformed_cursor_is_rejected_not_ignored(admin):
    """Silently ignoring it would quietly restart pagination from the top and an
    export would repeat rows without anyone noticing."""
    assert admin.get("/api/v1/admin/students?cursor=garbage").status_code == 422


def test_student_search_and_filters_narrow_the_list(admin, sat_exam):
    found = admin.get("/api/v1/admin/students?q=Admin+Fixture").json()["students"]
    assert any(s["email"] == sat_exam["email"] for s in found)

    nobody = admin.get("/api/v1/admin/students?q=zzz-no-such-student").json()["students"]
    assert nobody == []

    by_status = admin.get("/api/v1/admin/students?attempt_status=submitted").json()["students"]
    assert all(s["attempt_status"] == "submitted" for s in by_status)


def test_student_detail_shows_the_per_question_breakdown_admins_need(admin, sat_exam):
    listed = admin.get(f"/api/v1/admin/students?q={sat_exam['email']}").json()["students"][0]
    detail = admin.get(f"/api/v1/admin/students/{listed['id']}").json()

    assert detail["certificate_id"] == sat_exam["certificate_id"]
    assert len(detail["questions"]) == 15
    assert detail["questions"][0]["is_correct"] is True
    assert detail["questions"][0]["response_ms"] == 4000
    assert isinstance(detail["flags"], list)


def test_student_detail_404s_for_an_unknown_id(admin):
    assert admin.get(
        "/api/v1/admin/students/00000000-0000-0000-0000-000000000000").status_code == 404


# ------------------------------------------------------------------ questions

def test_question_crud_round_trips(admin):
    payload = {
        "domain_slug": "tech", "type": "mcq",
        "body": "Which HTTP status means the request conflicts with server state?",
        "topic": "HTTP", "difficulty": "easy", "status": "draft",
        "options": ["409 Conflict", "402 Payment Required", "418 Teapot"],
        "correct_index": 0,
    }
    created = admin.post("/api/v1/admin/questions", json=payload)
    assert created.status_code == 201
    qid = created.json()["id"]

    listed = admin.get("/api/v1/admin/questions?q=conflicts+with+server").json()
    mine = next(q for q in listed["questions"] if q["id"] == qid)
    assert mine["status"] == "draft"
    assert [o["is_correct"] for o in mine["options"]] == [True, False, False]

    payload["correct_index"] = 2
    payload["status"] = "active"
    assert admin.put(f"/api/v1/admin/questions/{qid}", json=payload).status_code == 200
    again = admin.get("/api/v1/admin/questions?q=conflicts+with+server").json()["questions"]
    edited = next(q for q in again if q["id"] == qid)
    assert [o["is_correct"] for o in edited["options"]] == [False, False, True]
    assert edited["status"] == "active"
    assert scalar(f"select version from questions where id = '{qid}'") == "2"


def test_a_question_is_retired_never_deleted(admin):
    """Deleting one would cascade away the attempt_questions rows that explain
    the score of every student who was given it."""
    payload = {
        "domain_slug": "tech", "type": "mcq", "body": "Retire me please, thanks?",
        "topic": "Misc", "difficulty": "easy", "options": ["a", "b"], "correct_index": 0,
    }
    qid = admin.post("/api/v1/admin/questions", json=payload).json()["id"]
    assert admin.delete(f"/api/v1/admin/questions/{qid}").status_code == 200
    assert scalar(f"select status from questions where id = '{qid}'") == "retired"
    assert scalar(f"select count(*) from questions where id = '{qid}'") == "1"


def test_a_correct_index_outside_the_options_is_refused(admin):
    """Accepting it would create a question with no correct answer — every
    student who drew it would be marked wrong whatever they picked."""
    r = admin.post("/api/v1/admin/questions", json={
        "domain_slug": "tech", "type": "mcq", "body": "Broken question here?",
        "topic": "Misc", "difficulty": "easy", "options": ["a", "b"], "correct_index": 4,
    })
    assert r.status_code == 422
    assert scalar("select count(*) from questions where body = 'Broken question here?'") == "0"


def test_unknown_domain_is_refused(admin):
    r = admin.post("/api/v1/admin/questions", json={
        "domain_slug": "underwater-basket-weaving", "type": "mcq",
        "body": "Does this domain exist?", "topic": "Misc", "difficulty": "easy",
        "options": ["a", "b"], "correct_index": 0,
    })
    assert r.status_code == 404


def test_csv_import_dry_run_changes_nothing(admin):
    csv_text = (
        "external_id,domain,type,topic,difficulty,question,code,language,"
        "option_a,option_b,option_c,option_d,correct,explanation\n"
        "ADM-I001,tech,mcq,http,easy,"
        "What does CORS stand for in this import test?,,,"
        "Cross-Origin Resource Sharing,Cross Origin Route Skipping,"
        "Client Origin Request Scope,Crossed Over Router Setup,A,"
        "Cross-Origin Resource Sharing.\n"
    )
    before = scalar("select count(*) from questions")
    dry = admin.post("/api/v1/admin/questions/import", content=csv_text,
                     headers={"X-Dry-Run": "1"})
    assert dry.json() == {"ok": True, "dry_run": True, "rows": 1}
    assert scalar("select count(*) from questions") == before

    real = admin.post("/api/v1/admin/questions/import", content=csv_text)
    assert real.json() == {"ok": True, "created": 1, "updated": 0}
    assert scalar("select count(*) from questions") == str(int(before) + 1)


def test_a_bad_csv_is_rejected_whole_not_partially_applied(admin):
    before = scalar("select count(*) from questions")
    bad = admin.post("/api/v1/admin/questions/import", content=(
        "external_id,domain,type,topic,difficulty,question,code,language,"
        "option_a,option_b,option_c,option_d,correct,explanation\n"
        "ADM-B001,tech,mcq,http,easy,A fine row for the partial import test?,,,"
        "a,b,c,d,A,Because.\n"
        "ADM-B002,no-such-domain,mcq,http,easy,A broken row in the same file?,,,"
        "a,b,c,d,A,Because.\n"
    ))
    assert bad.json()["ok"] is False
    assert bad.json()["errors"]
    assert scalar("select count(*) from questions") == before


# ------------------------------------------------------------------ analytics

def test_question_analytics_surfaces_the_worst_answered_first(admin, sat_exam):
    """A question everyone gets wrong is usually broken, not hard. Ordering by
    correct rate is what makes that reviewable at all."""
    rows = admin.get("/api/v1/admin/analytics/questions").json()["questions"]
    assert rows
    rates = [r["correct_rate"] for r in rows]
    assert rates == sorted(rates), "worst-answered questions must come first"
    assert all(0 <= r <= 1 for r in rates)
    assert all(r["answered"] > 0 for r in rows)
    # A skipped question is not a wrong answer: the rate is over attempts only,
    # so a question nobody tried must not be reported as one nobody could do.
    assert all(r["skipped"] == 0 or r["seen"] > r["answered"] for r in rows)
    assert all(r["correct"] <= r["answered"] <= r["seen"] for r in rows)


def test_college_analytics_counts_participation(admin, sat_exam):
    rows = admin.get("/api/v1/admin/analytics/colleges").json()["colleges"]
    mine = next(c for c in rows if c["name"] == "ABC College of Engineering")
    assert mine["students"] >= 1
    assert mine["completed"] >= 1


# ------------------------------------------------------------------ exports

def test_csv_export_streams_every_filtered_row(admin, sat_exam):
    r = admin.get("/api/v1/admin/export/csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]

    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert lines[0].startswith("name,email,phone")
    assert any(sat_exam["email"] in ln for ln in lines[1:])


def test_csv_export_honours_the_same_filters_as_the_list(admin, sat_exam):
    """The export must cover exactly what the screen showed. An organiser who
    filters and then exports a different set has been lied to."""
    listed = admin.get("/api/v1/admin/students?q=Admin+Fixture").json()["students"]
    exported = admin.get("/api/v1/admin/export/csv?q=Admin+Fixture").text
    rows = [ln for ln in exported.splitlines()[1:] if ln.strip()]
    assert len(rows) == len(listed)


def test_batch_pdf_returns_a_real_zip_of_real_pdfs(admin, sat_exam):
    r = admin.get("/api/v1/admin/export/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert f"{sat_exam['certificate_id']}.pdf" in names
        assert zf.read(names[0]).startswith(b"%PDF-")


def test_batch_pdf_is_capped_rather_than_becoming_an_outage(admin, monkeypatch):
    """Nobody reads a 50,000-certificate archive, and rendering one is not a
    thing to do inside a request. Above the cap, CSV is the answer."""
    from server import admin as admin_module

    monkeypatch.setattr(admin_module, "MAX_BATCH_PDF", 0)
    assert admin.get("/api/v1/admin/export/pdf").status_code == 413


def test_batch_pdf_404s_when_nothing_matches(admin):
    assert admin.get("/api/v1/admin/export/pdf?q=zzz-nobody").status_code == 404


# ------------------------------------------------------------------ cron-independence

def test_the_dashboard_refreshes_itself_when_the_counters_go_stale(admin, sat_exam):
    """Vercel's Hobby plan caps cron jobs at once per day. If the dashboard
    depended on that cron it would show yesterday's numbers all through the
    event, so a stale read recomputes rather than serving what it has."""
    from server import db as dbmod

    with dbmod.cursor() as cur:
        cur.execute("update admin_overview set refreshed_at = now() - interval '1 day', "
                    "students = -1 where id")

    body = admin.get("/api/v1/admin/overview").json()
    assert body["students"] > 0, "a stale dashboard served its stale value"
    assert body["stale_seconds"] < 60


def test_a_fresh_dashboard_does_not_recompute_on_every_read(admin, sat_exam):
    """The counters exist because COUNT(*) over every attempt on each page load
    would be the slowest thing in the system. Refreshing on read must not
    quietly reintroduce exactly that."""
    admin.get("/api/v1/admin/overview")
    first = scalar("select refreshed_at from admin_overview where id")
    for _ in range(5):
        admin.get("/api/v1/admin/overview")
    assert scalar("select refreshed_at from admin_overview where id") == first


def test_an_organiser_can_finalise_abandoned_attempts_without_the_cron(admin, client):
    """Same reason: on a daily cron a student who walked away would wait until
    tomorrow for the certificate they already earned."""
    from server.test_exam import register, start

    auth = register(client, "walkaway@example.edu", "Walk Away", "WA0001")
    attempt = start(client, auth).json()["attempt"]
    psql("-c", f"update exam_attempts set expires_at = now() - interval '1 hour' "
               f"where id = '{attempt['id']}'")
    admin.cookies.clear()
    signin(admin)

    r = admin.post("/api/v1/admin/attempts/finalise-abandoned")
    assert r.status_code == 200
    assert r.json()["swept"] >= 1
    assert scalar(f"select status from exam_attempts where id = '{attempt['id']}'") == "expired"
    assert scalar(f"select count(*) from certificates where attempt_id = '{attempt['id']}'") == "1"


def test_finalising_abandoned_attempts_is_writer_only(client):
    """A viewer watching the dashboard must not be able to close out a slot."""
    client.cookies.clear()
    signin(client, "watcher@arena.test")
    assert client.post("/api/v1/admin/attempts/finalise-abandoned").status_code == 403
    client.cookies.clear()
