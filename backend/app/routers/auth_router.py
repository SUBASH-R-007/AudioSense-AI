"""Login, and the middleware that makes every other route require it."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services import auth as A

router = APIRouter(prefix="/api/auth")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


#: Peer addresses whose ``X-Forwarded-For`` may be believed, comma-separated.
#: Empty by default: unset means "nothing trusted sits in front of us", and the
#: socket address is then the only identity a caller cannot choose.
_TRUSTED_PROXIES = frozenset(
    p.strip() for p in os.environ.get("AUDIOSENSE_TRUSTED_PROXIES", "").split(",")
    if p.strip())


def _client(request: Request) -> str:
    """Client identity for throttling.

    The throttle bucket IS the brute-force control, so it must never be
    derived from something the caller writes. ``X-Forwarded-For`` is caller-
    supplied: honouring it unconditionally let an attacker rotate the header to
    get unlimited guesses, and — the same hole in the other direction — aim
    failures at somebody else's bucket to lock them out.

    So the header is read only when the request actually arrived from a proxy
    the operator declared, and then from the RIGHT of the chain: the rightmost
    entry is the one that trusted proxy appended itself, whereas the leftmost
    is whatever the client sent. Behind a platform ingress, set
    ``AUDIOSENSE_TRUSTED_PROXIES`` to its address; otherwise every request
    would share the proxy's single bucket.
    """
    peer = request.client.host if request.client else "-"
    if peer in _TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip() or peer
    return peer


@router.get("/status")
def status():
    """Whether this instance requires a login. Safe to call unauthenticated.

    The frontend needs to know whether to show a login screen before it has
    anyone to authenticate, and a developer running locally with no accounts
    configured needs to be told why nothing works.
    """
    return {
        "auth_required": A.auth_enabled(),
        "mode": A.mode(),
        "session_hours": A.token_ttl_seconds() // 3600,
        "note": (
            "Sign in with the credentials issued for this instance."
            if A.auth_enabled() else
            "Running without authentication — local development only. Never "
            "deploy in this mode."
            if A.anonymous_allowed() else
            "This instance is locked: no accounts are configured. Set "
            "AUDIOSENSE_USERS to enable sign-in."),
    }


@router.post("/login")
def login(req: LoginRequest, request: Request):
    """Exchange a username and password for a session token."""
    client = _client(request)

    wait = A.throttled(client, req.username)
    if wait is not None:
        raise HTTPException(
            429, f"Too many failed attempts. Try again in {wait} seconds.")

    if not A.auth_enabled():
        # Fail closed, and say why — an operator staring at a login box that
        # rejects everything needs to know it is configuration, not their
        # password.
        raise HTTPException(
            503, "No accounts are configured on this instance. Set "
                 "AUDIOSENSE_USERS before anyone can sign in.")

    token = A.authenticate(req.username, req.password, client)
    if not token:
        # One message for both "no such user" and "wrong password", so the
        # response cannot be used to find out who has an account.
        raise HTTPException(401, "Incorrect username or password.")

    return {"token": token, "username": req.username,
            "expires_in": A.token_ttl_seconds()}


@router.get("/me")
def me(request: Request):
    """Confirm a token is still good — used on page load to restore a session."""
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(401, "Not signed in.")
    return {"username": username}


async def require_auth(request: Request, call_next):
    """Reject anything that is not public and not carrying a valid token.

    This is middleware rather than a per-route dependency on purpose. There are
    twenty routers and sixty-odd routes; a dependency has to be remembered on
    every new one, and the failure mode of forgetting is an endpoint that
    silently serves patient data to the world. Here the default is closed and a
    new route is protected the moment it is registered.
    """
    path = request.url.path

    # CORS preflight carries no credentials by design and must be answered
    # before the browser will send the real, authenticated request.
    #
    # Everything else is protected unless it is on the allowlist — including
    # /docs, /redoc and /openapi.json, which publish the whole route table and
    # every request schema. Exempting non-/api paths instead would have made
    # that disclosure the default, and would have let a leading double slash
    # walk straight past the guard.
    if request.method == "OPTIONS" or A.is_public(path):
        return await call_next(request)

    # Local development and the test suite opt out explicitly; a deployment
    # that simply forgot to configure anything does not, and gets a locked
    # instance rather than an open one.
    if A.anonymous_allowed():
        return await call_next(request)

    if not A.auth_enabled():
        return JSONResponse(
            {"detail": "This instance is locked: no accounts are configured. "
                       "Set AUDIOSENSE_USERS to enable sign-in."},
            status_code=503)

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    username = A.read_token(token) if scheme.lower() == "bearer" else None
    if not username:
        return JSONResponse(
            {"detail": "Sign in to use this instance."},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"})

    request.state.username = username
    return await call_next(request)
