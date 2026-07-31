"""Provider routing: every backend reaches the right endpoint.

These never touch the network. httpx.post is replaced with a recorder, so
the tests pin the URL, headers and body shape each provider receives —
the part that silently breaks when a provider is added.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import llm_provider
from app.services.ai_config import PROVIDERS, AIConfig
from app.services.llm_provider import OPENAI_COMPATIBLE, call_llm

client = TestClient(app)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def recorder(monkeypatch):
    """Capture the outbound request instead of making it."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse({
            # Shapes for every dialect; each provider reads only its own.
            "choices": [{"message": {"content": "OK"}}],
            "content": [{"type": "text", "text": "OK"}],
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
            "message": {"content": "OK"},
        })

    monkeypatch.setattr(llm_provider.httpx, "post", fake_post)
    return calls


# ------------------------------------------------------------- registry ---

def test_openai_is_registered_as_a_provider():
    assert "openai" in PROVIDERS
    p = PROVIDERS["openai"]
    assert p["label"] == "OpenAI"
    assert p["needs_key"] is True
    assert p["supports_vision"] is True
    assert p["free_tier"] is False       # OpenAI has no free tier — say so
    assert p["default_model"]


def test_every_provider_entry_is_complete():
    required = {"label", "default_model", "needs_key", "supports_vision",
                "free_tier", "key_hint"}
    for name, p in PROVIDERS.items():
        assert required <= set(p), f"{name} is missing {required - set(p)}"


def test_openai_compatible_providers_are_all_registered():
    for name in OPENAI_COMPATIBLE:
        assert name in PROVIDERS, f"{name} routes but is not offered in settings"


def _isolate_env(monkeypatch):
    import app.services.ai_config as ai_config
    for env, _ in ai_config.ENV_SEEDS:
        monkeypatch.delenv(env, raising=False)


def test_openai_key_in_the_environment_seeds_api_mode(tmp_path, monkeypatch):
    """An exported OPENAI_API_KEY turns API mode on without any UI step."""
    import app.services.ai_config as ai_config
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    _isolate_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")

    cfg = ai_config.load_config()
    assert cfg.mode == "api"
    assert cfg.provider == "openai"
    assert cfg.api_key == "sk-from-env"


def test_no_provider_keys_means_offline(tmp_path, monkeypatch):
    import app.services.ai_config as ai_config
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    _isolate_env(monkeypatch)

    cfg = ai_config.load_config()
    assert cfg.mode == "offline"
    assert cfg.api_key == ""


def test_a_saved_config_beats_the_environment(tmp_path, monkeypatch):
    """An explicit UI choice must not be overridden by a stray env var."""
    import app.services.ai_config as ai_config
    path = tmp_path / "ai_config.json"
    monkeypatch.setattr(ai_config, "CONFIG_PATH", path)
    _isolate_env(monkeypatch)
    path.write_text(ai_config.AIConfig(mode="offline").model_dump_json(),
                    encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")

    assert ai_config.load_config().mode == "offline"


def test_settings_endpoint_offers_openai():
    providers = client.get("/api/settings/ai").json()["providers"]
    assert "openai" in providers
    assert providers["openai"]["label"] == "OpenAI"


def test_openai_can_be_selected_and_persisted(tmp_path, monkeypatch):
    import app.services.ai_config as ai_config
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    monkeypatch.setattr(ai_config, "_current", None)

    body = client.post("/api/settings/ai", json={
        "mode": "api", "provider": "openai", "api_key": "sk-test-1234",
    }).json()
    assert body["config"]["provider"] == "openai"
    assert body["config"]["api_key"] == "••••1234"        # never echoed raw
    assert body["config"]["model"] == PROVIDERS["openai"]["default_model"]

    monkeypatch.setattr(ai_config, "_current", None)
    assert client.get("/api/settings/ai").json()["config"]["provider"] == "openai"
    client.post("/api/settings/ai", json={"mode": "offline", "api_key": ""})


# -------------------------------------------------------------- routing ---

@pytest.mark.parametrize("provider,expected_base", list(OPENAI_COMPATIBLE.items()))
def test_openai_dialect_providers_hit_their_own_endpoint(provider, expected_base, recorder):
    cfg = AIConfig(mode="api", provider=provider, api_key="k-123")
    assert call_llm("hello", cfg=cfg) == "OK"

    call = recorder[0]
    assert call["url"] == f"{expected_base}/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer k-123"
    assert call["json"]["model"] == PROVIDERS[provider]["default_model"]
    assert call["json"]["messages"][-1]["content"] == "hello"


def test_openai_sends_images_as_data_urls(recorder):
    cfg = AIConfig(mode="api", provider="openai", api_key="k")
    call_llm("read this", image_b64="QUJD", image_mime="image/png", cfg=cfg)
    content = recorder[0]["json"]["messages"][-1]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,QUJD")


def test_openai_passes_the_system_prompt(recorder):
    cfg = AIConfig(mode="api", provider="openai", api_key="k")
    call_llm("hi", system="You are an audiologist.", cfg=cfg)
    messages = recorder[0]["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are an audiologist."


def test_model_override_is_respected(recorder):
    cfg = AIConfig(mode="api", provider="openai", api_key="k", model="gpt-4o-mini")
    call_llm("hi", cfg=cfg)
    assert recorder[0]["json"]["model"] == "gpt-4o-mini"


def test_providers_do_not_share_endpoints(recorder):
    """A regression guard: adding a provider must not reroute an existing one."""
    for provider in OPENAI_COMPATIBLE:
        call_llm("hi", cfg=AIConfig(mode="api", provider=provider, api_key="k"))
    urls = [c["url"] for c in recorder]
    assert len(set(urls)) == len(OPENAI_COMPATIBLE)


def test_gemini_and_anthropic_still_use_their_own_dialects(recorder):
    call_llm("hi", cfg=AIConfig(mode="api", provider="gemini", api_key="g"))
    assert "generativelanguage.googleapis.com" in recorder[0]["url"]
    assert recorder[0]["headers"]["x-goog-api-key"] == "g"

    call_llm("hi", cfg=AIConfig(mode="api", provider="anthropic", api_key="a"))
    assert recorder[1]["url"] == "https://api.anthropic.com/v1/messages"
    assert recorder[1]["headers"]["x-api-key"] == "a"


# --------------------------------------------------------------- errors ---

def test_http_error_is_wrapped_not_raised_raw(monkeypatch):
    def failing_post(url, **kwargs):
        return FakeResponse({"error": "invalid_api_key"}, status_code=401)
    monkeypatch.setattr(llm_provider.httpx, "post", failing_post)

    with pytest.raises(llm_provider.LLMError) as exc:
        call_llm("hi", cfg=AIConfig(mode="api", provider="openai", api_key="bad"))
    assert "openai" in str(exc.value) and "401" in str(exc.value)


def test_connection_test_reports_failure_cleanly(monkeypatch):
    def failing_post(url, **kwargs):
        raise RuntimeError("network down")
    monkeypatch.setattr(llm_provider.httpx, "post", failing_post)

    result = llm_provider.test_connection(
        AIConfig(mode="api", provider="openai", api_key="k"))
    assert result["ok"] is False
    assert isinstance(result["message"], str)


def test_report_falls_back_to_offline_when_openai_fails(monkeypatch, tmp_path):
    """The demo must survive a dead provider."""
    import app.services.ai_config as ai_config
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    monkeypatch.setattr(ai_config, "_current",
                        AIConfig(mode="api", provider="openai", api_key="k"))

    def failing_post(url, **kwargs):
        raise RuntimeError("openai unreachable")
    monkeypatch.setattr(llm_provider.httpx, "post", failing_post)

    from app.services.demo_cases import DEMO_CASES
    analysis = client.post("/api/analyze", json=DEMO_CASES[0]["record"]).json()
    report = client.post("/api/report", json=analysis).json()
    assert report["engine"] == "offline-template"
    assert report["fallback_used"] is True
    assert report["report"]["findings"]
    monkeypatch.setattr(ai_config, "_current", None)
