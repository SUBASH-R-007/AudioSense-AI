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
response says which. A frequency that could not be judged never counts
towards a pass, a refer, or a finding of cochlear damage: when the decision
would turn on what those frequencies might have shown, the outcome is
"incomplete".

The per-frequency judgement (SNR, minimum emission level, noise ceiling) is
``oae.judge_emission`` — one rule shared with the battery, so the instrument
page and the dashboard cannot disagree about the same recording.

Reference: BSA (2023) Recommended Procedure: Clinical Application of OAEs,
s.6.2, s.7.2, s.8.1; Gorga et al. (1997) normative DPOAE levels; ASHA (1997)
and JCIH (2019) screening protocols; Lonsbury-Martin & Martin (1990).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from app.clinical.oae import (MIN_EMISSION_DB_SPL, NOISE_FLOOR_MAX_DB_SPL,
                              OAE_CEILING_DB_HL, SNR_PRESENT_DB, criterion_text,
                              display_snr, judge_emission)

#: Standard DP-gram frequencies (f2, Hz). A clinic is not limited to these —
#: see the ``custom`` protocol and ``cochlear_region`` below, which handle any
#: frequency set the instrument was actually run at.
DP_FREQS: List[int] = [1000, 1500, 2000, 3000, 4000, 6000, 8000]

#: Outcome vocabulary for a result recorded WITHOUT per-frequency values.
#: A screening instrument often prints nothing but PASS or REFER, and a camp
#: record is often nothing but that word — so it has to be enterable. Clinics
#: say "fail" and "refer" interchangeably for the same thing, and the word is
#: not interchangeable clinically: a refer is a referral for diagnostic
#: testing, never a diagnosis of hearing loss. "fail" is therefore accepted as
#: input and normalised to "refer" everywhere downstream.
OUTCOME_ALIASES: Dict[str, str] = {
    "pass": "pass", "p": "pass", "clear": "pass", "present": "pass",
    "refer": "refer", "fail": "refer", "f": "refer", "r": "refer",
    "no_clear_response": "refer", "absent": "refer",
    "incomplete": "incomplete", "inconclusive": "incomplete",
    "invalid": "incomplete", "not_tested": "incomplete",
}

#: A noise floor above this makes the measurement uninterpretable, whatever
#: the SNR appears to be: an absent emission could be hidden in the noise, and
#: BSA (2023) s.7.2 requires low noise for a present response too. Same value
#: as the battery's rule (``oae.NOISE_FLOOR_MAX_DB_SPL``, BSA 2023 s.6.2).
NOISE_FLOOR_CEILING_DB = NOISE_FLOOR_MAX_DB_SPL

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
    # The protocols above are published criteria, and their frequency lists are
    # part of the criterion — a "newborn screening pass" measured at 1 and 2
    # kHz is not a newborn screening pass. So a clinic that tested a different
    # set gets its own protocol rather than being scored against a standard it
    # did not follow, or having its extra frequencies silently ignored.
    "custom": {
        "name": "As tested (custom frequency set)",
        # Resolved at analysis time from the frequencies actually supplied.
        "freqs": [],
        "snr": 6.0,
        # Default: every frequency tested must pass. Overridable per request.
        "required": None,
        "note": ("Scored against the frequencies actually tested rather than a "
                 "published protocol's list. The decision is only as "
                 "transferable as the frequency set behind it, so report the "
                 "set with the outcome."),
    },
}

#: Protocols whose frequency list and pass count come from the request rather
#: than from a published standard.
CUSTOM_PROTOCOLS = frozenset({"custom"})

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

#: Greenwood (1990) cochlear frequency-place map, human coefficients:
#: f = A(10^(a·x) − k), inverted to give x, the fraction of the distance from
#: apex (0) to base (1). It is what lets an arbitrary test frequency be given a
#: real cochlear place instead of a blank: a clinic that adds 5 kHz to its
#: DP-gram should not get an empty "region" column.
GREENWOOD_A = 165.4
GREENWOOD_a = 2.1
GREENWOOD_k = 0.88

#: Place bands, as (upper bound on x, label). The bounds are chosen to
#: reproduce ``COCHLEAR_REGION`` exactly for the seven standard frequencies —
#: ``test_dpoae`` asserts that — so adding a frequency cannot silently change
#: how an existing one is described.
_PLACE_BANDS = (
    (0.44, "apical (low-frequency) turn"),
    (0.50, "apical turn"),
    (0.57, "mid turn"),
    (0.64, "mid-basal turn"),
    (0.78, "basal turn"),
    (float("inf"), "extreme base"),
)


def cochlear_place(freq: float) -> Optional[float]:
    """Fraction of the distance from the cochlear apex (0) to the base (1).

    None for a frequency below the map's floor, where the formula has no
    real solution rather than an answer worth printing.
    """
    try:
        ratio = float(freq) / GREENWOOD_A + GREENWOOD_k
        if ratio <= 0:
            return None
        return math.log10(ratio) / GREENWOOD_a
    except (TypeError, ValueError):
        return None


def cochlear_region(freq: float) -> str:
    """Where along the cochlea a frequency sits, for any frequency.

    The seven standard DP-gram frequencies come from ``COCHLEAR_REGION``
    verbatim, so the wording a clinician is used to never shifts. Anything
    else is placed by the Greenwood map above, which is why a custom
    frequency set still produces a cochlear profile rather than a gap.
    """
    exact = COCHLEAR_REGION.get(int(freq)) if freq == int(freq) else None
    if exact:
        return exact
    x = cochlear_place(freq)
    if x is None:
        return ""
    for upper, label in _PLACE_BANDS:
        if x < upper:
            return label
    return ""  # pragma: no cover — the last band is unbounded


def normalise_outcome(value: Optional[str]) -> Optional[str]:
    """Map what a clinic typed onto 'pass' | 'refer' | 'incomplete'."""
    if value is None:
        return None
    return OUTCOME_ALIASES.get(str(value).strip().lower().replace(" ", "_"))


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


def resolve_protocol(protocol: str, tested_freqs: Sequence[int],
                     required: Optional[int] = None) -> dict:
    """The criterion this gram is scored against.

    For a published protocol the frequency list and pass count ARE the
    criterion, so a caller cannot change them — a "newborn screening pass"
    measured at 1 and 2 kHz is not a newborn screening pass, and silently
    honouring an overridden count would put a standard's name on a decision it
    did not make. ``required`` is therefore accepted only for ``custom``,
    whose whole purpose is to score the set actually tested.
    """
    spec = dict(PROTOCOLS.get(protocol, PROTOCOLS["screening"]))
    if protocol in CUSTOM_PROTOCOLS:
        freqs = sorted({int(f) for f in tested_freqs})
        spec["freqs"] = freqs
        if required is None:
            # Default: everything tested must pass. The clinic chose the set,
            # so there is no reason to assume any of it was optional.
            spec["required"] = len(freqs)
        else:
            spec["required"] = max(0, min(int(required), len(freqs)))
    return spec


def dp_gram(
    points: Sequence,
    protocol: str = "screening",
    ac_numeric: Optional[Dict[int, Optional[float]]] = None,
    required: Optional[int] = None,
) -> Optional[dict]:
    """Full DP-gram with per-frequency verdicts and a protocol decision."""
    rows = [p for p in (_point(i) for i in points or []) if p]
    if not rows:
        return None

    spec = resolve_protocol(protocol, [r["freq"] for r in rows], required)
    thresholds = ac_numeric or {}

    for row in rows:
        judged = judge_emission(row["amplitude"], row["noise_floor"], spec["snr"])
        row["snr"] = display_snr(judged["snr"], spec["snr"])
        row["present"] = judged["present"]
        row["status"] = judged["status"]
        row["noisy_response"] = judged["noisy_response"]
        row["region"] = cochlear_region(row["freq"])
        row["cochlear_place"] = cochlear_place(row["freq"])
        row["in_protocol"] = row["freq"] in spec["freqs"]

        threshold = thresholds.get(row["freq"])
        row["threshold"] = threshold
        if judged["status"] == "inconclusive":
            row["verdict"] = "invalid"
            if judged["noisy_response"]:
                # A response above a noisy floor is neither a pass (BSA s.6.2:
                # low noise was not reached) nor something to throw away.
                row["reason"] = (
                    f"A response clears the noise floor by {row['snr']:g} dB, but the "
                    f"floor ({row['noise_floor']:g} dB SPL) is above the "
                    f"{NOISE_FLOOR_CEILING_DB:g} dB SPL a valid result needs, so this "
                    "frequency cannot pass. Repeat in quiet to confirm it."
                    + (f" At a threshold of {threshold:g} dB HL a confirmed emission "
                       "would mean the thresholds overstate the loss or the lesion "
                       "lies beyond the cochlea."
                       if threshold is not None and threshold > OAE_CEILING_DB_HL
                       else ""))
            else:
                row["reason"] = (f"Noise floor {row['noise_floor']:g} dB SPL is above the "
                                 f"{NOISE_FLOOR_CEILING_DB:g} dB SPL needed to judge this "
                                 "frequency — an emission could be hidden in the noise. "
                                 "Quieten the room or settle the patient and repeat.")
        elif not row["present"] and threshold is not None \
                and threshold > OAE_CEILING_DB_HL:
            # Expected absence: says nothing beyond what the audiogram said.
            row["verdict"] = "uninformative"
            row["reason"] = (f"Emissions are not expected at a threshold of "
                             f"{threshold:g} dB HL, so their absence adds nothing.")
        elif row["present"]:
            row["verdict"] = "pass"
            row["reason"] = f"Emission {row['snr']:g} dB above the noise floor."
            if threshold is not None and threshold > OAE_CEILING_DB_HL:
                row["reason"] += (
                    f" A threshold of {threshold:g} dB HL would not normally leave an "
                    "emission: the thresholds may overstate the loss, or the lesion "
                    "lies beyond the cochlea.")
        elif judged["status"] == "reduced":
            row["verdict"] = "refer"
            row["reason"] = (f"Emission {row['snr']:g} dB above the noise floor but "
                             f"only {row['amplitude']:g} dB SPL, below the "
                             f"{MIN_EMISSION_DB_SPL:g} dB SPL minimum — outer hair "
                             "cell function is reduced at this frequency.")
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

    # A refer must hold whatever the unjudged frequencies would have shown:
    # with 1 pass, 1 refer and 1 noisy frequency against a 2-of-3 rule, the
    # noisy one decides the outcome, so the answer is "incomplete", not refer.
    if missing:
        outcome, headline = "incomplete", (
            f"Not enough valid frequencies to reach a screening decision — "
            f"{missing} Hz not tested.")
    elif len(passed) >= spec["required"]:
        outcome, headline = "pass", (
            f"PASS — {len(passed)} of {len(tested)} protocol frequencies present.")
    elif len(passed) + len(invalid) < spec["required"]:
        outcome, headline = "refer", (
            f"REFER — only {len(passed)} of {len(tested)} protocol frequencies "
            f"present, against {spec['required']} required.")
    else:
        outcome, headline = "incomplete", (
            "Not enough valid frequencies to reach a screening decision — "
            f"{[r['freq'] for r in invalid]} Hz too noisy to judge, and they "
            "decide the outcome. Repeat them in quiet.")

    return {
        "points": rows,
        "protocol": {"key": protocol, **spec},
        "custom_protocol": protocol in CUSTOM_PROTOCOLS,
        "outcome": outcome,
        "headline": headline,
        "passed_freqs": [r["freq"] for r in rows if r["verdict"] == "pass"],
        "referred_freqs": [r["freq"] for r in rows if r["verdict"] == "refer"],
        "invalid_freqs": [r["freq"] for r in rows if r["verdict"] == "invalid"],
        "uninformative_freqs": [r["freq"] for r in rows
                                if r["verdict"] == "uninformative"],
        "missing_freqs": missing,
        "criterion": criterion_text(spec["snr"]),
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
    invalid = [r["freq"] for r in gram["points"] if r["verdict"] == "invalid"]
    if not referred:
        # "Intact" needs emissions that were actually seen. A gram in which
        # nothing could be judged has shown nothing either way.
        if not any(r["verdict"] == "pass" for r in gram["points"]):
            return {
                "pattern": "undetermined",
                "summary": ("No frequency gave a usable present-or-absent result, "
                            "so outer hair cell function cannot be judged from "
                            "this recording."),
                "regions": [],
            }
        summary = "Outer hair cell function is present across the tested range."
        if invalid:
            summary = ("Outer hair cell function is present at every frequency "
                       f"that could be judged; {invalid} Hz could not be tested "
                       "for noise.")
        return {
            "pattern": "intact",
            "summary": summary,
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
        # "Confined" is a claim about the frequencies below the loss; one that
        # could not be judged may hold the same loss.
        unjudged = [f for f in invalid if f < low]
        summary = (("Loss confined to the basal turn" if not unjudged else
                    "Loss at the basal turn")
                   + " — the high-frequency end, which noise and ageing damage first."
                   + (f" {unjudged} Hz could not be judged for noise, so whether "
                      "the loss extends lower is not known." if unjudged else ""))
    elif high <= 2000:
        pattern = "apical"
        unjudged = [f for f in invalid if f > high]
        summary = (("Loss confined to the apical turn" if not unjudged else
                    "Loss at the apical turn")
                   + " — an unusual low-frequency pattern; consider hydrops or a "
                   "conductive component blocking the emission."
                   + (f" {unjudged} Hz could not be judged for noise, so whether "
                      "the loss extends higher is not known." if unjudged else ""))
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


def from_outcome(
    ear: str = "right",
    outcome: Optional[str] = None,
    protocol: str = "screening",
    note: str = "",
    kind: str = "dpoae",
    freqs: Optional[Sequence[int]] = None,
) -> dict:
    """An OAE result recorded as PASS or REFER, with no per-frequency values.

    This is how most screening actually arrives. A newborn screener, a camp
    tablet and a handwritten card all print one word, and a system that
    demands amplitudes and noise floors before it will record anything simply
    does not get used in those settings.

    WHAT AN OUTCOME CANNOT DO, which this result states rather than quietly
    omitting:

    - NO COCHLEAR PROFILE. "Where along the cochlea" is a pattern across
      frequencies; one word has no pattern.
    - NO PRE-CLINICAL DAMAGE FINDING. That inference needs an absent emission
      AT A FREQUENCY compared against the threshold AT THAT FREQUENCY. A
      refer with no frequencies cannot distinguish outer hair cell damage
      from a middle-ear block or a noisy room, which is the entire content of
      the finding.
    - NO AUDIOGRAM RECONCILIATION. Same reason: the cross-check is
      per-frequency.

    So the outcome is recorded, interpreted as a screening decision, and
    explicitly marked as not supporting the inferences a full gram supports.
    Reporting it as if it did would be the one failure mode worse than not
    recording it at all.
    """
    normalised = normalise_outcome(outcome)
    if normalised is None:
        return {"ear": ear, "kind": kind, "available": False,
                "entry_mode": "outcome",
                "note": (f"'{outcome}' is not a screening outcome — expected "
                         "pass, refer or incomplete.")}

    spec = dict(PROTOCOLS.get(protocol, PROTOCOLS["screening"]))
    if protocol in CUSTOM_PROTOCOLS:
        spec["freqs"] = sorted({int(f) for f in (freqs or [])})
        spec["required"] = len(spec["freqs"]) or None

    headline = {
        "pass": "PASS — emissions present to the screening criterion.",
        "refer": ("REFER — emissions did not meet the screening criterion. A "
                  "refer is a referral for diagnostic testing, not a diagnosis "
                  "of hearing loss."),
        "incomplete": ("INCOMPLETE — the screen did not reach a decision. "
                       "Repeat it before the result is read either way."),
    }[normalised]

    interpretation = [headline]
    if protocol in CUSTOM_PROTOCOLS and spec["freqs"]:
        interpretation.append(
            f"Recorded against the frequencies tested: {spec['freqs']} Hz.")
    interpretation.append(
        "Recorded as an outcome only, with no per-frequency emission levels. "
        "That is a valid screening record, and it is all it is: the cochlear "
        "place of any dropout, the comparison against the audiogram frequency "
        "by frequency, and the pre-clinical outer-hair-cell finding all need "
        "the amplitudes and noise floors, so none of them is reported here.")
    if normalised == "refer":
        interpretation.append(
            "A refer has three common causes that an outcome alone cannot "
            "separate — outer hair cell damage, a middle-ear disorder, and a "
            "noisy or unsettled recording. Tympanometry distinguishes the "
            "second; a repeat in quiet distinguishes the third.")
    if note:
        interpretation.append(note)

    return {
        "ear": ear,
        "kind": kind,
        "available": True,
        "entry_mode": "outcome",
        "outcome": normalised,
        "recorded_outcome": normalised,
        "headline": headline,
        "note": note,
        "protocol": {"key": protocol, **spec},
        "custom_protocol": protocol in CUSTOM_PROTOCOLS,
        "points": [],
        # Every per-frequency list is empty BY CONSTRUCTION, not by accident.
        # Consumers that count these (the battery, the report) must see empty
        # rather than absent, so they do not fall back to "not tested".
        "passed_freqs": [], "referred_freqs": [], "invalid_freqs": [],
        "uninformative_freqs": [], "missing_freqs": [],
        "cochlear_profile": None,
        "mismatches": [],
        "preclinical_damage": [],
        "possible_unexplained_emissions": [],
        "unexplained_emissions": [],
        "interpretation": interpretation,
        "limits": [
            "No cochlear place — that needs a pattern across frequencies.",
            "No pre-clinical damage finding — that needs an absent emission at "
            "a frequency with a normal threshold at the same frequency.",
            "No frequency-by-frequency comparison against the audiogram.",
        ],
        "criterion": (f"as recorded by the screening instrument "
                      f"({criterion_text(spec['snr'])})"),
    }


def analyze(
    ear: str = "right",
    points: Optional[Sequence] = None,
    protocol: str = "screening",
    ac_numeric: Optional[Dict[int, Optional[float]]] = None,
    kind: str = "dpoae",
    required: Optional[int] = None,
    recorded_outcome: Optional[str] = None,
    outcome_note: str = "",
    freqs: Optional[Sequence[int]] = None,
) -> dict:
    """One OAE study: gram, protocol decision, cochlear profile, caveats.

    ``recorded_outcome`` switches to outcome-only entry (see ``from_outcome``)
    and is used only when no per-frequency points were supplied — values beat
    a summary whenever both are present, because they support strictly more.
    """
    from app.clinical.oae import oae_audiogram_agreement

    gram = dp_gram(points or [], protocol, ac_numeric, required=required)
    if not gram and recorded_outcome is not None:
        return from_outcome(ear=ear, outcome=recorded_outcome, protocol=protocol,
                            note=outcome_note, kind=kind, freqs=freqs)
    if not gram:
        return {"ear": ear, "kind": kind, "available": False,
                "note": "No emission data entered."}

    profile = cochlear_profile(gram)
    # Reuse the existing agreement engine so the audiogram cross-check is
    # identical whether OAEs arrive through this instrument or the full
    # battery endpoint. Frequencies too noisy to judge are left out: they
    # are evidence of neither damage nor a working cochlea.
    mismatches = oae_audiogram_agreement(
        {"points": [{"freq": r["freq"], "snr": r["snr"], "present": r["present"],
                     "status": r["status"], "amplitude": r["amplitude"],
                     "noise_floor": r["noise_floor"],
                     "noisy_response": r.get("noisy_response", False),
                     "valid": r["verdict"] != "invalid"}
                    for r in gram["points"]
                    if r["verdict"] != "invalid" or r.get("noisy_response")]},
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
        "entry_mode": "values",
        **gram,
        "cochlear_profile": profile,
        "mismatches": mismatches,
        "preclinical_damage": [m for m in mismatches
                               if m["kind"] == "preclinical_damage"],
        "possible_unexplained_emissions": [m for m in mismatches
                                           if m["kind"] == "possible_threshold_mismatch"],
        "unexplained_emissions": [m for m in mismatches
                                  if m["kind"] == "oae_threshold_mismatch"],
        "interpretation": interpretation,
        "ceiling_db_hl": OAE_CEILING_DB_HL,
        "default_snr_criterion": SNR_PRESENT_DB,
        "min_emission_db_spl": MIN_EMISSION_DB_SPL,
        "noise_floor_ceiling_db_spl": NOISE_FLOOR_CEILING_DB,
    }
