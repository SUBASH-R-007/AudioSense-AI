"""Deployment configuration: CORS, health checks, and env handling.

Deployment breakage is usually silent until a browser blocks a request, so
the origin rules are pinned here rather than discovered in production.
"""
import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import ALLOWED_ORIGINS, app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def test_local_dev_origins_always_allowed():
    """The dev server must work with no configuration at all."""
    assert "http://localhost:5173" in ALLOWED_ORIGINS
    assert "http://127.0.0.1:5173" in ALLOWED_ORIGINS
    # `vite preview` serves a production build locally on 4173.
    assert "http://localhost:4173" in ALLOWED_ORIGINS


def test_cors_headers_returned_for_dev_origin():
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_preflight_is_answered():
    r = client.options("/api/analyze", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert r.status_code in (200, 204)
    assert "access-control-allow-origin" in r.headers


def test_deployed_origin_can_be_added_by_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS",
                       "https://audiosense.vercel.app, https://custom.example.com/")
    import app.main as main
    reloaded = importlib.reload(main)
    try:
        # Trailing slashes are stripped; both entries survive.
        assert "https://audiosense.vercel.app" in reloaded.ALLOWED_ORIGINS
        assert "https://custom.example.com" in reloaded.ALLOWED_ORIGINS
        # Local development is never lost by configuring production.
        assert "http://localhost:5173" in reloaded.ALLOWED_ORIGINS
    finally:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        importlib.reload(main)


def test_origin_regex_supports_vercel_previews(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    import app.main as main
    reloaded = importlib.reload(main)
    try:
        assert reloaded.ORIGIN_REGEX == r"https://.*\.vercel\.app"
        preview = TestClient(reloaded.app).get(
            "/api/health",
            headers={"Origin": "https://audiosense-git-branch-user.vercel.app"})
        assert preview.headers.get("access-control-allow-origin")
    finally:
        monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
        importlib.reload(main)


def test_root_route_is_a_usable_health_check():
    """Railway's healthcheckPath points here."""
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "AudioSense AI"
    assert isinstance(body["model_trained"], bool)


def test_api_health_still_works():
    assert client.get("/api/health").json()["status"] == "ok"


# ------------------------------------------------------- config files ------

def test_railway_config_is_valid_and_binds_the_platform_port():
    cfg = json.loads((ROOT / "backend" / "railway.json").read_text(encoding="utf-8"))
    start = cfg["deploy"]["startCommand"]
    assert "--host 0.0.0.0" in start, "must bind all interfaces, not localhost"
    assert "$PORT" in start, "must use the platform-assigned port"
    assert cfg["deploy"]["healthcheckPath"] == "/"
    # The model artifacts are gitignored, so the build has to create them.
    build = cfg["build"]["buildCommand"]
    assert "app.ml.generate_dataset" in build
    assert "app.ml.train" in build


def test_procfile_matches_the_railway_start_command():
    proc = (ROOT / "backend" / "Procfile").read_text(encoding="utf-8")
    assert "0.0.0.0" in proc and "$PORT" in proc


def test_vercel_config_rewrites_spa_routes():
    cfg = json.loads((ROOT / "frontend" / "vercel.json").read_text(encoding="utf-8"))
    rewrites = cfg["rewrites"]
    assert any(r["destination"] == "/index.html" for r in rewrites), (
        "client-side routes such as /dashboard would 404 without a rewrite")
    assert cfg["outputDirectory"] == "dist"
