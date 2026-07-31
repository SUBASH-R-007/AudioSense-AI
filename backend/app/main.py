"""AudioSense AI — FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    batch,
    clinic,
    core,
    digitize,
    feedback,
    handout,
    pdf_router,
    progression_router,
    report_router,
    settings,
    validation_router,
)

app = FastAPI(
    title="AudioSense AI",
    description="AI-powered Pure Tone Audiometry interpretation platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (core, digitize, report_router, progression_router, batch,
          pdf_router, settings, feedback, handout, clinic, validation_router):
    app.include_router(r.router)
