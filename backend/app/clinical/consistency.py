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

Named patterns implemented:
  effusion_confirmed      conductive loss + Type B tympanogram
  otosclerosis_pattern    conductive loss + Type As + absent reflexes
  preclinical_nihl        normal thresholds + absent OAEs (damage before shift)
  auditory_neuropathy     OAEs present + reflexes absent + poor speech
  non_organic             OAEs and/or reflexes better than the audiogram allows
  retrocochlear           reflexes absent / rollover with a cochlea that works
  cochlear_confirmed      loss + absent OAEs + normal middle ear (sensorineural)
"""
from __future__ import annotations

from typing import Dict, List, Optional


def _mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


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
    patterns: List[str] = []

    pta = (rules_ear.get("ac_pta") or {}).get("value")
    ear_type = rules_ear.get("type", "")
    conductive = "Conductive" in ear_type or "Mixed" in ear_type
    tymp = (immittance or {}).get("tympanogram")
    reflexes = (immittance or {}).get("reflexes")

    # ---------------------------------------------------------- middle ear
    if tymp:
        if conductive and tymp["suggests_conductive"]:
            patterns.append(
                "effusion_confirmed" if tymp["type"] == "B" else "conductive_confirmed"
            )
            confirmations.append({
                "title": f"Conductive loss confirmed by tympanometry ({tymp['label']})",
                "detail": (
                    f"The air-bone gap is corroborated by an independent "
                    f"measure of middle-ear function. {tymp['interpretation']}"
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
    if oae:
        if oae.get("preclinical_damage"):
            patterns.append("preclinical_nihl")
            freqs = [m["freq"] for m in oae["preclinical_damage"]]
            confirmations.append({
                "title": "Pre-clinical cochlear damage detected",
                "detail": (
                    f"Emissions are absent at {freqs} Hz while thresholds there are still "
                    "normal. Outer hair cells are being lost before the audiogram moves — "
                    "this is the window in which the remaining hearing can still be saved."
                ),
                "priority": True,
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

        if pta is not None and pta > 25 and oae.get("all_absent") and (
                not tymp or not tymp["suggests_conductive"]):
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

    if oae_present and reflexes_absent:
        if poor_speech:
            patterns.append("auditory_neuropathy")
            contradictions.append({
                "title": "Auditory neuropathy spectrum disorder pattern",
                "detail": (
                    "Emissions present (outer hair cells working) with absent acoustic "
                    "reflexes and word recognition disproportionately poor for the "
                    "thresholds — the classic dys-synchrony picture."
                ),
                "action": "Refer for auditory brainstem response (ABR) testing. "
                          "Conventional amplification often disappoints in ANSD.",
            })
        else:
            patterns.append("retrocochlear")
            contradictions.append({
                "title": "Reflexes absent despite a functioning cochlea",
                "detail": ("Emissions are present but acoustic reflexes are absent, "
                           "pointing along the reflex arc rather than to the cochlea."),
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
                "The speech reception threshold is substantially better than the "
                "pure-tone average"
                + (", and emissions are present where thresholds say they should "
                   "not be" if emissions_too else "")
                + " — the pure-tone thresholds are unlikely to be genuine."
            ),
            "action": "Repeat with re-instruction before any certification; "
                      "objective testing (ABR/ASSR) if it persists.",
        })

    if reflexes and reflexes["pattern"] == "present" and pta is not None and pta > 60:
        contradictions.append({
            "title": "Reflexes present with a severe loss",
            "detail": ("Acoustic reflexes are normally absent once the loss exceeds about "
                       "60 dB HL. Their presence suggests the thresholds overstate the "
                       "true loss, or recruitment in a cochlear lesion."),
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
    elif contradictions:
        headline = f"{contradictions} finding(s) across the battery do not agree."
    elif confirmations:
        headline = f"All {n_tests} tests agree — the audiogram is corroborated."
    else:
        headline = "Only pure-tone audiometry available; no cross-checks possible."

    return {
        "right": per_ear.get("right"),
        "left": per_ear.get("left"),
        "patterns": patterns,
        "contradiction_count": contradictions,
        "confirmation_count": confirmations,
        "tests_run": n_tests,
        "headline": headline,
        "has_contradictions": contradictions > 0,
    }
