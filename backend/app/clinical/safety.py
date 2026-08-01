"""Clinical safety layer — red-flag referrals and test-validity checks.

Two jobs that matter more than any classification:

1. RED FLAGS. Some audiograms are not a fitting problem but a medical
   emergency or a tumour screen. Sudden sensorineural hearing loss is
   treatable with corticosteroids but the window is days; asymmetric
   sensorineural loss can be the first sign of a vestibular schwannoma.
   Missing either is the costliest mistake this tool could make.

2. VALIDITY. An unmasked audiogram can record the *other* ear (a "shadow
   curve") and look like real hearing that isn't there. Flagging when
   masking was indicated stops the rest of the pipeline from confidently
   interpreting an invalid test.

Thresholds below follow criteria in common clinical use; exact cut-offs
vary between guidelines, so every flag states its own rule and the payload
is advisory — it recommends referral, it does not diagnose.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import AC_FREQS, PTA_FREQS, ThresholdValue, ear_to_numeric

#: Interaural attenuation for supra-aural earphones, dB. Sound presented
#: above this level can cross the skull and be heard by the opposite
#: cochlea, so the non-test ear must be masked.
INTERAURAL_ATTENUATION_AC = 40
#: Bone conduction crosses the skull essentially unattenuated.
INTERAURAL_ATTENUATION_BC = 0

#: Sudden SNHL: ≥30 dB over ≥3 contiguous frequencies developing within 72 h.
SUDDEN_DROP_DB = 30
SUDDEN_CONTIGUOUS_FREQS = 3


def _n(ear) -> Dict[int, Optional[float]]:
    return ear_to_numeric(ear)


# ---------------------------------------------------------------- asymmetry


def asymmetry_check(right_ac, left_ac) -> dict:
    """Interaural difference screen for retrocochlear referral.

    Commonly used referral criteria (variants exist across guidelines):
    a difference of ≥20 dB at any single frequency, or ≥15 dB at two or
    more frequencies, warrants further investigation — typically MRI with
    contrast to exclude a vestibular schwannoma.
    """
    r, l = _n(right_ac), _n(left_ac)
    diffs: Dict[int, float] = {}
    for f in AC_FREQS:
        if r.get(f) is not None and l.get(f) is not None:
            diffs[f] = round(abs(r[f] - l[f]), 1)
    if not diffs:
        return {"flag": False, "diffs": {}, "reason": "insufficient paired data"}

    single = [f for f, d in diffs.items() if d >= 20]
    moderate = [f for f, d in diffs.items() if d >= 15]
    flag = bool(single) or len(moderate) >= 2
    poorer = None
    if flag:
        r_mean = sum(v for f, v in r.items() if v is not None and f in diffs)
        l_mean = sum(v for f, v in l.items() if v is not None and f in diffs)
        poorer = "right" if r_mean > l_mean else "left"

    reasons = []
    if single:
        reasons.append(f"≥20 dB interaural difference at {single} Hz")
    if len(moderate) >= 2:
        reasons.append(f"≥15 dB interaural difference at {moderate} Hz")

    return {
        "flag": flag,
        "diffs": diffs,
        "max_diff": max(diffs.values()),
        "poorer_ear": poorer,
        "reasons": reasons,
        "criterion": "≥20 dB at one frequency, or ≥15 dB at two or more",
    }


# ------------------------------------------------------------- sudden SNHL


def sudden_loss_check(
    ac: Dict[int, Optional[ThresholdValue]],
    bc: Dict[int, Optional[ThresholdValue]],
    onset: str = "unknown",
    baseline_ac: Optional[Dict[int, Optional[ThresholdValue]]] = None,
) -> dict:
    """Screen for sudden sensorineural hearing loss (an ENT emergency).

    Definition in wide clinical use: ≥30 dB sensorineural loss across three
    contiguous audiometric frequencies developing within 72 hours.

    With a documented earlier audiogram the drop is measured directly.
    Without one, the criterion cannot be confirmed from thresholds alone,
    so the check relies on reported onset and returns a *conditional* flag
    that says exactly what would make it an emergency.
    """
    current = _n(ac)

    if baseline_ac:
        base = _n(baseline_ac)
        run, worst_run = 0, []
        best: List[int] = []
        for f in AC_FREQS:
            if base.get(f) is not None and current.get(f) is not None and \
                    current[f] - base[f] >= SUDDEN_DROP_DB:
                run += 1
                worst_run.append(f)
                if run >= SUDDEN_CONTIGUOUS_FREQS:
                    best = list(worst_run)
            else:
                run, worst_run = 0, []
        if best:
            return {
                "flag": True,
                "urgency": "emergency",
                "confirmed": True,
                "freqs": best,
                "message": (
                    f"≥{SUDDEN_DROP_DB} dB drop across {len(best)} contiguous "
                    "frequencies versus the previous audiogram — consistent with "
                    "sudden sensorineural hearing loss."
                ),
                "action": "Immediate ENT referral. Corticosteroid treatment is "
                          "time-critical; benefit falls sharply after ~2 weeks.",
            }

    # No baseline: use reported onset plus a substantial sensorineural loss.
    bc_n = _n(bc)
    pta_vals = [current[f] for f in PTA_FREQS if current.get(f) is not None]
    pta = sum(pta_vals) / len(pta_vals) if pta_vals else None
    gaps = [current[f] - bc_n[f] for f in PTA_FREQS
            if current.get(f) is not None and bc_n.get(f) is not None]
    sensorineural = (sum(gaps) / len(gaps) <= 10) if gaps else True

    substantial = pta is not None and pta >= 30 and sensorineural
    if onset == "sudden" and substantial:
        return {
            "flag": True,
            "urgency": "emergency",
            "confirmed": False,
            "freqs": [],
            "message": (
                f"Reported sudden onset with a sensorineural loss of {pta:.0f} dB HL "
                "(PTA) — treat as sudden SNHL until proven otherwise."
            ),
            "action": "Immediate ENT referral. Corticosteroid treatment is "
                      "time-critical; benefit falls sharply after ~2 weeks.",
        }
    if onset == "unknown" and substantial:
        return {
            "flag": False,
            "urgency": "ask",
            "confirmed": False,
            "freqs": [],
            "message": (
                "Onset not recorded. If this sensorineural loss appeared within "
                "72 hours, it meets the sudden-SNHL definition and is an emergency."
            ),
            "action": "Ask the patient when the loss began before scheduling routine follow-up.",
        }
    return {"flag": False, "urgency": "none", "confirmed": False, "freqs": [],
            "message": None, "action": None}


# ---------------------------------------------------------------- masking


def masking_check(test_ac, test_bc, other_ac, other_bc, masked: bool = False,
                  transducer: str = None) -> dict:
    """Was masking required to make these thresholds trustworthy?

    Delegates to ``masking.masking_plan``, which holds the full per-frequency
    rule set, the transducer-dependent interaural attenuation and the masking
    dilemma. This module used to carry a second, narrower copy of the rules —
    one air-conduction condition instead of two, and a 10 dB bone-conduction
    trigger instead of 15 — so the safety layer and a clinician working from
    the reference could disagree about the same ear.
    """
    from app.clinical.masking import DEFAULT_TRANSDUCER, masking_plan

    return masking_plan(test_ac, test_bc, other_ac, other_bc,
                        transducer or DEFAULT_TRANSDUCER, masked)


# ------------------------------------------------------------------ bundle


#: Display priority — an emergency must never be pushed below anything else.
ALERT_ORDER = {"emergency": 0, "urgent": 1, "validity": 2, "info": 3}


def sort_alerts(alerts: List[dict]) -> List[dict]:
    """Sort alerts by clinical urgency, in place."""
    alerts.sort(key=lambda a: ALERT_ORDER.get(a["level"], 9))
    return alerts


def safety_review(right, left, onset: str = "unknown",
                  baseline=None, transducer: str = None) -> dict:
    """All safety checks for a full test. ``right``/``left`` are EarData."""
    asym = asymmetry_check(right.ac, left.ac)
    sudden = {
        "right": sudden_loss_check(right.ac, right.bc, onset,
                                   baseline["right"].ac if baseline else None),
        "left": sudden_loss_check(left.ac, left.bc, onset,
                                  baseline["left"].ac if baseline else None),
    }
    from app.clinical.masking import masking_review

    # One review for both ears so the transducer, and therefore the crossover
    # point, is the same on each side of the same test.
    masking_bundle = masking_review(right, left, transducer)
    masking = {"right": masking_bundle["right"], "left": masking_bundle["left"]}

    alerts: List[dict] = []
    for side in ("right", "left"):
        s = sudden[side]
        if s["flag"]:
            alerts.append({
                "level": "emergency", "title": "Possible sudden sensorineural hearing loss",
                "ear": side, "detail": s["message"], "action": s["action"],
            })
        elif s["urgency"] == "ask":
            alerts.append({
                "level": "info", "title": "Onset not recorded",
                "ear": side, "detail": s["message"], "action": s["action"],
            })
    if asym["flag"]:
        alerts.append({
            "level": "urgent", "title": "Asymmetric hearing loss — retrocochlear screen",
            "ear": asym["poorer_ear"],
            "detail": "; ".join(asym["reasons"]),
            "action": "Refer for ENT assessment; MRI with contrast is usually "
                      "indicated to exclude a vestibular schwannoma.",
        })
    for side in ("right", "left"):
        m = masking[side]
        if m["has_dilemma"]:
            alerts.append({
                "level": "validity",
                "title": "Masking dilemma — these thresholds cannot be masked",
                "ear": side,
                "detail": (f"At {m['dilemma_freqs']} Hz the noise needed to cover "
                           "the crossed signal exceeds the level at which it "
                           "crosses back. A bilateral conductive loss with large "
                           "air-bone gaps leaves no usable masking level."),
                "action": "Repeat with insert earphones, which raise interaural "
                          "attenuation by 10-20 dB. If it persists, report these "
                          "thresholds as unmaskable rather than as measured.",
            })
        if m["warning"]:
            alerts.append({
                "level": "validity", "title": "Masking indicated — results may be invalid",
                "ear": side, "detail": "; ".join(m["reasons"]), "action": m["message"],
            })

    sort_alerts(alerts)

    return {
        "alerts": alerts,
        "has_emergency": any(a["level"] == "emergency" for a in alerts),
        "has_urgent": any(a["level"] in ("emergency", "urgent") for a in alerts),
        "validity_warning": any(a["level"] == "validity" for a in alerts),
        "asymmetry": asym,
        "sudden": sudden,
        "masking": masking,
        "masking_review": masking_bundle,
    }
