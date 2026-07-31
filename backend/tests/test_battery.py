"""Tests for tympanometry, reflexes, OAEs and the cross-modal engine."""
import pytest
from fastapi.testclient import TestClient

from app.clinical.consistency import reconcile_ear
from app.clinical.immittance import analyze_reflexes, classify_tympanogram
from app.clinical.oae import classify_oae, oae_audiogram_agreement
from app.clinical.prescription import verify_fitting
from app.main import app
from app.services.demo_cases import DEMO_CASES

client = TestClient(app)


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


# --------------------------------------------------------- tympanometry ---

@pytest.mark.parametrize("pressure,compliance,ecv,expected", [
    (-10, 0.7, 1.2, "A"),      # normal
    (0, 0.15, 1.0, "B"),       # flat, normal volume -> effusion
    (-20, 0.2, 1.1, "As"),     # stiff
    (0, 2.4, 1.2, "Ad"),       # hypercompliant
    (-250, 0.6, 1.2, "C"),     # negative pressure
])
def test_tympanogram_types(pressure, compliance, ecv, expected):
    assert classify_tympanogram(pressure, compliance, ecv)["type"] == expected


def test_type_b_distinguishes_perforation_by_canal_volume():
    effusion = classify_tympanogram(None, 0.1, 1.0)
    perforation = classify_tympanogram(None, 0.1, 4.5)
    assert "effusion" in effusion["interpretation"].lower()
    assert "perforation" in perforation["interpretation"].lower()
    assert perforation["ecv_flag"] == "large"


def test_untested_tympanogram_returns_none():
    assert classify_tympanogram(None, None) is None


# -------------------------------------------------------------- reflexes --

def test_reflexes_present_and_absent():
    assert analyze_reflexes({"ipsi": 85, "contra": 90})["pattern"] == "present"
    assert analyze_reflexes({"ipsi": None, "contra": None})["pattern"] == "absent"
    assert analyze_reflexes({"ipsi": 85, "contra": None})["pattern"] == "partial"


def test_reflex_sensation_level_flagged_when_elevated():
    r = analyze_reflexes({"ipsi": 110, "contra": 110}, pta=10)
    assert r["sensation_level"] == 100.0
    assert r["elevated"] is False          # exactly at the 100 dB SL limit
    assert analyze_reflexes({"ipsi": 115}, pta=10)["elevated"] is True


def test_reflexes_not_tested_returns_none():
    assert analyze_reflexes({}) is None


# ------------------------------------------------------------------ OAE ---

def test_oae_present_when_snr_at_least_6db():
    oae = classify_oae([
        {"freq": 1000, "amplitude": 2, "noise_floor": -4},   # SNR 6 -> present
        {"freq": 2000, "amplitude": 0, "noise_floor": -5},   # SNR 5 -> absent
    ])
    assert oae["present_freqs"] == [1000]
    assert oae["absent_freqs"] == [2000]


def test_absent_oae_with_normal_thresholds_is_preclinical_damage():
    oae = classify_oae([{"freq": 4000, "amplitude": -3, "noise_floor": -6}])
    findings = oae_audiogram_agreement(oae, {4000: 10.0})
    assert findings[0]["kind"] == "preclinical_damage"
    assert "before the audiogram" in findings[0]["detail"]


def test_present_oae_with_poor_thresholds_is_a_mismatch():
    oae = classify_oae([{"freq": 2000, "amplitude": 12, "noise_floor": -5}])
    findings = oae_audiogram_agreement(oae, {2000: 70.0})
    assert findings[0]["kind"] == "oae_threshold_mismatch"


def test_absent_oae_with_real_loss_is_not_flagged():
    """Absent emissions in an ear that genuinely cannot hear is expected."""
    oae = classify_oae([{"freq": 4000, "amplitude": -3, "noise_floor": -6}])
    assert oae_audiogram_agreement(oae, {4000: 65.0}) == []


# ------------------------------------------------- cross-modal reconcile --

def _ear(type_="Sensorineural", pta=30):
    return {"type": type_, "ac_pta": {"value": pta}}


def test_conductive_plus_type_b_confirms_effusion():
    tymp = classify_tympanogram(None, 0.1, 1.0)
    result = reconcile_ear("right", _ear("Conductive", 40),
                           {"tympanogram": tymp, "reflexes": None}, None, None, flat(40))
    assert "effusion_confirmed" in result["patterns"]
    assert result["agreement"] == "confirmed"


def test_conductive_without_middle_ear_pathology_contradicts():
    tymp = classify_tympanogram(-10, 0.7, 1.2)  # Type A
    result = reconcile_ear("right", _ear("Conductive", 40),
                           {"tympanogram": tymp, "reflexes": None}, None, None, flat(40))
    assert result["agreement"] == "conflicting"
    assert "third-window" in result["contradictions"][0]["detail"]


def test_otosclerosis_pattern_detected():
    tymp = classify_tympanogram(-20, 0.2, 1.1)  # As
    reflexes = analyze_reflexes({"ipsi": None, "contra": None})
    result = reconcile_ear("right", _ear("Conductive", 40),
                           {"tympanogram": tymp, "reflexes": reflexes}, None, None, flat(40))
    assert "otosclerosis_pattern" in result["patterns"]


def test_auditory_neuropathy_pattern():
    reflexes = analyze_reflexes({"ipsi": None, "contra": None})
    oae = {"present_freqs": [1000, 2000], "absent_freqs": [], "points": [],
           "preclinical_damage": [], "unexplained_emissions": []}
    speech = {"wrs": {"pb_max": 32}, "srt": None, "retrocochlear_suspicion": True}
    result = reconcile_ear("left", _ear("Sensorineural", 45),
                           {"tympanogram": None, "reflexes": reflexes}, oae, speech, flat(45))
    assert "auditory_neuropathy" in result["patterns"]
    assert any("ABR" in c["action"] for c in result["contradictions"])


def test_preclinical_damage_marked_priority():
    oae = {"present_freqs": [1000], "absent_freqs": [4000], "points": [],
           "preclinical_damage": [{"freq": 4000, "kind": "preclinical_damage",
                                   "detail": "x"}],
           "unexplained_emissions": []}
    result = reconcile_ear("right", _ear("Normal", 12),
                           None, oae, None, flat(12))
    assert "preclinical_nihl" in result["patterns"]
    assert result["confirmations"][0]["priority"] is True


def test_reflexes_present_with_severe_loss_contradicts():
    reflexes = analyze_reflexes({"ipsi": 95, "contra": 95})
    result = reconcile_ear("right", _ear("Sensorineural", 75),
                           {"tympanogram": None, "reflexes": reflexes}, None, None, flat(75))
    assert "reflex_threshold_mismatch" in result["patterns"]


def test_audiogram_only_gives_no_cross_checks():
    result = reconcile_ear("right", _ear(), None, None, None, flat(30))
    assert result["agreement"] == "insufficient"
    assert result["tests_available"]["tympanometry"] is False


# ------------------------------------------------------ fitting verify ----

def test_fitting_on_target():
    ac = flat(55)
    from app.clinical.prescription import aided_thresholds
    aided = aided_thresholds(ac)              # exactly the NAL-R target
    result = verify_fitting(ac, aided)
    assert result["on_target"] is True
    assert result["mean_abs_deviation"] == 0.0


def test_under_fitted_highs_are_called_out():
    ac = {250: 30, 500: 40, 1000: 50, 2000: 60, 4000: 65, 8000: 70}
    from app.clinical.prescription import aided_thresholds
    aided = dict(aided_thresholds(ac))
    aided[4000] += 18   # 18 dB less gain than prescribed
    result = verify_fitting(ac, aided)
    assert result["on_target"] is False
    assert 4000 in result["off_target_freqs"]
    assert "high-frequency gain" in result["action"]


def test_no_aided_thresholds_returns_none():
    assert verify_fitting(flat(50), {}) is None


# ------------------------------------------------------------ API level ---

def test_preclinical_demo_case_flags_damage_before_threshold_shift():
    case = next(c for c in DEMO_CASES if c["id"] == "preclinical_nihl")
    body = client.post("/api/analyze", json=case["record"]).json()

    # The audiogram alone looks completely normal.
    assert body["rules"]["right"]["who_grade"]["grade"] == "Normal hearing"
    # But the battery disagrees.
    assert "preclinical_nihl" in body["battery"]["patterns"]
    assert "before the audiogram" in body["battery"]["headline"]
    assert any(a["level"] == "urgent" for a in body["safety"]["alerts"])
    assert body["oae"]["right"]["preclinical_damage"]


def test_conductive_demo_confirmed_by_tympanometry():
    case = next(c for c in DEMO_CASES if c["id"] == "conductive")
    body = client.post("/api/analyze", json=case["record"]).json()
    assert body["immittance"]["right"]["tympanogram"]["type"] == "B"
    assert "effusion_confirmed" in body["battery"]["patterns"]
    assert body["battery"]["has_contradictions"] is False
    assert "agree" in body["battery"]["headline"]


def test_battery_absent_when_only_audiogram_supplied():
    body = client.post("/api/analyze", json={
        "patient": {"name": "T", "age": 40},
        "right": {"ac": flat(30), "bc": {}}, "left": {"ac": flat(30), "bc": {}},
    }).json()
    assert body["battery"]["tests_run"] >= 1
    assert body["immittance"]["right"] is None
    assert body["oae"]["right"] is None
