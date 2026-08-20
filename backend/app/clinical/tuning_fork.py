"""Tuning fork tests: Rinne, Weber, Bing, ABC, Schwabach and Gelle.

The oldest instruments in audiology and still the only ones that work at a
bedside, in a doorway, or in a camp with no power. What they give is not a
threshold — it is a *side* and a *type*, and one quantitative fact that is
easy to miss:

    THE FREQUENCY AT WHICH THE RINNE TURNS NEGATIVE BRACKETS THE SIZE OF THE
    AIR-BONE GAP.

Air conduction is normally far more efficient than bone conduction, so a
normal or purely sensorineural ear hears the fork louder at the meatus. Middle
ear pathology attenuates the air route only. Once the gap exceeds a
fork-specific crossover value the bone presentation wins and the Rinne
"reverses" — and because that crossover rises steeply with frequency, testing
three forks brackets the gap:

    256 Hz negative, 512 positive     ->  gap of roughly 15-30 dB
    256 and 512 negative, 1024 positive ->  roughly 30-45 dB
    all three negative                ->  roughly 45 dB or more

Those crossover values are the classical teaching figures and they carry only
MEDIUM confidence — empirical series place the 512 Hz transition lower than the
textbook 30 dB, nearer 20-25. The bands are therefore reported as bands, never
as a point estimate, and ``confidence`` travels with every one of them.

FORKS THAT CANNOT DO THIS. There is no trustworthy crossover value for 2048 or
4096 Hz, so this module refuses to compute one rather than extrapolating the
15/30/45 series. Those forks decay within a couple of seconds, radiate little
energy, couple poorly to the mastoid, and are inaudible to exactly the
presbycusic population most often tested. They remain available for crude
high-frequency air-conduction screening, labelled as such.

THE MOST DANGEROUS RESULT IN THE WHOLE BATTERY is the FALSE-NEGATIVE RINNE. A
severe or profound sensorineural ear hears nothing at its own meatus, but bone
conduction crosses the skull essentially unattenuated and is picked up by the
opposite cochlea. Bone therefore appears louder than air, the Rinne reads
negative, and an ear with no conductive component at all is reported as
conductive. The tell is the Weber: it lateralises AWAY from the ear whose
Rinne is negative, which cannot happen in a genuine conductive loss. The
module treats that combination as a contradiction to be flagged, never as a
diagnosis, and asks for masking of the non-test ear.

PRECEDENCE. Rules are layered, and a lower layer always wins:

    L0  validity gates          suppress the output entirely
    L1  contradictions          flag, never diagnose
    L2  warnings                downgrade to provisional
    L3  the Rinne x Weber grid  the diagnostic output
    L4  annotations             added to whatever L3 produced

Over the twelve cells of {positive, negative} x {positive, negative} x
{right, left, midline}, the grid rules form a complete and mutually exclusive
partition: exactly one fires on any complete input. That is asserted by test.

WHAT THIS MODULE MAY NOT OUTPUT. No hearing level in dB, no numeric air-bone
gap, and no named disease. Permitted outputs are a type of loss, a side, a
*band* of gap size, flags and recommendations. A fork battery that names a
disease is overreaching, and one that quotes a threshold is lying.

AND WHEN THE AUDIOGRAM DISAGREES, THE AUDIOGRAM WINS. Where thresholds exist,
the predicted gap band is checked against the measured air-bone gap at the
matching audiometric frequency, and a fork-derived conductive finding in an ear
the audiogram shows to have no gap is retracted rather than reconciled.

Sources: the classical crossover series and the false-negative mechanism are
standard across otolaryngology texts; StatPearls 'Rinne Test' (NBK431071),
'Weber Test' (NBK526135) and 'Bone Conduction Evaluation' (NBK578177) were used
for method and placement. Occlusion-effect frequency dependence follows the
insert-earphone correction data of Dean & Martin (2000) — 9 dB at 250 Hz, 7 dB
at 500 Hz, 0 dB at 1000 Hz. Those figures were measured with insert earphones
rather than a tragal press, so they are used here only for the FREQUENCY
DEPENDENCE they establish, which is well attested: large at 250 Hz, smaller at
500, negligible by 1000. That is why the Bing is restricted to the two low
forks. The absolute magnitude of a finger-occluded ear is not asserted. Published sensitivity and specificity figures for these tests could not
be verified and are therefore not asserted anywhere in this module.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import ThresholdValue, ear_to_numeric

# ==========================================================================
# The forks
# ==========================================================================

#: Response vocabulary for a single Rinne observation.
RINNE_RESPONSES = {
    "ac_louder": "Air louder (fork heard better at the meatus)",
    "bc_louder": "Bone louder (fork heard better on the mastoid)",
    "equal": "Equal / cannot choose",
    "not_heard": "Not heard at either placement",
}

#: Midline sites at which a Weber may legitimately be taken.
WEBER_SITES = {
    "upper_incisors": "Upper incisors — the most efficient coupling",
    "vertex": "Vertex — part the hair",
    "glabella_forehead": "Glabella / midline forehead — the usual site",
    "nasion": "Nasion (bridge of the nose)",
    "chin_symphysis": "Chin (mandibular symphysis)",
}

#: Per-fork properties. ``crossover_db`` is the air-bone gap at or above which
#: the Rinne is expected to reverse at this frequency; ``crossover_range`` is
#: the spread across sources. Both are ``None`` where no trustworthy value
#: exists — the field is deliberately empty rather than extrapolated.
FORKS: Dict[int, dict] = {
    250: {
        "fork_hz": 256,
        "crossover_db": 15,
        "crossover_range": [15, 20],
        "confidence": "medium",
        "rinne": True,
        "weber": True,
        "bing": True,
        "role": "adjunct",
        "note": (
            "The most sensitive fork — reverses at the smallest gap — but the "
            "most contaminated by vibrotactile sensation, which a patient may "
            "report as hearing. Preferred fork for the Bing, where the "
            "occlusion effect is largest. A negative Rinne here alone must be "
            "confirmed at 512 Hz."),
    },
    500: {
        "fork_hz": 512,
        "crossover_db": 30,
        "crossover_range": [20, 30],
        "confidence": "medium",
        "rinne": True,
        "weber": True,
        "bing": True,
        "role": "standard",
        "note": (
            "The clinical standard for the whole battery and the reference "
            "frequency for essentially all published accuracy data. Classical "
            "crossover is 30 dB; empirical series place the practical "
            "transition nearer 20-25, so the band is reported rather than the "
            "textbook figure alone."),
    },
    1000: {
        "fork_hz": 1024,
        "crossover_db": 45,
        "crossover_range": [45, 50],
        "confidence": "medium",
        "rinne": True,
        "weber": True,
        "bing": False,
        "role": "adjunct",
        "note": (
            "The least sensitive and therefore most specific fork: it reverses "
            "only near the largest gap a purely conductive lesion can produce. "
            "Minimal vibrotactile contamination, which makes it the safest "
            "choice when 256 Hz is suspect. It is also the fork on which a "
            "FALSE-negative Rinne most often appears, so masking is required "
            "before a negative result here is accepted. The occlusion effect "
            "is already negligible, so 'no change' on a Bing is uninterpretable "
            "rather than negative."),
    },
    2000: {
        "fork_hz": 2048,
        "crossover_db": None,
        "crossover_range": None,
        "confidence": "medium",
        "rinne": False,
        "weber": False,
        "bing": False,
        "role": "screen_only",
        "note": (
            "Not part of the Rinne battery and NO trustworthy crossover value "
            "exists — the crossover is null by design, not by omission. Decay "
            "is very rapid, radiated energy low, mastoid coupling poor, and "
            "high-frequency hearing is lost first with age, so a large share of "
            "the tested population cannot hear it by either route. Usable only "
            "as a crude high-frequency air-conduction screen. The occlusion "
            "effect is absent here, so the Bing and Gelle are invalid."),
    },
    4000: {
        "fork_hz": 4096,
        "crossover_db": None,
        "crossover_range": None,
        "confidence": "medium",
        "rinne": False,
        "weber": False,
        "bing": False,
        "role": "screen_only",
        "note": (
            "The shortest decay of the set — the tone dies within a couple of "
            "seconds, so neither an air-versus-bone comparison nor a "
            "lateralisation judgement is dependable. A 'not heard' here carries "
            "no information about an air-bone gap. Air-conduction screening "
            "only; the Bing and Gelle are invalid."),
    },
}

#: Forks that may drive a Rinne, lowest first — the bracketing ladder.
RINNE_FORKS: List[int] = [f for f, p in FORKS.items() if p["rinne"]]

#: Forks at which the occlusion effect is large enough for a Bing to mean
#: anything. Above these, 'no change' is the normal finding and recording it as
#: a negative Bing produces a spurious conductive diagnosis in every patient.
BING_FORKS: List[int] = [f for f, p in FORKS.items() if p["bing"]]

#: Bone conduction crosses the skull essentially unattenuated. This is the
#: whole mechanism of the false-negative Rinne.
INTERAURAL_ATTENUATION_BC = 0

#: Practical resolution of the Weber, dB. Lateralisation has been reported at
#: interaural differences as small as 2.5-4 dB, so this is an order-of-magnitude
#: statement and NOT a decision threshold — a midline Weber does not exclude an
#: asymmetry smaller than this.
WEBER_RESOLUTION_DB = 5

#: Frequencies at which the vibrating fork can be FELT rather than heard, which
#: a patient may report as hearing. The effect is largest at the lowest
#: frequency and the reason 256 Hz is an adjunct rather than the standard.
TACTILE_RISK = {250: "high", 500: "low", 1000: "negligible",
                2000: "negligible", 4000: "negligible"}

CITATIONS = (
    "StatPearls, Rinne Test (NCBI Bookshelf NBK431071)",
    "StatPearls, Weber Test (NCBI Bookshelf NBK526135)",
    "StatPearls, Bone Conduction Evaluation (NCBI Bookshelf NBK578177)",
    "Dean & Martin (2000), occlusion-effect corrections for insert earphones: "
    "9 dB at 250 Hz, 7 dB at 500 Hz, 0 dB at 1000 Hz",
)

LIMITS = (
    "Tuning fork tests give a side and a type, never a hearing level. No "
    "result here is a threshold and none may be entered on an audiogram.",
    "They are specific but insensitive: a positive Rinne does not exclude an "
    "air-bone gap smaller than the fork's crossover value.",
    "The crossover values are classical teaching figures carrying medium "
    "confidence; sources disagree, most sharply at 512 Hz. Bands are reported "
    "rather than point estimates.",
    "Published sensitivity and specificity for these tests could not be "
    "verified, so no accuracy figure is quoted anywhere in this module.",
    "A negative Rinne is only trustworthy with the non-test ear masked. "
    "Without masking, a dead ear reads as a conductive one.",
    "The Schwabach and the ABC are measured against the examiner's own bone "
    "conduction. An examiner with unrecognised high-frequency loss makes them "
    "read normal, and there is no internal way to detect that.",
    "Otoscopy comes first. A canal fully occluded by wax produces a genuine "
    "conductive pattern from a trivial and reversible cause.",
)


# ==========================================================================
# Rinne
# ==========================================================================


def rinne_sign(response: Optional[str]) -> str:
    """Map a raw observation to a sign.

    ``equivocal`` is preserved as its own value rather than folded into either
    sign. A patient who cannot choose between the two placements is telling you
    the gap is near this fork's crossover, which is information; recoding it as
    positive or negative throws that away and fabricates a decision.
    """
    return {
        "ac_louder": "positive",
        "bc_louder": "negative",
        "equal": "equivocal",
        "not_heard": "uninterpretable",
    }.get((response or "").lower(), "uninterpretable")


def gap_bracket(rinne_by_freq: Dict[int, str]) -> dict:
    """Bracket the air-bone gap from which forks reversed.

    Walks the usable forks from lowest to highest. The gap is at least the
    crossover of the highest fork that went negative, and below the crossover
    of the lowest fork that stayed positive. Only forks with a trustworthy
    crossover take part — 2 and 4 kHz are ignored here however they were
    answered, because they have no crossover value to contribute.

    Returns ``detected: False`` when every usable fork stayed positive. That is
    NOT "no gap": it means no gap large enough for the lowest fork to detect,
    which is the sensitivity limit of the whole method and is said as such.
    """
    negatives, positives = [], []
    for freq in RINNE_FORKS:
        sign = rinne_by_freq.get(freq)
        if sign == "negative":
            negatives.append(freq)
        elif sign == "positive":
            positives.append(freq)

    if not negatives and not positives:
        equivocal = [f for f in RINNE_FORKS if rinne_by_freq.get(f) == "equivocal"]
        if equivocal:
            return {"detected": None, "low_db": None, "high_db": None,
                    "label": "equivocal", "confidence": None,
                    "freqs_negative": [], "freqs_positive": [],
                    "statement": (
                        "Every fork tested came back equivocal, so no bracket can "
                        "be drawn. That is itself informative — a gap sitting near "
                        "a crossover value produces exactly this. Repeat with both "
                        "placement orders and corroborate with the Bing.")}
        return {"detected": None, "low_db": None, "high_db": None,
                "label": "not tested", "confidence": None,
                "statement": "No usable fork was tested for the Rinne."}

    if not negatives:
        floor = min(FORKS[f]["crossover_db"] for f in positives)
        return {
            "detected": False, "low_db": 0, "high_db": floor,
            "label": f"under {floor} dB", "confidence": "medium",
            "freqs_negative": [], "freqs_positive": sorted(positives),
            "statement": (
                f"Every fork tested stayed positive, so no air-bone gap of "
                f"about {floor} dB or more was detected. A smaller gap is NOT "
                f"excluded — this is the sensitivity limit of fork testing, "
                f"not a normal result."),
        }

    highest_negative = max(negatives)
    low = FORKS[highest_negative]["crossover_db"]
    # The ceiling is the crossover of the lowest fork that stayed positive, and
    # only if it sits above the floor — a fork that stayed positive BELOW a
    # fork that reversed is an inconsistency, handled by the caller, and must
    # not silently produce an inverted band here.
    above = [FORKS[f]["crossover_db"] for f in positives
             if FORKS[f]["crossover_db"] > low]
    high = min(above) if above else None

    if high is None:
        label = f"{low} dB or more"
        statement = (
            f"The Rinne reversed at {FORKS[highest_negative]['fork_hz']} Hz, the "
            f"highest fork tested, so the air-bone gap is at least about "
            f"{low} dB. No upper bound can be given from the forks used.")
    else:
        label = f"about {low}-{high} dB"
        statement = (
            f"The Rinne reversed at {FORKS[highest_negative]['fork_hz']} Hz but "
            f"not at the next fork up, which brackets the air-bone gap at "
            f"roughly {low}-{high} dB.")

    return {
        "detected": True, "low_db": low, "high_db": high, "label": label,
        "confidence": "medium",
        "freqs_negative": sorted(negatives), "freqs_positive": sorted(positives),
        "statement": statement,
    }


def analyze_rinne(ear: str, responses: Dict[int, str],
                  masked: bool = False,
                  otoscopy: str = "not_performed") -> dict:
    """One ear's Rinne across every fork it was tested at.

    ``responses`` maps a nominal audiometric frequency to one of
    ``RINNE_RESPONSES``. ``otoscopy`` is ``clear``, ``obstructed`` or
    ``not_performed`` and acts as a validity gate: a fully occluded canal
    produces a genuine conductive pattern from a trivial cause, and reporting
    that as middle-ear disease sends a wax plug for a tympanoplasty.
    """
    signs: Dict[int, str] = {}
    findings: List[str] = []
    flags: List[str] = []

    for freq, response in responses.items():
        freq = int(freq)
        if freq not in FORKS:
            continue
        sign = rinne_sign(response)
        if not FORKS[freq]["rinne"]:
            # G1: no crossover value exists for this fork, so no gap inference
            # may be drawn from it however the patient answered.
            if sign in ("positive", "negative"):
                flags.append("fork_not_valid_for_rinne")
                findings.append(
                    f"{FORKS[freq]['fork_hz']} Hz is not a Rinne fork — it has no "
                    f"established crossover value, so this answer cannot size an "
                    f"air-bone gap. Recorded, not interpreted.")
            continue
        signs[freq] = sign

    bracket = gap_bracket(signs)

    # An inconsistency worth naming: a lower fork stayed positive while a
    # higher one reversed. Crossover rises with frequency, so this ordering
    # should be impossible and points at technique rather than pathology.
    negatives = [f for f, s in signs.items() if s == "negative"]
    positives = [f for f, s in signs.items() if s == "positive"]
    if negatives and positives and min(positives) < max(negatives):
        flags.append("frequency_order_inconsistent")
        findings.append(
            "A lower fork stayed positive while a higher one reversed. The "
            "crossover rises with frequency, so this ordering should not occur "
            "— re-strike and repeat both, testing each placement order.")

    if "equivocal" in signs.values():
        flags.append("equivocal_present")
        eq = [FORKS[f]["fork_hz"] for f, s in sorted(signs.items())
              if s == "equivocal"]
        findings.append(
            f"Equivocal at {', '.join(str(h) + ' Hz' for h in eq)} — the gap may "
            f"sit near this fork's crossover. Repeat with both placement orders; "
            f"an equivocal result is never counted as positive or negative.")

    if negatives and not masked:
        flags.append("negative_rinne_unmasked")
        findings.append(
            "A negative Rinne was obtained without masking the opposite ear. "
            "Bone conduction crosses the skull unattenuated, so a severe "
            "sensorineural ear can produce this exact result. Mask the non-test "
            "ear before accepting it as conductive.")

    if 250 in signs and TACTILE_RISK[250] == "high" and signs[250] == "negative":
        flags.append("tactile_risk")
        findings.append(
            "The 256 Hz fork can be FELT as well as heard. Confirm the patient "
            "is reporting a tone and not a buzzing, and confirm the result at "
            "512 Hz before treating it as a gap.")

    if otoscopy == "obstructed" and negatives:
        flags.append("canal_occluded")
        findings.append(
            "The canal is occluded. A conductive pattern is fully explained by "
            "that — clear the canal and repeat the whole battery before "
            "ascribing this to middle-ear disease.")
    elif otoscopy == "not_performed":
        flags.append("otoscopy_not_performed")

    return {
        "ear": ear,
        "signs": {str(f): s for f, s in sorted(signs.items())},
        "gap_bracket": bracket,
        "masked": masked,
        "otoscopy": otoscopy,
        "findings": findings,
        "flags": flags,
    }


# ==========================================================================
# Weber
# ==========================================================================


def analyze_weber(lateralisation: Optional[str], freq: int = 500,
                  site: str = "glabella_forehead",
                  quiet_room: bool = True,
                  worse_ear_reported: Optional[str] = None) -> dict:
    """Which side the midline fork is heard in, and what that can mean alone.

    The Weber reports only the DIFFERENCE between the ears, which is why a
    midline result is never reported as "normal": bilateral disease of equal
    degree produces a perfectly midline Weber that is indistinguishable from
    normal hearing.
    """
    side = (lateralisation or "").lower()
    if side not in ("right", "left", "midline", "none"):
        side = "none"

    findings: List[str] = []
    flags: List[str] = []
    valid = True

    if site not in WEBER_SITES and site:
        valid = False
        flags.append("invalid_site")
        findings.append(
            "The fork was not on a recognised midline site. Lateralisation from "
            "an off-midline placement reflects geometry, not pathology.")

    if not FORKS.get(freq, {}).get("weber", False):
        valid = False
        flags.append("fork_not_valid_for_weber")
        findings.append(
            f"{FORKS.get(freq, {}).get('fork_hz', freq)} Hz decays too fast for a "
            f"dependable lateralisation judgement. Repeat at 512 Hz.")
    elif freq == 1000:
        flags.append("low_confidence_frequency")
        findings.append(
            "1024 Hz is valid for the Weber but lower in confidence than 512 Hz "
            "— the shorter decay leaves less time for the judgement.")

    if not quiet_room:
        flags.append("ambient_noise")
        findings.append(
            "Room noise masks the better ear by air conduction and can "
            "manufacture lateralisation. Repeat in quiet before reporting.")

    if side == "midline":
        interpretation = (
            "No lateralisation. Consistent with normal hearing bilaterally OR "
            "with a symmetric bilateral loss of any type — the Weber reports "
            "only the difference between the ears, so equal disease on both "
            "sides looks exactly like no disease.")
        findings.append(
            f"A midline Weber does not exclude an asymmetry smaller than "
            f"roughly {WEBER_RESOLUTION_DB} dB, and is not a normal result on "
            f"its own.")
    elif side == "none":
        interpretation = (
            "Not heard at the midline. Uninterpretable — repeat, and if it "
            "persists this is itself a finding pointing to a bilateral severe "
            "loss or a technical failure.")
    else:
        interpretation = (
            f"Lateralises to the {side}. Alone this means either a conductive "
            f"loss in the {side} ear or a sensorineural loss in the "
            f"{_other(side)} ear — the Weber cannot separate those two, and the "
            f"Rinne is what does.")
        if worse_ear_reported:
            if worse_ear_reported == side:
                findings.append(
                    f"It lateralises toward the ear the patient reports as worse "
                    f"({side}), which fits a conductive loss on that side.")
            elif worse_ear_reported == _other(side):
                findings.append(
                    f"It lateralises AWAY from the ear the patient reports as "
                    f"worse ({worse_ear_reported}), which fits a sensorineural "
                    f"loss in that ear.")

    return {
        "lateralisation": side,
        "freq": freq,
        "fork_hz": FORKS.get(freq, {}).get("fork_hz"),
        "site": site,
        "site_label": WEBER_SITES.get(site, site),
        "valid": valid,
        "interpretation": interpretation,
        "findings": findings,
        "flags": flags,
    }


def _other(side: str) -> str:
    return "left" if side == "right" else "right"


# ==========================================================================
# Bing, ABC, Schwabach, Gelle — the corroborants
# ==========================================================================


def analyze_bing(ear: str, response: Optional[str], freq: int = 250,
                 seal_demonstrated: bool = True) -> dict:
    """The occlusion test. Valid only where the occlusion effect is large.

    Occluding the canal traps low-frequency energy that would otherwise escape,
    so a normal or sensorineural ear hears the bone-conducted tone get LOUDER.
    An ear that already has a conductive block is, acoustically, occluded
    already — nothing changes.

    The trap this guards against: the occlusion effect is essentially absent
    above 1 kHz. Run at 1024 Hz or higher, "no change" is the normal finding in
    a completely normal ear, and recording it as a negative Bing manufactures a
    conductive diagnosis in every patient tested.
    """
    resp = (response or "").lower()
    findings: List[str] = []
    flags: List[str] = []

    if not FORKS.get(freq, {}).get("bing", False):
        return {
            "ear": ear, "freq": freq, "valid": False, "result": None,
            "flags": ["invalid_frequency"],
            "findings": [
                f"The Bing is invalid at {FORKS.get(freq, {}).get('fork_hz', freq)} "
                f"Hz — the occlusion effect is negligible or absent there, so "
                f"'no change' is what a normal ear gives. Use 256 Hz, where the "
                f"effect is largest, or 512 Hz."],
            "interpretation": None,
        }

    if not seal_demonstrated:
        return {
            "ear": ear, "freq": freq, "valid": False, "result": None,
            "flags": ["seal_not_demonstrated"],
            "findings": [
                "No canal seal was demonstrated. An unsealed canal gives no "
                "occlusion effect, so this would read as a negative Bing in a "
                "normal ear. Recorded as invalid rather than negative."],
            "interpretation": None,
        }

    if resp in ("louder", "positive"):
        result, interpretation = "positive", (
            "Positive Bing — the tone got louder on occlusion. The occlusion "
            "effect is intact, which is the normal or sensorineural pattern. "
            "Argues against a conductive component in this ear.")
    elif resp in ("no_change", "negative"):
        result, interpretation = "negative", (
            "Negative Bing — no change on occlusion. The ear behaves as though "
            "already occluded, which is the conductive pattern. The Bing detects "
            "a smaller gap than the Rinne can, so it may read negative in an ear "
            "whose Rinne is still positive.")
        flags.append("conductive_pattern")
    else:
        result, interpretation = "uninterpretable", (
            "No usable answer. Repeat, confirming the seal by asking whether "
            "the patient's own voice sounds hollow when the ear is pressed.")

    return {"ear": ear, "freq": freq, "fork_hz": FORKS[freq]["fork_hz"],
            "valid": True, "result": result, "interpretation": interpretation,
            "findings": findings, "flags": flags}


def analyze_bone_reference(ear: str, abc: Optional[str] = None,
                           schwabach: Optional[str] = None,
                           examiner_normal_hearing: bool = False) -> dict:
    """Absolute bone conduction and Schwabach — both examiner-relative.

    Each compares the patient's bone conduction against the EXAMINER'S, which
    is their entire weakness. Clinicians commonly have unrecognised
    high-frequency loss; such an examiner judges a reduced bone conduction to be
    normal and misses sensorineural loss systematically. There is no internal
    way to detect this, which is why the examiner's status is a required field
    and an unattested examiner stamps the result uncalibrated.
    """
    findings: List[str] = []
    flags: List[str] = []
    reduced = False

    a, s = (abc or "").lower(), (schwabach or "").lower()

    if a == "reduced":
        reduced = True
        findings.append(
            "Absolute bone conduction is reduced against the examiner's — the "
            "cochlear reserve is down, which is a sensorineural sign.")
    elif a == "normal":
        findings.append(
            "Absolute bone conduction matches the examiner's, arguing against a "
            "sensorineural component.")

    if s == "shortened":
        reduced = True
        findings.append(
            "Shortened Schwabach — the patient stops hearing the fork before "
            "the examiner does, again a sensorineural sign.")
    elif s == "prolonged":
        findings.append(
            "Prolonged Schwabach, classically the conductive pattern. This is "
            "weaker evidence than a shortened Schwabach: the test was designed "
            "around cochlear reserve, and prolongation also follows simply from "
            "release from ambient masking.")
    elif s == "normal":
        findings.append("Schwabach equal to the examiner's.")

    if (a or s) and not examiner_normal_hearing:
        flags.append("examiner_uncalibrated")
        findings.append(
            "The examiner's own hearing is not attested. Both tests use it as "
            "the reference zero, so this result is examiner-relative and "
            "supportive only.")

    return {"ear": ear, "abc": a or None, "schwabach": s or None,
            "cochlear_reserve_reduced": reduced,
            "examiner_normal_hearing": examiner_normal_hearing,
            "findings": findings, "flags": flags}


def analyze_gelle(ear: str, response: Optional[str],
                  freq: int = 500, vertigo: bool = False,
                  drum_intact: bool = True) -> dict:
    """Stapes mobility by pneumatic pressure. Largely superseded, and unsafe
    in some ears.

    Raising canal pressure with a Siegle speculum drives the stapes medially and
    stiffens the chain, so a normal ear hears the bone-conducted tone get
    quieter. A fixed stapes cannot move, so nothing changes.

    Two refusals: the test is meaningless without an intact drum and a sealed
    canal, and pressure on a labyrinth with a fistula provokes vertigo — which
    is itself an important finding rather than a failed test.
    """
    resp = (response or "").lower()
    findings: List[str] = []
    flags: List[str] = []

    if vertigo:
        return {
            "ear": ear, "valid": False, "result": "fistula_sign",
            "flags": ["fistula_sign", "stop_test"],
            "findings": [
                "Vertigo or nystagmus on pressure is a positive fistula "
                "(Hennebert) sign. Stop the test. This is a finding in its own "
                "right — it points to a labyrinthine fistula, superior canal "
                "dehiscence or a perilymph fistula and needs imaging and "
                "specialist referral, not a repeat."],
            "interpretation": None,
        }

    if not drum_intact:
        return {"ear": ear, "valid": False, "result": None,
                "flags": ["drum_not_intact"],
                "findings": ["A perforated drum or a ventilation tube makes a "
                             "seal impossible, so the Gelle cannot be performed."],
                "interpretation": None}

    if not FORKS.get(freq, {}).get("bing", False):
        return {"ear": ear, "valid": False, "result": None,
                "flags": ["invalid_frequency"],
                "findings": [f"The Gelle depends on the same low-frequency "
                             f"mechanics as the Bing and is invalid at "
                             f"{FORKS.get(freq, {}).get('fork_hz', freq)} Hz."],
                "interpretation": None}

    if resp in ("quieter", "positive"):
        result, interpretation = "positive", (
            "Positive Gelle — loudness fell with pressure, so the ossicular "
            "chain is mobile. Argues against stapes fixation.")
    elif resp in ("no_change", "negative"):
        result, interpretation = "negative", (
            "Negative Gelle — no change with pressure, the pattern of a fixed "
            "stapes. Ossicular discontinuity gives the same result, since "
            "pressure cannot reach the stapes across a break. Tympanometry with "
            "acoustic reflexes has largely replaced this test and should be "
            "obtained.")
        flags.append("stapes_fixation_pattern")
    else:
        result, interpretation = "uninterpretable", "No usable answer."

    return {"ear": ear, "freq": freq, "valid": True, "result": result,
            "interpretation": interpretation, "findings": findings,
            "flags": flags}


# ==========================================================================
# The combined grid — where the battery earns its keep
# ==========================================================================
#
# Neither test diagnoses alone. The Weber gives a side but cannot say whether
# that side is conductive or the other side is sensorineural; the Rinne gives a
# type but no comparison between the ears. Crossed, they resolve — and two of
# the twelve cells resolve to "these results cannot both be true", which is the
# finding the whole battery exists to surface.

#: Precedence layers. A lower layer always wins and no higher layer may modify
#: it. This ordering is the difference between a battery that flags a
#: false-negative Rinne and one that reports a dead ear as conductive.
PRECEDENCE = ["validity", "contradiction", "warning", "grid", "annotation"]


def _sign_at(rinne: Optional[dict], freq: int) -> str:
    if not rinne:
        return "uninterpretable"
    return rinne["signs"].get(str(freq), "uninterpretable")


def combined_grid(right: Optional[dict], left: Optional[dict],
                  weber: Optional[dict],
                  right_reserve: Optional[dict] = None,
                  left_reserve: Optional[dict] = None,
                  bing: Optional[Dict[str, dict]] = None,
                  worse_ear_reported: Optional[str] = None,
                  measured_gap: Optional[Dict[str, Optional[float]]] = None) -> dict:
    """Cross the two Rinnes with the Weber, in strict precedence order.

    ``measured_gap`` carries the air-bone gap actually measured at this
    frequency where an audiogram exists. It is what lets rule C8 retract a
    fork-derived conductive finding: the audiogram outranks the forks.
    """
    bing = bing or {}
    measured_gap = measured_gap or {}
    flags: List[str] = []
    notes: List[str] = []

    def suppressed(reason: str, level: str, rule: str) -> dict:
        return {"available": False, "level": level, "rule": rule,
                "headline": reason, "loss_type": None, "side": None,
                "flags": flags, "notes": notes,
                "recommendations": [
                    "Pure-tone audiometry with masked bone conduction."]}

    # ---- L0 validity gates ----------------------------------------------
    if weber is None:
        return suppressed(
            "A Weber is required before any type of loss may be reported. A "
            "Rinne alone gives a type without a comparison between the ears.",
            "validity", "W13")
    if not weber.get("valid", True):
        detail = weber["findings"][0] if weber["findings"] else ""
        return suppressed(
            "The Weber is invalid, so the combined interpretation is "
            "suppressed. " + detail, "validity", "C7")

    freq = weber["freq"]

    # G2 before C6: an occluded canal is an L0 validity gate and a frequency
    # mismatch is only an L2 warning, so the loops must be separate. Sharing
    # one loop lets a mismatch on the right ear preempt an occluded canal on
    # the left, which inverts the precedence the module promises.
    for ear_name, side in (("right", right), ("left", left)):
        if side and side["otoscopy"] == "obstructed":
            flags.append("canal_occluded")
            return suppressed(
                f"The {ear_name} canal is occluded. Any conductive pattern is "
                f"fully explained by that — clear it and repeat the whole "
                f"battery before ascribing this to middle-ear disease.",
                "validity", "G2")

    for ear_name, side in (("right", right), ("left", left)):
        if side and side["signs"] and str(freq) not in side["signs"]:
            flags.append("frequency_mismatch")
            return suppressed(
                f"The {ear_name} Rinne was not taken at "
                f"{FORKS[freq]['fork_hz']} Hz, the frequency of the Weber. The "
                f"grid requires all three at one frequency, because the "
                f"crossover value differs at every fork.", "warning", "C6")

    r_sign, l_sign = _sign_at(right, freq), _sign_at(left, freq)
    lat = weber["lateralisation"]
    sign = {"right": r_sign, "left": l_sign}
    reserve = {
        "right": bool(right_reserve and right_reserve["cochlear_reserve_reduced"]),
        "left": bool(left_reserve and left_reserve["cochlear_reserve_reduced"]),
    }

    if r_sign == "uninterpretable" and l_sign == "uninterpretable" and lat == "none":
        return {"available": True, "level": "grid", "rule": "D10",
                "headline": "Profound bilateral loss, or a technical failure.",
                "loss_type": None, "side": None,
                "flags": flags + ["uninterpretable"], "notes": notes,
                "recommendations": [
                    "Repeat the battery before any interpretation.",
                    "If it persists, go to objective testing (ABR/ASSR) rather "
                    "than repeating forks."]}

    # ---- L1 contradictions ----------------------------------------------
    for ear in ("right", "left"):
        other = _other(ear)
        if sign[ear] == "negative" and sign[other] == "positive" and lat == other:
            rule = "C1"
            extra = (
                f"The likeliest explanation is a FALSE-NEGATIVE RINNE: a severe "
                f"or profound sensorineural loss in the {ear} ear, with the "
                f"bone-conducted tone crossing the skull unattenuated and being "
                f"heard by the {other} cochlea. A mixed loss in the {ear} ear "
                f"with a dominant sensorineural component does the same.")
            if reserve[ear]:
                rule = "C4"
                extra = (
                    f"Reduced bone-conduction reserve on the {ear} settles it: "
                    f"this is a profound sensorineural loss in the {ear} ear "
                    f"with crossover, not a conductive loss. Escalate.")
            return {"available": True, "level": "contradiction", "rule": rule,
                    "headline": (
                        f"These cannot both be true. The {ear} Rinne is "
                        f"negative, which says conductive, but the Weber "
                        f"lateralises {other} — away from that ear, which a "
                        f"genuine conductive loss cannot do."),
                    "loss_type": None, "side": ear,
                    "flags": flags + ["false_negative_rinne_suspected"],
                    "notes": notes + [extra],
                    "recommendations": [
                        f"Repeat the {ear} Rinne with the non-test ear masked "
                        f"(Barany noise box). If the fork then disappears at "
                        f"both placements, the negative Rinne was crossover.",
                        "Pure-tone audiometry with masked bone conduction."]}

    # ---- L2 warnings -----------------------------------------------------
    # C8 — where the forks and the audiogram disagree, the audiogram wins.
    #
    # Both ears are examined before anything is returned. Retracting the right
    # ear's reversal and returning on the spot would bury a genuine conductive
    # loss in the left, which is the opposite of what an override is for. A
    # retracted ear is re-signed POSITIVE, because "positive" is exactly what
    # the audiogram measured there — no significant gap — and the grid then
    # runs on the corrected picture.
    retracted = []
    for ear in ("right", "left"):
        gap = measured_gap.get(ear)
        if sign[ear] == "negative" and gap is not None and gap <= 10:
            retracted.append((ear, gap))
            sign[ear] = "positive"

    if retracted:
        flags.append("contradicted_by_audiogram")
        for ear, gap in retracted:
            notes.append(
                f"The {ear} Rinne reversed, but the measured air-bone gap in that "
                f"ear is {gap:.0f} dB, which is not significant. Where the forks "
                f"and the audiogram disagree the audiogram wins, so the "
                f"fork-derived conductive finding for the {ear} ear is withdrawn "
                f"and it is read as a positive Rinne below.")

    # If no reversal survives the audiogram, the retraction IS the finding. If
    # one does, the grid runs on it and the retraction rides along as a note.
    if retracted and all(sign[e] != "negative" for e in ("right", "left")):
        ears = " and ".join(e for e, _ in retracted)
        return {"available": True, "level": "warning", "rule": "C8",
                "headline": (
                    f"False-negative Rinne confirmed against audiometry on the "
                    f"{ears}. The reversal is not supported by a measured gap."),
                "loss_type": None, "side": retracted[0][0], "flags": flags,
                "notes": notes,
                "recommendations": [
                    "Treat the fork result as crossover or technique, not as a "
                    "conductive component."]}

    if sign["right"] == "negative" and sign["left"] == "negative" \
            and lat in ("right", "left"):
        gr, gl = measured_gap.get("right"), measured_gap.get("left")
        if gr is not None and gl is not None and gr != gl:
            smaller = "right" if gr < gl else "left"
            if lat == smaller:
                flags.append("lateralises_to_lesser_gap")
                notes.append(
                    f"Both Rinnes are negative but the Weber lateralises to the "
                    f"{lat}, the ear with the SMALLER measured gap. Repeat both "
                    f"and consider an asymmetric mixed loss.")

    if lat in ("right", "left") and sign[lat] == "positive" \
            and sign[_other(lat)] == "positive" and worse_ear_reported == lat:
        flags.append("discordant_subjective")
        notes.append(
            f"The patient reports the {lat} ear as worse and the Weber "
            f"lateralises there, yet that ear's Rinne is positive. Consider an "
            f"air-bone gap below the reversal threshold — the Bing at 256 Hz is "
            f"the more sensitive test — or an unreliable subjective report.")

    # ---- L3 the grid -----------------------------------------------------
    if "equivocal" in (r_sign, l_sign):
        eq = [e for e in ("right", "left") if sign[e] == "equivocal"]
        return {"available": False, "level": "warning", "rule": "D9",
                "headline": (
                    f"The {' and '.join(eq)} Rinne is equivocal, so the grid is "
                    f"suppressed for that ear rather than forced into a sign."),
                "loss_type": None, "side": None,
                "flags": flags + ["equivocal_present"],
                "notes": notes + [
                    "An equivocal Rinne means the gap may sit near this fork's "
                    "crossover value. Repeat with both placement orders and "
                    "corroborate with the Bing and the adjacent forks."],
                "recommendations": [
                    "Repeat at 256 Hz and 1024 Hz to bracket the gap."]}

    result = None
    if r_sign == "positive" and l_sign == "positive" and lat == "midline":
        result = {"rule": "D1", "loss_type": "normal_or_symmetric", "side": None,
                  "headline": "Normal hearing bilaterally, or a symmetric "
                              "bilateral sensorineural loss.",
                  "note": "The Weber reports only the difference between the "
                          "ears, so equal disease on both sides is "
                          "indistinguishable from none. This is never reported "
                          "as 'normal' on its own, and a symptomatic patient "
                          "goes for audiometry regardless."}
    elif r_sign == "positive" and l_sign == "positive" and lat in ("right", "left"):
        result = {"rule": "D2", "loss_type": "sensorineural", "side": _other(lat),
                  "headline": f"Sensorineural loss in the {_other(lat)} ear, OR a "
                              f"small conductive loss in the {lat} ear below the "
                              f"Rinne reversal threshold.",
                  "note": f"Both stay open on this evidence and neither is picked "
                          f"silently. The Bing on the {lat} ear discriminates: "
                          f"negative points to the small conductive gap, positive "
                          f"to the sensorineural loss opposite."}
    elif lat in ("right", "left") and sign[lat] == "negative" \
            and sign[_other(lat)] == "positive":
        result = {"rule": "D3", "loss_type": "conductive", "side": lat,
                  "headline": f"Conductive loss in the {lat} ear.",
                  "note": "Internally consistent: the Rinne reversed on the side "
                          "the Weber lateralises to, which is the classic "
                          "conductive picture."}
    elif lat == "midline" and (r_sign == "negative") != (l_sign == "negative"):
        ear = "right" if r_sign == "negative" else "left"
        result = {"rule": "D4", "loss_type": "conductive", "side": ear,
                  "headline": f"Equivocal: a small conductive loss in the {ear} "
                              f"ear, or a bilateral near-symmetric conductive "
                              f"loss.",
                  "note": "A gap large enough to reverse the Rinne would usually "
                          "pull the Weber toward it. Repeat at a second "
                          "frequency before relying on this."}
    elif r_sign == "negative" and l_sign == "negative" and lat == "midline":
        result = {"rule": "D5", "loss_type": "conductive_bilateral", "side": None,
                  "headline": "Symmetric bilateral conductive loss — OR bilateral "
                              "severe sensorineural loss with a false-negative "
                              "Rinne on both sides.",
                  "note": "Forks alone cannot separate these two, and the second "
                          "is the dangerous reading, so no definitive conductive "
                          "diagnosis is issued from this cell."}
    elif r_sign == "negative" and l_sign == "negative" and lat in ("right", "left"):
        result = {"rule": "D6", "loss_type": "conductive_bilateral", "side": lat,
                  "headline": f"Bilateral conductive loss, the larger gap "
                              f"apparently on the {lat}. Provisional.",
                  "note": "Bilateral false-negative Rinnes are not excluded "
                          "without masking."}

    if result is None:
        return suppressed(
            "This combination is not interpretable as recorded — at least one "
            "ear gave no usable Rinne at this frequency.", "warning", "unmatched")

    # ---- D7, the only override an L3 rule may receive --------------------
    #
    # Every ear with reduced reserve is converted, not just the first one found.
    # Stopping at the first hides a mixed loss in the second ear of a bilateral
    # case; and for a BILATERAL conductive result the reserve may legitimately
    # be reduced on the ear the Weber did not lateralise to, so the eligible
    # ears are the ones the finding actually covers, not only ``result["side"]``.
    if result["loss_type"] in ("conductive", "conductive_bilateral"):
        covered = (("right", "left") if result["loss_type"] == "conductive_bilateral"
                   or result["side"] is None else (result["side"],))
        mixed = [e for e in ("right", "left") if reserve[e] and e in covered]
        if mixed:
            where = " and ".join(mixed)
            result = {**result, "rule": "D7", "loss_type": "mixed",
                      "side": mixed[0] if len(mixed) == 1 else None,
                      "sides": mixed,
                      "headline": f"Mixed loss in the {where} ear"
                                  f"{'s' if len(mixed) > 1 else ''}.",
                      "note": f"A conductive picture from the Rinne and Weber, "
                              f"but bone-conduction reserve on the {where} is "
                              f"reduced as well, so there is a sensorineural "
                              f"component beneath it."}
            flags.append("reserve_reduced")

    # ---- L4 annotations --------------------------------------------------
    for ear in ("right", "left"):
        b = bing.get(ear)
        if not b or not b.get("valid"):
            continue
        if sign[ear] == "positive" and b["result"] == "negative":
            flags.append("bing_suggests_small_gap")
            notes.append(
                f"The {ear} Rinne is positive but the Bing is negative. Not a "
                f"contradiction — the Bing detects a smaller gap than the Rinne "
                f"can, so this suggests an air-bone gap below the reversal "
                f"threshold.")
        elif sign[ear] == "negative" and b["result"] == "positive" and lat == ear:
            flags.append("bing_disagrees")
            notes.append(
                f"The {ear} Rinne is negative but the Bing is positive — the "
                f"occlusion effect is intact where a conductive block should "
                f"have abolished it. Repeat the Bing with the seal demonstrated; "
                f"the conductive reading is provisional until they agree.")

    recs = ["Pure-tone audiometry with masked bone conduction confirms and sizes "
            "what the forks indicate."]
    if result["loss_type"] in ("conductive", "conductive_bilateral", "mixed"):
        recs.append("Tympanometry with acoustic reflexes.")

    return {"available": True, "level": "grid", "rule": result["rule"],
            "headline": result["headline"], "loss_type": result["loss_type"],
            "side": result["side"],
            # ``sides`` is populated only by D7, which can name both ears at
            # once; every other rule names one side or none.
            "sides": result.get("sides", [result["side"]] if result["side"] else []),
            "flags": flags,
            "notes": notes + [result["note"]], "recommendations": recs}


# ==========================================================================
# Against the audiogram
# ==========================================================================


def measured_gaps(ac: Dict[int, Optional[ThresholdValue]],
                  bc: Dict[int, Optional[ThresholdValue]]) -> Dict[int, Optional[float]]:
    """Per-frequency air-bone gap, at the fork frequencies only.

    Deliberately per-frequency rather than the four-frequency average used for
    typing: a 512 Hz fork tests 500 Hz, and averaging it against 4 kHz would
    compare the fork with something it never sampled.

    A "No Response" is CENSORED, not measured. Elsewhere in the codebase it
    computes as 120 dB HL, which is the right convention for an average but the
    wrong one for a difference: a bone oscillator maxes out near 70 dB, so
    BC = NR against a measurable AC would subtract to a NEGATIVE gap, and
    AC = BC = NR would subtract to exactly zero. Both are unknowable gaps that
    would then satisfy the audiogram-override rule and retract a real conductive
    finding on a number nobody measured. So a gap involving a censored value is
    ``None`` — unknown — and the override simply does not run.
    """
    out: Dict[int, Optional[float]] = {}
    ac_n, bc_n = ear_to_numeric(ac), ear_to_numeric(bc)
    for freq in FORKS:
        if ac.get(freq) == "NR" or bc.get(freq) == "NR":
            out[freq] = None
            continue
        a, b = ac_n.get(freq), bc_n.get(freq)
        out[freq] = round(a - b, 1) if a is not None and b is not None else None
    return out


def cross_check(rinne: Optional[dict],
                ac: Dict[int, Optional[ThresholdValue]],
                bc: Dict[int, Optional[ThresholdValue]]) -> dict:
    """Does the gap the forks predicted match the gap actually measured?

    This is the only place in the module where a fork result meets a number,
    and it runs in one direction only: the audiogram judges the forks. A
    disagreement is reported as a disagreement rather than averaged away,
    because the two are not two estimates of the same quantity — one is a
    calibrated measurement and the other is a bracket.
    """
    if not rinne:
        return {"available": False, "reason": "No Rinne recorded."}

    gaps = measured_gaps(ac, bc)
    tested = {f: g for f, g in gaps.items() if g is not None}
    if not tested:
        return {"available": False,
                "reason": "No air-bone gap could be measured — both air and bone "
                          "thresholds are needed at a fork frequency."}

    bracket = rinne["gap_bracket"]
    rows, disagreements = [], []
    for freq in RINNE_FORKS:
        gap, s = gaps.get(freq), rinne["signs"].get(str(freq))
        if gap is None or s not in ("positive", "negative"):
            continue
        # The crossover is a BAND, not a point, and the module says so
        # everywhere else — so it must be a band here too. Judging the 512 Hz
        # fork against a bare 30 dB would call every gap of 20-29 dB a
        # disagreement, and a 25 dB otosclerosis with a properly reversed Rinne
        # would be reported as the signature of a dead ear. Inside the band the
        # fork may legitimately go either way, so neither answer disagrees.
        lo, hi = FORKS[freq]["crossover_range"] or (
            FORKS[freq]["crossover_db"], FORKS[freq]["crossover_db"])
        if gap >= hi:
            expected = "negative"
        elif gap < lo:
            expected = "positive"
        else:
            expected = "either"
        agrees = expected in ("either", s)
        rows.append({"freq": freq, "fork_hz": FORKS[freq]["fork_hz"],
                     "measured_gap_db": gap, "crossover_db": FORKS[freq]["crossover_db"],
                     "crossover_range": [lo, hi],
                     "rinne": s, "expected": expected, "agrees": agrees})
        if not agrees:
            disagreements.append(
                f"At {FORKS[freq]['fork_hz']} Hz the measured gap is {gap:.0f} dB, "
                f"outside the {lo}-{hi} dB band in which this fork may reverse, "
                f"so the Rinne would be expected {expected} — it was recorded "
                f"{s}." + (
                    " A negative Rinne over a gap this small is the signature of "
                    "crossover from a poor cochlea; mask and repeat."
                    if s == "negative" else
                    " The forks are insensitive to gaps near their crossover, so "
                    "this is within the method's known limits."))

    agree_n = sum(1 for r in rows if r["agrees"])
    return {
        "available": bool(rows),
        "rows": rows,
        "gaps": {str(f): g for f, g in gaps.items()},
        "predicted": bracket.get("label"),
        "agreement": f"{agree_n}/{len(rows)}" if rows else None,
        "disagreements": disagreements,
        "verdict": (
            "The forks and the audiogram agree at every frequency tested."
            if rows and not disagreements else
            "The forks and the audiogram disagree — the audiogram governs."
            if disagreements else
            "Not enough overlap between the forks used and the frequencies "
            "measured to compare."),
    }


# ==========================================================================
# The whole battery
# ==========================================================================


def tuning_fork_battery(right_rinne: Optional[dict] = None,
                        left_rinne: Optional[dict] = None,
                        weber: Optional[dict] = None,
                        right_reserve: Optional[dict] = None,
                        left_reserve: Optional[dict] = None,
                        bing: Optional[Dict[str, dict]] = None,
                        gelle: Optional[Dict[str, dict]] = None,
                        worse_ear_reported: Optional[str] = None,
                        right_ac: Optional[Dict[int, Optional[ThresholdValue]]] = None,
                        right_bc: Optional[Dict[int, Optional[ThresholdValue]]] = None,
                        left_ac: Optional[Dict[int, Optional[ThresholdValue]]] = None,
                        left_bc: Optional[Dict[int, Optional[ThresholdValue]]] = None) -> dict:
    """Everything, reconciled, with the audiogram given the last word."""
    gap_at_weber: Dict[str, Optional[float]] = {}
    checks: Dict[str, dict] = {}
    freq = weber["freq"] if weber else 500

    for ear, rin, ac, bc in (("right", right_rinne, right_ac, right_bc),
                             ("left", left_rinne, left_ac, left_bc)):
        if ac and bc:
            checks[ear] = cross_check(rin, ac, bc)
            gap_at_weber[ear] = measured_gaps(ac, bc).get(freq)

    grid = combined_grid(
        right_rinne, left_rinne, weber, right_reserve, left_reserve,
        bing=bing, worse_ear_reported=worse_ear_reported,
        measured_gap=gap_at_weber)

    urgent = [g for g in (gelle or {}).values() if "fistula_sign" in g.get("flags", [])]

    return {
        "grid": grid,
        "cross_check": checks or None,
        "gap_bracket": {
            "right": right_rinne["gap_bracket"] if right_rinne else None,
            "left": left_rinne["gap_bracket"] if left_rinne else None,
        },
        "urgent": [
            "Positive fistula sign on the Gelle — stop pressure testing, and "
            "refer for imaging and specialist assessment." for _ in urgent],
        "limits": list(LIMITS),
        "citations": list(CITATIONS),
    }


def reference() -> dict:
    """The forks, the vocabulary and the criteria, for the interface to state."""
    return {
        "forks": [{"nominal_hz": f, **p} for f, p in FORKS.items()],
        "rinne_responses": [{"key": k, "label": v}
                            for k, v in RINNE_RESPONSES.items()],
        "weber_sites": [{"key": k, "label": v} for k, v in WEBER_SITES.items()],
        "rinne_forks": list(RINNE_FORKS),
        "bing_forks": list(BING_FORKS),
        "interaural_attenuation_bc": INTERAURAL_ATTENUATION_BC,
        "weber_resolution_db": WEBER_RESOLUTION_DB,
        "tactile_risk": {str(k): v for k, v in TACTILE_RISK.items()},
        "precedence": list(PRECEDENCE),
        "bracketing": (
            "The frequency at which the Rinne reverses brackets the air-bone "
            "gap: 256 Hz alone means roughly 15-30 dB, 256 and 512 means "
            "30-45 dB, and all three means about 45 dB or more. No such value "
            "exists for 2048 or 4096 Hz, so no gap is inferred from them."),
        "limits": list(LIMITS),
        "citations": list(CITATIONS),
    }
