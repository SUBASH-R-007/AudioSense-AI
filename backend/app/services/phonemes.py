"""MODULE 5 — Phoneme audibility map ("speech banana").

Hardcodes approximate (frequency, intensity) positions of conversational
English phonemes on the audiogram — the classic "speech banana" — and
compares them against a patient's air-conduction thresholds to derive
which speech sounds are audible, plus a plain-language functional-impact
statement.

Positions are the widely used approximations from clinical audiology
counseling charts (e.g. Northern & Downs, *Hearing in Children*): nasals
and vowel fundamentals sit low-frequency/moderate-intensity; voiceless
fricatives /s/, /f/, /th/ sit high-frequency/low-intensity, which is why
high-frequency loss removes plural endings and soft consonants first.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.models.schemas import AC_FREQS, ThresholdValue, ear_to_numeric

# (symbol, frequency Hz, intensity dB HL, group, example word)
SPEECH_BANANA: List[dict] = [
    {"symbol": "m", "freq": 250, "db": 30, "group": "nasal", "example": "mom"},
    {"symbol": "n", "freq": 350, "db": 30, "group": "nasal", "example": "no"},
    {"symbol": "ng", "freq": 400, "db": 28, "group": "nasal", "example": "ring"},
    {"symbol": "u", "freq": 300, "db": 32, "group": "vowel", "example": "blue"},
    {"symbol": "o", "freq": 500, "db": 35, "group": "vowel", "example": "go"},
    {"symbol": "a", "freq": 750, "db": 36, "group": "vowel", "example": "father"},
    {"symbol": "e", "freq": 1000, "db": 33, "group": "vowel", "example": "bed"},
    {"symbol": "i", "freq": 1250, "db": 30, "group": "vowel", "example": "see"},
    {"symbol": "b", "freq": 900, "db": 40, "group": "voiced consonant", "example": "ball"},
    {"symbol": "d", "freq": 1100, "db": 38, "group": "voiced consonant", "example": "dog"},
    {"symbol": "g", "freq": 1500, "db": 36, "group": "voiced consonant", "example": "go"},
    {"symbol": "r", "freq": 1200, "db": 35, "group": "voiced consonant", "example": "red"},
    {"symbol": "l", "freq": 1400, "db": 34, "group": "voiced consonant", "example": "lip"},
    {"symbol": "j", "freq": 2200, "db": 32, "group": "voiced consonant", "example": "jump"},
    {"symbol": "ch", "freq": 2000, "db": 30, "group": "soft consonant", "example": "chair"},
    {"symbol": "sh", "freq": 2500, "db": 30, "group": "soft consonant", "example": "shoe"},
    {"symbol": "k", "freq": 2800, "db": 28, "group": "soft consonant", "example": "key"},
    {"symbol": "p", "freq": 3200, "db": 32, "group": "soft consonant", "example": "pig"},
    {"symbol": "h", "freq": 3400, "db": 30, "group": "soft consonant", "example": "hat"},
    {"symbol": "t", "freq": 3600, "db": 28, "group": "soft consonant", "example": "top"},
    {"symbol": "f", "freq": 4000, "db": 28, "group": "soft consonant", "example": "fish"},
    {"symbol": "s", "freq": 5000, "db": 25, "group": "soft consonant", "example": "sun"},
    {"symbol": "th", "freq": 5500, "db": 24, "group": "soft consonant", "example": "think"},
]


def interpolate_threshold(
    ac: Dict[int, Optional[ThresholdValue]], freq: float
) -> Optional[float]:
    """Patient AC threshold at an arbitrary frequency.

    Linear interpolation in log-frequency between the two nearest measured
    audiometric frequencies (the audiogram x-axis is logarithmic). Clamps
    to the nearest measured value outside the tested range.
    """
    numeric = {f: v for f, v in ear_to_numeric(ac).items() if v is not None}
    if not numeric:
        return None
    freqs = sorted(numeric)
    if freq <= freqs[0]:
        return numeric[freqs[0]]
    if freq >= freqs[-1]:
        return numeric[freqs[-1]]
    for f1, f2 in zip(freqs, freqs[1:]):
        if f1 <= freq <= f2:
            t = (math.log2(freq) - math.log2(f1)) / (math.log2(f2) - math.log2(f1))
            return numeric[f1] + t * (numeric[f2] - numeric[f1])
    return None  # pragma: no cover


def phoneme_audibility(ac: Dict[int, Optional[ThresholdValue]]) -> dict:
    """Classify every speech-banana phoneme as audible/borderline/inaudible.

    A phoneme is audible when its conversational intensity is at or above
    the patient's threshold at that frequency (threshold <= phoneme dB).
    Within 5 dB of threshold -> "borderline".
    """
    results = []
    for p in SPEECH_BANANA:
        thr = interpolate_threshold(ac, p["freq"])
        if thr is None:
            status, margin = "unknown", None
        else:
            margin = round(p["db"] - thr, 1)  # positive = headroom above threshold
            if margin >= 5:
                status = "audible"
            elif margin >= 0:
                status = "borderline"
            else:
                status = "inaudible"
        results.append({**p, "threshold_at_freq": None if thr is None else round(thr, 1),
                        "margin_db": margin, "status": status})

    audible = [r for r in results if r["status"] == "audible"]
    borderline = [r for r in results if r["status"] == "borderline"]
    inaudible = [r for r in results if r["status"] == "inaudible"]
    known = len(audible) + len(borderline) + len(inaudible)
    pct = round(100 * (len(audible) + 0.5 * len(borderline)) / known, 1) if known else None

    return {
        "phonemes": results,
        "audible": [r["symbol"] for r in audible],
        "borderline": [r["symbol"] for r in borderline],
        "inaudible": [r["symbol"] for r in inaudible],
        "audibility_pct": pct,
        "impact": functional_impact(results),
    }


def functional_impact(results: List[dict]) -> List[str]:
    """Rule-generated plain-language functional-impact statements."""
    lost = {g: [r["symbol"] for r in results if r["status"] == "inaudible" and r["group"] == g]
            for g in ("nasal", "vowel", "voiced consonant", "soft consonant")}
    statements: List[str] = []

    if lost["soft consonant"]:
        sounds = ", ".join(f"/{s}/" for s in lost["soft consonant"][:5])
        statements.append(
            f"High-frequency soft consonants ({sounds}) fall below threshold: "
            "will miss plurals, possessives and word endings (\"cat\" vs \"cats\"), "
            "and soft consonants in quiet speech."
        )
        statements.append(
            "Expect particular difficulty understanding female and children's "
            "voices, and speech in background noise."
        )
    if lost["voiced consonant"]:
        statements.append(
            "Mid-frequency consonant loss: confusion between similar words "
            "(\"bat\"/\"pat\", \"door\"/\"more\"); frequent requests for repetition."
        )
    if lost["vowel"]:
        statements.append(
            "Vowel energy is inaudible at conversational level: even loud "
            "speech will be hard to detect without amplification."
        )
    if lost["nasal"]:
        statements.append(
            "Low-frequency nasal cues (/m/, /n/) are lost: reduced awareness "
            "of voice prosody and hum-type environmental sounds."
        )
    if not any(lost.values()):
        borderline = [r for r in results if r["status"] == "borderline"]
        if borderline:
            statements.append(
                "All conversational phonemes are audible, but "
                f"{len(borderline)} sit within 5 dB of threshold — listening "
                "effort will rise in noise or at distance."
            )
        else:
            statements.append(
                "All conversational speech sounds are comfortably audible; no "
                "functional communication impact expected."
            )
    return statements
