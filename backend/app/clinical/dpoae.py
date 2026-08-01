"""Otoacoustic emissions as an instrument: the DP-gram and the pass criterion.

``oae.py`` decides present-or-absent per frequency and reconciles that against
the audiogram. This module is the machine in front of it: a full
distortion-product gram across the test frequencies, with the noise floor
plotted beneath each emission, an explicit pass/refer decision against a
stated protocol, and a cochlear profile that says *where along the cochlea*
the outer hair cells have gone.

Three things are worth being precise about.

THE CRITERION IS A PROTOCOL, NOT A CONSTANT. Newborn screening, occupational
monitoring and diagnostic testing use different rules — how many frequencies
must pass, and at what signal-to-noise ratio. A "refer" only means something
alongside the protocol that produced it, so the protocol is an input and is
reported in the result.

AN ABSENT EMISSION AT A HIGH THRESHOLD SAYS NOTHING. Emissions disappear once
the loss exceeds roughly 50 dB HL, so "absent" in an ear with a 70 dB
threshold is expected and carries no information. Counting it as evidence of
outer hair cell damage would be double-counting the audiogram. Frequencies
above that ceiling are marked uninformative rather than failed.

THE NOISE FLOOR IS PART OF THE RESULT. A 3 dB signal-to-noise ratio in a
quiet ear and in a screaming infant are not the same measurement. A high
noise floor invalidates the frequency rather than failing it, and the
response says which.

Reference: Gorga et al. (1997) normative DPOAE levels; ASHA (1997) and
JCIH (2019) screening protocols; Lonsbury-Martin & Martin (1990).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from app.clinical.oae import OAE_CEILING_DB_HL, SNR_PRESENT_DB

#: Standard DP-gram frequencies (f2, Hz).
DP_FREQS: List[int] = [1000, 1500, 2000, 3000, 4000, 6000, 8000]

#: A noise floor above this makes the measurement uninterpretable, whatever
#: the SNR appears to be.
NOISE_FLOOR_CEILING_DB = 10.0

#: Screening protocols. ``required`` is how many of ``freqs`` must pass.
PROTOCOLS: Dict[str, dict] = {
    "newborn": {
        "name": "Newborn hearing screening",
        "freqs": [2000, 3000, 4000],
        "snr": 6.0,
        "required": 3,
        "note": ("JCIH-style newborn screening. All three frequencies must pass; "
                 "a refer is a referral for diagnostic testing, not a diagnosis "
                 "of hearing loss."),
    },
    "screening": {
        "name": "General screening",
        "freqs": [2000, 3000, 4000],
        "snr": 6.0,
        "required": 2,
        "note": "Two of three frequencies must pass.",
    },
    "occupational": {
        "name": "Occupational / noise monitoring",
        "freqs": [3000, 4000, 6000],
        "snr": 6.0,
        "required": 3,
        "note": ("Weighted to the frequencies noise damages first. A refer here "
                 "with a still-normal audiogram is the whole point of the test: "
                 "damage detected while it is still preventable."),
    },
    "diagnostic": {
        "name": "Diagnostic DP-gram",
        "freqs": DP_FREQS,
        "snr": 6.0,
        "required": 5,
        "note": "Full-range gram; interpret frequency by frequency rather than "
                "as a single pass or refer.",
    },
}

#: Cochlear place for each test frequency — base to apex. Outer hair cells
#: are tonotopically arranged, so the pattern of absent emissions maps onto a
#: region of the cochlea rather than a set of numbers.
COCHLEAR_REGION: Dict[int, str] = {
    1000: "apical (low-frequency) turn",
    1500: "apical turn",
    2000: "mid turn",
    3000: "mid-basal turn",
    4000: "basal turn",
    6000: "basal turn",
    8000: "extreme base",
}


def _point(item) -> Optional[dict]:
    if isinstance(item, dict):
        freq, amp, nf = item.get("freq"), item.get("amplitude"), item.get("noise_floor")
    else:
        freq = getattr(item, "freq", None)
        amp = getattr(item, "amplitude", None)
        nf = getattr(item, "noise_floor", None)
    if freq is None or amp is None or nf is None:
        return None
    return {"freq": int(freq), "amplitude": float(amp), "noise_floor": float(nf)}


def dp_gram(
    points: Sequence,
    protocol: str = "screening",
    ac_numeric: Optional[Dict[int, Optional[float]]] = None,
) -> Optional[dict]:
    """Full DP-gram with per-frequency verdicts and a protocol decision."""
    rows = [p for p in (_point(i) for i in points or []) if p]
    if not rows:
        return None

    spec = PROTOCOLS.get(protocol, PROTOCOLS["screening"])
    thresholds = ac_numeric or {}

    for row in rows:
        row["snr"] = round(row["amplitude"] - row["noise_floor"], 1)
        row["present"] = row["snr"] >= spec["snr"]
        row["region"] = COCHLEAR_REGION.get(row["freq"], "")
        row["in_protocol"] = row["freq"] in spec["freqs"]

        threshold = thresholds.get(row["freq"])
        row["threshold"] = threshold
        if row["noise_floor"] > NOISE_FLOOR_CEILING_DB:
            row["verdict"] = "invalid"
            row["reason"] = (f"Noise floor {row['noise_floor']:g} dB SPL is too high "
                             "to judge this frequency — quieten the room or settle "
                             "the patient and repeat.")
        elif not row["present"] and threshold is not None \
                and threshold > OAE_CEILING_DB_HL:
            # Expected absence: says nothing beyond what the audiogram said.
            row["verdict"] = "uninformative"
            row["reason"] = (f"Emissions are not expected at a threshold of "
                             f"{threshold:g} dB HL, so their absence adds nothing.")
        elif row["present"]:
            row["verdict"] = "pass"
            row["reason"] = f"Emission {row['snr']:g} dB above the noise floor."
        else:
            row["verdict"] = "refer"
            row["reason"] = (f"No emission ({row['snr']:g} dB SNR, criterion "
                             f"{spec['snr']:g} dB) — outer hair cell function is "
                             "reduced at this frequency.")

    rows.sort(key=lambda r: r["freq"])

    tested = [r for r in rows if r["in_protocol"]]
    passed = [r for r in tested if r["verdict"] == "pass"]
    invalid = [r for r in tested if r["verdict"] == "invalid"]
    missing = [f for f in spec["freqs"] if f not in {r["freq"] for r in rows}]

    if missing or len(invalid) > len(tested) - spec["required"]:
        outcome, headline = "incomplete", (
            "Not enough valid frequencies to reach a screening decision.")
    elif len(passed) >= spec["required"]:
        outcome, headline = "pass", (
            f"PASS — {len(passed)} of {len(tested)} protocol frequencies present.")
    else:
        outcome, headline = "refer", (
            f"REFER — only {len(passed)} of {len(tested)} protocol frequencies "
            f"present, against {spec['required']} required.")

    return {
        "points": rows,
        "protocol": {"key": protocol, **spec},
        "outcome": outcome,
        "headline": headline,
        "passed_freqs": [r["freq"] for r in rows if r["verdict"] == "pass"],
        "referred_freqs": [r["freq"] for r in rows if r["verdict"] == "refer"],
        "invalid_freqs": [r["freq"] for r in rows if r["verdict"] == "invalid"],
        "uninformative_freqs": [r["freq"] for r in rows
                                if r["verdict"] == "uninformative"],
        "missing_freqs": missing,
        "criterion": f"emission >= {spec['snr']:g} dB above the noise floor",
    }


def cochlear_profile(gram: Optional[dict]) -> Optional[dict]:
    """Where along the cochlea the outer hair cells have been lost.

    A frequency list is a set of numbers. "The basal turn, where noise damage
    starts" is a location — and it is what makes the result explainable to
    the patient sitting in the chair.
    """
    if not gram:
        return None
    referred = [r for r in gram["points"] if r["verdict"] == "refer"]
    if not referred:
        return {
            "pattern": "intact",
            "summary": "Outer hair cell function is present across the tested range.",
            "regions": [],
        }

    freqs = [r["freq"] for r in referred]
    regions = sorted({r["region"] for r in referred if r["region"]})
    low = min(freqs)
    high = max(freqs)
    passed = {r["freq"] for r in gram["points"] if r["verdict"] == "pass"}

    # Recovery ABOVE the affected band is checked first: it is the most
    # specific pattern here, and a 4 kHz dropout with 8 kHz intact is a noise
    # notch rather than a generic basal loss. Testing "basal" first would
    # swallow it, since a notch usually sits in the basal range too.
    if passed and any(f > high for f in passed) and any(f < low for f in passed):
        pattern = "notch"
        summary = (f"Emissions absent at {freqs} Hz with recovery both above and "
                   "below — a notched pattern, characteristic of noise injury.")
    elif low >= 3000:
        pattern = "basal"
        summary = ("Loss confined to the basal turn — the high-frequency end, "
                   "which noise and ageing damage first.")
    elif high <= 2000:
        pattern = "apical"
        summary = ("Loss confined to the apical turn — an unusual low-frequency "
                   "pattern; consider hydrops or a conductive component blocking "
                   "the emission.")
    else:
        pattern = "diffuse"
        summary = "Loss across most of the tested range — widespread outer hair "\
                  "cell involvement."

    return {
        "pattern": pattern,
        "summary": summary,
        "regions": regions,
        "affected_freqs": freqs,
    }


def analyze(
    ear: str = "right",
    points: Optional[Sequence] = None,
    protocol: str = "screening",
    ac_numeric: Optional[Dict[int, Optional[float]]] = None,
    kind: str = "dpoae",
) -> dict:
    """One OAE study: gram, protocol decision, cochlear profile, caveats."""
    from app.clinical.oae import oae_audiogram_agreement

    gram = dp_gram(points or [], protocol, ac_numeric)
    if not gram:
        return {"ear": ear, "kind": kind, "available": False,
                "note": "No emission data entered."}

    profile = cochlear_profile(gram)
    # Reuse the existing agreement engine so the audiogram cross-check is
    # identical whether OAEs arrive through this instrument or the full
    # battery endpoint.
    mismatches = oae_audiogram_agreement(
        {"points": [{"freq": r["freq"], "snr": r["snr"], "present": r["present"]}
                    for r in gram["points"]]},
        ac_numeric or {},
    )

    interpretation: List[str] = [gram["headline"]]
    if profile:
        interpretation.append(profile["summary"])
    for m in mismatches:
        interpretation.append(m["detail"])
    if gram["invalid_freqs"]:
        interpretation.append(
            f"Frequencies {gram['invalid_freqs']} Hz could not be judged because "
            "the noise floor was too high. Repeat them in quiet.")
    if gram["uninformative_freqs"]:
        interpretation.append(
            f"Absence at {gram['uninformative_freqs']} Hz is expected given the "
            "thresholds there and is not counted as evidence of cochlear damage.")

    return {
        "ear": ear,
        "kind": kind,
        "available": True,
        **gram,
        "cochlear_profile": profile,
        "mismatches": mismatches,
        "preclinical_damage": [m for m in mismatches
                               if m["kind"] == "preclinical_damage"],
        "unexplained_emissions": [m for m in mismatches
                                  if m["kind"] == "oae_threshold_mismatch"],
        "interpretation": interpretation,
        "ceiling_db_hl": OAE_CEILING_DB_HL,
        "default_snr_criterion": SNR_PRESENT_DB,
    }
