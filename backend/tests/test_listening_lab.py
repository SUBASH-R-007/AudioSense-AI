"""Tests for localization, speech-in-noise, tinnitus and the deep ensemble."""
import pytest
from fastapi.testclient import TestClient

from app.clinical.listening_lab import (
    analyze_tinnitus,
    compare_srtn_with_audiogram,
    predict_localization,
    score_digits_in_noise,
    score_localization,
)
from app.main import app

client = TestClient(app)


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


# ---------------------------------------------------------- localization --

def test_symmetric_hearing_predicts_normal_localization():
    p = predict_localization(flat(15), flat(15))
    assert p["band"] == "normal"
    assert p["asymmetry_db"] == 0.0


def test_large_asymmetry_predicts_severe_impairment():
    p = predict_localization(flat(15), flat(65))
    assert p["asymmetry_db"] == 50.0
    assert p["band"] == "severely impaired"
    assert "turn the wrong way" in p["expectation"]


def test_symmetric_but_severe_loss_is_reduced_not_impaired():
    """Both ears equally bad still leaves the interaural comparison intact."""
    p = predict_localization(flat(60), flat(60))
    assert p["band"] == "reduced"


def test_prediction_needs_both_ears():
    assert predict_localization({}, flat(20)) is None


def test_perfect_responses_score_normal():
    trials = [{"presented_deg": a, "responded_deg": a}
              for a in (-90, -45, 0, 45, 90, 135)]
    r = score_localization(trials)
    assert r["rms_error_deg"] == 0.0
    assert r["band"] == "normal"
    assert r["reversals"] == 0


def test_angle_wrapping_is_handled():
    """A response of 350 against a target of 10 is a 20 degree error, not 340."""
    r = score_localization([{"presented_deg": 10, "responded_deg": 350}])
    assert r["rms_error_deg"] == 20.0


def test_left_right_reversals_are_counted():
    trials = [{"presented_deg": 90, "responded_deg": -90},
              {"presented_deg": -60, "responded_deg": 60}]
    assert score_localization(trials)["reversals"] == 2


def test_consistent_bias_names_the_side():
    trials = [{"presented_deg": a, "responded_deg": a + 25}
              for a in (-60, -30, 0, 30, 60)]
    r = score_localization(trials)
    assert r["pulled_toward"] == "right"
    assert "pulled toward the right" in r["interpretation"]


def test_large_errors_score_impaired():
    trials = [{"presented_deg": a, "responded_deg": a + 45}
              for a in (-90, -45, 0, 45)]
    assert score_localization(trials)["band"] == "impaired"


def test_no_trials_returns_none():
    assert score_localization([]) is None


def test_localization_endpoint():
    r = client.post("/api/listening/localization", json={
        "trials": [{"presented_deg": 45, "responded_deg": 50},
                   {"presented_deg": -30, "responded_deg": -35}],
        "right_ac": {"1000": 10}, "left_ac": {"1000": 10},
    })
    assert r.status_code == 200
    assert r.json()["result"]["trials"] == 2


def test_localization_endpoint_rejects_empty():
    assert client.post("/api/listening/localization",
                       json={"trials": []}).status_code == 400


# ------------------------------------------------------- speech in noise --

def test_good_srtn_scores_normal():
    r = score_digits_in_noise([-6, -8, -9, -10, -9, -10, -9])
    assert r["srt_db_snr"] < -7
    assert r["band"] == "normal"


def test_poor_srtn_scores_poor():
    r = score_digits_in_noise([0, -1, 1, 0, 1, 0, 0])
    assert r["band"] == "poor"
    assert "restaurants" in r["interpretation"] or "clinic" in r["interpretation"]


def test_first_reversals_are_discarded():
    """The early, coarse reversals must not drag the estimate."""
    with_junk = score_digits_in_noise([10, 8, -9, -9, -9, -9, -9])
    assert with_junk["srt_db_snr"] == pytest.approx(-9.0, abs=0.1)


def test_short_track_uses_every_reversal():
    r = score_digits_in_noise([-8, -6])
    assert r["reversals_used"] == 2


def test_hidden_hearing_loss_is_flagged():
    """Normal pure tones with poor speech in noise is the case that matters."""
    srtn = score_digits_in_noise([0, 0, 1, 0, 1, 0, 0])
    cmp = compare_srtn_with_audiogram(srtn, flat(10), flat(12))
    assert cmp["hidden_hearing_loss"] is True
    assert "hidden hearing loss" in cmp["note"]


def test_poor_speech_with_real_loss_is_not_called_hidden():
    srtn = score_digits_in_noise([0, 0, 1, 0, 1, 0, 0])
    cmp = compare_srtn_with_audiogram(srtn, flat(55), flat(55))
    assert cmp["hidden_hearing_loss"] is False
    assert "consistent with" in cmp["note"]


def test_digits_endpoint():
    r = client.post("/api/listening/digits-in-noise", json={
        "reversals": [-6, -8, -9, -10, -9, -10],
        "right_ac": {"500": 10, "1000": 10, "2000": 10, "4000": 10},
        "left_ac": {"500": 10, "1000": 10, "2000": 10, "4000": 10},
    })
    assert r.status_code == 200
    assert r.json()["result"]["band"] == "normal"


# -------------------------------------------------------------- tinnitus --

def test_tinnitus_pitch_inside_the_loss_region_is_recognised():
    ac = {250: 10, 500: 10, 1000: 15, 2000: 35, 4000: 60, 8000: 65}
    r = analyze_tinnitus({"pitch_hz": 4000, "loudness_db_sl": 8, "ear": "right"}, ac, ac)
    assert r["matches_loss_region"] is True
    assert any("inside the region of hearing loss" in n for n in r["notes"])


def test_tinnitus_pitch_in_normal_region_is_questioned():
    ac = flat(10)
    r = analyze_tinnitus({"pitch_hz": 1000, "ear": "right"}, ac, ac)
    assert r["matches_loss_region"] is False
    assert any("less typical" in n for n in r["notes"])


def test_low_matched_loudness_prompts_the_counselling_point():
    ac = {250: 10, 500: 10, 1000: 15, 2000: 35, 4000: 60, 8000: 65}
    r = analyze_tinnitus({"pitch_hz": 4000, "loudness_db_sl": 5}, ac, ac)
    assert any("distress correlates with intrusiveness" in n for n in r["notes"])


def test_notch_is_half_an_octave_around_the_pitch():
    r = analyze_tinnitus({"pitch_hz": 4000}, flat(40), flat(40))
    notch = r["notch"]
    assert notch["low_hz"] < 4000 < notch["high_hz"]
    # Half an octave total width => ratio of high to low is 2^0.5.
    assert notch["high_hz"] / notch["low_hz"] == pytest.approx(2 ** 0.5, abs=0.02)


def test_tinnitus_requires_a_pitch():
    assert analyze_tinnitus({}, flat(20), flat(20)) is None
    assert client.post("/api/listening/tinnitus",
                       json={"pitch_hz": 0}).status_code == 400


def test_tinnitus_always_carries_the_red_flag_disclaimer():
    r = analyze_tinnitus({"pitch_hz": 6000}, flat(30), flat(30))
    assert "pulsatile" in r["disclaimer"]


def test_tinnitus_endpoint():
    r = client.post("/api/listening/tinnitus", json={
        "pitch_hz": 4000, "loudness_db_sl": 10, "ear": "right",
        "right_ac": {"2000": 30, "4000": 60, "8000": 65},
        "left_ac": {"2000": 30, "4000": 60, "8000": 65},
    })
    assert r.status_code == 200
    assert r.json()["notch"]["centre_hz"] == 4000


# ---------------------------------------------------------- deep ensemble --

def test_model_comparison_reports_both_models():
    r = client.get("/api/model/comparison")
    if r.status_code == 503:
        pytest.skip("deep ensemble not trained")
    body = r.json()
    assert 0 <= body["randomforest"]["accuracy"] <= 1
    assert 0 <= body["deep_ensemble"]["accuracy"] <= 1
    assert body["primary_model"] == "randomforest"
    assert body["more_accurate"] in ("randomforest", "deep_ensemble")
    assert body["better_calibrated"] in ("randomforest", "deep_ensemble")
    assert "synthetic" in body["caveat"]


def test_deep_prediction_separates_epistemic_uncertainty():
    notch = {"ac": {1000: 15, 2000: 15, 4000: 55, 8000: 20, 250: 10, 500: 10},
             "bc": {1000: 10, 2000: 10, 4000: 50}}
    r = client.post("/api/model/deep-predict", json=notch)
    if r.status_code == 503:
        pytest.skip("deep ensemble not trained")
    body = r.json()
    assert body["pattern"] == "noise_notch_4k"
    assert 0 <= body["entropy_normalized"] <= 1
    assert body["epistemic_uncertainty"] >= 0
    assert body["ensemble_size"] >= 2


def test_absurd_input_raises_ensemble_disagreement():
    """Members should disagree more on nonsense than on a textbook notch."""
    textbook = {"ac": {250: 10, 500: 10, 1000: 15, 2000: 15, 4000: 55, 8000: 20}}
    nonsense = {"ac": {250: 120, 500: -10, 1000: 120, 2000: -10, 4000: 120, 8000: -10}}
    a = client.post("/api/model/deep-predict", json=textbook)
    if a.status_code == 503:
        pytest.skip("deep ensemble not trained")
    b = client.post("/api/model/deep-predict", json=nonsense)
    assert b.json()["entropy"] >= a.json()["entropy"]
