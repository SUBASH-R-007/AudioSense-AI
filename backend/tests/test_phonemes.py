"""Tests for the phoneme audibility map (speech banana)."""
from app.services.phonemes import (
    SPEECH_BANANA,
    interpolate_threshold,
    phoneme_audibility,
)


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


def test_normal_hearing_hears_everything():
    result = phoneme_audibility(flat(5))
    assert result["inaudible"] == []
    assert result["audibility_pct"] == 100.0
    assert any("comfortably audible" in s for s in result["impact"])


def test_profound_loss_hears_nothing():
    result = phoneme_audibility(flat(110))
    assert result["audible"] == []
    assert result["audibility_pct"] == 0.0


def test_high_freq_loss_kills_soft_consonants_keeps_vowels():
    # Normal through 1k, steep loss above (classic presbycusis/ski-slope)
    ac = {250: 10, 500: 10, 1000: 15, 2000: 55, 4000: 70, 8000: 75}
    result = phoneme_audibility(ac)
    assert "s" in result["inaudible"]
    assert "f" in result["inaudible"]
    assert "th" in result["inaudible"]
    assert "m" in result["audible"]
    assert "o" in result["audible"]
    text = " ".join(result["impact"])
    assert "plurals" in text
    assert "female and children" in text


def test_interpolation_is_log_frequency_linear():
    ac = {1000: 20, 2000: 40}
    # 1414 Hz is the log-midpoint of 1k and 2k -> threshold midpoint 30 dB
    assert abs(interpolate_threshold(ac, 1414.2) - 30.0) < 0.5


def test_every_phoneme_gets_a_status():
    result = phoneme_audibility(flat(40))
    assert len(result["phonemes"]) == len(SPEECH_BANANA)
    assert all(p["status"] in ("audible", "borderline", "inaudible")
               for p in result["phonemes"])
