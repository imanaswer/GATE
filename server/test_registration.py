"""End-to-end check of Phase 1 against a real Postgres.

Run: pnpm api:test  (creates and drops a scratch database)

Covers the thing Phase 1 exists to prove: a Google account can register once,
and the *database* — not application logic, not the browser — is what stops a
second attempt.
"""
import subprocess

from server.conftest import DB, make_student, scalar

REG = {
    "phone": "+91 98765 43210",
    "college_name": "ABC College of Engineering",
    "location": "Kochi",
    "student_id": "CS21001",
}


def test_health(client):
    assert client.get("/api/v1/health").json() == {"ok": True}


def test_rejects_unauthenticated(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/register", json=REG).status_code == 401


def test_rejects_forged_token(client):
    import jwt, uuid
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
    assert client.post("/api/v1/register", json={**REG, "location": ""}, headers=h).status_code == 422
    assert client.post("/api/v1/register", json={k: v for k, v in REG.items() if k != "location"},
                       headers=h).status_code == 422
    no_college = {k: v for k, v in REG.items() if k != "college_name"}
    assert client.post("/api/v1/register", json=no_college, headers=h).status_code == 422


def test_duplicate_student_id_is_flagged_not_blocked(client):
    """The whole point of §1.1: a typo must not lock anyone out."""
    auth = make_student("typo@example.edu", "Typo Student")
    r = client.post("/api/v1/register", json=REG, headers={"Authorization": auth})
    assert r.status_code == 200                          # registration SUCCEEDS
    assert r.json()["flagged_duplicate_student_id"] is True
    assert r.json()["profile"]["registered"] is True

    assert int(scalar(
        "select count(*) from suspicious_activity where type='duplicate_student_id'"
    )) >= 1                                              # and an admin can see it


def test_colleges_are_deduplicated_by_name(client):
    auth = make_student("dedupe@example.edu", "Dedupe")
    client.post(
        "/api/v1/register",
        json={**REG, "college_name": "  abc college OF engineering ", "student_id": "CS21500"},
        headers={"Authorization": auth},
    )
    assert scalar("select count(*) from colleges where lower(name) like 'abc college%'") == "1"


def test_domains_listed(client):
    rows = client.get("/api/v1/domains").json()
    assert {r["slug"] for r in rows} == {
        "general", "math", "science", "commerce", "tech", "data", "combined"}


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


def test_hs256_is_refused_unless_explicitly_enabled(monkeypatch):
    """A shared signing secret lets anyone mint a token for any user. It must be
    opted into, never picked up silently from a stray environment variable."""
    import importlib

    import server.settings as settings_module

    monkeypatch.delenv("ALLOW_HS256_JWT", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "leaked-from-a-dotenv")
    reloaded = importlib.reload(settings_module)
    assert reloaded.settings.supabase_jwt_secret is None
    assert reloaded.settings.allow_hs256 is False

    monkeypatch.setenv("ALLOW_HS256_JWT", "true")
    monkeypatch.setenv("VERCEL_ENV", "production")
    try:
        importlib.reload(settings_module)
        raise AssertionError("production must refuse the symmetric path")
    except RuntimeError as e:
        assert "must not be set in production" in str(e)
    finally:
        monkeypatch.delenv("VERCEL_ENV", raising=False)
        importlib.reload(settings_module)


# ------------------------------------------------------- collecting less

def test_registration_succeeds_without_a_student_id(client):
    """Optional means optional. A student who does not know their register
    number must still be able to sit the exam."""
    auth = make_student("noid@example.edu", "No Id")
    payload = {k: v for k, v in REG.items() if k != "student_id"}
    r = client.post("/api/v1/register", json=payload, headers={"Authorization": auth})
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["registered"] is True
    assert r.json()["profile"]["student_id"] is None


def test_students_without_a_student_id_do_not_flag_each_other(client):
    """Two absent IDs are not the same ID. Flagging them would fill the review
    list an organiser reads with people who simply left a field blank."""
    payload = {k: v for k, v in REG.items() if k != "student_id"}
    for email in ("blank-a@example.edu", "blank-b@example.edu"):
        auth = make_student(email, email.split("@")[0])
        r = client.post("/api/v1/register", json=payload, headers={"Authorization": auth})
        assert r.json()["flagged_duplicate_student_id"] is False

    assert scalar(
        "select count(*) from suspicious_activity where type = 'duplicate_student_id' "
        "and user_id in (select id from users where email like 'blank-%')"
    ) == "0"


def test_location_is_required(client):
    auth = make_student("noloc@example.edu", "No Loc")
    payload = {k: v for k, v in REG.items() if k != "location"}
    assert client.post("/api/v1/register", json=payload,
                       headers={"Authorization": auth}).status_code == 422


def test_the_same_place_spelled_differently_is_one_row(client):
    """The whole reason location is a table and not a text column: 'Kochi',
    'kochi' and '  Kochi  ' must group as one place in the analytics."""
    for i, spelling in enumerate(("Trivandrum", "trivandrum", "  Trivandrum  ")):
        auth = make_student(f"place{i}@example.edu", f"Place {i}")
        r = client.post("/api/v1/register",
                        json={**REG, "location": spelling, "student_id": f"PL{i}"},
                        headers={"Authorization": auth})
        assert r.status_code == 200, r.text
        assert r.json()["profile"]["location"] == "Trivandrum"

    assert scalar("select count(*) from locations where lower(name) = 'trivandrum'") == "1"


def test_the_form_no_longer_collects_course_or_year(client):
    """Collecting less is a schema fact, not a form convention — otherwise the
    columns come back the first time someone adds an input."""
    columns = scalar(
        "select count(*) from information_schema.columns "
        "where table_name = 'users' and column_name in ('course', 'academic_year')"
    )
    assert columns == "0"


def test_locations_autocomplete_lists_places_already_entered(client):
    auth = make_student("autoc@example.edu", "Auto C")
    client.post("/api/v1/register", json={**REG, "location": "Coimbatore"},
                headers={"Authorization": auth})
    names = [p["name"] for p in client.get("/api/v1/locations?q=coim").json()]
    assert "Coimbatore" in names
    assert client.get("/api/v1/locations?q=zzzznowhere").json() == []
