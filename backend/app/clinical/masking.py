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

BSA Recommended Procedure, Pure-tone audiometry (2018), section 8.6.1 (Rule 1)
uses 40 dB for supra- or circum-aural earphones and 55 dB for inserts, 55 being
the MINIMUM transcranial loss with correctly inserted earphones (Munro & Agnew
1999). Inserts are decided here at 50 dB, the conservative end of the clinical
team's 50-60 dB reference: an insert that is not seated deeply loses part of
that attenuation, and deciding at 50 means a 50-54 dB difference is masked
rather than assumed safe. The cost is extra masking, never a missed shadow.

BONE CONDUCTION — mask when EITHER holds:

    AC(test ear) − BC(unmasked)  >=  15 dB
    air-bone gap                 >=  15 dB

Bone conduction crosses the skull essentially unattenuated (IA ~ 0 dB), so an
unmasked bone threshold never belongs to a known ear on its own. The 15 dB
trigger is the point at which the gap is large enough that the other cochlea
could be the one responding.

The 15 dB trigger is the clinical team's choice and is LESS sensitive than BSA
(2018) section 8.6.2 (Rule 2), which masks whenever the not-masked BC is better
than the AC by 10 dB or more. It is kept because it matches the type rules:
rules.py counts an air-bone gap as significant only when it exceeds 10 dB,
i.e. 15 dB or more on 5 dB steps, and masking can only raise a bone threshold,
so a 10 dB gap cannot become significant by being masked and cannot change
the loss type. BSA's own notes on Rule 2 allow that masking small air-bone gaps
may not benefit management. A 10 dB gap is therefore not masked here even
though BSA Rule 2 would mask it.

THE MASKING DILEMMA. Masking has a floor and a ceiling: enough noise to cover
the crossed signal, but not so much that the noise itself crosses back and
shifts the test ear. When the floor rises above the ceiling there is no usable
level and the threshold cannot be masked at all. This happens in bilateral
conductive losses with large air-bone gaps, and it is a finding to report
rather than a gap to fill with a number.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.clinical.safety import NORMAL_LIMIT_DB
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
#: Air-bone gap at or above which bone-conduction masking is required. BSA
#: (2018) Rule 2 uses 10 dB; see the module docstring for why this is 15.
BC_MASKING_GAP_DB = 15
#: Safety margin subtracted from the maximum masking level.
MAX_MASKING_SAFETY_DB = 5
#: Safety factor added to the minimum air-conduction masking level, covering
#: inter-subject variation in how effective a given noise level is. 10 dB is
#: Martin's (1967, 1974, 1980) safety factor, as used in the initial masking
#: level of the clinical masking literature (Yacullo, "Clinical masking", in
#: Katz, Handbook of Clinical Audiology).
MIN_MASKING_SAFETY_DB = 10

CITATIONS = [
    "Interaural attenuation: 40 dB supra-aural, 50-60 dB insert (clinical reference); "
    "BSA (2018) Rule 1 uses 40 dB supra/circum-aural, 55 dB insert",
    "Occlusion effect after Goldstein & Hayes (1965)",
    "Plateau method — Hood (1960); BSA Recommended Procedure (2018) section 8.8",
    "Minimum masking: crossed signal plus non-test air-bone gap (after Lidén, Nilsson "
    "& Anderson 1959; Studebaker 1964) with a 10 dB safety factor (Martin 1967, 1974, 1980)",
]


def transducer_spec(name: Optional[str]) -> dict:
    return TRANSDUCERS.get(name or DEFAULT_TRANSDUCER, TRANSDUCERS[DEFAULT_TRANSDUCER])


# --------------------------------------------------------------------------
# the two decisions
# --------------------------------------------------------------------------
def ac_masking_required(ac_te: Optional[float], ac_nte: Optional[float],
                        bc_nte: Optional[float], ia: int,
                        bc_nte_estimate: Optional[dict] = None) -> dict:
    """Air-conduction masking decision at one frequency.

    Both rules are evaluated and both are reported, because which one fires
    tells the clinician why. Rule 2 firing alone means the non-test ear has a
    conductive component — its bone threshold is better than its air threshold,
    so the crossed signal has a lower bar to clear than rule 1 suggests.

    Without a measured BC(NTE) — always the case at 8 kHz, where bone
    conduction is not tested — rule 2 cannot be applied. ``bc_nte_estimate``
    then carries the non-test ear's bone threshold estimated from its own
    air-bone gap at the nearest frequency where both were measured
    (``_estimated_bc_nte``). If rule 1 does not fire but that estimate would
    meet rule 2, the result is ``undetermined``: masking cannot be ruled out,
    and the plan says so instead of passing the frequency as unmasked-safe.
    """
    rules: List[dict] = []
    if ac_te is None:
        return {"required": False, "rules": rules, "testable": False,
                "undetermined": False}

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

    required = any(r["met"] for r in rules)
    undetermined = False
    if not required and bc_nte is None and bc_nte_estimate is not None:
        margin = round(ac_te - bc_nte_estimate["value"], 1)
        if margin >= ia:
            undetermined = True
            rules.append({
                "rule": "AC(TE) − BC(NTE) ≥ IA",
                "value": margin, "threshold": ia, "met": None,
                "estimated": True,
                "note": bc_nte_estimate["note"],
            })

    return {
        "required": required,
        "rules": rules,
        "testable": bool(rules),
        "undetermined": undetermined,
    }


def _estimated_bc_nte(freq: int, o_ac: Dict[int, Optional[float]],
                      o_bc: Dict[int, Optional[float]],
                      o_bc_nr: set) -> Optional[dict]:
    """The non-test ear's bone threshold at ``freq`` where it was not measured,
    from its own air-bone gap at the nearest frequency with both measured.

    Used only to decide whether rule 2 can be ruled out, never as a
    threshold. Nearest by octave distance; on a tie the larger gap is used, so
    the estimate never makes a crossover look less likely than the measured
    gaps allow. None when the non-test ear has no air threshold at ``freq`` or
    no frequency with both thresholds measured.
    """
    ac_here = o_ac.get(freq)
    if ac_here is None:
        return None
    measured = [f for f in AC_FREQS
                if f != freq and f not in o_bc_nr
                and o_ac.get(f) is not None and o_bc.get(f) is not None]
    if not measured:
        return None
    order = {f: i for i, f in enumerate(AC_FREQS)}
    distance = min(abs(order[f] - order[freq]) for f in measured)
    nearest = [f for f in measured if abs(order[f] - order[freq]) == distance]
    gaps = {f: max(o_ac[f] - o_bc[f], 0.0) for f in nearest}
    source = max(nearest, key=lambda f: (gaps[f], -f))
    gap = gaps[source]
    return {
        "value": ac_here - gap,
        "source_freq": source,
        "gap": gap,
        "note": (f"the non-test ear's bone conduction was not measured at {freq} Hz; "
                 f"with the {gap:g} dB air-bone gap it shows at {source} Hz its bone "
                 f"threshold there may be as good as {ac_here - gap:g} dB HL"),
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
                   spec: dict, bc_nte: Optional[float] = None) -> dict:
    """Minimum and maximum effective masking, and whether they overlap.

    Minimum has to cover the signal that crossed over. Maximum is the point at
    which the masking noise itself crosses back and starts shifting the test
    ear. A plateau exists only between them.

    Air-conduction minimum, formula method (after Lidén, Nilsson & Anderson
    1959 and Studebaker 1964) with Martin's 10 dB safety factor:

        M_min = AC(TE) − IA + ABG(NTE) + 10

    AC(TE) − IA is the crossed tone's level at the non-test cochlea. The noise
    reaches that cochlea by air, so a conductive gap in the non-test ear
    attenuates it and is added back. ``bc_nte`` is the non-test ear's measured
    bone threshold; when it is untested or a no-response (pass None) the gap
    is taken as if that bone threshold were 0 dB HL, i.e. ABG = AC(NTE), so
    the floor is never lowered by a guess. The floor is also never below
    Martin's initial masking level, AC(NTE) + 10: noise below the non-test
    ear's own threshold masks nothing.

    BSA (2018) section 8.8 finds the masked threshold empirically, starting
    the noise at the non-test ear's threshold and seeking a plateau. This
    minimum is the planning estimate that decides whether a plateau can exist
    at all; it does not replace finding one.
    """
    ia = spec["ia_ac"]
    minimum = maximum = None

    if mode == "ac":
        if ac_nte is not None and ac_te is not None:
            gap_nte = (max(ac_nte - bc_nte, 0) if bc_nte is not None
                       else max(ac_nte, 0))
            formula = max(ac_te - ia, 0) + gap_nte + MIN_MASKING_SAFETY_DB
            initial = ac_nte + MIN_MASKING_SAFETY_DB
            minimum = round(max(formula, initial), 1)
    else:
        if ac_nte is not None:
            # Bone conduction crosses unattenuated, and covering the non-test
            # ear boosts its own low frequencies — the occlusion effect.
            # The floor is BSA (2018) section 8.8's starting level (effective
            # masking equal to the non-test ear's threshold) plus occlusion.
            # Martin's 10 dB safety factor, added to the air-conduction floor
            # above, is NOT added here: with it, a 35 dB bilateral air-bone
            # gap (AC 50 / BC 15) on inserts would turn from maskable to a
            # dilemma at 250 and 500 Hz (floor 70 and 65 against a ceiling of
            # 60), and whether to plan bone masking that conservatively is
            # the clinical team's decision, not a formula's.
            minimum = round(ac_nte + spec["occlusion"].get(freq, 0), 1)

    if bc_te is not None:
        # Overmasking ceiling: the noise reaches the test cochlea at its level
        # minus IA, so it must stay below BC(TE) + IA, less a 5 dB margin. IA
        # is the transducer's minimum, so this is the lowest, most cautious
        # ceiling. With supra-aural earphones a very sensitive test-ear bone
        # threshold therefore meets the 30 dB occlusion floor at 250 Hz:
        # BC(TE) -5 against AC(NTE) 10 gives ceiling 30, floor 40, a dilemma
        # that inserts remove (floor 20, ceiling 40), as the dilemma message
        # advises.
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
    # A bone no-response only bounds the threshold from below (the vibrator's
    # output limit), so it cannot size the non-test ear's air-bone gap.
    o_bc_nr = {int(f) for f, v in (other_bc or {}).items() if v == "NR"}

    rows: List[dict] = []
    for freq in AC_FREQS:
        estimate = (_estimated_bc_nte(freq, o_ac, o_bc, o_bc_nr)
                    if o_bc.get(freq) is None else None)
        ac = ac_masking_required(t_ac.get(freq), o_ac.get(freq),
                                 o_bc.get(freq), ia, bc_nte_estimate=estimate)
        # Bone conduction is not tested above 4 kHz.
        bc = (bc_masking_required(t_ac.get(freq), t_bc.get(freq))
              if freq in PTA_FREQS or freq == 250
              else {"required": False, "rules": [], "testable": False, "abg": None})

        bc_nte_for_gap = None if freq in o_bc_nr else o_bc.get(freq)
        ac_levels = masking_levels("ac", freq, t_ac.get(freq), t_bc.get(freq),
                                   o_ac.get(freq), spec,
                                   bc_nte=bc_nte_for_gap) if ac["required"] else None
        bc_levels = masking_levels("bc", freq, t_ac.get(freq), t_bc.get(freq),
                                   o_ac.get(freq), spec) if bc["required"] else None

        dilemma = bool((ac_levels and ac_levels["dilemma"])
                       or (bc_levels and bc_levels["dilemma"]))
        rows.append({
            "freq": freq,
            "ac_threshold": t_ac.get(freq),
            "bc_threshold": t_bc.get(freq),
            "ac": ac, "bc": bc,
            "ac_levels": ac_levels, "bc_levels": bc_levels,
            "dilemma": dilemma,
            # A dilemma where the test ear's air conduction is within normal
            # limits can only leave the size of an air-bone gap behind normal
            # hearing unconfirmed: the cochlea there is normal whichever ear
            # answered the bone vibrator, so degree and type stand.
            "dilemma_affects_degree_or_type": dilemma and not (
                t_ac.get(freq) is not None and t_ac[freq] <= NORMAL_LIMIT_DB),
        })

    ac_freqs = [r["freq"] for r in rows if r["ac"]["required"]]
    bc_freqs = [r["freq"] for r in rows if r["bc"]["required"]]
    undetermined_freqs = [r["freq"] for r in rows if r["ac"].get("undetermined")]
    dilemma_freqs = [r["freq"] for r in rows if r["dilemma"]]
    consequential_dilemma_freqs = [r["freq"] for r in rows
                                   if r["dilemma_affects_degree_or_type"]]
    required = bool(ac_freqs or bc_freqs)
    # Masking that cannot be ruled out is owed until it is done or the
    # missing bone threshold is measured — never assumed unnecessary.
    owed = required or bool(undetermined_freqs)

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
    if undetermined_freqs:
        notes = "; ".join(
            next(x["note"] for x in r["ac"]["rules"] if x.get("estimated"))
            for r in rows if r["ac"].get("undetermined"))
        reasons.append(
            f"AC masking cannot be ruled out at {undetermined_freqs} Hz: rule 1 does "
            f"not fire, and rule 2 cannot be applied — {notes}. Mask there, or "
            "measure the opposite ear's bone conduction, before taking the "
            "threshold as this ear's.")
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
        minor = [f for f in dilemma_freqs if f not in consequential_dilemma_freqs]
        if minor:
            reasons.append(
                f"At {minor} Hz air conduction is within normal limits "
                f"(≤ {NORMAL_LIMIT_DB} dB HL), so the dilemma leaves only the size "
                "of the air-bone gap there unconfirmed, not the degree or type "
                "of hearing.")

    return {
        "ear": ear,
        "transducer": {"key": transducer or DEFAULT_TRANSDUCER, **spec},
        "interaural_attenuation_db": ia,
        "masking_indicated": required,
        "masking_reported": masked,
        # A validity warning when masking was indicated, or cannot be ruled
        # out, and was not recorded.
        "warning": owed and not masked,
        "ac_freqs": ac_freqs,
        "bc_freqs": bc_freqs,
        "undetermined_freqs": undetermined_freqs,
        "dilemma_freqs": dilemma_freqs,
        "has_dilemma": bool(dilemma_freqs),
        "consequential_dilemma_freqs": consequential_dilemma_freqs,
        "rows": rows,
        "reasons": reasons,
        "message": (
            ("Masking was indicated but not recorded — these thresholds may be a "
             "shadow curve from the opposite ear. Confirm masked thresholds before "
             "interpreting.") if required else
            ("Masking could not be ruled out and was not recorded — these "
             "thresholds may be a shadow curve from the opposite ear. Mask, or "
             "measure the opposite ear's bone conduction, before interpreting.")
        ) if (owed and not masked) else None,
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
