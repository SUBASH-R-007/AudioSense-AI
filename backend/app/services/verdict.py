"""The one-sentence answer.

Everything else this system produces is evidence. This module produces the
conclusion — what is wrong with this patient, and what should happen next —
so that it can sit above the evidence rather than have to be assembled from
a dozen cards.

Three parts, in the order a clinician actually wants them:
  HEADLINE   the diagnosis in one plain sentence
  NUMBERS    the three figures that carry the decision
  ACTION     the single most important next step
"""
from __future__ import annotations

from typing import List, Optional

SEVERITY_ORDER = [
    "Profound hearing loss", "Severe hearing loss", "Moderately severe hearing loss",
    "Moderate hearing loss", "Mild hearing loss", "Normal hearing",
]


def _worse_grade(rules: dict) -> Optional[str]:
    grades = [
        (rules.get(side) or {}).get("who_grade", {}).get("grade")
        for side in ("right", "left")
    ]
    grades = [g for g in grades if g]
    if not grades:
        return None
    return min(grades, key=lambda g: SEVERITY_ORDER.index(g)
               if g in SEVERITY_ORDER else 99)


def _symmetry(rules: dict) -> str:
    r = ((rules.get("right") or {}).get("who_grade") or {}).get("grade")
    l = ((rules.get("left") or {}).get("who_grade") or {}).get("grade")
    if r and l and r == l:
        return "Bilateral"
    if r and l:
        return "Asymmetric"
    return "Unilateral"


def build_verdict(analysis: dict) -> dict:
    """Assemble the leading conclusion from the full analysis."""
    rules = analysis.get("rules") or {}
    ml = analysis.get("ml") or {}
    safety = analysis.get("safety") or {}
    triage = analysis.get("triage") or {}
    norms = analysis.get("norms") or {}
    battery = analysis.get("battery") or {}
    patient = analysis.get("patient") or {}
    sii = (analysis.get("sii") or {}).get("better") or (analysis.get("sii") or {}).get("right")

    grade = _worse_grade(rules)
    ear_type = (rules.get("right") or {}).get("type") or (rules.get("left") or {}).get("type")
    pattern = None
    for side in ("right", "left"):
        m = ml.get(side)
        if m:
            pattern = m.get("pattern_label")
            break

    # ---------------- headline ------------------------------------------
    if safety.get("has_emergency"):
        emergency = next(a for a in safety["alerts"] if a["level"] == "emergency")
        headline = f"{emergency['title']} — treat as an emergency."
        tone = "emergency"
    elif "preclinical_nihl" in (battery.get("patterns") or []):
        headline = ("Hearing thresholds are still normal, but the cochlea is already "
                    "being damaged — this loss is still preventable.")
        tone = "warning"
    elif grade == "Normal hearing":
        headline = "Hearing is within normal limits in both ears."
        tone = "normal"
    elif grade:
        symmetry = _symmetry(rules)
        type_word = (ear_type or "").replace(" (provisional)", "").lower()
        descriptor = f"{symmetry.lower()} {grade.lower()}"
        if type_word and type_word not in ("normal", "indeterminate"):
            descriptor = f"{symmetry.lower()} {type_word} {grade.lower()}"
        headline = descriptor[0].upper() + descriptor[1:] + "."
        if pattern:
            # Decapitalize the first letter only — lowercasing the whole label
            # would turn "4 kHz" into "4 khz".
            label = pattern[0].lower() + pattern[1:]
            headline = headline[:-1] + f", {label} configuration."
        tone = "loss"
    else:
        headline = "Insufficient data to reach a conclusion."
        tone = "unknown"

    # ---------------- the numbers that carry the decision ---------------
    numbers: List[dict] = []
    for side in ("right", "left"):
        pta = ((rules.get(side) or {}).get("ac_pta") or {}).get("value")
        if pta is not None:
            numbers.append({
                "label": f"{side.capitalize()} ear PTA",
                "value": f"{pta:g}",
                "unit": "dB HL",
                "hint": ((rules.get(side) or {}).get("who_grade") or {}).get("grade"),
            })
    disability = rules.get("disability")
    if disability:
        numbers.append({
            "label": "Disability (RPwD 2016)",
            "value": f"{disability['binaural_pct']:g}",
            "unit": "%",
            "hint": ("meets the 40% benchmark" if disability["benchmark_disability"]
                     else "below the 40% benchmark"),
            "emphasis": disability["benchmark_disability"],
        })
    if norms.get("hearing_age") and patient.get("age"):
        gap = norms.get("age_gap") or 0
        numbers.append({
            "label": "Hearing age",
            "value": f"{norms['hearing_age']:.0f}",
            "unit": f"vs actual {patient['age']}",
            "hint": (f"{gap:.0f} years older than expected" if gap > 3
                     else "age-appropriate"),
            "emphasis": gap >= 15,
        })
    if sii:
        numbers.append({
            "label": "Speech cues audible",
            "value": f"{sii['quiet']['percent']:g}",
            "unit": "%",
            "hint": f"{sii['noise']['percent']:g}% in noise" if sii.get("noise") else None,
        })

    # ---------------- the single next action ----------------------------
    # Only genuine alerts displace the clinical next step. An informational
    # prompt such as "onset not recorded" is worth showing, but it is not
    # what the clinician should do about this patient's hearing.
    actionable = [a for a in safety.get("alerts", [])
                  if a["level"] in ("emergency", "urgent", "validity")]
    if actionable:
        top = actionable[0]
        action = top.get("action") or top["title"]
        action_level = top["level"]
    elif grade and grade != "Normal hearing":
        worst_pta = max(
            (((rules.get(s) or {}).get("ac_pta") or {}).get("value") or 0)
            for s in ("right", "left")
        )
        if worst_pta >= 80:
            action = "Refer for cochlear implant candidacy assessment."
        elif worst_pta >= 35:
            action = "Refer for hearing-aid evaluation and fitting."
        else:
            action = ("Counsel on hearing protection and repeat audiometry in "
                      "6–12 months.")
        action_level = "routine"
    elif "preclinical_nihl" in (battery.get("patterns") or []):
        action = ("Enforce hearing protection now and re-screen in 6 months — the "
                  "damage is not yet in the audiogram.")
        action_level = "urgent"
    else:
        action = "No action required beyond routine re-screening."
        action_level = "routine"

    return {
        "headline": headline,
        "tone": tone,
        "numbers": numbers[:4],
        "action": action,
        "action_level": action_level,
        "review_required": triage.get("review_required", True),
        "confidence_note": (
            "Interpretation is unambiguous and confident."
            if triage.get("auto_releasable")
            else "Flagged for audiologist review — see the reasons below."
        ),
        "disclaimer": ("AI-assisted interpretation; final diagnosis requires a "
                       "qualified audiologist."),
    }
