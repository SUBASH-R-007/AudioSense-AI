"""AudioSense AI — FastAPI application entry point.

Local:  uvicorn app.main:app --reload --port 8000
Deploy: uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _load_dotenv() -> None:
    """Read ``backend/.env`` into the environment, if it exists.

    Credentials must not live in a tracked file. The launcher config is
    committed, so an account hash placed there would end up in the repository
    history — and a hash of a short, guessable password is worth cracking. This
    gives local development somewhere gitignored to keep them.

    Real environment variables always win: a deployment sets them properly and
    must never be overridden by a file that happened to be copied into the
    image.

    Called BEFORE the routers are imported. Importing them pulls in every
    service, and anything one of those reads from ``os.environ`` at import time
    would otherwise be fixed before this file was ever opened — which is
    precisely how AUDIOSENSE_SESSION_HOURS came to be silently ignored.
    """
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

from app.routers import (  # noqa: E402  (must follow _load_dotenv)
    aep_router,
    anatomy_router,
    auth_router,
    batch,
    clinic,
    core,
    diagnosis_router,
    digitize,
    feedback,
    handout,
    instruments,
    linkage_router,
    listening,
    masking_router,
    otoscopy_router,
    pdf_router,
    progression_router,
    report_router,
    settings,
    speech_router,
    symptoms_router,
    tuning_fork_router,
    validation_router,
)

app = FastAPI(
    title="AudioSense AI",
    description="AI-powered Pure Tone Audiometry interpretation platform",
    version="1.0.0",
)

# The dev server always works without configuration; deployment adds its own
# origin through CORS_ORIGINS (comma-separated). Vercel gives every branch and
# every pull request its own preview hostname, so CORS_ORIGIN_REGEX exists to
# match those without listing each one.
DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",  # `vite preview`, used to test a production build
]
_configured = [
    o.strip().rstrip("/")
    for o in os.environ.get("CORS_ORIGINS", "").split(",")
    if o.strip()
]
ALLOWED_ORIGINS = DEFAULT_ORIGINS + _configured
ORIGIN_REGEX = os.environ.get("CORS_ORIGIN_REGEX") or None

# Registered before CORS so that CORS wraps it: Starlette runs middleware in
# reverse registration order, and a 401 that is not CORS-wrapped reaches the
# browser as an opaque network failure with no way to tell the user why.
app.middleware("http")(auth_router.require_auth)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    # The session token travels in Authorization, so it has to be allowed
    # through preflight explicitly rather than relying on the wildcard, which
    # browsers ignore once credentials are in play.
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

for r in (core, auth_router, aep_router, anatomy_router, digitize, report_router, progression_router, batch,
          pdf_router, settings, feedback, handout, clinic, validation_router,
          listening, otoscopy_router, symptoms_router, instruments,
          linkage_router, speech_router, masking_router,
          tuning_fork_router, diagnosis_router):
    app.include_router(r.router)


@app.get("/")
def root():
    """Service banner — also the platform health check target."""
    from app.ml.classifier import model_available

    return {
        "service": "AudioSense AI",
        "status": "ok",
        "docs": "/docs",
        "health": "/api/health",
        "model_trained": model_available(),
        # The CORS allowlist used to be published here. It tells an attacker
        # exactly which origins are trusted with credentials, which is a map of
        # where to aim, and it helps nobody who is not already an operator.
    }
