"""Occupational noise dose — grounding the forecast in actual exposure.

A trend line says hearing is getting worse. A noise dose says *why*, and
by how much it would improve if the exposure changed. Two standards, both
in everyday use and deliberately different:

OSHA (29 CFR 1910.95): 90 dBA criterion for an 8-hour day, 5 dB exchange
rate. Permissible time T = 8 / 2^((L - 90) / 5) hours. Dose is the sum of
C/T across exposures. OSHA computes that sum twice, with different sound
included each time (OSHA Technical Manual, Sec. III Ch. 5, II.J.1-2):

  PEL dose      only sound at or above 90 dBA is integrated. The
                permissible exposure limit is exceeded only when this sum
                EXCEEDS 100% (Table G-16, footnote 1: "exceeds unity").
  Action dose   all sound from 80 dBA up is integrated (1910.95(d)(2)(i):
                80 to 130 dB). At 50% or more — an 8-hour TWA of 85 dBA —
                a hearing conservation programme is required (1910.95(c)(1)).

A day of 89 dBA plus one hour at 95 dBA is therefore 25% of the PEL but
112% on the action-level scale: within the limit, inside a mandatory
hearing conservation programme. A single dose cannot express both.

NIOSH (Criteria for a Recommended Standard, 1998, DHHS Pub. 98-126): 85 dBA
REL, 3 dB exchange rate — the more protective standard, because sound
energy genuinely doubles every 3 dB. Sound from 80 to 140 dBA is integrated
(Sec. 1.3.3), and exposure at or above the REL — 100% dose — is hazardous
(Sec. 1.1). NIOSH dose almost always exceeds OSHA dose for the same
exposure, which is itself worth showing a factory owner.

Hearing protector attenuation uses the NRR derating convention: an NRR
rating is reduced by 7 dB (C-weighted correction) and then halved, because
real-world fit never matches laboratory fit.
"""
from __future__ import annotations

import math
from typing import List, Optional

OSHA_CRITERION = 90.0
OSHA_EXCHANGE = 5.0
OSHA_ACTION_LEVEL = 85.0
#: Sound below this level is not integrated into the PEL dose
#: (OSHA Technical Manual Sec. III Ch. 5, II.J.2: "90-dBA threshold").
OSHA_PEL_THRESHOLD = 90.0
#: Sound below this level is not integrated into the action-level dose
#: (1910.95(d)(2)(i); OSHA Technical Manual Sec. III Ch. 5, II.J.1).
OSHA_ACTION_THRESHOLD = 80.0
#: 1910.95(c)(1): an 8-hour TWA of 85 dBA, "or, equivalently, a dose of
#: fifty percent", requires a hearing conservation programme.
OSHA_ACTION_DOSE_PCT = 50.0
NIOSH_CRITERION = 85.0
NIOSH_EXCHANGE = 3.0
#: NIOSH 1998 Sec. 1.3.3: sound levels from 80 to 140 dBA are integrated.
NIOSH_THRESHOLD = 80.0
CRITERION_HOURS = 8.0

# Levels above the upper integration bounds (130 dBA OSHA, 140 dBA NIOSH)
# are still counted: excluding them could only lower the dose of an
# exposure that is already extreme.


def permissible_hours(level_dba: float, criterion: float, exchange: float) -> float:
    """Hours of exposure allowed at a given level before reaching 100% dose."""
    return CRITERION_HOURS / (2 ** ((level_dba - criterion) / exchange))


def derate_nrr(nrr_db: Optional[float]) -> float:
    """Real-world attenuation from a laboratory NRR rating."""
    if not nrr_db or nrr_db <= 0:
        return 0.0
    return round(max(0.0, (nrr_db - 7) / 2), 1)


def _osha_twa(dose_pct: float) -> Optional[float]:
    """8-hour TWA from an OSHA dose (1910.95 Appendix A):
    TWA = 16.61 x log10(D / 100) + 90."""
    return (round(16.61 * math.log10(dose_pct / 100) + OSHA_CRITERION, 1)
            if dose_pct > 0 else None)


def _shown_pct(dose: float) -> float:
    """Dose fraction -> percent, rounded UP to 0.1%.

    Every verdict is decided on this shown figure, so the number on screen
    and the verdict beside it cannot disagree. Rounding up keeps that
    agreement on the safe side at every limit: a dose that truly exceeds
    100% (Table G-16 note 1, "exceeds unity") is never shown as 100.0% and
    called "at the limit", and a dose less than 0.1% short of a limit (50%
    action level, 100% NIOSH REL) is shown at the limit and judged as
    reaching it — an over-call of under 0.02 dB in TWA terms
    (16.61 x log10(50 / 49.9) = 0.014 dB). The 1e-6 guard
    stops floating-point residue in an exact dose (8 h at 90 dBA is exactly
    100%) from being rounded up.
    """
    if not math.isfinite(dose):
        return float(dose)
    return math.ceil(dose * 1000 - 1e-6) / 10


def compute_dose(exposures: List[dict], nrr: Optional[float] = None,
                 protection_worn: bool = False) -> dict:
    """exposures: [{"level_dba": float, "hours": float, "label": str}]."""
    attenuation = derate_nrr(nrr) if protection_worn else 0.0

    rows = []
    pel_dose = action_dose = niosh_dose = 0.0
    for e in exposures:
        level = float(e["level_dba"]) - attenuation
        hours = float(e["hours"])
        if hours <= 0:
            continue
        t_osha = permissible_hours(level, OSHA_CRITERION, OSHA_EXCHANGE)
        t_niosh = permissible_hours(level, NIOSH_CRITERION, NIOSH_EXCHANGE)
        d_osha = hours / t_osha if t_osha > 0 else float("inf")
        d_pel = d_osha if level >= OSHA_PEL_THRESHOLD else 0.0
        d_action = d_osha if level >= OSHA_ACTION_THRESHOLD else 0.0
        d_niosh = ((hours / t_niosh if t_niosh > 0 else float("inf"))
                   if level >= NIOSH_THRESHOLD else 0.0)
        pel_dose += d_pel
        action_dose += d_action
        niosh_dose += d_niosh
        rows.append({
            "label": e.get("label", "exposure"),
            "level_dba": round(level, 1),
            "hours": hours,
            "permissible_hours_osha": round(t_osha, 2),
            "dose_pct": _shown_pct(d_action),
            "pel_dose_pct": _shown_pct(d_pel),
            "niosh_dose_pct": _shown_pct(d_niosh),
        })

    if not rows:
        return {"available": False, "reason": "no exposures entered"}

    # Every verdict below is decided on the figure the payload shows
    # (_shown_pct), so the displayed dose and its verdict always agree.
    pel_pct = _shown_pct(pel_dose)
    action_pct = _shown_pct(action_dose)
    niosh_pct = _shown_pct(niosh_dose)
    twa = _osha_twa(action_dose * 100)
    pel_twa = _osha_twa(pel_dose * 100)

    if pel_pct > 100:
        risk, verdict = "high", (
            f"Exposure exceeds the OSHA permissible exposure limit: the PEL dose, "
            f"which counts only sound at or above {OSHA_PEL_THRESHOLD:g} dBA, is "
            f"{pel_pct:g}% (over 100%). Feasible engineering or administrative "
            "controls are required, with hearing protection until they bring "
            "exposure within the limit (29 CFR 1910.95(b)(1)).")
    elif action_pct >= OSHA_ACTION_DOSE_PCT:
        pel_clause = (
            f"The PEL dose is {pel_pct:g}% — at the permissible limit, not over it; "
            "any further exposure would exceed it."
            if pel_pct >= 100 else
            f"The permissible limit is not exceeded (PEL dose {pel_pct:g}%, "
            f"counting only sound at or above {OSHA_PEL_THRESHOLD:g} dBA).")
        risk, verdict = "action", (
            f"Exposure is at or above the OSHA action level: counting all sound "
            f"from {OSHA_ACTION_THRESHOLD:g} dBA, the dose is {action_pct:g}% "
            f"(8-h TWA {twa:g} dBA; the action level is 50% / 85 dBA) — a hearing "
            "conservation programme with annual audiometry is required "
            f"(29 CFR 1910.95(c)). {pel_clause}")
    elif niosh_pct >= 100:
        risk, verdict = "niosh", ("Within the OSHA limits but at or above the NIOSH "
                                  "recommended exposure limit — damage risk remains "
                                  "real; OSHA's 5 dB exchange rate under-counts it.")
    else:
        risk, verdict = "low", "Exposure is below both recommended limits."

    return {
        "available": True,
        "exposures": rows,
        # ``osha_dose_pct`` / ``twa_dba`` are the action-level figures (all
        # sound from 80 dBA); the PEL is judged on ``osha_pel_dose_pct``.
        "osha_dose_pct": action_pct,
        "osha_action_dose_pct": action_pct,
        "osha_pel_dose_pct": pel_pct,
        "niosh_dose_pct": niosh_pct,
        "twa_dba": twa,
        "pel_twa_dba": pel_twa,
        "protection_attenuation_db": attenuation,
        "risk": risk,
        "verdict": verdict,
        "standards": {
            "osha": "29 CFR 1910.95 — 90 dBA criterion, 5 dB exchange",
            "osha_pel": ("PEL dose: sound ≥ 90 dBA integrated; exceeded above 100% "
                         "(Table G-16 note 1)"),
            "osha_action": ("Action-level dose: sound 80–130 dBA integrated "
                            "(1910.95(d)(2)(i)); hearing conservation from 50% "
                            "(1910.95(c)(1))"),
            "niosh": ("NIOSH 1998 — 85 dBA criterion, 3 dB exchange, sound "
                      "80–140 dBA integrated"),
        },
        "protection_note": (
            f"Hearing protectors derated to {attenuation:g} dB of real-world "
            "attenuation ((NRR − 7) / 2)."
            if attenuation else
            "No hearing protection applied to this calculation."
        ),
    }
