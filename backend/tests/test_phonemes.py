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
    # The impact statements are GRADED rather than stacked, so this ski-slope
    # (mid and high consonants gone, vowels intact) comes back as one sentence
    # carrying both consequences instead of four that repeat each other.
    assert "children's voices" in text
    assert len(result["impact"]) <= 2, result["impact"]


def test_impact_statements_are_graded_not_stacked():
    """A patient who cannot detect speech is not told about plural endings.

    These rules used to fire independently and concatenate: a loss severe
    enough to take the vowels out produced four statements, three of which
    described consequences the fourth had already made irrelevant, and the
    one sentence that mattered was last.
    """
    profound = phoneme_audibility(flat(95))
    assert profound["inaudible"], "nothing inaudible at 95 dB HL?"
    impact = profound["impact"]
    text = " ".join(impact)
    # The dominant finding leads, and it is the only one.
    assert len(impact) <= 2, impact
    assert "not reliably detected" in text
    # The subsumed detail is gone rather than repeated as its own sentence.
    assert "plurals" not in text
    assert "requests for repetition" not in text


def test_a_rising_loss_still_reports_its_own_low_frequency_consequence():
    """Nasal loss is a separate axis, not a milder consonant loss.

    The nasals sit a few dB softer on the banana than the low vowels beside
    them, so a shallow low-frequency loss takes /m/, /n/ and /ng/ while the
    vowels survive — and that says something no consonant statement does.
    A deeper low-frequency loss takes the vowels too, and then the nasal
    detail IS subsumed and is correctly dropped.
    """
    shallow = phoneme_audibility({250: 31, 500: 31, 1000: 15, 2000: 10,
                                  4000: 10, 8000: 10})
    assert "m" in shallow["inaudible"]
    # Borderline is its own status, so "not inaudible" is the right test here.
    assert "u" not in shallow["inaudible"], "the vowels should survive this one"
    text = " ".join(shallow["impact"])
    assert "nasal" in text.lower()
    assert "prosody" in text

    deep = phoneme_audibility({250: 70, 500: 65, 1000: 30, 2000: 15,
                               4000: 10, 8000: 10})
    deep_text = " ".join(deep["impact"])
    assert "not reliably detected" in deep_text
    assert "prosody" not in deep_text


def test_interpolation_is_log_frequency_linear():
    ac = {1000: 20, 2000: 40}
    # 1414 Hz is the log-midpoint of 1k and 2k -> threshold midpoint 30 dB
    assert abs(interpolate_threshold(ac, 1414.2) - 30.0) < 0.5


def test_every_phoneme_gets_a_status():
    result = phoneme_audibility(flat(40))
    assert len(result["phonemes"]) == len(SPEECH_BANANA)
    assert all(p["status"] in ("audible", "borderline", "inaudible")
               for p in result["phonemes"])
