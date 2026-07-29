"""Occupational noise dose — grounding the forecast in actual exposure.

A trend line says hearing is getting worse. A noise dose says *why*, and
by how much it would improve if the exposure changed. Two standards, both
in everyday use and deliberately different:

OSHA (29 CFR 1910.95): 90 dBA criterion for an 8-hour day, 5 dB exchange
rate. Permissible time T = 8 / 2^((L - 90) / 5) hours. Dose is the sum of
C/T across exposures; 100% dose = the permissible limit, and a hearing
conservation programme is required from 50% (an 85 dBA action level).

NIOSH (1998 criteria): 85 dBA criterion, 3 dB exchange rate — the more
protective standard, because sound energy genuinely doubles every 3 dB.
NIOSH dose almost always exceeds OSHA dose for the same exposure, which is
itself worth showing a factory owner.

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
NIOSH_CRITERION = 85.0
NIOSH_EXCHANGE = 3.0
CRITERION_HOURS = 8.0


def permissible_hours(level_dba: float, criterion: float, exchange: float) -> float:
    """Hours of exposure allowed at a given level before reaching 100% dose."""
    return CRITERION_HOURS / (2 ** ((level_dba - criterion) / exchange))


def derate_nrr(nrr_db: Optional[float]) -> float:
    """Real-world attenuation from a laboratory NRR rating."""
    if not nrr_db or nrr_db <= 0:
        return 0.0
    return round(max(0.0, (nrr_db - 7) / 2), 1)


def compute_dose(exposures: List[dict], nrr: Optional[float] = None,
                 protection_worn: bool = False) -> dict:
    """exposures: [{"level_dba": float, "hours": float, "label": str}]."""
    attenuation = derate_nrr(nrr) if protection_worn else 0.0

    rows, osha_dose, niosh_dose = [], 0.0, 0.0
    for e in exposures:
        level = float(e["level_dba"]) - attenuation
        hours = float(e["hours"])
        if hours <= 0:
            continue
        t_osha = permissible_hours(level, OSHA_CRITERION, OSHA_EXCHANGE)
        t_niosh = permissible_hours(level, NIOSH_CRITERION, NIOSH_EXCHANGE)
        d_osha = hours / t_osha if t_osha > 0 else float("inf")
        d_niosh = hours / t_niosh if t_niosh > 0 else float("inf")
        osha_dose += d_osha
        niosh_dose += d_niosh
        rows.append({
            "label": e.get("label", "exposure"),
            "level_dba": round(level, 1),
            "hours": hours,
            "permissible_hours_osha": round(t_osha, 2),
            "dose_pct": round(d_osha * 100, 1),
            "niosh_dose_pct": round(d_niosh * 100, 1),
        })

    if not rows:
        return {"available": False, "reason": "no exposures entered"}

    osha_pct = round(osha_dose * 100, 1)
    niosh_pct = round(niosh_dose * 100, 1)
    # Equivalent 8-hour time-weighted average, back-calculated from dose
    # (OSHA Appendix A): TWA = 16.61 x log10(D / 100) + 90.
    twa = round(16.61 * math.log10(osha_pct / 100) + OSHA_CRITERION, 1) \
        if osha_pct > 0 else None

    if osha_pct >= 100:
        risk, verdict = "high", ("Exposure exceeds the OSHA permissible limit — "
                                 "engineering controls and hearing protection are "
                                 "mandatory, not optional.")
    elif osha_pct >= 50:
        risk, verdict = "action", ("Exposure is at or above the OSHA action level "
                                   "(50% dose / 85 dBA TWA) — a hearing conservation "
                                   "programme with annual audiometry is required.")
    elif niosh_pct >= 100:
        risk, verdict = "niosh", ("Within the OSHA limit but above the NIOSH "
                                  "recommended limit — damage risk remains real; "
                                  "OSHA's 5 dB exchange rate under-counts it.")
    else:
        risk, verdict = "low", "Exposure is below both recommended limits."

    return {
        "available": True,
        "exposures": rows,
        "osha_dose_pct": osha_pct,
        "niosh_dose_pct": niosh_pct,
        "twa_dba": twa,
        "protection_attenuation_db": attenuation,
        "risk": risk,
        "verdict": verdict,
        "standards": {
            "osha": "29 CFR 1910.95 — 90 dBA criterion, 5 dB exchange",
            "niosh": "NIOSH 1998 — 85 dBA criterion, 3 dB exchange",
        },
        "protection_note": (
            f"Hearing protectors derated to {attenuation:g} dB of real-world "
            "attenuation ((NRR − 7) / 2)."
            if attenuation else
            "No hearing protection applied to this calculation."
        ),
    }
