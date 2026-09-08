"""Phase 7 — rate limits and the post-hoc integrity signals.

The bias throughout: a limiter that fires on a real student is worse than the
abuse it prevents, so these tests pin down what is deliberately *not* limited
as firmly as what is.
"""
import pytest

from server.conftest import DB, scalar
from server.test_admin import admin_env  # noqa: F401  (creates the admin accounts)
from server.test_exam import register, seed_bank, start  # noqa: F401


@pytest.fixture(autouse=True)
def clean_limits(database):
    import os

    from server import db as dbmod

    os.environ["DATABASE_URL"] = f"postgresql:///{DB}"
    dbmod.pool.open()
    with dbmod.cursor() as cur:
        cur.execute("delete from rate_limits")
    yield
    with dbmod.cursor() as cur:
        cur.execute("delete from rate_limits")


def correct_option(attempt_id, position):
    return scalar(f"""
        select o.id from attempt_questions aq
        join question_options o on o.question_id = aq.question_id
        where aq.attempt_id = '{attempt_id}' and aq.position = {position} and o.is_correct
    """)


# ------------------------------------------------------------------ limits

def test_public_verification_is_rate_limited(client):
    """The only unauthenticated endpoint. Unlimited, it is a free scraping
    target; the limiter is also cheaper than the five-table join it guards."""
    auth = register(client, "rl-verify@example.edu", "Rl Verify", "RL0001")
    attempt = start(client, auth).json()["attempt"]
    cert = client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                       headers={"Authorization": auth}).json()["certificate_id"]

    codes = [client.get(f"/api/v1/certificates/{cert}").status_code for _ in range(35)]
    assert codes[0] == 200
    assert 429 in codes, "verification was not limited"
    assert codes.count(200) <= 30


def test_a_limited_response_says_when_to_come_back(client):
    codes = [client.get("/api/v1/certificates/TA-2026-K7M2QX9VBT") for _ in range(35)]
    limited = next(r for r in codes if r.status_code == 429)
    assert int(limited.headers["Retry-After"]) > 0
    assert "Too many requests" in limited.json()["detail"]


def test_answer_saving_is_deliberately_not_limited(client):
    """The hot path — roughly 110 writes a second at slot capacity. An autosave
    is an idempotent upsert onto one row that a student cannot use to do harm,
    so limiting it would double the write load on the one path that cannot be
    degraded on event day, to prevent nothing."""
    auth = register(client, "rl-save@example.edu", "Rl Save", "RL0002")
    body = start(client, auth).json()
    attempt, qs = body["attempt"], body["questions"]
    h = {"Authorization": auth}

    codes = {
        client.put(f"/api/v1/attempts/{attempt['id']}/answers/1",
                   json={"option_id": qs[0]["options"][0]["id"]}, headers=h).status_code
        for _ in range(80)
    }
    assert codes == {200}


def test_submitting_is_deliberately_not_limited(client):
    """A limit that fires here has blocked a real student from handing in a real
    exam. An impatient double-click is not an attack, and a repeat submit is a
    row lock plus a read of a result already computed."""
    auth = register(client, "rl-submit@example.edu", "Rl Submit", "RL0003")
    attempt = start(client, auth).json()["attempt"]
    h = {"Authorization": auth}

    codes = {client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                         headers=h).status_code for _ in range(12)}
    assert codes == {200}


def test_admin_login_locks_out_after_repeated_failures(client):
    client.cookies.clear()
    bad = {"email": "boss@arena.test", "password": "wrong"}
    codes = [client.post("/api/v1/admin/login", json=bad).status_code for _ in range(9)]
    assert codes[0] == 401
    assert 429 in codes, "brute force was not limited"


def test_successful_admin_logins_are_not_counted_as_attacks(client):
    """An admin signing in from a phone and a laptop is not a brute force, and
    locking them out for it would be the limiter causing the incident it exists
    to prevent."""
    from server.test_admin import ADMIN_PW

    client.cookies.clear()
    good = {"email": "boss@arena.test", "password": ADMIN_PW}
    codes = {client.post("/api/v1/admin/login", json=good).status_code for _ in range(9)}
    assert codes == {200}
    client.cookies.clear()


def test_the_limiter_fails_open_rather_than_blocking_the_exam(monkeypatch):
    """A limiter outage must never be the reason a student cannot sit an exam."""
    from server import ratelimit

    def broken(*_a, **_k):
        raise RuntimeError("database is unreachable")

    monkeypatch.setattr(ratelimit.db, "fetch_one", broken)
    ratelimit.check("verify", "1.2.3.4", limit=1, per_seconds=60)
    ratelimit.guard("verify", "1.2.3.4", limit=1, per_seconds=60)


def test_old_windows_are_swept_by_the_existing_cron(client):
    from server import db as dbmod

    with dbmod.cursor() as cur:
        cur.execute(
            "insert into rate_limits (bucket, subject, window_start, count) "
            "values ('stale', 'x', now() - interval '3 hours', 99)"
        )
    client.post("/api/v1/cron/expire-attempts",
                headers={"Authorization": "Bearer test-cron-secret"})
    assert scalar("select count(*) from rate_limits where bucket = 'stale'") == "0"


# ------------------------------------------------------------------ integrity

def test_identical_answer_sequences_are_flagged_as_a_pair(client):
    """Two students who answered every question the same way. Flagged for a
    human, never disqualified."""
    from server import db as dbmod

    attempts = []
    for i in (1, 2):
        auth = register(client, f"twin{i}@example.edu", f"Twin {i}", f"TW000{i}")
        body = start(client, auth).json()
        attempts.append((auth, body["attempt"]))

    # Hand both students the same paper, which is the case the fingerprint is
    # looking for. Rebuilt rather than updated in place: unique(attempt_id,
    # question_id) is checked per row, so a bulk swap trips over itself.
    a_id, b_id = attempts[0][1]["id"], attempts[1][1]["id"]
    with dbmod.cursor() as cur:
        cur.execute("delete from attempt_questions where attempt_id = %s", (b_id,))
        cur.execute(
            "insert into attempt_questions (attempt_id, question_id, position, option_order) "
            "select %s, question_id, position, option_order from attempt_questions "
            "where attempt_id = %s",
            (b_id, a_id),
        )
    for auth, attempt in attempts:
        for pos in range(1, 6):
            client.put(f"/api/v1/attempts/{attempt['id']}/answers/{pos}",
                       json={"option_id": correct_option(attempt["id"], pos)},
                       headers={"Authorization": auth})
        client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                    headers={"Authorization": auth})

    client.post("/api/v1/cron/scan-integrity",
                headers={"Authorization": "Bearer test-cron-secret"})

    flagged = scalar(
        f"select count(*) from suspicious_activity "
        f"where type = 'pattern_match' and attempt_id in ('{a_id}','{b_id}')")
    assert flagged == "2", "both halves of a matching pair must be flagged"


def test_two_different_papers_are_not_flagged_as_a_pattern(client):
    """Papers are individually selected, so students answering 'A' throughout
    have not colluded. Flagging them would bury the real signal."""
    ids = []
    for i in (1, 2):
        auth = register(client, f"solo{i}@example.edu", f"Solo {i}", f"SL000{i}")
        body = start(client, auth).json()
        attempt, qs = body["attempt"], body["questions"]
        for pos in range(1, 6):
            client.put(f"/api/v1/attempts/{attempt['id']}/answers/{pos}",
                       json={"option_id": qs[pos - 1]["options"][0]["id"]},
                       headers={"Authorization": auth})
        client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                    headers={"Authorization": auth})
        ids.append(attempt["id"])

    client.post("/api/v1/cron/scan-integrity",
                headers={"Authorization": "Bearer test-cron-secret"})
    flagged = scalar(
        f"select count(*) from suspicious_activity "
        f"where type = 'pattern_match' and attempt_id in ('{ids[0]}','{ids[1]}')")
    assert flagged == "0"


def test_an_all_blank_paper_is_not_a_conspiracy(client):
    """Several students who answered nothing all share a fingerprint. That is
    absence, not collusion."""
    ids = []
    for i in (1, 2):
        auth = register(client, f"blank{i}@example.edu", f"Blank {i}", f"BL000{i}")
        attempt = start(client, auth).json()["attempt"]
        client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                    headers={"Authorization": auth})
        ids.append(attempt["id"])

    client.post("/api/v1/cron/scan-integrity",
                headers={"Authorization": "Bearer test-cron-secret"})
    assert scalar(
        f"select count(*) from suspicious_activity "
        f"where type = 'pattern_match' and attempt_id in ('{ids[0]}','{ids[1]}')") == "0"


def test_implausibly_fast_correct_answers_are_flagged(client):
    from server import db as dbmod

    auth = register(client, "speedy@example.edu", "Speedy", "SP0001")
    attempt = start(client, auth).json()["attempt"]
    for pos in range(1, 8):
        client.put(f"/api/v1/attempts/{attempt['id']}/answers/{pos}",
                   json={"option_id": correct_option(attempt["id"], pos),
                         "response_ms": 900},
                   headers={"Authorization": auth})
    client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                headers={"Authorization": auth})

    client.post("/api/v1/cron/scan-integrity",
                headers={"Authorization": "Bearer test-cron-secret"})
    assert scalar(f"select count(*) from suspicious_activity "
                  f"where type = 'fast_response' and attempt_id = '{attempt['id']}'") == "1"
    del dbmod


def test_one_lucky_quick_answer_is_not_a_flag(client):
    """One fast answer is luck. The threshold exists so the list an organiser
    reads is short enough to actually be read."""
    auth = register(client, "lucky@example.edu", "Lucky", "LK0001")
    attempt = start(client, auth).json()["attempt"]
    client.put(f"/api/v1/attempts/{attempt['id']}/answers/1",
               json={"option_id": correct_option(attempt["id"], 1), "response_ms": 900},
               headers={"Authorization": auth})
    client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                headers={"Authorization": auth})

    client.post("/api/v1/cron/scan-integrity",
                headers={"Authorization": "Bearer test-cron-secret"})
    assert scalar(f"select count(*) from suspicious_activity "
                  f"where type = 'fast_response' and attempt_id = '{attempt['id']}'") == "0"


def test_rescanning_replaces_flags_rather_than_duplicating_them(client):
    for _ in range(3):
        client.post("/api/v1/cron/scan-integrity",
                    headers={"Authorization": "Bearer test-cron-secret"})
    rows = scalar("select count(*) from suspicious_activity where type = 'fast_response'")
    dupes = scalar("""
        select coalesce(max(n), 0) from (
          select count(*) as n from suspicious_activity
          where type = 'fast_response' group by attempt_id
        ) t
    """)
    assert int(rows) >= 0 and dupes in ("0", "1")


def test_a_flag_never_changes_the_score_or_the_certificate(client):
    """The whole design position: these signals produce a list for a human. If a
    scan could void an attempt, one false positive costs a student their exam."""
    auth = register(client, "integrity-flagged@example.edu", "Integrity Flagged", "FL0001")
    attempt = start(client, auth).json()["attempt"]
    for pos in range(1, 8):
        client.put(f"/api/v1/attempts/{attempt['id']}/answers/{pos}",
                   json={"option_id": correct_option(attempt["id"], pos), "response_ms": 500},
                   headers={"Authorization": auth})
    before = client.post(f"/api/v1/attempts/{attempt['id']}/submit",
                         headers={"Authorization": auth}).json()

    client.post("/api/v1/cron/scan-integrity",
                headers={"Authorization": "Bearer test-cron-secret"})
    after = client.get(f"/api/v1/attempts/{attempt['id']}/result",
                       headers={"Authorization": auth}).json()

    assert scalar(f"select count(*) from suspicious_activity "
                  f"where type = 'fast_response' and attempt_id = '{attempt['id']}'") == "1"
    assert after["score"] == before["score"]
    assert after["status"] == before["status"] == "submitted"
    assert after["certificate_id"] == before["certificate_id"]


# ------------------------------------------------------------------ advisory fields

@pytest.mark.parametrize("bad_ms", [
    52341.87,          # a float — what performance.now() deltas look like
    -1,                # a clock that went backwards
    999_999_999_999,   # a tab left open, or a clock jump
    "not a number",
])
def test_a_bad_response_time_never_costs_a_student_their_answer(client, bad_ms):
    """response_ms is client-reported analytics that is explicitly never an
    input to scoring. Rejecting the request over it would throw away a real
    answer to protect a number nobody scores on."""
    auth = register(client, f"ms{abs(hash(str(bad_ms))) % 9999}@example.edu",
                    "Advisory", f"AV{abs(hash(str(bad_ms))) % 9999:04d}")
    body = start(client, auth).json()
    attempt, qs = body["attempt"], body["questions"]
    option = qs[0]["options"][0]["id"]

    r = client.put(f"/api/v1/attempts/{attempt['id']}/answers/1",
                   json={"option_id": option, "response_ms": bad_ms},
                   headers={"Authorization": auth})
    assert r.status_code == 200, f"a bad response_ms rejected the answer: {r.text}"
    assert scalar(f"""
        select selected_option_id from answers ans
        join attempt_questions aq on aq.id = ans.attempt_question_id
        where aq.attempt_id = '{attempt['id']}' and aq.position = 1
    """) == option


def test_a_sane_response_time_is_still_recorded(client):
    """Leniency must not become 'the field is ignored' — it is the signal the
    integrity scan reads."""
    auth = register(client, "goodms@example.edu", "Good Ms", "GM0001")
    body = start(client, auth).json()
    attempt, qs = body["attempt"], body["questions"]
    client.put(f"/api/v1/attempts/{attempt['id']}/answers/1",
               json={"option_id": qs[0]["options"][0]["id"], "response_ms": 7500},
               headers={"Authorization": auth})
    assert scalar(f"""
        select ans.response_ms from answers ans
        join attempt_questions aq on aq.id = ans.attempt_question_id
        where aq.attempt_id = '{attempt['id']}' and aq.position = 1
    """) == "7500"
