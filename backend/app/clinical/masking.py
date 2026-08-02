"""When masking is required, how much, and when it cannot be done at all.

Sound presented to one ear crosses the skull and can be heard by the other.
An unmasked threshold may therefore belong to the WRONG EAR — a shadow curve
that looks like real hearing and is not. Masking noise in the non-test ear is
what makes a threshold attributable, and deciding when it is needed is a
per-frequency question with an exact answer.

The conditions implemented here are the ones the clinical team supplied.

AIR CONDUCTION — mask when EITHER holds at a frequency:

    1.  AC(test ear) − AC(non-test ear)  >=  IA
    2.  AC(test ear) − BC(non-test ear)  >=  IA

Rule 2 is the one that catches the dangerous case: the non-test ear's *bone*
threshold is what the crossed signal actually has to exceed, so an ear with a
conductive loss can shadow at a level rule 1 alone would pass over.

Interaural attenuation depends on the transducer, and this is the single
choice that changes how much masking a clinic has to do:

    supra-aural earphones   40 dB
    insert earphones        50-60 dB

Inserts push the crossover 10-20 dB higher, which removes the need to mask in
a large share of cases and — more importantly — makes the masking dilemma
below far rarer.

BONE CONDUCTION — mask when EITHER holds:

    AC(test ear) − BC(unmasked)  >=  15 dB
    air-bone gap                 >=  15 dB

Bone conduction crosses the skull essentially unattenuated (IA ~ 0 dB), so an
unmasked bone threshold never belongs to a known ear on its own. The 15 dB
trigger is the point at which the gap is large enough that the other cochlea
could be the one responding.

THE MASKING DILEMMA. Masking has a floor and a ceiling: enough noise to cover
the crossed signal, but not so much that the noise itself crosses back and
shifts the test ear. When the floor rises above the ceiling there is no usable
level and the threshold cannot be masked at all. This happens in bilateral
conductive losses with large air-bone gaps, and it is a finding to report
rather than a gap to fill with a number.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import AC_FREQS, PTA_FREQS, ThresholdValue, ear_to_numeric

#: Interaural attenuation by transducer, dB. The reference gives inserts as a
#: 50-60 dB range; the conservative end is used for the decision so masking is
#: never skipped on an optimistic assumption.
TRANSDUCERS: Dict[str, dict] = {
    "supra_aural": {
        "label": "Supra-aural earphones (TDH/telephonics)",
        "ia_ac": 40,
        "ia_range": [40, 40],
        # Occlusion effect, dB — how much a covered ear's own bone-conducted
        # low frequencies are boosted. It raises the masking noise needed for
        # bone conduction and disappears above 1 kHz.
        "occlusion": {250: 30, 500: 20, 1000: 10, 2000: 0, 4000: 0, 8000: 0},
        "note": "The default in most clinics, and the least forgiving.",
    },
    "insert": {
        "label": "Insert earphones (ER-3A/ER-5A)",
        "ia_ac": 50,
        "ia_range": [50, 60],
        "occlusion": {250: 10, 500: 5, 1000: 0, 2000: 0, 4000: 0, 8000: 0},
        "note": ("Raises interaural attenuation by 10-20 dB, which removes the "
                 "need to mask in many cases and makes the masking dilemma rare."),
    },
    "circumaural": {
        "label": "Circumaural earphones",
        "ia_ac": 45,
        "ia_range": [45, 45],
        "occlusion": {250: 25, 500: 15, 1000: 10, 2000: 0, 4000: 0, 8000: 0},
        "note": "Between supra-aural and insert.",
    },
}
DEFAULT_TRANSDUCER = "supra_aural"

#: Bone conduction crosses the skull with essentially no attenuation.
INTERAURAL_ATTENUATION_BC = 0
#: Air-bone gap at or above which bone-conduction masking is required.
BC_MASKING_GAP_DB = 15
#: Safety margin subtracted from the maximum masking level.
MAX_MASKING_SAFETY_DB = 5

CITATIONS = [
    "Interaural attenuation: 40 dB supra-aural, 50-60 dB insert (clinical reference)",
    "Occlusion effect after Goldstein & Hayes (1965)",
    "Plateau method — Hood (1960)",
]


def transducer_spec(name: Optional[str]) -> dict:
    return TRANSDUCERS.get(name or DEFAULT_TRANSDUCER, TRANSDUCERS[DEFAULT_TRANSDUCER])


# --------------------------------------------------------------------------
# the two decisions
# --------------------------------------------------------------------------
def ac_masking_required(ac_te: Optional[float], ac_nte: Optional[float],
                        bc_nte: Optional[float], ia: int) -> dict:
    """Air-conduction masking decision at one frequency.

    Both rules are evaluated and both are reported, because which one fires
    tells the clinician why. Rule 2 firing alone means the non-test ear has a
    conductive component — its bone threshold is better than its air threshold,
    so the crossed signal has a lower bar to clear than rule 1 suggests.
    """
    rules: List[dict] = []
    if ac_te is None:
        return {"required": False, "rules": rules, "testable": False}

    if ac_nte is not None:
        margin = round(ac_te - ac_nte, 1)
        rules.append({
            "rule": "AC(TE) − AC(NTE) ≥ IA",
            "value": margin, "threshold": ia, "met": margin >= ia,
        })
    if bc_nte is not None:
        margin = round(ac_te - bc_nte, 1)
        rules.append({
            "rule": "AC(TE) − BC(NTE) ≥ IA",
            "value": margin, "threshold": ia, "met": margin >= ia,
        })

    return {
        "required": any(r["met"] for r in rules),
        "rules": rules,
        "testable": bool(rules),
    }


def bc_masking_required(ac_te: Optional[float],
                        bc_unmasked: Optional[float]) -> dict:
    """Bone-conduction masking decision at one frequency.

    One measurement drives both stated conditions: the air-bone gap. With no
    interaural attenuation to rely on, a gap of 15 dB or more means the
    opposite cochlea may be the one responding.
    """
    if ac_te is None or bc_unmasked is None:
        return {"required": False, "rules": [], "testable": False, "abg": None}

    gap = round(ac_te - bc_unmasked, 1)
    rules = [{
        "rule": "AC(TE) − BC(unmasked) ≥ 15 dB",
        "value": gap, "threshold": BC_MASKING_GAP_DB, "met": gap >= BC_MASKING_GAP_DB,
    }, {
        "rule": "ABG ≥ 15 dB",
        "value": gap, "threshold": BC_MASKING_GAP_DB, "met": gap >= BC_MASKING_GAP_DB,
    }]
    return {
        "required": gap >= BC_MASKING_GAP_DB,
        "rules": rules,
        "testable": True,
        "abg": gap,
    }


# --------------------------------------------------------------------------
# how much masking, and whether it is possible
# --------------------------------------------------------------------------
def masking_levels(mode: str, freq: int, ac_te: Optional[float],
                   bc_te: Optional[float], ac_nte: Optional[float],
                   spec: dict) -> dict:
    """Minimum and maximum effective masking, and whether they overlap.

    Minimum has to cover the signal that crossed over. Maximum is the point at
    which the masking noise itself crosses back and starts shifting the test
    ear. A plateau exists only between them.
    """
    ia = spec["ia_ac"]
    minimum = maximum = None

    if mode == "ac":
        if ac_nte is not None and ac_te is not None:
            # Enough noise to raise the non-test ear above the crossed signal.
            minimum = round(ac_nte + max(ac_te - ia, 0), 1)
    else:
        if ac_nte is not None:
            # Bone conduction crosses unattenuated, and covering the non-test
            # ear boosts its own low frequencies — the occlusion effect.
            minimum = round(ac_nte + spec["occlusion"].get(freq, 0), 1)

    if bc_te is not None:
        maximum = round(bc_te + ia - MAX_MASKING_SAFETY_DB, 1)

    dilemma = (minimum is not None and maximum is not None and minimum > maximum)
    return {
        "minimum": minimum,
        "maximum": maximum,
        "plateau_width": (None if minimum is None or maximum is None
                          else round(maximum - minimum, 1)),
        "dilemma": dilemma,
    }


# --------------------------------------------------------------------------
# the plan for one ear
# --------------------------------------------------------------------------
def masking_plan(test_ac: Dict[int, Optional[ThresholdValue]],
                 test_bc: Dict[int, Optional[ThresholdValue]],
                 other_ac: Dict[int, Optional[ThresholdValue]],
                 other_bc: Dict[int, Optional[ThresholdValue]],
                 transducer: str = DEFAULT_TRANSDUCER,
                 masked: bool = False,
                 ear: str = "right") -> dict:
    """Frequency-by-frequency masking requirement for one ear."""
    spec = transducer_spec(transducer)
    ia = spec["ia_ac"]
    t_ac, t_bc = ear_to_numeric(test_ac), ear_to_numeric(test_bc)
    o_ac, o_bc = ear_to_numeric(other_ac), ear_to_numeric(other_bc)

    rows: List[dict] = []
    for freq in AC_FREQS:
        ac = ac_masking_required(t_ac.get(freq), o_ac.get(freq),
                                 o_bc.get(freq), ia)
        # Bone conduction is not tested above 4 kHz.
        bc = (bc_masking_required(t_ac.get(freq), t_bc.get(freq))
              if freq in PTA_FREQS or freq == 250
              else {"required": False, "rules": [], "testable": False, "abg": None})

        ac_levels = masking_levels("ac", freq, t_ac.get(freq), t_bc.get(freq),
                                   o_ac.get(freq), spec) if ac["required"] else None
        bc_levels = masking_levels("bc", freq, t_ac.get(freq), t_bc.get(freq),
                                   o_ac.get(freq), spec) if bc["required"] else None

        rows.append({
            "freq": freq,
            "ac_threshold": t_ac.get(freq),
            "bc_threshold": t_bc.get(freq),
            "ac": ac, "bc": bc,
            "ac_levels": ac_levels, "bc_levels": bc_levels,
            "dilemma": bool((ac_levels and ac_levels["dilemma"])
                            or (bc_levels and bc_levels["dilemma"])),
        })

    ac_freqs = [r["freq"] for r in rows if r["ac"]["required"]]
    bc_freqs = [r["freq"] for r in rows if r["bc"]["required"]]
    dilemma_freqs = [r["freq"] for r in rows if r["dilemma"]]
    required = bool(ac_freqs or bc_freqs)

    reasons: List[str] = []
    if ac_freqs:
        # Naming which rule fired is the difference between "mask here" and
        # "mask here, and this is what it tells you about the other ear".
        by_bc_only = [r["freq"] for r in rows
                      if r["ac"]["required"]
                      and not any(x["met"] for x in r["ac"]["rules"]
                                  if x["rule"].startswith("AC(TE) − AC"))]
        reasons.append(
            f"AC masking indicated at {ac_freqs} Hz (interaural attenuation "
            f"{ia} dB, {spec['label']}).")
        if by_bc_only:
            reasons.append(
                f"At {by_bc_only} Hz only the AC−BC rule fires: the opposite ear "
                "has a conductive component, so the crossed signal clears a lower "
                "bar than the air thresholds suggest.")
    if bc_freqs:
        reasons.append(
            f"BC masking indicated at {bc_freqs} Hz — air-bone gap "
            f"≥ {BC_MASKING_GAP_DB} dB with no interaural attenuation to rely on.")
    if dilemma_freqs:
        reasons.append(
            f"Masking dilemma at {dilemma_freqs} Hz: the noise needed to cover "
            "the crossed signal exceeds the level at which it crosses back. "
            "These thresholds cannot be masked conventionally — use insert "
            "earphones, or report them as unmaskable rather than as measured.")

    return {
        "ear": ear,
        "transducer": {"key": transducer or DEFAULT_TRANSDUCER, **spec},
        "interaural_attenuation_db": ia,
        "masking_indicated": required,
        "masking_reported": masked,
        # A validity warning only when masking was indicated and not recorded.
        "warning": required and not masked,
        "ac_freqs": ac_freqs,
        "bc_freqs": bc_freqs,
        "dilemma_freqs": dilemma_freqs,
        "has_dilemma": bool(dilemma_freqs),
        "rows": rows,
        "reasons": reasons,
        "message": (
            "Masking was indicated but not recorded — these thresholds may be a "
            "shadow curve from the opposite ear. Confirm masked thresholds before "
            "interpreting."
        ) if (required and not masked) else None,
        "citations": list(CITATIONS),
    }


def masking_review(right, left, transducer: str = DEFAULT_TRANSDUCER) -> dict:
    """Both ears, plus the headline a clinician needs first."""
    plans = {
        "right": masking_plan(right.ac, right.bc, left.ac, left.bc,
                              transducer, right.masked, "right"),
        "left": masking_plan(left.ac, left.bc, right.ac, right.bc,
                             transducer, left.masked, "left"),
    }
    indicated = [s for s in ("right", "left") if plans[s]["masking_indicated"]]
    unmasked = [s for s in ("right", "left") if plans[s]["warning"]]
    dilemma = [s for s in ("right", "left") if plans[s]["has_dilemma"]]

    if dilemma:
        headline = (f"Masking dilemma in the {' and '.join(dilemma)} ear — these "
                    "thresholds cannot be masked with this transducer.")
    elif unmasked:
        headline = (f"Masking was indicated in the {' and '.join(unmasked)} ear "
                    "but not recorded.")
    elif indicated:
        headline = (f"Masking indicated and recorded in the "
                    f"{' and '.join(indicated)} ear.")
    else:
        headline = "No masking required — no frequency reaches the crossover point."

    return {
        **plans,
        "transducer": plans["right"]["transducer"],
        "any_indicated": bool(indicated),
        "any_unmasked": bool(unmasked),
        "any_dilemma": bool(dilemma),
        "headline": headline,
        "note": ("Masking decides which ear a threshold belongs to. An unmasked "
                 "threshold past the crossover point is not a measurement of the "
                 "test ear."),
    }
