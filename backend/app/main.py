"""AudioSense AI — FastAPI application entry point.

Local:  uvicorn app.main:app --reload --port 8000
Deploy: uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    batch,
    clinic,
    core,
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (core, digitize, report_router, progression_router, batch,
          pdf_router, settings, feedback, handout, clinic, validation_router,
          listening, otoscopy_router, symptoms_router, instruments,
          linkage_router, speech_router, masking_router):
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
        "allowed_origins": ALLOWED_ORIGINS,
        "origin_regex": ORIGIN_REGEX,
    }
