"""Provider-agnostic LLM access over plain REST (httpx, no heavy SDKs).

One call surface for five providers — Gemini, Anthropic, Groq, OpenRouter
(OpenAI-compatible) and Ollama (local). Text and vision. All failures raise
LLMError so callers can fall back to the offline engines.
"""
from __future__ import annotations

import json
import re
import time
from typing import Optional

import httpx

from app.services.ai_config import AIConfig, get_config


class LLMError(RuntimeError):
    pass


#: Providers that speak the OpenAI chat-completions dialect, and the base URL
#: each one serves it from. Adding another is a single line here plus an entry
#: in PROVIDERS — the request and response handling is identical.
OPENAI_COMPATIBLE = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def ai_enabled() -> bool:
    cfg = get_config()
    if cfg.mode != "api":
        return False
    from app.services.ai_config import PROVIDERS

    if PROVIDERS[cfg.provider]["needs_key"] and not cfg.api_key:
        return False
    return True


def call_llm(
    prompt: str,
    system: str = "",
    image_b64: Optional[str] = None,
    image_mime: str = "image/png",
    max_tokens: int = 4096,
    timeout: float = 90.0,
    cfg: Optional[AIConfig] = None,
) -> str:
    """Send one prompt (optionally with an image) to the active provider."""
    cfg = cfg or get_config()
    try:
        if cfg.provider == "gemini":
            return _gemini(cfg, prompt, system, image_b64, image_mime, max_tokens, timeout)
        if cfg.provider == "anthropic":
            return _anthropic(cfg, prompt, system, image_b64, image_mime, max_tokens, timeout)
        if cfg.provider in OPENAI_COMPATIBLE:
            return _openai_style(cfg, prompt, system, image_b64, image_mime, max_tokens, timeout)
        if cfg.provider == "ollama":
            return _ollama(cfg, prompt, system, image_b64, timeout)
    except LLMError:
        raise
    except Exception as exc:  # network, JSON shape, etc.
        raise LLMError(f"{cfg.provider}: {exc}") from exc
    raise LLMError(f"unknown provider {cfg.provider}")


def _gemini(cfg, prompt, system, image_b64, image_mime, max_tokens, timeout) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cfg.resolved_model()}:generateContent"
    )
    parts = [{"text": prompt}]
    if image_b64:
        parts.append({"inline_data": {"mime_type": image_mime, "data": image_b64}})
    body: dict = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    r = httpx.post(url, json=body, timeout=timeout,
                   headers={"x-goog-api-key": cfg.api_key})
    _raise_for_status(r, "gemini")
    data = r.json()
    try:
        return "".join(
            p.get("text", "") for p in data["candidates"][0]["content"]["parts"]
        )
    except (KeyError, IndexError) as exc:
        raise LLMError(f"gemini: unexpected response shape: {data}") from exc


def _anthropic(cfg, prompt, system, image_b64, image_mime, max_tokens, timeout) -> str:
    content: list = [{"type": "text", "text": prompt}]
    if image_b64:
        content.insert(0, {
            "type": "image",
            "source": {"type": "base64", "media_type": image_mime, "data": image_b64},
        })
    body = {
        "model": cfg.resolved_model(),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        body["system"] = system
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        json=body,
        timeout=timeout,
        headers={"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01"},
    )
    _raise_for_status(r, "anthropic")
    return "".join(
        b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text"
    )


def _openai_style(cfg, prompt, system, image_b64, image_mime, max_tokens, timeout) -> str:
    base = OPENAI_COMPATIBLE[cfg.provider]
    if image_b64:
        user_content: object = [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
        ]
    else:
        user_content = prompt
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": user_content}
    ]
    r = httpx.post(
        f"{base}/chat/completions",
        json={"model": cfg.resolved_model(), "messages": messages,
              "max_tokens": max_tokens},
        timeout=timeout,
        headers={"Authorization": f"Bearer {cfg.api_key}"},
    )
    _raise_for_status(r, cfg.provider)
    return r.json()["choices"][0]["message"]["content"]


def _ollama(cfg, prompt, system, image_b64, timeout) -> str:
    msg: dict = {"role": "user", "content": prompt}
    if image_b64:
        msg["images"] = [image_b64]
    messages = ([{"role": "system", "content": system}] if system else []) + [msg]
    r = httpx.post(
        f"{cfg.base_url.rstrip('/')}/api/chat",
        json={"model": cfg.resolved_model(), "messages": messages, "stream": False},
        timeout=timeout,
    )
    _raise_for_status(r, "ollama")
    return r.json()["message"]["content"]


def _raise_for_status(r: httpx.Response, provider: str) -> None:
    if r.status_code >= 400:
        detail = r.text[:300]
        raise LLMError(f"{provider}: HTTP {r.status_code} — {detail}")


def extract_json(text: str) -> dict:
    """Parse a JSON object out of an LLM reply (handles ``` fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("no JSON object in LLM reply")
    return json.loads(text[start : end + 1])


def test_connection(cfg: AIConfig) -> dict:
    """One trivial round-trip to verify the provider settings."""
    t0 = time.perf_counter()
    try:
        reply = call_llm("Reply with exactly: OK", max_tokens=10,
                         timeout=20.0, cfg=cfg)
        ms = round((time.perf_counter() - t0) * 1000)
        return {"ok": True, "latency_ms": ms,
                "message": f"Connected — replied in {ms} ms",
                "reply": reply.strip()[:40]}
    except LLMError as exc:
        return {"ok": False, "latency_ms": None, "message": str(exc)[:300]}
