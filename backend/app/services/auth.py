"""Username and password protection for a deployed instance.

Until now every endpoint was anonymous. That is defensible for a laptop demo
and indefensible the moment the container has a public hostname: the record
store hands out every patient's name, age, sex and occupation to anyone who
asks, and the AI settings route lets a stranger point the instance at their own
LLM endpoint and start receiving patient data.

DESIGN CONSTRAINTS, and why this looks the way it does.

  STDLIB ONLY. The image is already near a gigabyte and the deploy targets are
  free tiers. ``hashlib``, ``hmac`` and ``secrets`` give PBKDF2-HMAC-SHA256 and
  constant-time comparison, which is what this needs. No new dependency.

  NO USER TABLE. ``records.py`` has no owner column and adding one properly is
  a migration, a tenant model and an admin UI — the work described in
  SCALING.md, not a login box. Users therefore come from the environment, which
  a container host already knows how to inject as a secret.

  STATELESS TOKENS. Two replicas must accept each other's sessions without a
  shared session store, so a token is an HMAC over its own claims. The cost is
  that logout cannot revoke server-side; the mitigation is a short lifetime and
  a secret that can be rotated to invalidate everything at once.

IT FAILS CLOSED. This is the property that matters most. If ``AUDIOSENSE_USERS``
is unset or unparseable there are no accounts, and with no accounts every login
attempt is rejected — the app does not fall back to open access, and it does
not invent a default password. An instance nobody can log into is a bad day; an
instance anybody can log into is a notifiable incident.

Passwords are never logged, never returned, and never compared with ``==``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Dict, Optional, Tuple

#: PBKDF2 work factor. OWASP's 2023 floor for PBKDF2-HMAC-SHA256 is 600,000;
#: this sits above it and still verifies in well under a second on the free
#: tiers this deploys to.
PBKDF2_ROUNDS = 600_000
SALT_BYTES = 16

#: Default session length in hours. Short, because tokens cannot be revoked
#: individually — a stolen one stays valid until it expires or the secret is
#: rotated. A clinic session is an afternoon, not a fortnight.
DEFAULT_SESSION_HOURS = 12.0


def token_ttl_seconds() -> int:
    """Session lifetime, read at call time rather than at import.

    This has to be lazy. ``backend/.env`` is loaded by ``app.main``, which
    imports the routers — and therefore this module — before the loader runs,
    so a constant computed at import would freeze at the default and silently
    ignore the one file the operator was told to configure. Every other
    setting here (accounts, signing secret) is already read lazily; this was
    the single exception, and shortening a session is exactly the mitigation
    the no-revocation note above points at.

    A malformed value falls back to the default instead of raising, which
    would otherwise take the whole app down at startup.
    """
    raw = os.environ.get("AUDIOSENSE_SESSION_HOURS")
    try:
        hours = float(raw) if raw not in (None, "") else DEFAULT_SESSION_HOURS
    except ValueError:
        hours = DEFAULT_SESSION_HOURS
    if hours <= 0:
        hours = DEFAULT_SESSION_HOURS
    return max(1, int(hours * 3600))

#: Failed logins tolerated from one address before it is made to wait. This is
#: a speed bump against credential stuffing, not a substitute for a WAF.
MAX_FAILURES = 8
LOCKOUT_SECONDS = 300

_ENV_USERS = "AUDIOSENSE_USERS"
_ENV_SECRET = "AUDIOSENSE_SECRET"


# ==========================================================================
# Password hashing
# ==========================================================================


def hash_password(password: str, *, salt: Optional[bytes] = None,
                  rounds: int = PBKDF2_ROUNDS) -> str:
    """Hash a password into the ``pbkdf2_sha256$rounds$salt$digest`` form.

    Used by ``scripts/make_user.py`` to mint the value an operator pastes into
    the environment. The plaintext never leaves this function.
    """
    if not password:
        raise ValueError("refusing to hash an empty password")
    salt = salt or secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return "$".join([
        "pbkdf2_sha256", str(rounds),
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    ])


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check of a password against a stored hash.

    Returns False for anything malformed rather than raising: a corrupted
    entry in the environment must not become a stack trace on the login route,
    and it must certainly not become a successful login.
    """
    try:
        scheme, rounds, salt_b64, digest_b64 = encoded.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"),
            base64.b64decode(salt_b64), int(rounds))
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


# ==========================================================================
# Accounts, from the environment
# ==========================================================================


def load_users() -> Dict[str, str]:
    """Parse ``AUDIOSENSE_USERS`` into ``{username: password_hash}``.

    Format, one account per comma-separated entry::

        alice:pbkdf2_sha256$600000$c2FsdA==$ZGlnZXN0,bob:pbkdf2_sha256$...

    A malformed entry is dropped rather than guessed at. Dropping the only
    entry leaves no accounts, which locks the instance — the correct direction
    to fail.
    """
    raw = os.environ.get(_ENV_USERS, "").strip()
    users: Dict[str, str] = {}
    if not raw:
        return users
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name, _, encoded = entry.partition(":")
        name, encoded = name.strip(), encoded.strip()
        # A username without a properly-formed hash is a configuration error,
        # and the safe reading of a configuration error is "no such account".
        if name and encoded.startswith("pbkdf2_sha256$"):
            users[name] = encoded
    return users


def auth_enabled() -> bool:
    """Whether any account exists."""
    return bool(load_users())


def anonymous_allowed() -> bool:
    """Whether this process may serve requests with nobody signed in.

    Requiring a login unconditionally would make a freshly cloned repository
    unusable and would break every existing test, so there is an opt-out — but
    it is an EXPLICIT one, and it is deliberately not the default. An operator
    who deploys without configuring anything gets an instance that refuses
    every request, which is a support call. The alternative default would be an
    instance that serves patient records to the internet, which is a breach.

    Configuring accounts wins over the opt-out. Setting both is a contradiction,
    and the safe reading of a contradiction is the stricter one.
    """
    if auth_enabled():
        return False
    return os.environ.get("AUDIOSENSE_ALLOW_ANONYMOUS", "").strip().lower() in (
        "1", "true", "yes", "on")


def mode() -> str:
    """``protected`` | ``anonymous`` | ``locked`` — for startup logging."""
    if auth_enabled():
        return "protected"
    return "anonymous" if anonymous_allowed() else "locked"


# ==========================================================================
# Tokens
# ==========================================================================


def _secret() -> bytes:
    """The signing key.

    Taken from the environment where one is configured. Where it is not, a
    random key is generated for the life of the process: sessions then die on
    restart and do not survive across replicas, which is inconvenient and
    safe. The alternative — a constant baked into the source — would let anyone
    holding the repository mint a valid session for every deployment of it.
    """
    configured = os.environ.get(_ENV_SECRET, "").strip()
    if configured:
        return configured.encode("utf-8")
    global _EPHEMERAL_SECRET
    if _EPHEMERAL_SECRET is None:
        _EPHEMERAL_SECRET = secrets.token_bytes(32)
    return _EPHEMERAL_SECRET


_EPHEMERAL_SECRET: Optional[bytes] = None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(username: str, ttl: Optional[int] = None) -> Tuple[str, int]:
    """Mint a signed session token. Returns ``(token, expires_at_epoch)``.

    ``ttl`` defaults at call time, not in the signature — a default argument is
    evaluated once at import and would reintroduce the freeze this avoids.
    """
    ttl = token_ttl_seconds() if ttl is None else ttl
    expires = int(time.time()) + ttl
    claims = {"u": username, "exp": expires, "n": secrets.token_hex(8)}
    body = _b64(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}", expires


def read_token(token: str) -> Optional[str]:
    """Return the username a token belongs to, or None if it is not valid.

    Checks the signature before it trusts anything inside the token, compares
    it in constant time, and re-checks that the account still exists — so
    removing a user from the environment and restarting ends their sessions
    even though the token itself has not expired.
    """
    try:
        body, signature = (token or "").split(".")
        expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(signature), expected):
            return None
        claims = json.loads(_unb64(body))
    except Exception:
        return None
    if not isinstance(claims, dict) or claims.get("exp", 0) < time.time():
        return None
    username = claims.get("u")
    if not isinstance(username, str) or username not in load_users():
        return None
    return username


# ==========================================================================
# Login
# ==========================================================================

#: bucket -> (failure count, moment the lockout lifts). In-process only, so it
#: resets on restart and is not shared between replicas. It raises the cost of
#: guessing; it does not make guessing impossible.
#:
#: The bucket is (client address, username), not the address alone. Keying on
#: the address by itself has two failure modes that both bite a clinic: an
#: entire practice behind one NAT egress shares a bucket, so eight fat-fingered
#: logins anywhere lock out everybody; and an attacker who can influence the
#: address can push failures into someone else's bucket. Pairing with the
#: username confines a lockout to the one account actually being guessed.
_failures: Dict[Tuple[str, str], Tuple[int, float]] = {}

#: Hard ceiling on distinct buckets held at once, so the dict cannot grow
#: without bound. Well above any real clinic; only a flood reaches it.
_MAX_BUCKETS = 4096


def _bucket(client: str, username: str) -> Tuple[str, str]:
    return (client or "-", username or "")


def _prune(now: float) -> None:
    """Drop buckets whose lockout has lapsed."""
    for key in [k for k, (_, until) in _failures.items() if until <= now]:
        _failures.pop(key, None)


def throttled(client: str, username: str = "") -> Optional[int]:
    """Seconds this client must wait for this account, or None to proceed."""
    now = time.time()
    count, until = _failures.get(_bucket(client, username), (0, 0.0))
    if count >= MAX_FAILURES and now < until:
        return int(until - now) + 1
    return None


def _record_failure(client: str, username: str = "") -> None:
    now = time.time()
    key = _bucket(client, username)
    count, until = _failures.get(key, (0, 0.0))
    # An elapsed window starts the count over. Carrying the old count forward
    # would let one failed attempt every LOCKOUT_SECONDS hold an account shut
    # indefinitely, because the count would never fall back below MAX_FAILURES.
    if until <= now:
        count = 0
    if len(_failures) >= _MAX_BUCKETS and key not in _failures:
        _prune(now)
        if len(_failures) >= _MAX_BUCKETS:
            return  # flooded; the ceiling holds rather than growing memory
    _failures[key] = (count + 1, now + LOCKOUT_SECONDS)


def _clear_failures(client: str, username: str = "") -> None:
    _failures.pop(_bucket(client, username), None)


def authenticate(username: str, password: str, client: str = "-") -> Optional[str]:
    """Check credentials and mint a token, or return None.

    The failure path is deliberately uniform: an unknown username and a wrong
    password take the same route and produce the same answer, so the response
    cannot be used to enumerate who has an account. An unknown username is
    still run through a PBKDF2 verification against a dummy hash so the two
    cases take comparable time.
    """
    users = load_users()
    encoded = users.get(username or "")
    if encoded is None:
        # Spend the same work as a real check would, then fail.
        verify_password(password or "", _DUMMY_HASH)
        _record_failure(client, username)
        return None
    if not verify_password(password or "", encoded):
        _record_failure(client, username)
        return None
    _clear_failures(client, username)
    token, _ = issue_token(username)
    return token


#: A real hash of a value nobody knows, used only to equalise timing on the
#: unknown-username path.
_DUMMY_HASH = hash_password(secrets.token_hex(16), rounds=PBKDF2_ROUNDS)


# ==========================================================================
# What stays reachable without a login
# ==========================================================================

#: Paths that must answer before, or without, a session — each for a stated
#: reason. Everything not matched here requires a valid token.
#:
#: These are exact paths or prefixes; the check is a prefix match, which is why
#: each entry is specific enough that no protected route sits beneath it.
PUBLIC_PATHS = (
    # Uptime probes run before anyone logs in, and it discloses only whether
    # the service is up and whether a model is loaded.
    "/api/health",
    # Logging in cannot itself require being logged in, and the frontend has
    # to discover whether this instance wants a login before it has anyone to
    # log in as. Note /api/auth/me is deliberately NOT here — it exists to
    # validate a token, so it must demand one.
    "/api/auth/login",
    "/api/auth/status",
    # The patient's own counselling sheet, opened by scanning the QR on a
    # printed report. Protecting it would mean handing patients an account.
    "/api/handout/",
    # Report verification, same reasoning: the person holding the printout is
    # checking it is genuine, and they are not a user of this system.
    "/api/verify/",
    # Rendered into an <img>, which cannot carry an Authorization header.
    # Exact — see EXACT_PUBLIC below.
    "/api/qr",
    # Reference atlas photographs. They ship in the repository, contain no
    # patient data, and are likewise loaded as <img>.
    "/api/otoscopy/image/",
)


#: Entries above that are whole paths rather than prefixes. A bare prefix match
#: on "/api/qr" would silently make a future "/api/qr-history" public, so the
#: ones with nothing beneath them are matched exactly.
EXACT_PUBLIC = frozenset({
    "/api/health", "/api/auth/login", "/api/auth/status", "/api/qr",
    # The service banner. Platforms probe it before anything is configured.
    "/",
})


def normalise(path: str) -> str:
    """Collapse repeated slashes and drop a trailing one.

    A guard written as ``path.startswith("/api/")`` is defeated by
    ``//api/records/patients``, which is not an /api path by that test but may
    still route to one depending on how the server normalises. Relying on the
    router to reject it is relying on a property nobody promised, so the check
    is done on a normalised copy instead.
    """
    while "//" in path:
        path = path.replace("//", "/")
    return path if path == "/" else path.rstrip("/")


def is_public(path: str) -> bool:
    """Whether a path may be served without a session.

    An allowlist, deliberately: everything is protected unless it appears here,
    so a route added tomorrow is closed by default rather than open until
    somebody remembers.
    """
    path = normalise(path)
    if path in EXACT_PUBLIC:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PATHS
               if prefix.endswith("/"))
