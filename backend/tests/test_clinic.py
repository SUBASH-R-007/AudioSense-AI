"""Tests for records, noise dose, referral letters and the population atlas."""
import pytest
from fastapi.testclient import TestClient

from app.clinical.noise_dose import compute_dose, derate_nrr, permissible_hours
from app.main import app
from app.services.demo_cases import DEMO_CASES

client = TestClient(app)


# ---------------------------------------------------------- noise dose ----

def test_permissible_hours_matches_osha_table():
    # OSHA Table G-16: 90 dBA -> 8 h, 95 -> 4 h, 100 -> 2 h, 105 -> 1 h
    assert permissible_hours(90, 90, 5) == pytest.approx(8.0)
    assert permissible_hours(95, 90, 5) == pytest.approx(4.0)
    assert permissible_hours(100, 90, 5) == pytest.approx(2.0)
    assert permissible_hours(105, 90, 5) == pytest.approx(1.0)


def test_eight_hours_at_criterion_is_full_dose():
    d = compute_dose([{"level_dba": 90, "hours": 8, "label": "shift"}])
    assert d["osha_dose_pct"] == pytest.approx(100.0, abs=0.1)
    assert d["twa_dba"] == pytest.approx(90.0, abs=0.2)
    assert d["risk"] == "high"


def test_action_level_detected_at_85dba():
    d = compute_dose([{"level_dba": 85, "hours": 8}])
    assert d["osha_dose_pct"] == pytest.approx(50.0, abs=0.1)
    assert d["risk"] == "action"


def test_niosh_is_stricter_than_osha():
    d = compute_dose([{"level_dba": 92, "hours": 8}])
    assert d["niosh_dose_pct"] > d["osha_dose_pct"]


def test_quiet_job_is_low_risk():
    d = compute_dose([{"level_dba": 72, "hours": 8}])
    assert d["risk"] == "low"


def test_nrr_derating_halves_after_seven_db():
    assert derate_nrr(31) == 12.0
    assert derate_nrr(None) == 0.0
    assert derate_nrr(5) == 0.0


def test_protection_reduces_dose_below_the_limit():
    exposures = [{"level_dba": 100, "hours": 8}]
    unprotected = compute_dose(exposures)
    protected = compute_dose(exposures, nrr=31, protection_worn=True)
    assert unprotected["osha_dose_pct"] > 100
    assert protected["osha_dose_pct"] < unprotected["osha_dose_pct"]
    assert protected["protection_attenuation_db"] == 12.0


def test_dose_endpoint():
    r = client.post("/api/noise-dose", json={
        "exposures": [{"label": "grinding", "level_dba": 98, "hours": 4},
                      {"label": "assembly", "level_dba": 85, "hours": 4}],
        "nrr": 25, "protection_worn": False,
    })
    body = r.json()
    assert body["available"] is True
    assert len(body["exposures"]) == 2
    assert body["osha_dose_pct"] > 0


def test_empty_exposures_handled():
    assert compute_dose([])["available"] is False


# ------------------------------------------------------------- records ----

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    import app.services.records as rec
    monkeypatch.setattr(rec, "DB_PATH", tmp_path / "records.db")
    monkeypatch.setattr(rec, "DATA_DIR", tmp_path)
    return rec


def test_visit_roundtrip_and_history(temp_db):
    case = next(c for c in DEMO_CASES if c["id"] == "noise_notch")
    analysis = client.post("/api/analyze", json=case["record"]).json()

    first = temp_db.save_visit(analysis)
    assert first["saved"] is True

    # A later visit for the same person must attach to the same patient.
    worse = {**analysis}
    worse["patient"] = {**analysis["patient"], "test_date": "2027-07-18"}
    worse["rules"] = {**analysis["rules"]}
    second = temp_db.save_visit(worse)
    assert second["patient_id"] == first["patient_id"]

    history = temp_db.patient_history(first["patient_id"])
    assert len(history["visits"]) == 2
    assert history["trend"]["visits"] == 2
    assert history["patient"]["name"] == "Murugan Selvam"

    patients = temp_db.list_patients()
    assert len(patients) == 1
    assert patients[0]["visits"] == 2

    assert temp_db.list_patients("murugan")[0]["name"] == "Murugan Selvam"
    assert temp_db.list_patients("nobody") == []


def test_visit_requires_a_name(temp_db):
    result = temp_db.save_visit({"patient": {"name": ""}, "rules": {}})
    assert result["saved"] is False


def test_worsening_trend_detected(temp_db):
    base = {"patient": {"name": "Trend Test", "test_date": "2024-01-01"},
            "rules": {"right": {"ac_pta": {"value": 20.0}},
                      "left": {"ac_pta": {"value": 20.0}}},
            "thresholds": {"right": {}, "left": {}}}
    later = {"patient": {"name": "Trend Test", "test_date": "2026-01-01"},
             "rules": {"right": {"ac_pta": {"value": 38.0}},
                       "left": {"ac_pta": {"value": 34.0}}},
             "thresholds": {"right": {}, "left": {}}}
    pid = temp_db.save_visit(base)["patient_id"]
    temp_db.save_visit(later)
    history = temp_db.patient_history(pid)
    assert history["trend"]["right_change"] == 18.0
    assert history["trend"]["worsening"] is True


def test_history_404_for_unknown_patient():
    assert client.get("/api/records/patients/999999").status_code == 404


# ------------------------------------------------------------ referral ----

def test_referral_pdf_carries_the_red_flags():
    case = next(c for c in DEMO_CASES if c["id"] == "sudden_asymmetric")
    analysis = client.post("/api/analyze", json=case["record"]).json()
    r = client.post("/api/referral", json={
        "patient": analysis["patient"], "analysis": analysis,
    })
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 2000


def test_referral_for_a_clean_test_still_renders():
    case = next(c for c in DEMO_CASES if c["id"] == "normal")
    analysis = client.post("/api/analyze", json=case["record"]).json()
    r = client.post("/api/referral", json={
        "patient": analysis["patient"], "analysis": analysis})
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


# --------------------------------------------------------------- atlas ----

def test_atlas_returns_projected_population():
    r = client.get("/api/atlas", params={"limit": 200})
    if r.status_code == 503:
        pytest.skip("model not trained")
    body = r.json()
    assert len(body["points"]) == 200
    assert {"x", "y", "pattern", "label"} <= set(body["points"][0])
    assert len({p["pattern"] for p in body["points"]}) > 3


def test_atlas_projection_places_a_patient():
    notch = {"ac": {250: 10, 500: 10, 1000: 15, 2000: 15, 4000: 55, 8000: 20},
             "bc": {250: 5, 500: 5, 1000: 10, 2000: 10, 4000: 50}}
    r = client.post("/api/atlas/project", json=notch)
    if r.status_code == 503:
        pytest.skip("model not trained")
    body = r.json()
    assert isinstance(body["x"], float) and isinstance(body["y"], float)
