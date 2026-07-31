"""Tests for NAL-R prescription, SII, and word-level audibility."""
import pytest

from app.clinical.prescription import aided_thresholds, nal_r_gains, prescribe
from app.services.sii import (
    BAND_IMPORTANCE,
    compute_sii,
    sii_bundle,
    word_intelligibility,
)


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


# ------------------------------------------------------------- NAL-R -------

def test_normal_hearing_gets_no_gain():
    gains = nal_r_gains(flat(5))
    assert all(g == 0 for g in gains.values())


def test_nal_r_matches_hand_computed_formula():
    # Flat 60 dB: X = 0.05 * (60+60+60) = 9; IG(1k) = 9 + 0.31*60 + 1 = 28.6
    gains = nal_r_gains(flat(60))
    assert gains[1000] == pytest.approx(28.6, abs=0.05)
    # IG(250) = 9 + 18.6 - 17 = 10.6
    assert gains[250] == pytest.approx(10.6, abs=0.05)


def test_gain_is_greater_where_loss_is_greater():
    ac = {250: 30, 500: 35, 1000: 40, 2000: 55, 4000: 70, 8000: 75}
    gains = nal_r_gains(ac)
    assert gains[4000] > gains[1000] > gains[250]


def test_bands_within_normal_limits_get_no_gain():
    # Ski-slope: normal lows must stay unamplified, highs get gain.
    ac = {250: 10, 500: 15, 1000: 20, 2000: 45, 4000: 70, 8000: 75}
    gains = nal_r_gains(ac)
    assert gains[250] == gains[500] == gains[1000] == 0.0  # 20 dB = normal limit
    assert gains[2000] > 0 and gains[4000] > 0


def test_gain_capped_at_max():
    gains = nal_r_gains(flat(120))
    assert all(g <= 45.0 for g in gains.values())


def test_aided_thresholds_improve_but_never_beat_normal():
    ac = flat(60)
    aided = aided_thresholds(ac)
    assert all(0 <= aided[f] < 60 for f in aided)
    assert all(aided[f] >= 0 for f in aided)


def test_prescribe_bundle_shape():
    b = prescribe(flat(50))
    assert "NAL-R" in b["method"]
    assert set(b["gains"]) == {250, 500, 1000, 2000, 4000, 8000}


# --------------------------------------------------------------- SII -------

def test_band_importance_sums_to_one():
    assert sum(BAND_IMPORTANCE.values()) == pytest.approx(1.0, abs=1e-6)


def test_normal_hearing_sii_is_full():
    result = compute_sii({f: 5.0 for f in BAND_IMPORTANCE})
    assert result["sii"] == 1.0
    assert "essentially all" in result["descriptor"]


def test_profound_loss_sii_is_zero():
    result = compute_sii({f: 110.0 for f in BAND_IMPORTANCE})
    assert result["sii"] == 0.0


def test_noise_lowers_sii_for_normal_hearing():
    thresholds = {f: 5.0 for f in BAND_IMPORTANCE}
    quiet = compute_sii(thresholds, noise=False)["sii"]
    noise = compute_sii(thresholds, noise=True)["sii"]
    assert noise < quiet


def test_high_frequency_loss_costs_weighted_bands():
    # Loss confined to 4k/8k: SII drops by roughly those bands' importance.
    thresholds = {250: 5.0, 500: 5.0, 1000: 5.0, 2000: 5.0, 4000: 90.0, 8000: 90.0}
    result = compute_sii(thresholds)
    expected_loss = BAND_IMPORTANCE[4000] + BAND_IMPORTANCE[8000]
    assert result["sii"] == pytest.approx(1 - expected_loss, abs=0.01)


def test_sii_bundle_shows_aided_benefit():
    ac = {250: 30, 500: 40, 1000: 50, 2000: 60, 4000: 70, 8000: 75}
    b = sii_bundle(ac)
    assert b["aided_quiet"]["sii"] > b["quiet"]["sii"]
    assert b["aided_gain_quiet"] > 0
    assert b["noise"]["sii"] <= b["quiet"]["sii"]


def test_sii_bundle_none_without_data():
    assert sii_bundle({}) is None


def test_untested_band_renormalizes_rather_than_penalizes():
    full = compute_sii({f: 5.0 for f in BAND_IMPORTANCE})
    partial = compute_sii({250: 5.0, 500: 5.0, 1000: 5.0, 2000: 5.0})
    assert partial["sii"] == pytest.approx(full["sii"], abs=1e-9)


# ---------------------------------------------------- word intelligibility -

def test_normal_hearing_hears_every_word():
    result = word_intelligibility(flat(5))
    assert result["counts"]["missed"] == 0
    assert all(w["status"] == "clear" for w in result["words"])


def test_high_frequency_loss_misses_sibilant_words():
    ac = {250: 10, 500: 10, 1000: 15, 2000: 55, 4000: 75, 8000: 80}
    result = word_intelligibility(ac)
    words = {w["word"].lower().strip('.'): w["status"] for w in result["words"]}
    assert words["sells"] in ("missed", "degraded")
    assert words["seashells"] in ("missed", "degraded")
    assert result["missed_pct"] > 0


def test_custom_text_supported():
    result = word_intelligibility(flat(80), "sun fish")
    assert [w["word"] for w in result["words"]] == ["sun", "fish"]


def test_single_lost_consonant_degrades_rather_than_kills_a_word():
    """"the" losing only /th/ stays recoverable from context."""
    ac = {250: 10, 500: 10, 1000: 15, 2000: 55, 4000: 75, 8000: 80}
    result = word_intelligibility(ac, "the fish")
    by_word = {w["word"]: w["status"] for w in result["words"]}
    assert by_word["the"] == "degraded"      # one consonant cue lost
    assert by_word["fish"] == "missed"       # both /f/ and /sh/ gone


def test_mild_notch_does_not_wipe_out_most_words():
    """A mild 4 kHz notch should degrade speech, not obliterate it."""
    ac = {250: 15, 500: 15, 1000: 20, 2000: 25, 4000: 60, 8000: 30}
    result = word_intelligibility(ac)
    assert result["missed_pct"] < 35
