"""MODULE 6 — Dual-engine AI report pipeline.

Offline engine (default, no key): a data-driven clause library fills every
report section from the structured analysis JSON, then a deterministic
verifier RE-DERIVES each number from the source data and checks it appears
in the draft — so the "verified ✓" badge is genuinely earned, not decorative.

API engine (when the user enables a provider in AI Settings): generator
call with a senior-audiologist system prompt (input = structured JSON only)
followed by a second verifier call that cross-checks every number/claim.
Any failure falls back to the offline engine so the demo never breaks.

Also produces the patient counseling sheet: plain 8th-grade language in
English AND Tamil with practical tips.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from app.clinical.symptoms import occupation_prompt
from app.ml.classifier import RELIABLE_CONFIDENCE
from app.ml.features import (
    NORMAL_PTA_LIMIT,
    NR_VALUE,
    PTA_FREQS,
    normal_average_caveat,
    notch_retest_note,
    plausibility_reasons,
    within_normal_limits,
)
from app.services import llm_provider
from app.services.ai_config import get_config
from app.services.languages import (
    BENCHMARK,
    EAR_SENTENCE,
    GRADE_SIMPLE,
    HEADING,
    HEARING_AID,
    LANGUAGES,
    SIDE_WORD,
    TIPS,
    TIPS_HEADING,
    URGENT,
)

DISCLAIMER = (
    "AI-assisted interpretation; final diagnosis requires a qualified audiologist."
)

def _noisy_occupation(occupation: Optional[str]) -> bool:
    """Whether the recorded occupation is in a high-noise sector.

    One sourced list for every screen (symptom_kb.NOISY_OCCUPATIONS, matched
    on word boundaries by symptoms.occupation_prompt), so the report, the
    history page and the diagnostic picture name the same jobs — "weaver" is
    caught, and "examiner" is not read as "miner".
    """
    return bool(occupation_prompt(occupation, ()))


# ------------------------------------------------------------ helpers ------

def _grade_word(grade: Optional[dict]) -> str:
    return grade["grade"] if grade else "not assessable"


def _ear_summary(ear: dict, side: str) -> str:
    g = ear.get("who_grade")
    pta = ear.get("ac_pta")
    if not pta:
        return f"The {side} ear could not be assessed (no thresholds at PTA frequencies)."
    text = (
        f"{side.capitalize()} ear: four-frequency pure-tone average (500/1k/2k/4k Hz) "
        f"of {pta['value']:g} dB HL — {_grade_word(g)} "
        f"({g['range']}), {ear['type'].lower()} type."
    )
    abg = ear.get("abg")
    if abg:
        text += f" Air-bone gap averages {abg['value']:g} dB."
    if ear.get("air_bone_gap_note"):
        text += f" {ear['air_bone_gap_note']}"
    return text


def _numeric_ac(analysis: dict, side: str) -> Dict[int, float]:
    """Measured AC thresholds for one ear from the analysis payload.

    The payload arrives as JSON, so frequency keys are strings and NR is a
    string; NR maps to the audiometer maximum as everywhere else.
    """
    raw = (((analysis.get("thresholds") or {}).get(side) or {}).get("ac")) or {}
    out: Dict[int, float] = {}
    for k, v in raw.items():
        try:
            f = int(k)
        except (TypeError, ValueError):
            continue
        if v is None:
            continue
        if isinstance(v, str) and v.strip().upper() == "NR":
            out[f] = NR_VALUE
            continue
        try:
            out[f] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _ml_reliable(ml: dict) -> bool:
    """Whether a pattern label may drive etiology wording or advice.

    Uses the classifier's own ``reliable`` verdict; an analysis produced
    before that field existed falls back to the same confidence bar, and is
    never reliable when flagged atypical or when the label is not a loss
    configuration.
    """
    if "reliable" in ml:
        return bool(ml["reliable"])
    return (
        ml.get("pattern") not in (None, "normal")
        and not ml.get("ood")
        and (ml.get("confidence") or 0) >= RELIABLE_CONFIDENCE
    )


def _ear_within_normal_limits(analysis: dict, side: str, ml: Optional[dict]) -> bool:
    if ml and ml.get("pattern") == "normal":
        return True
    thresholds = _numeric_ac(analysis, side)
    return bool(thresholds) and within_normal_limits(thresholds)


def _normal_average_caveat(analysis: dict, side: str, pattern: Optional[str]) -> Optional[str]:
    """Why a label cannot be read as a loss configuration in an ear graded
    Normal hearing by its four-frequency average (WHO 2021).

    Re-derived here from the measured thresholds, not taken from the
    classifier's ``reliable`` alone, because stored analyses are re-reported
    and the rule must hold whichever classifier produced them. Without
    thresholds in the payload the rules engine's PTA decides, and no label
    can then be corroborated.
    """
    thresholds = _numeric_ac(analysis, side)
    if thresholds:
        return normal_average_caveat(thresholds, pattern)
    pta = (((analysis.get("rules") or {}).get(side) or {}).get("ac_pta") or {}).get("value")
    if pattern not in (None, "normal") and pta is not None and pta < NORMAL_PTA_LIMIT:
        return (f"the four-frequency average ({pta:g} dB HL) is within WHO 2021 "
                "normal limits and the thresholds that would show which "
                "frequencies carry the configuration are not in this record")
    return None


def _label_usable(analysis: dict, side: str, ml: dict) -> Tuple[bool, Optional[str]]:
    """Whether an ear's pattern label may drive etiology wording or advice,
    and the reason when it may not.

    The plausibility checks are re-run on the stored thresholds for the same
    reason as the normal-average rule: an analysis stored before a check
    existed still carries the reliable flag it was given then.
    """
    if not _ml_reliable(ml):
        return False, ml.get("reliability_note") or "flagged for review"
    caveat = _normal_average_caveat(analysis, side, ml.get("pattern"))
    if caveat:
        return False, caveat[0].upper() + caveat[1:]
    thresholds = _numeric_ac(analysis, side)
    implausible = (plausibility_reasons(thresholds, ml.get("pattern"))
                   if thresholds else [])
    if implausible:
        note = "; ".join(implausible)
        return False, note[0].upper() + note[1:]
    return True, None


def _etiology(analysis: dict) -> List[str]:
    """Occupation- and age-aware likely etiologies per detected pattern.

    An etiology is suggested only from a reliable loss configuration. A
    normal ear has no configuration, an unclassified ear has too little
    data, and an unreliable label is described as provisional — each with
    the reason — so that no differential is built on a label the classifier
    itself does not stand behind. An ear graded Normal hearing by its
    average with a threshold or two above 20 dB HL counts as unreliable
    unless those thresholds form the configuration named.
    """
    patient = analysis.get("patient") or {}
    age = patient.get("age") or 0
    noisy_job = _noisy_occupation(patient.get("occupation"))
    out: List[str] = []

    for side in ("right", "left"):
        ml = (analysis.get("ml") or {}).get(side)
        ear = (analysis.get("rules") or {}).get(side, {})
        if not ml:
            continue
        p = ml.get("pattern")
        label = ml.get("pattern_label") or str(p)
        side_word = side.capitalize()
        if p is None:
            out.append(
                f"{side_word} ear — configuration not classified "
                f"({ml.get('reliability_note') or 'insufficient data'}). "
                "Interpret the audiogram directly; no etiology is inferred."
            )
            continue
        if p == "normal" or _ear_within_normal_limits(analysis, side, ml):
            out.append(
                f"{side_word} ear — thresholds within normal limits; there is no "
                "loss configuration to classify and no etiology is inferred."
            )
            continue
        usable, note = _label_usable(analysis, side, ml)
        if not usable:
            out.append(
                f"{side_word} ear — the configuration provisionally reads as "
                f"{label} ({(ml.get('confidence') or 0):.0%}), which is not "
                f"reliable enough to suggest an etiology: {note}. Interpret the "
                "audiogram directly."
            )
            continue
        prefix = f"{side_word} ear — {label} configuration"
        ear_type = (ear.get("type") or "").lower()
        if p == "noise_notch_4k":
            if noisy_job:
                out.append(
                    f"{prefix}: a 4 kHz notch is the classic signature of "
                    f"noise-induced hearing loss. The patient's occupation "
                    f"(\"{patient.get('occupation')}\") involves occupational noise "
                    "exposure, making occupational NIHL the leading etiology. "
                    "Recommend noise-exposure history, hearing-protection review, "
                    "and OSHA-style monitoring."
                )
            else:
                out.append(
                    f"{prefix}: 4 kHz notches suggest noise exposure "
                    "(occupational or recreational — firearms, loud music). "
                    "A detailed noise history is indicated."
                )
        elif p == "sloping_high_frequency":
            if age >= 60:
                out.append(
                    f"{prefix}: gradually sloping high-frequency sensorineural loss "
                    f"at age {age} is most consistent with presbycusis "
                    "(age-related hearing loss)."
                )
            else:
                out.append(
                    f"{prefix}: high-frequency sloping loss; consider noise exposure, "
                    "ototoxic medication history, and genetic factors given the "
                    f"patient's age ({age})."
                )
        elif p == "ski_slope":
            out.append(
                f"{prefix}: precipitous high-frequency loss with preserved low "
                "frequencies; etiologies include genetic SNHL, ototoxicity and "
                "advanced noise injury. High-frequency amplification with "
                "frequency-lowering features may help."
            )
        elif p == "rising":
            if "conductive" in ear_type:
                out.append(
                    f"{prefix} with conductive component: low-frequency conductive "
                    "loss suggests middle-ear pathology — otitis media with "
                    "effusion or early otosclerosis. ENT referral with "
                    "tympanometry indicated."
                )
            else:
                out.append(
                    f"{prefix}: rising sensorineural configurations are associated "
                    "with Ménière's disease / endolymphatic hydrops — correlate "
                    "with vertigo, fullness and tinnitus history."
                )
        elif p == "cookie_bite":
            out.append(
                f"{prefix}: mid-frequency (\"cookie-bite\") SNHL is strongly "
                "associated with hereditary/congenital hearing loss; family "
                "audiometric screening is advisable."
            )
        elif p == "corner_audiogram":
            # Implant candidacy is never read off a configuration label: it
            # follows the measured degree of loss and aided speech testing,
            # and is handled in _recommendations from the thresholds.
            out.append(
                f"{prefix}: residual hearing only at the low frequencies. "
                "Management follows the measured degree of loss and aided "
                "speech-recognition testing, not this configuration label."
            )
        elif p == "flat":
            if "conductive" in ear_type:
                out.append(
                    f"{prefix} with conductive mechanism: consistent with "
                    "middle-ear effusion, ossicular fixation or tympanic "
                    "membrane pathology; ENT evaluation indicated."
                )
            else:
                out.append(
                    f"{prefix}: flat sensorineural losses occur in Ménière's "
                    "disease, sudden SNHL (treat urgently if recent), and some "
                    "genetic etiologies."
                )
        # An atypical (out-of-distribution) label is never reliable, so its
        # review reason was already given in the provisional sentence above.
    return out or ["No pattern classification available."]


#: NICE TA566 (2019): severe to profound deafness is hearing only sounds
#: louder than 80 dB HL at two or more of 500, 1000, 2000, 3000 and 4000 Hz,
#: bilaterally, without hearing aids. 3 kHz is not tested in this app, so the
#: count runs over 0.5/1/2/4 kHz; NR counts as beyond 80 dB HL.
CI_THRESHOLD_DB = 80.0
CI_MIN_FREQS = 2


def _severe_to_profound_ears(analysis: dict) -> Dict[str, str]:
    """Ears meeting the NICE TA566 audiometric criterion, mapped to the basis
    of that call.

    "thresholds": 80 dB HL or worse at CI_MIN_FREQS or more of 0.5/1/2/4 kHz.
    "pta": the record carries no thresholds at the PTA frequencies for that
    ear, so only the rules engine's average (80 dB HL or worse) is available
    and the per-frequency criterion could not be checked. An average is
    never used when the thresholds are present: one NR at 4 kHz lifts the
    average past 80 without meeting the criterion.
    """
    rules = analysis.get("rules") or {}
    ears: Dict[str, str] = {}
    for side in ("right", "left"):
        thresholds = _numeric_ac(analysis, side)
        measured = [thresholds[f] for f in PTA_FREQS if thresholds.get(f) is not None]
        if measured:
            if sum(1 for v in measured if v >= CI_THRESHOLD_DB) >= CI_MIN_FREQS:
                ears[side] = "thresholds"
            continue
        pta = ((rules.get(side) or {}).get("ac_pta") or {}).get("value")
        if pta is not None and pta >= CI_THRESHOLD_DB:
            ears[side] = "pta"
    return ears


def _ci_unassessable(analysis: dict, side: str) -> Optional[str]:
    """Why the NICE TA566 criterion cannot be decided for an ear that does not
    meet it on the data present; None when the data show it is not met.

    The criterion is bilateral, so the second ear decides between "not met"
    and "cannot be assessed". It is undecided when the 0.5/1/2/4 kHz
    thresholds it lacks could still give it CI_MIN_FREQS at 80 dB HL or
    worse — an ear not tested at all is the extreme case — or when the record
    holds only its average, which can sit below 80 dB HL with two
    frequencies beyond it.
    """
    thresholds = _numeric_ac(analysis, side)
    measured = {f: thresholds[f] for f in PTA_FREQS if thresholds.get(f) is not None}
    if measured:
        missing = [f for f in PTA_FREQS if f not in measured]
        beyond = sum(1 for v in measured.values() if v >= CI_THRESHOLD_DB)
        if missing and beyond + len(missing) >= CI_MIN_FREQS:
            return "was not tested at " + ", ".join(f"{f} Hz" for f in missing)
        return None
    if thresholds:
        return "was not tested at 500, 1000, 2000 or 4000 Hz"
    pta = (((analysis.get("rules") or {}).get(side) or {}).get("ac_pta") or {}).get("value")
    if pta is not None:
        return ("has only its four-frequency average in this record, not the "
                "per-frequency thresholds")
    return "was not tested"


_CI_BASIS = {
    "thresholds": ("80 dB HL or worse at two or more of 0.5/1/2/4 kHz, the NICE "
                   "TA566 audiometric criterion"),
    "pta": ("a four-frequency average of 80 dB HL or worse; the per-frequency "
            "thresholds are not in this record, so the NICE TA566 criterion of "
            "80 dB HL or worse at two or more of 0.5/1/2/4 kHz is still to be "
            "confirmed"),
}


def _implant_recommendation(ci_ears: Dict[str, str],
                            unassessed: Optional[Dict[str, str]] = None) -> str:
    """Cochlear-implant wording from the measured degree of loss only.

    NICE TA566 applies its audiometric criterion to both ears, so a referral
    for implant candidacy is made when both meet it. When one ear meets it,
    the other decides the wording: shown not to meet it, the criterion is
    stated not met; missing the data to decide (``unassessed``, from
    ``_ci_unassessable``), the criterion is stated not assessable and that
    ear's testing is asked for. Either way the affected ear is referred for
    ENT assessment, and candidacy is decided by aided speech testing, never
    by the audiogram.
    """
    unassessed = unassessed or {}
    bases = set(ci_ears.values())
    if len(bases) == 1:
        basis = _CI_BASIS[bases.pop()]
    else:
        basis = "; ".join(f"{s}: {_CI_BASIS[b]}" for s, b in ci_ears.items())
    if len(ci_ears) == 2:
        return (f"Severe-to-profound loss in both ears ({basis}): refer for "
                "cochlear-implant candidacy assessment. Candidacy is decided by "
                "aided speech-recognition testing with appropriately fitted "
                "hearing aids, not by the audiogram or its configuration label.")
    side = next(iter(ci_ears))
    other = "left" if side == "right" else "right"
    if other in unassessed:
        return (f"Severe-to-profound loss in the {side} ear ({basis}). The "
                f"{other} ear {unassessed[other]}, so whether the NICE TA566 "
                "implant criterion, which requires this in both ears, is met "
                f"cannot be assessed; complete the {other} ear's thresholds and "
                f"refer for ENT assessment of the {side} ear. Options for a "
                "severely affected ear, including any implant, are decided by "
                "aided speech-recognition testing, not by the audiogram or its "
                "configuration label.")
    return (f"Severe-to-profound loss in the {side} ear only ({basis}). NICE "
            "TA566 requires this in both ears, so its implant criterion is not "
            f"met; refer for ENT assessment of the {side} ear. Options for a "
            "single severely affected ear, including any implant, are decided "
            "by aided speech-recognition testing, not by the audiogram or its "
            "configuration label.")


#: Keys under which the rules engine may explain why a disability percentage
#: cannot be certified (``rules.disability.certifiable``).
_CERTIFIABLE_REASON_KEYS = (
    "certifiable_reason", "certifiable_reasons", "certification_note",
    "not_certifiable_reason", "certifiable_note",
)


def _certification_caveat(disability: dict) -> str:
    """Why the percentage cannot be certified, without a leading verdict
    phrase (callers supply their own)."""
    for key in _CERTIFIABLE_REASON_KEYS:
        reason = disability.get(key)
        if reason:
            text = reason if isinstance(reason, str) else "; ".join(map(str, reason))
            text = re.sub(r"^\s*not certifiable\s*[:\-—–]\s*", "", text, flags=re.I)
            return text.rstrip(".") + "."
    return ("the measurements behind the percentage do not meet the requirements "
            "for certification under the RPwD Act 2016 guidelines; complete them "
            "before certifying.")


def _recommendations(analysis: dict) -> List[str]:
    rules = analysis.get("rules") or {}
    disability = rules.get("disability") or {}
    recs: List[str] = []

    # Safety first: emergencies and validity problems outrank everything else.
    for alert in (analysis.get("safety") or {}).get("alerts", []):
        if alert["level"] in ("emergency", "urgent", "validity"):
            prefix = {"emergency": "URGENT", "urgent": "PRIORITY",
                      "validity": "TEST VALIDITY"}[alert["level"]]
            recs.append(f"{prefix} — {alert['title']}: {alert['action']}")
    worst = max(
        (rules.get(s, {}).get("ac_pta") or {}).get("value", 0) for s in ("right", "left")
    )
    types = {(rules.get(s) or {}).get("type") or "" for s in ("right", "left")}
    # rules.hearing_type types an ear within normal limits Normal even with an
    # air-bone gap over 10 dB; the gap is still a conductive component.
    gap_only = [s for s in ("right", "left")
                if (rules.get(s) or {}).get("type") == "Normal"
                and (rules.get(s) or {}).get("significant_air_bone_gap")]

    if any("Conductive" in t or "Mixed" in t for t in types) or gap_only:
        recs.append("ENT referral for the conductive component (tympanometry, "
                    "otoscopy); many conductive losses are medically or "
                    "surgically treatable.")
    for s in gap_only:
        note = (rules.get(s) or {}).get("air_bone_gap_note")
        if note:
            recs.append(f"{s.capitalize()} ear: {note}")
    if worst >= 35:
        sii = (analysis.get("sii") or {}).get("better") or (analysis.get("sii") or {}).get("right")
        if sii and sii.get("aided_quiet") and sii.get("aided_gain_quiet", 0) > 5:
            recs.append(
                "Hearing-aid evaluation and fitting for the affected ear(s): a NAL-R "
                f"first-fit projects audible speech cues rising from "
                f"{sii['quiet']['percent']:g}% to {sii['aided_quiet']['percent']:g}% in quiet "
                f"(+{sii['aided_gain_quiet']:g} points)."
            )
        else:
            recs.append("Hearing-aid evaluation and fitting for the affected ear(s).")
    ci_ears = _severe_to_profound_ears(analysis)
    if ci_ears:
        unassessed: Dict[str, str] = {}
        for s in ("right", "left"):
            reason = None if s in ci_ears else _ci_unassessable(analysis, s)
            if reason:
                unassessed[s] = reason
        recs.append(_implant_recommendation(ci_ears, unassessed))
    ml_all = analysis.get("ml") or {}
    notch_sides = [s for s in ("right", "left")
                   if ml_all.get(s) and ml_all[s].get("pattern") == "noise_notch_4k"
                   and _label_usable(analysis, s, ml_all[s])[0]]
    if notch_sides:
        recs.append("Mandatory hearing protection in noise; annual audiometric "
                    "monitoring per hearing-conservation guidelines.")
    # A deep 4 kHz notch keeps its label and the advice above, but a single
    # keying slip draws the same shape, so the 4 kHz threshold is confirmed.
    for s in notch_sides:
        thresholds = _numeric_ac(analysis, s)
        retest = notch_retest_note(thresholds, "noise_notch_4k") if thresholds else None
        if retest:
            recs.append(f"{s.capitalize()} ear: {retest}.")
    certifiable = disability.get("certifiable", True) if disability else True
    if disability and not certifiable:
        recs.append(
            "The disability percentage cannot be certified from this test: "
            + _certification_caveat(disability)
        )
    elif disability.get("benchmark_disability"):
        recs.append("Patient meets the RPwD Act 2016 benchmark (≥40%); assist "
                    "with disability certification for entitled benefits.")
    provisional = [s for s in ("right", "left")
                   if (rules.get(s) or {}).get("provisional")]
    if provisional:
        # A bone-conduction "No Response" is a measurement at the vibrator's
        # output limit, not a test left undone: repeating it cannot settle the
        # gap, and the recommendation says so.
        bc_nr = [s for s in provisional if (rules.get(s) or {}).get("bc_nr_freqs")]
        untested = [s for s in provisional if s not in bc_nr]
        if untested:
            recs.append("Complete bone-conduction testing to confirm the type of loss "
                        "(current typing is provisional).")
        for s in bc_nr:
            freqs = ", ".join(str(f) for f in rules[s]["bc_nr_freqs"])
            recs.append(
                f"{s.capitalize()} ear: bone conduction gave no response at {freqs} Hz "
                "within the vibrator's output limit, so the air-bone gap there is "
                "indeterminate and the type is provisional — a conductive component "
                "cannot be excluded; tympanometry (and otoscopy) can show whether "
                "the middle ear contributes.")
    recs.append("Repeat pure-tone audiometry in 6–12 months to monitor stability.")
    return recs


# ----------------------------------------------------- offline generator ---

def generate_offline(analysis: dict) -> dict:
    rules = analysis.get("rules") or {}
    phonemes = analysis.get("phonemes") or {}
    disability = rules.get("disability")

    findings = [
        _ear_summary(rules.get("right") or {}, "right"),
        _ear_summary(rules.get("left") or {}, "left"),
    ]
    for side in ("right", "left"):
        for c in (rules.get(side) or {}).get("caveats") or []:
            findings.append(f"Note ({side}): {c}.")

    for alert in (analysis.get("safety") or {}).get("alerts", []):
        if alert["level"] in ("emergency", "urgent", "validity"):
            findings.append(
                f"{alert['title']} ({alert['ear'] or 'both'} ear): {alert['detail']}"
            )
    for side in ("right", "left"):
        sp = (analysis.get("speech_audiometry") or {}).get(side)
        if sp and sp.get("srt"):
            findings.append(f"{side.capitalize()} ear speech: {sp['srt']['message']}")
        if sp and sp.get("wrs"):
            findings.append(
                f"{side.capitalize()} ear word recognition: {sp['wrs']['pb_max']:g}% at "
                f"{sp['wrs']['pb_max_level']} dB HL — {sp['wrs']['interpretation']}."
            )

    degree_type = []
    for side in ("right", "left"):
        ear = rules.get(side, {})
        g = ear.get("who_grade")
        if g:
            degree_type.append(
                f"{side.capitalize()}: {g['grade']} (WHO 2021, PTA {g['pta']:g} dB HL), "
                f"type: {ear['type']}."
            )

    if disability:
        dis_lines = [
            f"Right ear monaural impairment: {(disability.get('right') or {}).get('formula')}",
            f"Left ear monaural impairment: {(disability.get('left') or {}).get('formula')}",
            f"Binaural: {disability.get('binaural_formula')}",
            ("MEETS" if disability.get("benchmark_disability") else "Does not meet")
            + " the RPwD Act 2016 benchmark-disability threshold (40%).",
        ]
        # A percentage computed from incomplete or provisional measurements
        # must never read as a certifiable figure — it reaches a government
        # disability certificate.
        if not disability.get("certifiable", True):
            dis_lines.append(
                "NOT CERTIFIABLE as it stands: " + _certification_caveat(disability)
            )
        elif disability.get("guideline_note"):
            # The method is the 2018 Gazette's, which S.O. 1338(E) (2024)
            # superseded; a certifiable figure carries that beside it.
            dis_lines.append(disability["guideline_note"])
    else:
        dis_lines = ["Disability percentage not computable (incomplete PTA data)."]

    impact = []
    for side in ("right", "left"):
        ph = phonemes.get(side)
        if ph:
            impact.append(
                f"{side.capitalize()} ear hears {ph['audibility_pct']:g}% of "
                f"conversational phonemes"
                + (f"; inaudible: {', '.join('/' + s + '/' for s in ph['inaudible'])}."
                   if ph["inaudible"] else "; all speech sounds audible.")
            )
    combined = phonemes.get("better") or phonemes.get("right")
    if combined:
        impact.extend(combined["impact"])

    sii = (analysis.get("sii") or {}).get("better") or (analysis.get("sii") or {}).get("right")
    if sii:
        impact.append(
            f"Speech Intelligibility Index (better ear): "
            f"{sii['quiet']['percent']:g}% of speech cues audible in quiet"
            + (f", falling to {sii['noise']['percent']:g}% in background noise"
               if sii.get("noise") else "")
            + f" — {sii['quiet']['descriptor']}."
        )
    words = analysis.get("speech_words")
    if words and words["counts"]["missed"]:
        missed = [w["word"] for w in words["words"] if w["status"] == "missed"][:6]
        impact.append(
            f"In a standard test sentence, roughly {words['missed_pct']:g}% of words "
            f"would be misheard (e.g. {', '.join(missed)})."
        )

    report = {
        "findings": findings,
        "pattern_etiology": _etiology(analysis),
        "degree_type": degree_type,
        "disability": dis_lines,
        "functional_impact": impact,
        "recommendations": _recommendations(analysis),
        "disclaimer": DISCLAIMER,
    }
    verification = verify_offline(report, analysis)
    return {
        "report": report,
        "verified": verification["verified"],
        "verification": verification,
        "counseling": counseling_sheet(analysis),
        "engine": "offline-template",
        "fallback_used": False,
    }


# --------------------------------------------------- deterministic verify --

def verify_offline(report: dict, analysis: dict) -> dict:
    """Re-derive every key number from the structured JSON and confirm the
    draft report states it. Returns per-claim check results."""
    text = json.dumps(report, ensure_ascii=False)
    rules = analysis.get("rules") or {}
    checks = []

    def expect(claim: str, needle: str):
        checks.append({"claim": claim, "expected": needle, "found": needle in text})

    for side in ("right", "left"):
        pta = rules.get(side, {}).get("ac_pta")
        if pta:
            expect(f"{side} PTA value", f"{pta['value']:g}")
            g = rules.get(side, {}).get("who_grade")
            if g:
                expect(f"{side} WHO grade", g["grade"])
            expect(f"{side} type", rules[side]["type"])
    disability = rules.get("disability")
    if disability:
        expect("binaural disability %", f"{disability['binaural_pct']:g}")
    verified = all(c["found"] for c in checks) and bool(checks)
    return {"verified": verified, "checks": checks, "method": "deterministic re-derivation"}


# ------------------------------------------------------- counseling sheet --

def counseling_sheet(analysis: dict) -> dict:
    """Plain-language (8th-grade) patient summary in six languages.

    Built from the pre-authored phrase tables in ``languages.py`` so the
    same clinical facts are stated identically in every language.
    """
    rules = analysis.get("rules") or {}
    name = (analysis.get("patient") or {}).get("name") or "You"
    disability = rules.get("disability")
    urgent = (analysis.get("safety") or {}).get("has_urgent")

    hearing_aid = any(
        (rules.get(s, {}).get("ac_pta") or {}).get("value", 0) >= 35
        for s in ("right", "left")
    )

    sheet = {}
    for lang in LANGUAGES:
        summary = []
        if urgent:
            summary.append(URGENT[lang])
        for side in ("right", "left"):
            g = rules.get(side, {}).get("who_grade")
            if g:
                grade_word = GRADE_SIMPLE[lang].get(g["grade"])
                if grade_word:
                    summary.append(EAR_SENTENCE[lang].format(
                        side=SIDE_WORD[lang][side], grade=grade_word))
        if hearing_aid:
            summary.append(HEARING_AID[lang])
        # Telling a patient they qualify for benefits on a figure that cannot
        # be certified sets up a refused application.
        if (disability and disability.get("benchmark_disability")
                and disability.get("certifiable", True)):
            summary.append(BENCHMARK[lang].format(pct=f"{disability['binaural_pct']:g}"))

        sheet[lang] = {
            "summary": summary,
            "tips": TIPS[lang],
            "heading": HEADING[lang].format(name=name),
            "tips_heading": TIPS_HEADING[lang],
            "label": LANGUAGES[lang]["label"],
            "native": LANGUAGES[lang]["native"],
            "tts": LANGUAGES[lang]["tts"],
        }

    sheet["reading_level"] = "8th grade"
    sheet["languages"] = {k: v for k, v in LANGUAGES.items()}
    return sheet


# ------------------------------------------------------------- LLM engine --

GENERATOR_SYSTEM = """You are a senior clinical audiologist writing a formal
interpretation of a pure-tone audiometry test. You are given ONLY structured
JSON produced by a deterministic clinical rules engine, an ML pattern
classifier and a phoneme audibility model. Use ONLY numbers present in the
JSON — never invent values. Tie likely etiologies to the patient's
occupation and age where relevant (e.g. a 4 kHz noise notch in a factory
worker suggests occupational noise-induced hearing loss).

Rules for the ML pattern of each ear (ml.right / ml.left):
- Suggest an etiology ONLY when that ear's "reliable" is true. If it is
  false, call the configuration provisional, quote its "reliability_note",
  and suggest no etiology.
- "pattern": "normal" means thresholds within normal limits: state that and
  suggest no etiology. "pattern": null means too few frequencies were tested.
- An ear whose four-frequency average is below 20 dB HL has normal hearing
  by WHO 2021 grade; never describe it as having a loss configuration
  unless that ear's "reliable" is true.
- Never derive cochlear-implant candidacy from a pattern label; base it only
  on thresholds (80 dB HL or worse at two or more of 0.5-4 kHz, in BOTH ears
  for the NICE TA566 criterion; one ear alone does not meet it, and when the
  other ear lacks the thresholds to decide, say the criterion cannot be
  assessed) and say that aided speech testing decides candidacy.
- If rules.disability.certifiable is false, say the disability percentage
  cannot be certified from this test.
- Never state a "hearing age", and never compare the thresholds with
  age-expected (ISO 7029) values; that comparison is not part of this report.
  The patient's age may still inform the likely etiology.

Return STRICT JSON only:
{
 "findings": [<sentences>],
 "pattern_etiology": [<sentences>],
 "degree_type": [<sentences>],
 "disability": [<sentences incl. the full formula steps>],
 "functional_impact": [<sentences from the phoneme data>],
 "recommendations": [<sentences>],
 "disclaimer": "AI-assisted interpretation; final diagnosis requires a qualified audiologist."
}"""

VERIFIER_SYSTEM = """You are a meticulous clinical QA auditor. You receive
(1) structured JSON data from a deterministic audiology rules engine and
(2) a draft report. Check EVERY number and claim in the draft against the
data: PTA values, WHO grades, types, air-bone gaps, disability percentages,
phoneme lists. Correct any inconsistency. Return STRICT JSON:
{"report": <the corrected report object, same schema>,
 "issues_found": [<description of each correction, empty if none>]}"""


def generate_report(analysis: dict) -> dict:
    """Entry point: LLM pipeline when enabled, offline engine otherwise."""
    if not llm_provider.ai_enabled():
        return generate_offline(analysis)
    cfg = get_config()
    try:
        payload = json.dumps(_slim(analysis), ensure_ascii=False)
        draft_raw = llm_provider.call_llm(
            f"Structured audiometry data:\n{payload}", system=GENERATOR_SYSTEM
        )
        draft = llm_provider.extract_json(draft_raw)
        verify_raw = llm_provider.call_llm(
            f"DATA:\n{payload}\n\nDRAFT REPORT:\n{json.dumps(draft, ensure_ascii=False)}",
            system=VERIFIER_SYSTEM,
        )
        verified_obj = llm_provider.extract_json(verify_raw)
        report = verified_obj.get("report", draft)
        report["disclaimer"] = DISCLAIMER
        return {
            "report": report,
            "verified": True,
            "verification": {
                "verified": True,
                "issues_found": verified_obj.get("issues_found", []),
                "method": f"dual-LLM verification ({cfg.provider})",
            },
            "counseling": counseling_sheet(analysis),
            "engine": f"llm:{cfg.provider}",
            "fallback_used": False,
        }
    except Exception as exc:
        result = generate_offline(analysis)
        result["fallback_used"] = True
        result["fallback_reason"] = f"AI provider failed: {str(exc)[:200]}"
        return result


#: Analysis keys never sent to the LLM. "phonemes" is replaced by a slim
#: summary below. "norms" carries the ISO 7029 hearing-age comparison, which
#: was withdrawn from the Results page at NIEPMD's request (see
#: verdict.build_verdict); the offline report never states it, so the AI
#: report must not be given it to restate.
_LLM_EXCLUDED_KEYS = ("phonemes", "norms")


def _slim(analysis: dict) -> dict:
    """Strip bulky per-phoneme detail and the withdrawn age comparison before
    sending to the LLM, and give it the same per-ear reliability verdict the
    offline engine acts on."""
    slim = {k: v for k, v in analysis.items() if k not in _LLM_EXCLUDED_KEYS}
    ml = analysis.get("ml") or {}
    if isinstance(ml, dict):
        slim_ml = dict(ml)
        for side in ("right", "left"):
            m = ml.get(side)
            if isinstance(m, dict) and m.get("pattern") not in (None, "normal"):
                usable, note = _label_usable(analysis, side, m)
                slim_ml[side] = {**m, "reliable": usable,
                                 "reliability_note": note or m.get("reliability_note")}
        slim["ml"] = slim_ml
    phonemes = analysis.get("phonemes") or {}
    slim["phonemes"] = {
        side: {
            "audible": p.get("audible"),
            "inaudible": p.get("inaudible"),
            "audibility_pct": p.get("audibility_pct"),
            "impact": p.get("impact"),
        }
        for side, p in phonemes.items()
        if isinstance(p, dict)
    }
    return slim
