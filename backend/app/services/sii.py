"""Speech Intelligibility Index (SII-style) and word-level audibility.

Band-importance-weighted audibility, simplified from ANSI S3.5-1997. For
each octave band the proportion of the conversational speech dynamic range
that sits above the listener's threshold is computed, then weighted by the
standard octave-band importance function:

    SII = sum_i  I(i) x A(i)
    A(i) = clamp( (L_loud(i) - threshold(i)) / (L_loud(i) - L_soft(i)), 0, 1 )

L_soft / L_loud are the upper and lower boundaries of the speech banana in
dB HL — the same curve drawn on the audiogram, so the chart and the number
always agree.

SII is reported as the share of speech *cues that are audible* (its actual
definition), not as a predicted word score — audibility is necessary but
not sufficient for understanding, especially in sensorineural loss.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.clinical.prescription import aided_thresholds, nal_r_gains
from app.models.schemas import ThresholdValue, ear_to_numeric
from app.services.phonemes import SPEECH_BANANA, interpolate_threshold

#: ANSI S3.5-1997 octave-band importance function (sums to 1.0).
BAND_IMPORTANCE = {250: 0.0617, 500: 0.1671, 1000: 0.2373,
                   2000: 0.2648, 4000: 0.2231, 8000: 0.0460}

#: Conversational speech dynamic range per band, dB HL (speech banana).
SPEECH_SOFT = {250: 22, 500: 17, 1000: 15, 2000: 13, 4000: 13, 8000: 18}
SPEECH_LOUD = {250: 52, 500: 57, 1000: 60, 2000: 55, 4000: 48, 8000: 42}

#: Competing babble in a typical restaurant masks the softest ~12 dB of
#: the speech range, raising the effective threshold.
NOISE_MASKING_DB = 12

#: Bundled simulator speech sample (must match public/audio/speech_sample.wav).
SAMPLE_TRANSCRIPT = (
    "She sells seashells by the seashore. "
    "The sixty-six thieves seized fifty fish. "
    "Peter puts fresh peaches and thin biscuits in the basket. "
    "This is a test of speech understanding."
)


def _band_audibility(threshold: Optional[float], freq: int, noise: bool) -> Optional[float]:
    if threshold is None:
        return None
    soft, loud = SPEECH_SOFT[freq], SPEECH_LOUD[freq]
    effective = max(threshold, soft + NOISE_MASKING_DB) if noise else threshold
    return min(1.0, max(0.0, (loud - effective) / (loud - soft)))


def compute_sii(thresholds: Dict[int, Optional[float]], noise: bool = False) -> Optional[dict]:
    """SII for one ear given numeric thresholds (dB HL)."""
    bands, total, weight_used = {}, 0.0, 0.0
    for freq, importance in BAND_IMPORTANCE.items():
        a = _band_audibility(thresholds.get(freq), freq, noise)
        if a is None:
            continue
        bands[freq] = round(a, 3)
        total += importance * a
        weight_used += importance
    if weight_used == 0:
        return None
    sii = total / weight_used  # renormalize if a band was untested
    return {
        "sii": round(sii, 3),
        "percent": round(sii * 100, 1),
        "bands": bands,
        "condition": "in background noise" if noise else "in quiet",
        "descriptor": _descriptor(sii),
    }


def _descriptor(sii: float) -> str:
    if sii >= 0.85:
        return "essentially all speech cues audible"
    if sii >= 0.65:
        return "most speech cues audible; effort rises in noise"
    if sii >= 0.45:
        return "many speech cues lost; frequent repetition needed"
    if sii >= 0.20:
        return "most speech cues inaudible; conversation very difficult"
    return "speech essentially inaudible without amplification"


def sii_bundle(ac: Dict[int, Optional[ThresholdValue]]) -> Optional[dict]:
    """Unaided (quiet + noise) and NAL-R-aided SII for one ear."""
    numeric = ear_to_numeric(ac)
    if not any(v is not None for v in numeric.values()):
        return None
    gains = nal_r_gains(ac)
    aided = aided_thresholds(ac, gains)

    quiet = compute_sii(numeric, noise=False)
    noise = compute_sii(numeric, noise=True)
    aided_quiet = compute_sii(aided, noise=False)
    aided_noise = compute_sii(aided, noise=True)
    if not quiet:
        return None

    return {
        "quiet": quiet,
        "noise": noise,
        "aided_quiet": aided_quiet,
        "aided_noise": aided_noise,
        "aided_gain_quiet": round(aided_quiet["percent"] - quiet["percent"], 1)
        if aided_quiet else None,
        "prescription_gains": gains,
        "method": "Band-importance-weighted audibility, simplified from ANSI S3.5-1997",
        "caveat": "SII measures audibility of speech cues, not comprehension; "
                  "sensorineural distortion can reduce understanding further.",
    }


# ---------------------------------------------------------------------------
# Word-level audibility for the live caption strike-through
# ---------------------------------------------------------------------------

#: Approximate grapheme -> speech-banana phoneme mapping. Digraphs are
#: matched first. Letters without a distinct banana entry map to their
#: nearest acoustic analogue.
DIGRAPHS = {"sh": "sh", "ch": "ch", "th": "th", "ng": "ng", "ck": "k",
            "ph": "f", "wh": "h", "qu": "k"}
LETTERS = {
    "a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "y": "i",
    "m": "m", "n": "n", "b": "b", "d": "d", "g": "g", "r": "r", "l": "l",
    "j": "j", "k": "k", "c": "k", "p": "p", "h": "h", "t": "t", "f": "f",
    "s": "s", "z": "s", "v": "f", "w": "u", "x": "k",
}
VOWELS = set("aeiouy")
_BANANA = {p["symbol"]: p for p in SPEECH_BANANA}


def _word_phonemes(word: str) -> List[str]:
    w = re.sub(r"[^a-z]", "", word.lower())
    out, i = [], 0
    while i < len(w):
        if i + 1 < len(w) and w[i:i + 2] in DIGRAPHS:
            out.append(DIGRAPHS[w[i:i + 2]])
            i += 2
            continue
        if w[i] in LETTERS:
            out.append(LETTERS[w[i]])
        i += 1
    return out


def word_intelligibility(
    ac: Dict[int, Optional[ThresholdValue]], text: str = SAMPLE_TRANSCRIPT
) -> dict:
    """Mark each word clear / degraded / missed from phoneme audibility.

    Grapheme-to-phoneme mapping is a documented approximation intended for
    counseling illustration, not for phonetic research.
    """
    words = []
    for token in text.split():
        phonemes = _word_phonemes(token)
        lost, consonants, lost_consonants = [], 0, 0
        for sym in phonemes:
            p = _BANANA.get(sym)
            if not p:
                continue
            is_consonant = sym not in VOWELS
            if is_consonant:
                consonants += 1
            thr = interpolate_threshold(ac, p["freq"])
            if thr is not None and thr > p["db"]:
                lost.append(sym)
                if is_consonant:
                    lost_consonants += 1

        # Consonants carry the intelligibility load; vowels are loud and
        # rarely lost. A word is only "missed" when most of its consonant
        # cues are gone AND it has more than one to lose — losing /th/ from
        # "the" degrades it, but context still recovers the word.
        if not lost_consonants:
            status = "clear"
        elif consonants >= 2 and lost_consonants / consonants >= 0.67:
            status = "missed"
        else:
            status = "degraded"
        words.append({"word": token, "status": status, "lost_phonemes": lost})

    counts = {s: sum(1 for w in words if w["status"] == s)
              for s in ("clear", "degraded", "missed")}
    return {
        "text": text,
        "words": words,
        "counts": counts,
        "missed_pct": round(100 * counts["missed"] / max(1, len(words)), 1),
        "note": "Approximate grapheme-to-phoneme mapping for counseling illustration.",
    }
