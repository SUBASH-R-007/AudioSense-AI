"""API-level tests: full request/response cycle through FastAPI TestClient."""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.demo_cases import DEMO_CASES

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_demo_cases_served():
    r = client.get("/api/demo-cases")
    assert r.status_code == 200
    body = r.json()
    assert len(body["cases"]) == 7
    assert {c["id"] for c in body["cases"]} >= {
        "normal", "noise_notch", "presbycusis", "conductive",
        "sudden_asymmetric", "preclinical_nihl", "profound",
    }
    assert "progression_pair" in body


def test_sudden_asymmetric_demo_raises_every_red_flag():
    case = next(c for c in DEMO_CASES if c["id"] == "sudden_asymmetric")
    body = client.post("/api/analyze", json=case["record"]).json()
    safety = body["safety"]
    assert safety["has_emergency"] is True          # sudden onset + SNHL
    assert safety["asymmetry"]["flag"] is True      # one-sided
    assert safety["alerts"][0]["level"] == "emergency"
    titles = " ".join(a["title"] for a in safety["alerts"])
    assert "sudden sensorineural" in titles.lower()
    assert "asymmetric" in titles.lower()
    # Rollover in the affected ear should raise retrocochlear suspicion.
    assert body["speech_audiometry"]["left"]["retrocochlear_suspicion"] is True
    # And the report must lead with the urgent action.
    rep = client.post("/api/report", json=body).json()
    assert rep["report"]["recommendations"][0].startswith("URGENT")


@pytest.mark.parametrize("case", DEMO_CASES, ids=[c["id"] for c in DEMO_CASES])
def test_analyze_every_demo_case(case):
    r = client.post("/api/analyze", json=case["record"])
    assert r.status_code == 200
    body = r.json()
    assert body["rules"]["right"]["who_grade"] is not None
    assert body["phonemes"]["right"]["audibility_pct"] is not None


def test_analyze_noise_notch_full_pipeline():
    case = next(c for c in DEMO_CASES if c["id"] == "noise_notch")
    body = client.post("/api/analyze", json=case["record"]).json()
    if body["ml"]["right"]:  # model trained
        assert body["ml"]["right"]["pattern"] == "noise_notch_4k"

    # Report from the analysis (offline template engine, deterministic verify)
    r2 = client.post("/api/report", json=body)
    assert r2.status_code == 200
    rep = r2.json()
    assert rep["verified"] is True
    assert rep["engine"] == "offline-template"
    assert any("noise" in s.lower() for s in rep["report"]["pattern_etiology"])
    # Occupation-aware: factory worker should be tied to the etiology.
    assert any("occupational" in s.lower() for s in rep["report"]["pattern_etiology"])
    # Counseling in both languages
    assert rep["counseling"]["english"]["summary"]
    assert rep["counseling"]["tamil"]["summary"]


def test_conductive_case_flags_conductive():
    case = next(c for c in DEMO_CASES if c["id"] == "conductive")
    body = client.post("/api/analyze", json=case["record"]).json()
    assert body["rules"]["right"]["type"] == "Conductive"
    assert body["rules"]["right"]["abg"]["value"] > 10


def test_progression_endpoint_flags_shift():
    r = client.get("/api/demo-cases").json()["progression_pair"]
    resp = client.post("/api/progression",
                       json={"baseline": r["baseline"], "current": r["current"]})
    assert resp.status_code == 200
    prog = resp.json()["progression"]
    assert prog["right"]["osha_sts"]["flag"] is True


def test_batch_csv():
    csv = (
        "name,age,sex,occupation,test_date,"
        "r_ac_250,r_ac_500,r_ac_1000,r_ac_2000,r_ac_4000,r_ac_8000,"
        "r_bc_250,r_bc_500,r_bc_1000,r_bc_2000,r_bc_4000,"
        "l_ac_250,l_ac_500,l_ac_1000,l_ac_2000,l_ac_4000,l_ac_8000,"
        "l_bc_250,l_bc_500,l_bc_1000,l_bc_2000,l_bc_4000\n"
        "Test One,40,male,clerk,2026-01-01,"
        "10,10,15,20,25,30,5,5,10,15,20,"
        "10,15,15,20,30,35,5,10,10,15,25\n"
        "Test Two,60,female,farmer,2026-01-02,"
        "40,45,50,55,60,NR,35,40,45,50,55,"
        "45,50,55,60,65,70,40,45,50,55,60\n"
    )
    r = client.post("/api/batch",
                    files={"file": ("batch.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    # Results come back as a triage-ordered worklist, not in CSV row order.
    by_name = {r["name"]: r for r in body["results"]}
    assert by_name["Test One"]["right"]["grade"] == "Normal hearing"
    assert by_name["Test Two"]["binaural_disability_pct"] is not None
    assert body["results"][0]["name"] == "Test Two"  # worse hearing seen first


def test_pdf_generation_and_verify_roundtrip():
    case = DEMO_CASES[0]
    analysis = client.post("/api/analyze", json=case["record"]).json()
    bundle = client.post("/api/report", json=analysis).json()
    r = client.post("/api/pdf", json={
        "patient": analysis["patient"],
        "analysis": analysis,
        "report_bundle": bundle,
    })
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"

    # The QR hash registered during PDF build must verify.
    from app.services.pdf import result_hash
    h = result_hash(analysis)
    v = client.get(f"/api/verify/{h}").json()
    assert v["valid"] is True
    assert client.get("/api/verify/deadbeef00000000").json()["valid"] is False


def test_ai_settings_toggle_and_persistence(tmp_path, monkeypatch):
    import app.services.ai_config as ai_config
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    monkeypatch.setattr(ai_config, "_current", None)

    r = client.get("/api/settings/ai")
    assert r.status_code == 200
    assert r.json()["config"]["mode"] == "offline"
    assert "gemini" in r.json()["providers"]

    r2 = client.post("/api/settings/ai",
                     json={"mode": "api", "provider": "gemini", "api_key": "abc12345"})
    assert r2.json()["config"]["api_key"] == "••••2345"  # masked

    # Persisted: a fresh load reads the same config back.
    monkeypatch.setattr(ai_config, "_current", None)
    r3 = client.get("/api/settings/ai")
    assert r3.json()["config"]["mode"] == "api"

    # Restore offline for other tests.
    client.post("/api/settings/ai", json={"mode": "offline", "api_key": ""})


def test_ai_test_connection_fails_cleanly_with_bogus_key(monkeypatch, tmp_path):
    import app.services.ai_config as ai_config
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    monkeypatch.setattr(ai_config, "_current", None)
    r = client.post("/api/settings/ai/test",
                    json={"mode": "api", "provider": "gemini",
                          "api_key": "bogus-key-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False  # graceful failure, no exception
    assert isinstance(body["message"], str)


def test_report_falls_back_to_offline_when_provider_errors(monkeypatch, tmp_path):
    """API mode + dead provider must still produce a full offline report."""
    import app.services.ai_config as ai_config
    from app.services.ai_config import AIConfig
    monkeypatch.setattr(ai_config, "CONFIG_PATH", tmp_path / "ai_config.json")
    monkeypatch.setattr(
        ai_config, "_current",
        AIConfig(mode="api", provider="ollama", base_url="http://localhost:1"),
    )
    analysis = client.post("/api/analyze", json=DEMO_CASES[0]["record"]).json()
    rep = client.post("/api/report", json=analysis).json()
    assert rep["engine"] == "offline-template"
    assert rep["fallback_used"] is True
    assert rep["report"]["findings"]
    monkeypatch.setattr(ai_config, "_current", None)
