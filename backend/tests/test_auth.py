"""Access control: the app must be shut to strangers and open to accounts.

The tests that matter most here are the negative ones. A login box that works
proves very little; what has to be proven is that the data endpoints refuse
everyone who has not been through it, that the app fails CLOSED when
misconfigured, and that no forged or expired token is ever accepted.
"""
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import auth as A

PASSWORD = "correct horse battery staple"
# One round keeps the suite fast. The production factor is asserted separately.
HASH = A.hash_password(PASSWORD, rounds=1)


@pytest.fixture
def signed_in(monkeypatch):
    """An instance with one account and a fixed signing secret."""
    monkeypatch.delenv("AUDIOSENSE_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("AUDIOSENSE_USERS", f"alice:{HASH}")
    monkeypatch.setenv("AUDIOSENSE_SECRET", "test-secret-not-a-real-one")
    A._failures.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def no_accounts(monkeypatch):
    """A misconfigured instance: no accounts at all."""
    monkeypatch.delenv("AUDIOSENSE_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.delenv("AUDIOSENSE_USERS", raising=False)
    monkeypatch.setenv("AUDIOSENSE_SECRET", "test-secret-not-a-real-one")
    A._failures.clear()
    with TestClient(app) as c:
        yield c


def token_for(client, username="alice", password=PASSWORD):
    r = client.post("/api/auth/login",
                    json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# =========================================== the door is shut by default

#: A sample spanning every router that touches patient data or configuration.
PROTECTED = [
    ("get", "/api/records/patients"),
    ("get", "/api/demo-cases"),
    ("get", "/api/settings/ai"),
    ("get", "/api/otoscopy/reference"),
    ("get", "/api/diagnosis/reference"),
    ("get", "/api/masking/reference"),
    ("get", "/api/tuning-fork/reference"),
    ("get", "/api/aep/reference"),
    ("get", "/api/model/comparison"),
    ("get", "/api/atlas"),
    ("post", "/api/analyze"),
    ("post", "/api/diagnosis/picture"),
    ("post", "/api/symptoms/analyze"),
    ("post", "/api/tympanometry/analyze"),
    ("post", "/api/report"),
    ("post", "/api/pdf"),
    ("post", "/api/records/visit"),
    ("post", "/api/settings/ai"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_data_endpoint_refuses_an_anonymous_caller(signed_in, method, path):
    r = (signed_in.post(path, json={}) if method == "post"
         else signed_in.get(path))
    assert r.status_code == 401, f"{method.upper()} {path} answered {r.status_code}"


def test_the_patient_list_is_not_readable_without_a_login(signed_in):
    """The single worst leak: every patient's name, age, sex and occupation."""
    r = signed_in.get("/api/records/patients")
    assert r.status_code == 401
    assert "patients" not in r.text.lower() or "sign in" in r.text.lower()


def test_the_ai_settings_route_cannot_be_written_anonymously(signed_in):
    """It accepts an API key and a base_url — an exfiltration path if open."""
    r = signed_in.post("/api/settings/ai",
                       json={"mode": "api", "provider": "ollama",
                             "base_url": "http://attacker.example"})
    assert r.status_code == 401


def test_a_patient_record_cannot_be_deleted_anonymously(signed_in):
    r = signed_in.delete("/api/records/patients/1")
    assert r.status_code == 401


# ======================================================== signing in works


def test_correct_credentials_return_a_token(signed_in):
    r = signed_in.post("/api/auth/login",
                       json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "alice"
    assert body["token"] and "." in body["token"]
    assert body["expires_in"] > 0


def test_a_token_opens_the_protected_endpoints(signed_in):
    t = token_for(signed_in)
    assert signed_in.get("/api/demo-cases", headers=auth(t)).status_code == 200
    assert signed_in.get("/api/records/patients", headers=auth(t)).status_code == 200


def test_me_reports_the_signed_in_user(signed_in):
    t = token_for(signed_in)
    r = signed_in.get("/api/auth/me", headers=auth(t))
    assert r.status_code == 200 and r.json()["username"] == "alice"


def test_me_refuses_without_a_token(signed_in):
    assert signed_in.get("/api/auth/me").status_code == 401


# ================================================== bad credentials fail


@pytest.mark.parametrize("username,password", [
    ("alice", "wrong password entirely"),
    ("alice", ""),
    ("mallory", PASSWORD),
    ("", PASSWORD),
    ("ALICE", PASSWORD),          # usernames are case-sensitive
])
def test_bad_credentials_are_rejected(signed_in, username, password):
    r = signed_in.post("/api/auth/login",
                       json={"username": username, "password": password})
    assert r.status_code in (401, 422)


def test_the_failure_message_does_not_reveal_whether_the_user_exists(signed_in):
    """Otherwise the login form becomes a way to enumerate staff."""
    wrong_pass = signed_in.post(
        "/api/auth/login", json={"username": "alice", "password": "nope"})
    no_user = signed_in.post(
        "/api/auth/login", json={"username": "mallory", "password": "nope"})
    assert wrong_pass.status_code == no_user.status_code == 401
    assert wrong_pass.json()["detail"] == no_user.json()["detail"]


# ==================================================== tokens cannot be forged


def test_a_garbage_token_is_rejected(signed_in):
    assert signed_in.get("/api/demo-cases",
                         headers=auth("not-a-token")).status_code == 401


def test_a_token_signed_with_the_wrong_secret_is_rejected(signed_in, monkeypatch):
    t = token_for(signed_in)
    monkeypatch.setenv("AUDIOSENSE_SECRET", "a-different-secret")
    assert signed_in.get("/api/demo-cases", headers=auth(t)).status_code == 401


def test_tampering_with_the_claims_invalidates_the_signature(signed_in):
    """Re-encoding the payload as another user must not be accepted."""
    t = token_for(signed_in)
    body, signature = t.split(".")
    claims = json.loads(A._unb64(body))
    claims["u"] = "root"
    forged = A._b64(json.dumps(claims, separators=(",", ":")).encode()) + "." + signature
    assert A.read_token(forged) is None
    assert signed_in.get("/api/demo-cases", headers=auth(forged)).status_code == 401


def test_an_unsigned_token_is_rejected(signed_in):
    """A token whose signature section is simply dropped or blanked."""
    claims = {"u": "alice", "exp": time.time() + 3600, "n": "x"}
    body = A._b64(json.dumps(claims).encode())
    for forged in (body, f"{body}.", f"{body}.{A._b64(b'')}"):
        assert A.read_token(forged) is None


def test_an_expired_token_is_rejected(signed_in):
    expired, _ = A.issue_token("alice", ttl=-1)
    assert A.read_token(expired) is None
    assert signed_in.get("/api/demo-cases", headers=auth(expired)).status_code == 401


def test_a_token_for_a_deleted_account_stops_working(signed_in, monkeypatch):
    """Removing someone from the environment must end their session."""
    t = token_for(signed_in)
    assert signed_in.get("/api/demo-cases", headers=auth(t)).status_code == 200
    monkeypatch.setenv("AUDIOSENSE_USERS", f"bob:{HASH}")
    assert signed_in.get("/api/demo-cases", headers=auth(t)).status_code == 401


@pytest.mark.parametrize("header", [
    "", "Bearer", "Basic YWxpY2U6cA==", "Token abc", "bearer",
])
def test_malformed_authorization_headers_are_rejected(signed_in, header):
    r = signed_in.get("/api/demo-cases", headers={"Authorization": header})
    assert r.status_code == 401


# ======================================================== it fails closed


def test_with_no_accounts_configured_nothing_is_reachable(no_accounts):
    """The critical property: misconfiguration must lock, never unlock."""
    assert no_accounts.get("/api/demo-cases").status_code == 503
    assert no_accounts.get("/api/records/patients").status_code == 503


def test_with_no_accounts_configured_login_is_refused(no_accounts):
    r = no_accounts.post("/api/auth/login",
                         json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 503
    assert "no accounts" in r.json()["detail"].lower()


def test_no_account_exists_by_default(monkeypatch):
    """There must be no built-in username and no default password."""
    monkeypatch.delenv("AUDIOSENSE_USERS", raising=False)
    assert A.load_users() == {}
    assert A.auth_enabled() is False
    assert A.authenticate("admin", "admin") is None
    assert A.authenticate("audiosense", "audiosense") is None


@pytest.mark.parametrize("value", [
    "", "   ", "alice", "alice:", ":hash", "alice:plaintext",
    "alice:md5$x$y$z", ",,,", "alice:pbkdf2_sha512$1$a$b",
])
def test_malformed_user_configuration_yields_no_accounts(monkeypatch, value):
    """A broken entry must not become an account with an unknown password."""
    monkeypatch.setenv("AUDIOSENSE_USERS", value)
    assert A.load_users() == {}


def test_a_valid_entry_survives_a_broken_neighbour(monkeypatch):
    monkeypatch.setenv("AUDIOSENSE_USERS", f"broken,alice:{HASH}")
    assert list(A.load_users()) == ["alice"]


# ============================================== what stays deliberately open


@pytest.mark.parametrize("path", [
    "/api/health",
    "/api/auth/status",
    "/api/verify/deadbeefdeadbeef",
])
def test_the_documented_public_paths_answer_without_a_token(signed_in, path):
    assert signed_in.get(path).status_code == 200


def test_the_public_list_does_not_shadow_a_protected_route(signed_in):
    """Every public prefix must be specific enough to cover nothing else."""
    protected = {r.path for r in app.routes
                 if getattr(r, "methods", None) and r.path.startswith("/api/")}
    for path in protected:
        if A.is_public(path):
            assert any(path.startswith(p) for p in (
                "/api/health", "/api/auth/login", "/api/auth/status",
                "/api/handout/", "/api/verify/", "/api/qr",
                "/api/otoscopy/image/")), path


# ================================================== password hashing itself


def test_the_same_password_hashes_differently_every_time():
    """A shared salt would let one cracked hash reveal every reused password."""
    assert A.hash_password("x", rounds=1) != A.hash_password("x", rounds=1)


def test_a_hash_verifies_only_against_its_own_password():
    encoded = A.hash_password("the right one", rounds=1)
    assert A.verify_password("the right one", encoded) is True
    assert A.verify_password("the wrong one", encoded) is False
    assert A.verify_password("", encoded) is False


@pytest.mark.parametrize("encoded", [
    "", "garbage", "pbkdf2_sha256$notanumber$a$b", "pbkdf2_sha256$1$a",
    "$$$", "pbkdf2_sha256$1$!!!$!!!",
])
def test_a_malformed_hash_never_verifies(encoded):
    assert A.verify_password("anything", encoded) is False


def test_an_empty_password_cannot_be_hashed():
    with pytest.raises(ValueError):
        A.hash_password("")


def test_the_production_work_factor_meets_the_owasp_floor():
    assert A.PBKDF2_ROUNDS >= 600_000


def test_the_stored_hash_does_not_contain_the_password():
    encoded = A.hash_password("hunter2hunter2", rounds=1)
    assert "hunter2" not in encoded


# ====================================================== brute-force throttle


def test_repeated_failures_start_being_throttled(signed_in):
    A._failures.clear()
    for _ in range(A.MAX_FAILURES):
        signed_in.post("/api/auth/login",
                       json={"username": "alice", "password": "wrong"})
    r = signed_in.post("/api/auth/login",
                       json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 429
    A._failures.clear()


def test_a_successful_login_clears_the_failure_count(signed_in):
    A._failures.clear()
    for _ in range(A.MAX_FAILURES - 1):
        signed_in.post("/api/auth/login",
                       json={"username": "alice", "password": "wrong"})
    assert signed_in.post("/api/auth/login",
                          json={"username": "alice",
                                "password": PASSWORD}).status_code == 200
    assert A.throttled("testclient", "alice") is None


# ============================================================ the secret


def test_no_signing_secret_is_hardcoded(monkeypatch):
    """Two processes with no configured secret must not share a key."""
    monkeypatch.delenv("AUDIOSENSE_SECRET", raising=False)
    A._EPHEMERAL_SECRET = None
    first = A._secret()
    A._EPHEMERAL_SECRET = None
    second = A._secret()
    assert first != second
    assert len(first) >= 32


# ================================= the three modes, and which one is default

# The app can run protected (accounts configured), anonymous (explicitly opted
# out, for local development), or locked (nothing configured). Which one a
# blank environment produces is the whole safety property: an operator who
# deploys and forgets must get an instance nobody can use, not one anybody can.


def test_a_blank_environment_locks_rather_than_opens(monkeypatch):
    monkeypatch.delenv("AUDIOSENSE_USERS", raising=False)
    monkeypatch.delenv("AUDIOSENSE_ALLOW_ANONYMOUS", raising=False)
    assert A.mode() == "locked"
    assert A.anonymous_allowed() is False


def test_anonymous_access_requires_an_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("AUDIOSENSE_USERS", raising=False)
    for value in ("", "0", "false", "no", "off", "maybe"):
        monkeypatch.setenv("AUDIOSENSE_ALLOW_ANONYMOUS", value)
        assert A.anonymous_allowed() is False, value
    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("AUDIOSENSE_ALLOW_ANONYMOUS", value)
        assert A.anonymous_allowed() is True, value


def test_configured_accounts_override_the_anonymous_opt_out(monkeypatch):
    """Setting both is a contradiction; the stricter reading has to win."""
    monkeypatch.setenv("AUDIOSENSE_ALLOW_ANONYMOUS", "1")
    monkeypatch.setenv("AUDIOSENSE_USERS", f"alice:{HASH}")
    assert A.anonymous_allowed() is False
    assert A.mode() == "protected"


def test_an_instance_with_both_set_still_demands_a_token(monkeypatch):
    monkeypatch.setenv("AUDIOSENSE_ALLOW_ANONYMOUS", "1")
    monkeypatch.setenv("AUDIOSENSE_USERS", f"alice:{HASH}")
    monkeypatch.setenv("AUDIOSENSE_SECRET", "test-secret-not-a-real-one")
    A._failures.clear()
    with TestClient(app) as c:
        assert c.get("/api/records/patients").status_code == 401


def test_anonymous_mode_serves_the_app(monkeypatch):
    """The local-development path has to actually work, or nobody will use it."""
    monkeypatch.delenv("AUDIOSENSE_USERS", raising=False)
    monkeypatch.setenv("AUDIOSENSE_ALLOW_ANONYMOUS", "1")
    with TestClient(app) as c:
        assert c.get("/api/demo-cases").status_code == 200
        assert c.get("/api/auth/status").json()["mode"] == "anonymous"


def test_status_names_the_mode_so_the_operator_can_see_it(monkeypatch):
    monkeypatch.delenv("AUDIOSENSE_USERS", raising=False)
    monkeypatch.delenv("AUDIOSENSE_ALLOW_ANONYMOUS", raising=False)
    with TestClient(app) as c:
        body = c.get("/api/auth/status").json()
        assert body["mode"] == "locked"
        assert body["auth_required"] is False
        assert "AUDIOSENSE_USERS" in body["note"]


# ============================ the bypasses a penetration test actually tried

# These are regression tests for findings, not speculation. Each one was a real
# request that got further than it should have.


@pytest.mark.parametrize("path", [
    "//api/records/patients",          # leading double slash walked past the guard
    "///api/records/patients",
    "/api//records/patients",
    "/api/records/patients/",
    "//api//records//patients//",
])
def test_slash_tricks_do_not_walk_past_the_guard(signed_in, path):
    """The old guard was `not startswith("/api/")`, which `//api/` defeats."""
    assert signed_in.get(path).status_code in (401, 404)
    assert A.is_public(path) is False


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_schema_is_not_published_to_strangers(signed_in, path):
    """It lists every route and every request shape — a map for an attacker."""
    assert signed_in.get(path).status_code == 401


def test_the_banner_does_not_publish_the_cors_allowlist(signed_in):
    """Which origins are trusted with credentials is not public information."""
    r = signed_in.get("/")
    assert r.status_code == 200
    assert "allowed_origins" not in r.json()
    assert "origin_regex" not in r.json()


def test_the_qr_route_is_matched_exactly_not_as_a_prefix():
    """A bare prefix would make a future /api/qr-history public by accident."""
    assert A.is_public("/api/qr") is True
    assert A.is_public("/api/qr-history") is False
    assert A.is_public("/api/qrcodes/secret") is False


def test_prefix_entries_still_cover_their_children():
    assert A.is_public("/api/handout/abc123") is True
    assert A.is_public("/api/verify/abc123") is True
    assert A.is_public("/api/otoscopy/image/normal/a.jpg") is True
    # ...but not their siblings
    assert A.is_public("/api/otoscopy/analyze") is False
    assert A.is_public("/api/handout") is False


def test_everything_not_allowlisted_is_protected(signed_in):
    """The property the allowlist exists to guarantee, checked over all routes."""
    for route in app.routes:
        path = getattr(route, "path", "")
        if not getattr(route, "methods", None) or A.is_public(path):
            continue
        probe = path.replace("{h}", "x").replace("{patient_id}", "1") \
                    .replace("{label}", "a").replace("{filename}", "b.jpg")
        if "{" in probe:
            continue
        if "GET" in route.methods:
            assert signed_in.get(probe).status_code == 401, probe


def test_normalise_collapses_runs_of_slashes_and_the_trailing_one():
    """Pins the slash-collapsing loop itself.

    The parametrised cases above assert only that odd paths are REFUSED, and
    they hold whether or not normalisation runs — the allowlist is deny-by-
    default, so breaking normalisation makes more paths fail, never fewer.
    Deleting the loop left every one of them green.
    """
    assert A.normalise("//api//records//patients//") == "/api/records/patients"
    assert A.normalise("///api/health") == "/api/health"
    assert A.normalise("/api/records/patients/") == "/api/records/patients"
    assert A.normalise("/") == "/"      # the root must survive the rstrip
    assert A.normalise("//") == "/"


def test_a_doubled_slash_does_not_lock_out_an_uptime_probe():
    """The direction normalisation actually changes: allowed, not refused."""
    assert A.is_public("//api/health") is True
    assert A.is_public("/api/health/") is True
    assert A.is_public("///api//health//") is True


# ------------------------------------------- the throttle bucket itself ----
#
# The bucket IS the brute-force control, so it must not be derived from
# anything the caller writes. X-Forwarded-For used to be honoured from any
# peer, which broke it in both directions at once.


def _fail(client, username="alice", times=1, headers=None):
    r = None
    for _ in range(times):
        r = client.post("/api/auth/login",
                        json={"username": username, "password": "wrong"},
                        headers=headers or {})
    return r


def test_rotating_x_forwarded_for_does_not_buy_extra_guesses(signed_in):
    """Twenty guesses behind twenty fake addresses must still hit the wall."""
    A._failures.clear()
    codes = [signed_in.post("/api/auth/login",
                            json={"username": "alice", "password": f"guess{i}"},
                            headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
             for i in range(20)]
    assert 429 in codes, "the header was allowed to reset the throttle bucket"
    assert codes.index(429) <= A.MAX_FAILURES
    A._failures.clear()


def test_a_stranger_cannot_aim_failures_at_someone_elses_bucket(signed_in):
    """The same hole in the other direction: locking a clinician out.

    Eight failures carrying the victim's address as X-Forwarded-For used to
    fill the VICTIM's bucket, so their correct password came back 429. The
    property is that the header no longer selects the bucket at all — the
    failures must land on the attacker's own socket address.

    TestClient gives every request the peer "testclient", so the assertion is
    made on the bucket table rather than on a second connection: nothing may
    be recorded against the address the attacker named.
    """
    A._failures.clear()
    _fail(signed_in, times=A.MAX_FAILURES + 2,
          headers={"X-Forwarded-For": "203.0.113.44"})
    assert A.throttled("203.0.113.44", "alice") is None, (
        "a caller-supplied header decided whose bucket filled up")
    assert any(bucket[0] == "testclient" for bucket in A._failures), (
        "the failures should be recorded against the real peer")
    A._failures.clear()


class _Req:
    def __init__(self, headers, host="198.51.100.7"):
        self.headers = headers
        self.client = type("C", (), {"host": host})()


def test_an_untrusted_peer_cannot_choose_its_own_bucket():
    """_client falls back to the socket address unless the peer is declared."""
    from app.routers import auth_router as R
    assert R._client(_Req({"x-forwarded-for": "1.2.3.4"})) == "198.51.100.7"
    assert R._client(_Req({})) == "198.51.100.7"


def test_a_declared_proxy_is_believed_from_the_right_of_the_chain(monkeypatch):
    """Behind a real ingress the socket address is the proxy's, shared by all.

    The rightmost entry is the one the trusted proxy appended; the leftmost is
    whatever the client wrote, so only the rightmost may be believed.
    """
    import importlib

    from app.routers import auth_router as R
    monkeypatch.setenv("AUDIOSENSE_TRUSTED_PROXIES", "10.1.1.1")
    R = importlib.reload(R)
    try:
        # Client forged "1.2.3.4"; the proxy appended the real address after it.
        assert R._client(_Req({"x-forwarded-for": "1.2.3.4, 203.0.113.9"},
                              "10.1.1.1")) == "203.0.113.9"
        # A peer that is not the declared proxy is still not believed.
        assert R._client(_Req({"x-forwarded-for": "1.2.3.4"},
                              "198.51.100.7")) == "198.51.100.7"
    finally:
        monkeypatch.delenv("AUDIOSENSE_TRUSTED_PROXIES", raising=False)
        importlib.reload(R)


def test_one_locked_account_does_not_lock_the_whole_clinic(signed_in):
    """A practice behind one NAT egress shares an address, not a lockout."""
    A._failures.clear()
    _fail(signed_in, username="alice", times=A.MAX_FAILURES + 1)
    assert A.throttled("testclient", "alice") is not None
    assert A.throttled("testclient", "bob") is None
    A._failures.clear()


def test_an_elapsed_lockout_starts_the_count_over(monkeypatch):
    """Otherwise one failed attempt per window holds an account shut forever."""
    A._failures.clear()
    for _ in range(A.MAX_FAILURES):
        A._record_failure("1.2.3.4", "alice")
    assert A.throttled("1.2.3.4", "alice") is not None

    later = time.time() + A.LOCKOUT_SECONDS + 1
    monkeypatch.setattr(A.time, "time", lambda: later)
    assert A.throttled("1.2.3.4", "alice") is None
    A._record_failure("1.2.3.4", "alice")
    assert A.throttled("1.2.3.4", "alice") is None, (
        "the count carried over, so one attempt per window renews the lockout")
    A._failures.clear()


def test_the_failure_table_does_not_grow_without_bound():
    A._failures.clear()
    for i in range(A._MAX_BUCKETS + 500):
        A._record_failure(f"10.0.{i // 256}.{i % 256}", "alice")
    assert len(A._failures) <= A._MAX_BUCKETS
    A._failures.clear()


# ---------------------------------------------------- session lifetime ----


def test_session_hours_is_read_at_call_time_not_at_import(monkeypatch):
    """backend/.env is loaded after this module is imported.

    A constant computed at import froze at the 12-hour default, so the one
    setting an operator was told to put in .env was the one .env could not
    reach — and /api/auth/status confirmed the stale value.
    """
    monkeypatch.setenv("AUDIOSENSE_SESSION_HOURS", "1")
    assert A.token_ttl_seconds() == 3600
    monkeypatch.setenv("AUDIOSENSE_SESSION_HOURS", "8")
    assert A.token_ttl_seconds() == 8 * 3600


def test_a_malformed_session_length_falls_back_instead_of_crashing(monkeypatch):
    """A typo in .env must not take the whole app down at startup."""
    for bad in ("abc", "", "-4", "0"):
        monkeypatch.setenv("AUDIOSENSE_SESSION_HOURS", bad)
        assert A.token_ttl_seconds() == int(A.DEFAULT_SESSION_HOURS * 3600)


def test_the_issued_token_and_the_status_route_agree_on_the_lifetime(monkeypatch):
    monkeypatch.setenv("AUDIOSENSE_SESSION_HOURS", "2")
    monkeypatch.setenv("AUDIOSENSE_USERS", f"alice:{HASH}")
    monkeypatch.setenv("AUDIOSENSE_SECRET", "test-secret-not-a-real-one")
    monkeypatch.delenv("AUDIOSENSE_ALLOW_ANONYMOUS", raising=False)
    A._failures.clear()
    with TestClient(app) as c:
        assert c.get("/api/auth/status").json()["session_hours"] == 2
        body = c.post("/api/auth/login",
                      json={"username": "alice", "password": PASSWORD}).json()
        assert body["expires_in"] == 2 * 3600
        claims = json.loads(A._unb64(body["token"].split(".")[0]))
        assert abs(claims["exp"] - (time.time() + 2 * 3600)) < 60
