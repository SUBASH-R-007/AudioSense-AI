"""Tests for red-flag referral logic, masking validity, and speech audiometry."""
import pytest

from app.clinical.safety import (
    asymmetry_check,
    masking_check,
    safety_review,
    sudden_loss_check,
)
from app.clinical.speech_audiometry import srt_agreement, wrs_analysis
from app.models.schemas import EarData


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


def bc_flat(level):
    return {f: level for f in (250, 500, 1000, 2000, 4000)}


# ------------------------------------------------------------- asymmetry --

def test_symmetric_hearing_no_flag():
    assert asymmetry_check(flat(30), flat(30))["flag"] is False


def test_single_20db_difference_flags():
    left = {**flat(20), 4000: 40}
    result = asymmetry_check(flat(20), left)
    assert result["flag"] is True
    assert result["poorer_ear"] == "left"
    assert any("≥20 dB" in r for r in result["reasons"])


def test_two_15db_differences_flag():
    left = {**flat(20), 2000: 35, 4000: 35}
    result = asymmetry_check(flat(20), left)
    assert result["flag"] is True
    assert any("≥15 dB" in r for r in result["reasons"])


def test_single_15db_difference_does_not_flag():
    left = {**flat(20), 4000: 35}
    assert asymmetry_check(flat(20), left)["flag"] is False


# ----------------------------------------------------------- sudden SNHL --

def test_sudden_drop_versus_baseline_is_emergency():
    baseline = flat(15)
    current = {**baseline, 1000: 50, 2000: 55, 4000: 60}  # 3 contiguous, ≥30 dB
    result = sudden_loss_check(current, bc_flat(50), "unknown", baseline)
    assert result["flag"] is True
    assert result["urgency"] == "emergency"
    assert result["confirmed"] is True
    assert len(result["freqs"]) >= 3


def test_two_contiguous_frequencies_not_enough():
    baseline = flat(15)
    current = {**baseline, 2000: 55, 4000: 60}
    result = sudden_loss_check(current, bc_flat(50), "unknown", baseline)
    assert result["confirmed"] is False


def test_reported_sudden_onset_flags_without_baseline():
    result = sudden_loss_check(flat(55), bc_flat(50), onset="sudden")
    assert result["flag"] is True
    assert result["urgency"] == "emergency"


def test_conductive_loss_with_sudden_onset_is_not_snhl():
    # Big air-bone gap -> conductive, not sensorineural
    result = sudden_loss_check(flat(55), bc_flat(10), onset="sudden")
    assert result["flag"] is False


def test_unknown_onset_prompts_the_question():
    result = sudden_loss_check(flat(50), bc_flat(45), onset="unknown")
    assert result["urgency"] == "ask"
    assert "72 hours" in result["message"]


def test_normal_hearing_no_sudden_flag():
    assert sudden_loss_check(flat(10), bc_flat(10), "sudden")["flag"] is False


# -------------------------------------------------------------- masking ---

def test_masking_indicated_when_ac_exceeds_other_bc_by_40():
    # Test ear AC 70, other ear BC 10 -> 60 dB difference
    result = masking_check(flat(70), bc_flat(65), flat(10), bc_flat(10))
    assert result["masking_indicated"] is True
    assert result["warning"] is True
    assert "cross-hearing" in " ".join(result["reasons"])


def test_no_masking_warning_when_reported_as_masked():
    result = masking_check(flat(70), bc_flat(65), flat(10), bc_flat(10), masked=True)
    assert result["masking_indicated"] is True
    assert result["warning"] is False  # clinician already masked


def test_symmetric_mild_loss_needs_no_masking():
    result = masking_check(flat(25), bc_flat(22), flat(25), bc_flat(22))
    assert result["masking_indicated"] is False


def test_air_bone_gap_triggers_bc_masking():
    result = masking_check(flat(45), bc_flat(10), flat(45), bc_flat(10))
    assert result["bc_freqs"]  # gap > 10 dB
    assert result["masking_indicated"] is True


# --------------------------------------------------------- speech audio ---

def test_srt_agrees_with_pta():
    ac = flat(40)
    result = srt_agreement(ac, 40)
    assert result["agrees"] is True
    assert result["non_organic_suspected"] is False


def test_srt_much_better_than_pta_flags_non_organic():
    ac = flat(60)          # pure tones say 60 dB
    result = srt_agreement(ac, 30)  # but speech understood at 30 dB
    assert result["non_organic_suspected"] is True
    assert "exaggerated" in result["message"]


def test_srt_agreement_boundary_at_10db():
    ac = flat(40)
    assert srt_agreement(ac, 30)["agrees"] is True     # exactly 10 dB
    assert srt_agreement(ac, 29)["agrees"] is False    # 11 dB


def test_srt_none_without_measurement():
    assert srt_agreement(flat(40), None) is None


def test_rollover_detected():
    # Score peaks at 60% then collapses to 20% at higher level
    wrs = [{"level": 60, "score": 60}, {"level": 80, "score": 40},
           {"level": 100, "score": 20}]
    result = wrs_analysis(wrs, pta=45)
    assert result["rollover_index"] == pytest.approx((60 - 20) / 60, abs=0.01)
    assert result["rollover"] is True
    assert any("retrocochlear" in n for n in result["notes"])


def test_no_rollover_when_scores_hold():
    wrs = [{"level": 60, "score": 88}, {"level": 80, "score": 92}]
    result = wrs_analysis(wrs, pta=35)
    assert result["rollover"] is False
    assert "Good" in result["interpretation"] or "Excellent" in result["interpretation"]


def test_disproportionately_poor_wrs_flags():
    result = wrs_analysis([{"level": 70, "score": 40}], pta=35)
    assert result["disproportionate"] is True


# ----------------------------------------------------------- full review --

def test_safety_review_orders_emergency_first():
    right = EarData(ac={**flat(15), 1000: 55, 2000: 60, 4000: 65}, bc=bc_flat(55))
    left = EarData(ac=flat(15), bc=bc_flat(12))
    review = safety_review(right, left, onset="sudden")
    assert review["has_emergency"] is True
    assert review["alerts"][0]["level"] == "emergency"
    # Asymmetry should also be caught for this one-sided drop.
    assert review["asymmetry"]["flag"] is True


def test_clean_test_has_no_alerts():
    ear = EarData(ac=flat(10), bc=bc_flat(8))
    review = safety_review(ear, EarData(ac=flat(10), bc=bc_flat(8)))
    assert review["alerts"] == []
    assert review["has_urgent"] is False
