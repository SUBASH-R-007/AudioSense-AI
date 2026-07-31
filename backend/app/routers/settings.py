"""AI Settings endpoints: Offline <-> API mode toggle, provider config."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ai_config import (
    PROVIDERS,
    AIConfig,
    get_config,
    set_config,
)
from app.services.llm_provider import test_connection

router = APIRouter(prefix="/api/settings")


class AIConfigUpdate(BaseModel):
    mode: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None  # omit to keep the stored key
    model: Optional[str] = None
    base_url: Optional[str] = None


@router.get("/ai")
def get_ai_settings():
    cfg = get_config()
    return {"config": cfg.masked(), "providers": PROVIDERS,
            "active": cfg.mode == "api"}


@router.post("/ai")
def update_ai_settings(update: AIConfigUpdate):
    cfg = get_config()
    data = cfg.model_dump()
    for field in ("mode", "provider", "api_key", "model", "base_url"):
        v = getattr(update, field)
        if v is not None:
            data[field] = v
    if data["mode"] not in ("offline", "api"):
        raise HTTPException(400, "mode must be 'offline' or 'api'")
    if data["provider"] not in PROVIDERS:
        raise HTTPException(400, f"provider must be one of {list(PROVIDERS)}")
    new_cfg = set_config(AIConfig(**data))
    return {"config": new_cfg.masked()}


@router.post("/ai/test")
def test_ai_settings(update: AIConfigUpdate | None = None):
    """Test the stored config, optionally overlaid with unsaved edits."""
    cfg = get_config()
    data = cfg.model_dump()
    if update:
        for field in ("mode", "provider", "api_key", "model", "base_url"):
            v = getattr(update, field)
            if v is not None:
                data[field] = v
    candidate = AIConfig(**data)
    if PROVIDERS[candidate.provider]["needs_key"] and not candidate.api_key:
        return {"ok": False, "message": "No API key configured for this provider"}
    return test_connection(candidate)
