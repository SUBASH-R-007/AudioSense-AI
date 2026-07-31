"""Runtime AI settings: Offline mode vs API mode with selectable provider.

Persisted to backend/data/ai_config.json (gitignored — contains the key).
Environment variables seed the initial config on first run:
GEMINI_API_KEY / ANTHROPIC_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CONFIG_PATH = DATA_DIR / "ai_config.json"

PROVIDERS = {
    "gemini": {
        "label": "Google Gemini",
        "default_model": "gemini-2.0-flash",
        "needs_key": True,
        "supports_vision": True,
        "free_tier": True,
        "key_hint": "Free key at aistudio.google.com — no card needed",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "default_model": "claude-sonnet-4-6",
        "needs_key": True,
        "supports_vision": True,
        "free_tier": False,
        "key_hint": "Key from console.anthropic.com",
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4o",
        "needs_key": True,
        "supports_vision": True,
        "free_tier": False,
        "key_hint": "Key from platform.openai.com",
    },
    "groq": {
        "label": "Groq",
        "default_model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "needs_key": True,
        "supports_vision": True,
        "free_tier": True,
        "key_hint": "Free key at console.groq.com",
    },
    "openrouter": {
        "label": "OpenRouter",
        "default_model": "google/gemini-2.0-flash-exp:free",
        "needs_key": True,
        "supports_vision": True,
        "free_tier": True,
        "key_hint": "Key at openrouter.ai — free models available",
    },
    "ollama": {
        "label": "Ollama (local)",
        "default_model": "llama3.2",
        "needs_key": False,
        "supports_vision": False,
        "free_tier": True,
        "key_hint": "Local server — set base URL, no key",
    },
}

ENV_SEEDS = [
    ("GEMINI_API_KEY", "gemini"),
    ("ANTHROPIC_API_KEY", "anthropic"),
    ("OPENAI_API_KEY", "openai"),
    ("GROQ_API_KEY", "groq"),
    ("OPENROUTER_API_KEY", "openrouter"),
]


class AIConfig(BaseModel):
    mode: str = "offline"  # "offline" | "api"
    provider: str = "gemini"
    api_key: str = ""
    model: str = ""
    base_url: str = "http://localhost:11434"

    def resolved_model(self) -> str:
        return self.model or PROVIDERS[self.provider]["default_model"]

    def masked(self) -> dict:
        d = self.model_dump()
        if d["api_key"]:
            d["api_key"] = "••••" + d["api_key"][-4:]
        d["model"] = self.resolved_model()
        return d


def load_config() -> AIConfig:
    if CONFIG_PATH.exists():
        try:
            return AIConfig(**json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    cfg = AIConfig()
    for env, provider in ENV_SEEDS:
        key = os.environ.get(env)
        if key:
            cfg = AIConfig(mode="api", provider=provider, api_key=key)
            break
    return cfg


def save_config(cfg: AIConfig) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")


_current: AIConfig | None = None


def get_config() -> AIConfig:
    global _current
    if _current is None:
        _current = load_config()
    return _current


def set_config(cfg: AIConfig) -> AIConfig:
    global _current
    _current = cfg
    save_config(cfg)
    return cfg
