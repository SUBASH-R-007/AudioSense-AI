"""Triage — deciding which audiogram the audiologist opens first.

The bottleneck in a high-volume clinic is not interpreting one audiogram.
It is that two hundred of them arrive, all looking alike in a queue, and
the one that needed a doctor this week sits behind a hundred routine
screens. Automating the interpretation without ordering the queue moves
the delay rather than removing it.

This module assigns every analyzed case a priority and — separately — an
explicit routing decision:

  REVIEW REQUIRED   an audiologist must read this before anything is issued
  AUTO-RELEASABLE   the draft interpretation may be released as a draft

The routing is deliberately conservative. A case is auto-releasable only
when the clinical rules are unambiguous AND the classifier is confident
AND nothing about the test itself is in question. Anything unusual routes
to a human, because the cost of a missed sudden hearing loss is measured
in permanent deafness while the cost of an unnecessary review is a minute
of an audiologist's time.
"""
from __future__ import annotations

from typing import List, Optional

#: Priority bands, lowest number = seen first.
PRIORITIES = {
    1: {"key": "critical", "label": "Critical", "sla": "same day",
        "description": "Time-critical finding — treatment window is measured in days."},
    2: {"key": "urgent", "label": "Urgent", "sla": "within 1 week",
        "description": "Needs prompt specialist assessment."},
    3: {"key": "review", "label": "Needs review", "sla": "routine clinic",
        "description": "Interpretation is uncertain or the test needs checking."},
    4: {"key": "routine", "label": "Routine", "sla": "batch review",
        "description": "Unambiguous interpretation; draft can be released."},
}

#: Below this calibrated probability the pattern label is not trustworthy
#: enough to release without a human reading the audiogram.
CONFIDENCE_FLOOR = 0.60


def triage_case(analysis: dict) -> dict:
    """Priority band + routing decision for one analyzed test."""
    safety = analysis.get("safety") or {}
    rules = analysis.get("rules") or {}
    ml = analysis.get("ml") or {}
    battery = analysis.get("battery") or {}

    reasons: List[dict] = []
    priority = 4

    # ---- 1. Red flags set the ceiling ---------------------------------
    for alert in safety.get("alerts", []):
        if alert["level"] == "emergency":
            priority = min(priority, 1)
            reasons.append({"code": "emergency", "detail": alert["title"]})
        elif alert["level"] == "urgent":
            priority = min(priority, 2)
            reasons.append({"code": "urgent", "detail": alert["title"]})
        elif alert["level"] == "validity":
            priority = min(priority, 3)
            reasons.append({"code": "test_validity", "detail": alert["title"]})

    # ---- 2. Model uncertainty ------------------------------------------
    # The classifier is trained only on audiograms that show a loss, so a
    # normal audiogram legitimately sits outside its distribution. Nobody
    # classifies the *shape* of normal hearing, so pattern uncertainty is
    # recorded but does not hold the report when both ears grade normal.
    normal_ears = 0
    graded_ears = 0
    for side in ("right", "left"):
        grade = ((rules.get(side) or {}).get("who_grade") or {}).get("grade")
        if grade:
            graded_ears += 1
            if grade == "Normal hearing":
                normal_ears += 1
    hearing_is_normal = graded_ears > 0 and normal_ears == graded_ears

    for side in ("right", "left"):
        m = ml.get(side)
        if not m:
            continue
        if m.get("ood"):
            if not hearing_is_normal:
                priority = min(priority, 3)
            reasons.append({
                "code": "atypical_pattern",
                "detail": (
                    f"{side} ear: audiogram is outside the classifier's trained "
                    "distribution" + (" — expected, since hearing is normal and the "
                                      "model is trained only on losses"
                                      if hearing_is_normal else "")
                ),
                "blocking": not hearing_is_normal,
            })
        elif m.get("confidence", 1.0) < CONFIDENCE_FLOOR:
            if not hearing_is_normal:
                priority = min(priority, 3)
            reasons.append({
                "code": "low_confidence",
                "detail": (f"{side} ear: pattern confidence "
                           f"{m['confidence']:.0%} below the {CONFIDENCE_FLOOR:.0%} floor"),
                "blocking": not hearing_is_normal,
            })

    # ---- 3. Incomplete or caveated clinical data -----------------------
    for side in ("right", "left"):
        ear = rules.get(side) or {}
        if ear.get("provisional"):
            priority = min(priority, 3)
            reasons.append({
                "code": "provisional_type",
                "detail": f"{side} ear: type provisional — bone conduction incomplete",
            })
        if (ear.get("ac_pta") or {}).get("nr_freqs"):
            reasons.append({
                "code": "no_response",
                "detail": (f"{side} ear: 'No Response' at "
                           f"{ear['ac_pta']['nr_freqs']} Hz computed as 120 dB HL"),
            })

    # ---- 4. Cross-modal disagreement ------------------------------------
    if battery.get("has_contradictions"):
        priority = min(priority, 3)
        reasons.append({
            "code": "battery_conflict",
            "detail": f"{battery['contradiction_count']} test(s) disagree with the audiogram",
        })

    # ---- 5. Entitlement consequences ------------------------------------
    disability = rules.get("disability") or {}
    if disability.get("benchmark_disability"):
        priority = min(priority, 3)
        reasons.append({
            "code": "benchmark_disability",
            "detail": (f"Binaural disability {disability['binaural_pct']:g}% meets the "
                       "RPwD 40% benchmark — certification consequences require sign-off"),
        })

    band = PRIORITIES[priority]
    review_required = priority <= 3
    return {
        "priority": priority,
        "level": band["key"],
        "label": band["label"],
        "sla": band["sla"],
        "description": band["description"],
        "reasons": reasons,
        "review_required": review_required,
        "auto_releasable": not review_required,
        "routing": (
            "Audiologist review required before this interpretation is issued."
            if review_required else
            "Unambiguous and confident — the draft interpretation can be released "
            "for routine countersigning."
        ),
    }


def worklist_summary(cases: List[dict]) -> dict:
    """Aggregate triage across a batch — the clinic's queue at a glance."""
    if not cases:
        return {"total": 0}
    counts = {p["key"]: 0 for p in PRIORITIES.values()}
    for c in cases:
        counts[c["triage"]["level"]] += 1

    review = sum(1 for c in cases if c["triage"]["review_required"])
    auto = len(cases) - review
    top_reasons: dict = {}
    for c in cases:
        for r in c["triage"]["reasons"]:
            top_reasons[r["code"]] = top_reasons.get(r["code"], 0) + 1

    return {
        "total": len(cases),
        "by_priority": counts,
        "review_required": review,
        "auto_releasable": auto,
        "auto_release_pct": round(100 * auto / len(cases), 1),
        "review_reasons": dict(sorted(top_reasons.items(), key=lambda kv: -kv[1])),
        "headline": (
            f"{counts['critical'] + counts['urgent']} case(s) need a clinician now; "
            f"{auto} of {len(cases)} drafts ({round(100 * auto / len(cases))}%) can be "
            "released without one."
        ),
    }


def sort_worklist(cases: List[dict]) -> List[dict]:
    """Order a batch the way a clinic should work through it.

    Priority first, then — within a band — worse hearing first, so the
    people least able to wait are seen soonest.
    """
    def worst_pta(case) -> float:
        values = [
            case.get(side, {}).get("pta") for side in ("right", "left")
            if case.get(side, {}).get("pta") is not None
        ]
        return max(values) if values else 0.0

    return sorted(cases, key=lambda c: (c["triage"]["priority"], -worst_pta(c)))
