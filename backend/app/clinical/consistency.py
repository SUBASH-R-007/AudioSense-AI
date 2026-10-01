"""Cross-modal consistency engine — reconciling the whole test battery.

Any single test can mislead. Pure tones need a cooperative patient;
tympanometry says nothing about the cochlea; OAEs say nothing about the
neural pathway. Diagnosis comes from whether the tests AGREE, and from
naming the specific pattern when they do not.

This module takes the audiogram, immittance, reflexes, OAEs and speech
audiometry for one ear and returns:

  - CONFIRMATIONS: independent tests that corroborate the audiogram, which
    is what lets a clinician trust it.
  - CONTRADICTIONS: combinations that cannot all be true, each named with
    the classic differential.
  - NOTES: results that cannot be interpreted on their own — absent
    emissions or reflexes that an abnormal middle ear already explains, and
    emissions too noisy to judge. They neither confirm nor contradict the
    audiogram. A note marked ``follow_up`` leaves a clinical question open
    (cochlear status at a normal threshold that the emissions were run to
    answer, or word recognition the middle ear does not explain), so its
    repeat-test action must reach the verdict rather than read as "no action
    required". An emission repeat at a frequency whose threshold already
    shows a loss, or in an ear the audiogram already grades as a loss, is not
    a follow-up: it would refine the picture, and must not displace the
    referral those thresholds call for.

Named patterns implemented:
  effusion_confirmed        conductive loss + Type B tympanogram
  conductive_confirmed      conductive loss + another abnormal tympanogram
                            (including Type C negative pressure)
  otosclerosis_pattern      conductive loss + Type As + absent reflexes
  preclinical_nihl          normal thresholds + absent OAEs + CONFIRMED normal
                            middle ear (damage before shift)
  preclinical_nihl_possible the same with the middle ear not assessed
  oae_middle_ear_limited    absent OAEs explained by an abnormal middle ear
  oae_inconclusive          OAE frequencies too noisy to judge either way
  auditory_neuropathy       OAEs present + reflexes absent + poor speech
  non_organic               OAEs and/or reflexes better than the audiogram allows
  oae_threshold_mismatch_possible  a response above a noisy floor where the
                            thresholds say none should exist — repeat in quiet
  retrocochlear             reflexes absent / rollover with a cochlea that works
  reflexes_middle_ear_limited  absent reflexes explained by the middle ear
  cochlear_confirmed        loss + absent OAEs + normal middle ear (sensorineural)

THE MIDDLE EAR GATES EVERY INFERENCE FROM AN ABSENCE. Emissions travel out
through the middle ear and the reflex is read through it, so a middle-ear
disorder abolishes both on its own. Absent emissions point to the outer hair
cells only "with confirmation of normal middle ear function" (BSA 2023 OAE
Recommended Procedure, Table 4); absent reflexes point along the neural arc
only when the middle ear is not already enough to explain them (Jerger,
Anthony, Jerger & Mauldin 1974). ``_middle_ear_status`` is the one place that
decides whether that confirmation exists.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.clinical.oae import (EMISSION_EXPECTED_MAX_DB_HL, NOISE_FLOOR_MAX_DB_SPL,
                              OAE_CEILING_DB_HL)

#: Air-bone gap (dB, mean over the PTA frequencies) above which a conductive
#: component is present — the same "> 10 dB" convention as rules.hearing_type.
ABG_SIGNIFICANT_DB = 10.0

#: PTA (dB HL) above which present acoustic reflexes begin to question the
#: thresholds. "Absence of reflex responses is rare for hearing losses of less
#: than about 80 dB HL when the hearing loss is attributable to cochlear
#: involvement" (Silman & Gelfand 1981, J Speech Hear Disord 46:312-316);
#: Gelfand, Schwander & Silman (1990, JSHD 55:198-205) likewise find reflex
#: thresholds usable for losses up to about 75 dB before no-responses
#: dominate. Recruitment keeps reflexes in moderate and severe cochlear losses,
#: so their presence below this level is expected, not a validity problem.
REFLEX_PRESENT_UNEXPECTED_PTA = 80.0


def _mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


def _middle_ear_status(tymp: Optional[dict], rules_ear: dict,
                       immittance: Optional[dict] = None) -> Tuple[str, str]:
    """Whether the middle ear is confirmed normal, abnormal, or unknown.

    Returns ``(status, reason)``, ``status`` one of "normal" / "abnormal" /
    "unknown", and ``reason`` a clause naming the evidence for the report.

    Normal requires positive evidence: a Type A tympanogram that is not
    provisional, and no air-bone gap. Every other type counts as abnormal —
    Type C negative pressure, like an effusion, reduces or abolishes
    emissions — and a missing or provisional tympanogram is unknown, never
    assumed normal.
    """
    abg = (rules_ear.get("abg") or {}).get("value")
    ear_type = rules_ear.get("type", "") or ""
    if (abg is not None and abg > ABG_SIGNIFICANT_DB) \
            or "Conductive" in ear_type or "Mixed" in ear_type:
        gap = f" of {abg:g} dB" if abg is not None else ""
        return "abnormal", f"there is an air-bone gap{gap}"
    if not tymp:
        if (immittance or {}).get("tympanogram_untyped"):
            if (immittance or {}).get("infant_warning"):
                return "unknown", ("the infant tympanogram could not be typed "
                                   "without a 1000 Hz probe")
            return "unknown", ("the tympanogram values entered were not enough to "
                               "type it")
        return "unknown", "no tympanogram was recorded"
    if tymp.get("provisional"):
        return "unknown", ("the tympanogram is provisional (probe tone not valid "
                           "for the patient's age)")
    if tymp.get("type") != "A":
        return "abnormal", f"the tympanogram is {tymp.get('label') or tymp.get('type')}"
    return "normal", "Type A tympanogram with no air-bone gap"


#: Public name for the one middle-ear gate. Any other module that infers
#: something from an absent emission or reflex (the disease-linkage panel, for
#: one) should call this rather than restate the rule, or the two screens will
#: disagree about the same ear.
middle_ear_status = _middle_ear_status


def _informative(freqs: List[int], ac_numeric: Dict[int, Optional[float]]) -> List[int]:
    """The frequencies at which a cochlear loss could still leave an emission.

    Above ``OAE_CEILING_DB_HL`` a cochlear loss abolishes emissions, so a
    frequency there that was too noisy to judge cannot change where a cochlear
    loss is placed (only an emission that should not exist could, which the
    note says). Where no threshold was recorded, the emission could have
    mattered either way.
    """
    out = []
    for f in freqs:
        thr = ac_numeric.get(f)
        if thr is None or thr <= OAE_CEILING_DB_HL:
            out.append(f)
    return out


def _emission_expected(freqs: List[int],
                       ac_numeric: Dict[int, Optional[float]]) -> List[int]:
    """The frequencies at which a healthy cochlea would have given an emission.

    Within normal limits (``EMISSION_EXPECTED_MAX_DB_HL``) an absent emission
    is itself a finding — outer hair cell loss the audiogram cannot yet show —
    so a frequency there that was too noisy to judge leaves that screen
    undone. With no threshold recorded the emission may be the only evidence
    about the cochlea at all. Above the normal limit the thresholds already
    show the loss and already set the management; an emission there would
    only help place it.
    """
    out = []
    for f in freqs:
        thr = ac_numeric.get(f)
        if thr is None or thr <= EMISSION_EXPECTED_MAX_DB_HL:
            out.append(f)
    return out


def reconcile_ear(
    side: str,
    rules_ear: dict,
    immittance: Optional[dict],
    oae: Optional[dict],
    speech: Optional[dict],
    ac_numeric: Dict[int, Optional[float]],
) -> dict:
    """Reconcile every available test for one ear."""
    confirmations: List[dict] = []
    contradictions: List[dict] = []
    notes: List[dict] = []
    patterns: List[str] = []

    pta = (rules_ear.get("ac_pta") or {}).get("value")
    ear_type = rules_ear.get("type", "") or ""
    # An ear within normal limits is typed Normal even with a significant
    # air-bone gap (rules.hearing_type: a type names a loss), but the gap is
    # still a conductive finding and must be cross-checked like one.
    gap_without_loss = (not ("Conductive" in ear_type or "Mixed" in ear_type)
                        and bool(rules_ear.get("significant_air_bone_gap")))
    conductive = "Conductive" in ear_type or "Mixed" in ear_type or gap_without_loss
    tymp = (immittance or {}).get("tympanogram")
    reflexes = (immittance or {}).get("reflexes")
    middle_ear, middle_ear_reason = _middle_ear_status(tymp, rules_ear, immittance)

    # ---------------------------------------------------------- middle ear
    if tymp:
        if conductive and tymp["suggests_conductive"]:
            patterns.append(
                "effusion_confirmed" if tymp["type"] == "B" else "conductive_confirmed"
            )
            confirmations.append({
                "title": (f"Air-bone gap confirmed by tympanometry ({tymp['label']})"
                          if gap_without_loss else
                          f"Conductive loss confirmed by tympanometry ({tymp['label']})"),
                "detail": (
                    f"The air-bone gap is corroborated by an independent "
                    f"measure of middle-ear function. {tymp['interpretation']}"
                ),
            })
        elif conductive and tymp["type"] == "C":
            # Negative middle-ear pressure stiffens the drum and commonly
            # brings a mild conductive loss with it (Jerger 1970), so a gap
            # here is the expected companion of the tympanogram, not a reason
            # to suspect a third window.
            patterns.append("conductive_confirmed")
            confirmations.append({
                "title": f"Conductive component consistent with tympanometry ({tymp['label']})",
                "detail": (
                    "Negative middle-ear pressure commonly produces a mild conductive "
                    "loss, so the air-bone gap and the tympanogram agree. A gap larger "
                    "than a mild loss suggests fluid is collecting as well. "
                    f"{tymp['interpretation']}"
                ),
            })
        elif conductive and not tymp["suggests_conductive"]:
            contradictions.append({
                "title": "Air-bone gap without middle-ear pathology",
                "detail": (
                    f"The audiogram shows a conductive component but tympanometry is "
                    f"{tymp['label']}. Re-check bone-conduction placement and masking; "
                    "consider a third-window disorder such as superior canal dehiscence."
                ),
                "action": "Repeat masked bone conduction; ENT referral if it persists.",
            })
        elif not conductive and tymp["suggests_conductive"]:
            contradictions.append({
                "title": "Middle-ear pathology without an air-bone gap",
                "detail": (
                    f"{tymp['label']} indicates a middle-ear problem, yet the audiogram "
                    "shows no significant gap. Early or mild pathology, or bone "
                    "conduction needs re-checking."
                ),
                "action": "Confirm bone-conduction thresholds; consider otoscopy.",
            })

    if tymp and tymp["type"] == "As" and reflexes and reflexes["pattern"] == "absent" \
            and conductive:
        patterns.append("otosclerosis_pattern")
        confirmations.append({
            "title": "Pattern consistent with otosclerosis",
            "detail": ("Stiff (Type As) tympanogram with absent acoustic reflexes and a "
                       "conductive loss is the classic stapedial fixation picture."),
        })

    # -------------------------------------------------------------- cochlea
    # An emission repeat decides what happens next only while the emissions
    # are the screen for damage the audiogram cannot yet show: an ear the
    # audiogram grades normal (WHO 2021: PTA below 20 dB HL) or did not grade.
    # Once the thresholds grade a loss, the referral or counselling that grade
    # calls for comes first, and a repeat would refine the picture rather than
    # change the next step — so it is reported, but not as a follow-up.
    grade = (rules_ear.get("who_grade") or {}).get("grade")
    emissions_screen = grade in (None, "Normal hearing")
    if oae:
        inconclusive = list(oae.get("inconclusive_freqs") or [])
        # Noisy frequencies where an emission was still possible: what they
        # would have shown is unknown, so no conclusion may rest on their
        # absence from the "present" list.
        unresolved = _informative(inconclusive, ac_numeric)
        # A frequency too noisy to judge is not a result. Saying so keeps it
        # from being read as absent off the raw numbers.
        if inconclusive:
            patterns.append("oae_inconclusive")
            # Three bands, by the threshold at the noisy frequency: normal (or
            # not recorded) — an emission was expected and the screen is still
            # owed; outside normal limits up to the emission ceiling — one
            # would only help place a loss the audiogram already shows; above
            # the ceiling — none was possible.
            owed = _emission_expected(inconclusive, ac_numeric)
            localising = [f for f in unresolved if f not in owed]
            expected_absent = [f for f in inconclusive if f not in unresolved]
            detail = (
                f"The noise floor at {inconclusive} Hz was above "
                f"{NOISE_FLOOR_MAX_DB_SPL:g} dB SPL — too high to tell an absent "
                "emission from one hidden in the noise — so those frequencies are "
                "neither a pass nor evidence of damage."
            )
            if localising:
                detail += (f" At {localising} Hz the threshold is already outside "
                           "normal limits: an emission there would help place the "
                           "loss (its absence supports a cochlear site) but would not "
                           "change the management the thresholds call for.")
            if expected_absent:
                # A cochlear loss this large abolishes emissions, so a repeat
                # cannot help place it; but an emission that is present here is
                # the auditory-neuropathy / non-organic finding, which a noisy
                # recording can hide as easily as an absent one.
                detail += (f" At {expected_absent} Hz the threshold is above "
                           f"{OAE_CEILING_DB_HL:g} dB HL, where a cochlear loss "
                           "abolishes emissions; a repeat there matters only to look "
                           "for an emission that should not be present (auditory "
                           "neuropathy, or thresholds that overstate the loss).")
            if owed and not emissions_screen:
                detail += (" The thresholds in this ear already grade a loss, so the "
                           "repeat can wait for the visit that loss calls for.")
            if owed:
                action = (f"Repeat {unresolved} Hz in quiet, with the probe refitted "
                          "and the patient settled.")
            elif localising:
                action = (f"Repeat {localising} Hz in quiet if the site of the loss "
                          "needs confirming.")
            else:
                action = (f"Repeat {expected_absent} Hz in quiet if auditory neuropathy "
                          "or non-organic loss is in question (poor word recognition, "
                          "absent reflexes, or thresholds in doubt).")
            notes.append({
                "title": "Emissions could not be judged at some frequencies",
                "detail": detail,
                "action": action,
                # Where a normal threshold (or none) left an emission expected
                # in an ear the audiogram calls normal, the screen is still owed
                # to the patient: the repeat has to reach the verdict rather
                # than sit under "no action required". Where the thresholds
                # already show a loss, the repeat only refines the picture and
                # must not displace the referral those thresholds call for.
                "follow_up": bool(owed) and emissions_screen,
            })
        # Absent emissions with normal thresholds are outer hair cell damage
        # only once the middle ear is confirmed normal (BSA 2023 Table 4,
        # scenario 2). Without that confirmation the finding is a question,
        # not an urgent diagnosis; with an abnormal middle ear the absence
        # is already explained.
        if oae.get("preclinical_damage"):
            freqs = [m["freq"] for m in oae["preclinical_damage"]]
            # "Absent" here includes an emission that clears the noise but is
            # weaker than the -5 dB SPL minimum: BSA Table 4 counts reduced
            # amplitude and no clear response alike as abnormal.
            if middle_ear == "normal":
                patterns.append("preclinical_nihl")
                confirmations.append({
                    "title": "Pre-clinical cochlear damage detected",
                    "detail": (
                        f"Emissions are absent or abnormally weak at {freqs} Hz while "
                        "thresholds there are still normal, behind a normal middle "
                        "ear. Outer hair cells are being lost before the audiogram "
                        "moves — this is the window in which the remaining hearing "
                        "can still be saved."
                    ),
                    "priority": True,
                })
            elif middle_ear == "unknown":
                patterns.append("preclinical_nihl_possible")
                contradictions.append({
                    "title": ("Possible pre-clinical cochlear damage — confirm "
                              "middle-ear status first"),
                    "detail": (
                        f"Emissions are absent or abnormally weak at {freqs} Hz while "
                        f"thresholds there are normal, but {middle_ear_reason}. A "
                        "middle-ear disorder abolishes emissions just as outer hair "
                        "cell loss does, so this cannot yet be called cochlear damage."
                    ),
                    "action": ("Run tympanometry. If the middle ear is normal, repeat the "
                               "emissions; absence then marks pre-clinical outer hair cell "
                               "damage and hearing protection should be enforced."),
                })
            else:
                patterns.append("oae_middle_ear_limited")
                notes.append({
                    "title": "Absent emissions explained by the middle ear",
                    "detail": (
                        f"Emissions are absent or abnormally weak at {freqs} Hz with "
                        f"normal thresholds, but {middle_ear_reason}. Middle-ear "
                        "dysfunction blocks emissions on their way back to the probe, "
                        "so their absence says nothing yet about the outer hair cells."
                    ),
                    "action": ("Re-check middle-ear function, and repeat the emissions "
                               "once it is normal: until then they cannot show whether "
                               "the outer hair cells are damaged."),
                    # The emissions were run to look for damage the audiogram
                    # cannot yet show, and that question is still open — the
                    # next step, unless the audiogram already grades a loss
                    # whose own referral comes first.
                    "follow_up": emissions_screen,
                })
        if oae.get("unexplained_emissions"):
            freqs = [m["freq"] for m in oae["unexplained_emissions"]]
            contradictions.append({
                "title": "Working cochlea with poor pure-tone thresholds",
                "detail": (
                    f"Emissions are present at {freqs} Hz, so the outer hair cells there "
                    "function normally, yet the reported thresholds are much worse. "
                    "Either the thresholds are exaggerated, or the lesion lies beyond "
                    "the cochlea."
                ),
                "action": "Repeat audiometry with re-instruction; if thresholds hold, "
                          "investigate the neural pathway (ABR).",
            })
            patterns.append("oae_threshold_mismatch")
        elif oae.get("possible_unexplained_emissions"):
            # A response that cleared a noisy floor where the thresholds say
            # none should exist. Not a result (BSA 2023 s.6.2), but the
            # non-organic / neural question it raises is the one emissions
            # exist to answer, and it reaches a disability certificate — so it
            # holds the case for a repeat rather than vanishing into "noisy".
            freqs = [m["freq"] for m in oae["possible_unexplained_emissions"]]
            contradictions.append({
                "title": "Possible emission despite poor pure-tone thresholds",
                "detail": (
                    f"At {freqs} Hz a response clears the noise floor by the "
                    "criterion although the thresholds there should abolish it, "
                    "but the floor was too high for a valid result. If a repeat in "
                    "quiet confirms it, either the thresholds are exaggerated or "
                    "the lesion lies beyond the cochlea."
                ),
                "action": ("Repeat the emissions in quiet before certifying; if they "
                           "are present, repeat audiometry with re-instruction and "
                           "refer for ABR."),
            })
            patterns.append("oae_threshold_mismatch_possible")

        # Same gate as the pre-clinical rule: the text below claims a normal
        # middle ear, so it needs one on record. ``all_absent`` covers only
        # the frequencies that could be judged, and one present emission is
        # what separates a cochlear loss from a neural one — so a noisy
        # frequency where an emission was still possible withholds it.
        if pta is not None and pta > 25 and oae.get("all_absent") \
                and middle_ear == "normal" and not unresolved:
            patterns.append("cochlear_confirmed")
            confirmations.append({
                "title": "Sensorineural loss confirmed as cochlear",
                "detail": ("Absent emissions with a normal middle ear localise the lesion "
                           "to the cochlea, consistent with the audiogram."),
            })

    # ---------------------------------------------------- neural / retrocochlear
    oae_present = bool(oae and oae.get("present_freqs"))
    reflexes_absent = bool(reflexes and reflexes["pattern"] == "absent")
    poor_speech = bool(
        speech and speech.get("wrs") and speech["wrs"].get("pb_max") is not None
        and speech["wrs"]["pb_max"] < 60
    )

    # Absent reflexes point along the neural arc only when the middle ear
    # does not already explain them: a conductive disorder in the probe ear
    # abolishes the reflex in a large share of ears, rising with the size of
    # the gap (Jerger, Anthony, Jerger & Mauldin 1974), and negative pressure
    # alone can hide it when the test is not run at the tympanometric peak.
    if oae_present and reflexes_absent and middle_ear == "abnormal":
        patterns.append("reflexes_middle_ear_limited")
        notes.append({
            "title": "Absent reflexes explained by the middle ear",
            "detail": (
                f"Acoustic reflexes are absent, but {middle_ear_reason}. A middle-ear "
                "disorder abolishes the reflex on its own, so its absence is not "
                "evidence of a neural lesion here."
                + (" Word recognition is disproportionately poor, which the middle "
                   "ear does not explain." if poor_speech else "")
            ),
            "action": ("Repeat reflexes once the middle ear is normal"
                       + ("; if word recognition stays poor, refer for ABR."
                          if poor_speech else ".")),
            # Poor word recognition is unexplained by the middle ear and must
            # reach the verdict; absent reflexes alone are fully explained.
            "follow_up": poor_speech,
        })
    elif oae_present and reflexes_absent:
        unverified = (
            f" Note that {middle_ear_reason}: a middle-ear disorder also abolishes "
            "reflexes, so confirm the middle ear is normal before acting on this."
            if middle_ear == "unknown" else "")
        if (reflexes or {}).get("provisional"):
            # Infant reflexes without a recorded probe tone: a 226 Hz probe
            # misses reflexes that a 1000 Hz probe records in many newborns
            # (Jacob-Corteletti et al. 2015; JCIH 2019).
            unverified += (" The reflexes were recorded in an infant without a "
                           "recorded probe tone, and a 226 Hz probe misses reflexes "
                           "that are present in many young infants — repeat them "
                           "with a 1000 Hz probe.")
        if poor_speech:
            patterns.append("auditory_neuropathy")
            contradictions.append({
                "title": "Auditory neuropathy spectrum disorder pattern",
                "detail": (
                    "Emissions present (outer hair cells working) with absent acoustic "
                    "reflexes and word recognition disproportionately poor for the "
                    "thresholds — the classic dys-synchrony picture." + unverified
                ),
                "action": "Refer for auditory brainstem response (ABR) testing. "
                          "Conventional amplification often disappoints in ANSD.",
            })
        else:
            patterns.append("retrocochlear")
            contradictions.append({
                "title": "Reflexes absent despite a functioning cochlea",
                "detail": ("Emissions are present but acoustic reflexes are absent, "
                           "pointing along the reflex arc rather than to the cochlea."
                           + unverified),
                "action": "ENT / neuro-otology referral; consider ABR and imaging.",
            })

    if speech and speech.get("retrocochlear_suspicion") and oae_present:
        if "retrocochlear" not in patterns and "auditory_neuropathy" not in patterns:
            patterns.append("retrocochlear")

    # -------------------------------------------------------------- honesty
    non_organic_speech = bool(
        speech and speech.get("srt") and speech["srt"].get("non_organic_suspected")
    )
    if non_organic_speech:
        patterns.append("non_organic")
        emissions_too = bool(oae and oae.get("unexplained_emissions"))
        contradictions.append({
            "title": "Objective tests disagree with the pure tones",
            "detail": (
                "The speech reception threshold is more than 10 dB better than both "
                "the three-frequency average and Fletcher's best-two average "
                "(ASHA 1988)"
                + (", and emissions are present where thresholds say they should "
                   "not be" if emissions_too else "")
                + " — the pure-tone thresholds are unlikely to be genuine."
            ),
            "action": "Repeat with re-instruction before any certification; "
                      "objective testing (ABR/ASSR) if it persists.",
        })

    if reflexes and reflexes["pattern"] == "present" and pta is not None \
            and pta > REFLEX_PRESENT_UNEXPECTED_PTA:
        contradictions.append({
            "title": "Reflexes present with a profound loss",
            "detail": (
                f"A cochlear loss rarely abolishes the acoustic reflex below about "
                f"{REFLEX_PRESENT_UNEXPECTED_PTA:g} dB HL, but beyond it absence becomes "
                f"common. Reflexes present at a PTA of {pta:g} dB HL are still possible "
                "through recruitment, yet they also fit thresholds that overstate the "
                "true loss."
            ),
            "action": "Re-check thresholds; correlate with speech testing.",
        })
        patterns.append("reflex_threshold_mismatch")

    agreement = (
        "confirmed" if confirmations and not contradictions
        else "conflicting" if contradictions
        else "insufficient"
    )
    return {
        "ear": side,
        "confirmations": confirmations,
        "contradictions": contradictions,
        "notes": notes,
        "middle_ear": {"status": middle_ear, "reason": middle_ear_reason},
        "patterns": sorted(set(patterns)),
        "agreement": agreement,
        "tests_available": {
            "audiogram": pta is not None,
            "tympanometry": tymp is not None,
            "reflexes": reflexes is not None,
            "oae": oae is not None,
            "speech": speech is not None,
        },
    }


def battery_review(per_ear: Dict[str, dict]) -> dict:
    """Bundle both ears and surface the headline for the UI."""
    contradictions = sum(len(e["contradictions"]) for e in per_ear.values())
    confirmations = sum(len(e["confirmations"]) for e in per_ear.values())
    notes = sum(len(e.get("notes") or []) for e in per_ear.values())
    patterns = sorted({p for e in per_ear.values() for p in e["patterns"]})
    n_tests = max(
        (sum(1 for v in e["tests_available"].values() if v) for e in per_ear.values()),
        default=0,
    )

    if "preclinical_nihl" in patterns:
        headline = ("Cochlear damage is present before the audiogram shows it — "
                    "act now to protect the remaining hearing.")
    elif "auditory_neuropathy" in patterns:
        headline = "Findings fit auditory neuropathy — refer for ABR before fitting aids."
    elif "non_organic" in patterns or "oae_threshold_mismatch" in patterns:
        headline = "Objective tests contradict the pure tones — repeat before certifying."
    elif "oae_threshold_mismatch_possible" in patterns:
        headline = ("An emission may be present where the thresholds say it should "
                    "not be — repeat the emissions in quiet before certifying.")
    elif "preclinical_nihl_possible" in patterns:
        headline = ("Emissions are absent although thresholds are normal — confirm the "
                    "middle ear is normal before calling this cochlear damage.")
    elif contradictions:
        headline = f"{contradictions} finding(s) across the battery do not agree."
    elif notes:
        # "All tests agree" would overstate it: a result the middle ear
        # explains, or one too noisy to judge, has corroborated nothing.
        headline = ("No test contradicts another, but some results could not be "
                    "interpreted on their own — see the notes.")
    elif confirmations:
        headline = f"All {n_tests} tests agree — the audiogram is corroborated."
    elif n_tests > 1:
        headline = ("No cross-check findings — the other tests neither confirm nor "
                    "contradict the audiogram.")
    elif not any(e["tests_available"].get("audiogram") for e in per_ear.values()):
        headline = "No pure-tone audiogram, so there is nothing to cross-check against."
    else:
        headline = "Only pure-tone audiometry available; no cross-checks possible."

    return {
        "right": per_ear.get("right"),
        "left": per_ear.get("left"),
        "patterns": patterns,
        "contradiction_count": contradictions,
        "confirmation_count": confirmations,
        "note_count": notes,
        "tests_run": n_tests,
        "headline": headline,
        "has_contradictions": contradictions > 0,
    }
