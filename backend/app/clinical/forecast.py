"""Illustrative 5-year threshold projection from two dated tests.

Extrapolates the measured per-frequency shift rate under two scenarios —
continued exposure at the observed rate, versus effective hearing
protection where only age-related change remains — and reports when the
projection would cross clinically meaningful lines (WHO grades, the RPwD
25 dB disability floor, the 40% benchmark).

This is a linear trend projection from TWO measurements, presented with an
uncertainty band. It is a counseling and prevention-motivation aid, not a
validated prognostic model, and the returned payload says so.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from app.clinical.rules import PTA_FREQS, rpwd_disability, who_grade
from app.models.schemas import AC_FREQS, ThresholdValue, ear_to_numeric

#: Age-related (presbycusis-only) annual threshold change, dB/year,
#: simplified from ISO 7029 median trends. Applied in the "protected"
#: scenario, where occupational/noise contribution is removed.
PRESBYCUSIS_RATE = {
    250: (0.06, 0.12), 500: (0.07, 0.15), 1000: (0.09, 0.20),
    2000: (0.15, 0.35), 4000: (0.35, 0.75), 8000: (0.45, 0.95),
}  # (under 50 years, 50+ years)

MIN_INTERVAL_YEARS = 0.5


def _rate(freq: int, age: float) -> float:
    young, old = PRESBYCUSIS_RATE[freq]
    return old if age >= 50 else young


def _years_between(d1: Optional[str], d2: Optional[str]) -> Optional[float]:
    try:
        a = date.fromisoformat(str(d1))
        b = date.fromisoformat(str(d2))
    except (TypeError, ValueError):
        return None
    days = (b - a).days
    return days / 365.25 if days > 0 else None


def forecast_ear(
    baseline_ac: Dict[int, Optional[ThresholdValue]],
    current_ac: Dict[int, Optional[ThresholdValue]],
    interval_years: float,
    age: float,
    horizon_years: int = 5,
) -> Optional[dict]:
    """Project one ear forward under exposed and protected scenarios."""
    if interval_years < MIN_INTERVAL_YEARS:
        return None
    base, curr = ear_to_numeric(baseline_ac), ear_to_numeric(current_ac)

    slopes: Dict[int, float] = {}
    for f in AC_FREQS:
        if base.get(f) is not None and curr.get(f) is not None:
            slopes[f] = (curr[f] - base[f]) / interval_years
    if not slopes:
        return None

    years = list(range(0, horizon_years + 1))
    exposed: List[dict] = []
    protected: List[dict] = []

    for y in years:
        exp_point = {"year": y}
        prot_point = {"year": y}
        for f in AC_FREQS:
            if f not in slopes:
                continue
            start = curr[f]
            exp_point[str(f)] = round(min(120, start + slopes[f] * y), 1)
            prot_point[str(f)] = round(
                min(120, start + _rate(f, age + y) * y), 1
            )
        exposed.append(exp_point)
        protected.append(prot_point)

    def pta_of(point: dict) -> Optional[float]:
        vals = [point[str(f)] for f in PTA_FREQS if str(f) in point]
        return round(sum(vals) / len(vals), 1) if vals else None

    exposed_pta = [{"year": p["year"], "pta": pta_of(p)} for p in exposed]
    protected_pta = [{"year": p["year"], "pta": pta_of(p)} for p in protected]

    # Uncertainty widens with the projected distance — a heuristic band,
    # since two measurements cannot support a real confidence interval.
    band = [
        {"year": p["year"],
         "low": None if p["pta"] is None else round(max(-10, p["pta"] - (0.35 * abs(_mean_slope(slopes)) * p["year"] + 4)), 1),
         "high": None if p["pta"] is None else round(min(120, p["pta"] + (0.35 * abs(_mean_slope(slopes)) * p["year"] + 4)), 1)}
        for p in exposed_pta
    ]

    end_exposed = exposed_pta[-1]["pta"]
    end_protected = protected_pta[-1]["pta"]
    now_pta = exposed_pta[0]["pta"]

    return {
        "slopes_db_per_year": {str(f): round(s, 2) for f, s in slopes.items()},
        "mean_slope": round(_mean_slope(slopes), 2),
        "exposed": exposed,
        "protected": protected,
        "exposed_pta": exposed_pta,
        "protected_pta": protected_pta,
        "uncertainty_band": band,
        "current_grade": who_grade(now_pta)["grade"] if now_pta is not None else None,
        "exposed_grade": who_grade(end_exposed)["grade"] if end_exposed is not None else None,
        "protected_grade": who_grade(end_protected)["grade"] if end_protected is not None else None,
        "grade_change": (
            end_exposed is not None and now_pta is not None
            and who_grade(end_exposed)["grade"] != who_grade(now_pta)["grade"]
        ),
        "years_to_disability_floor": _years_until(exposed_pta, slopes, 25.0),
        "preventable_db": (
            None if end_exposed is None or end_protected is None
            else round(end_exposed - end_protected, 1)
        ),
    }


def _mean_slope(slopes: Dict[int, float]) -> float:
    return sum(slopes.values()) / len(slopes)


def _years_until(pta_series: List[dict], slopes: Dict[int, float], target: float) -> Optional[float]:
    """Years until the projected PTA crosses a threshold (None if never)."""
    start = pta_series[0]["pta"]
    if start is None:
        return None
    if start >= target:
        return 0.0
    pta_slope = sum(slopes[f] for f in PTA_FREQS if f in slopes) / max(
        1, len([f for f in PTA_FREQS if f in slopes])
    )
    if pta_slope <= 0:
        return None
    return round((target - start) / pta_slope, 1)


def forecast(
    baseline: dict,
    current: dict,
    baseline_date: Optional[str],
    current_date: Optional[str],
    age: float = 40,
    horizon_years: int = 5,
) -> dict:
    """Both ears. ``baseline``/``current``: {'right': {...}, 'left': {...}} AC dicts."""
    interval = _years_between(baseline_date, current_date)
    if interval is None:
        return {
            "available": False,
            "reason": "both tests need valid dates at least 6 months apart",
        }

    right = forecast_ear(baseline["right"], current["right"], interval, age, horizon_years)
    left = forecast_ear(baseline["left"], current["left"], interval, age, horizon_years)
    if right is None and left is None:
        return {"available": False, "reason": "insufficient paired thresholds"}

    projected = {}
    for side, f in (("right", right), ("left", left)):
        if f:
            projected[side] = f["exposed_pta"][-1]["pta"]
    disability_now = None
    disability_future = None
    if right and left:
        disability_now = rpwd_disability(
            right["exposed_pta"][0]["pta"], left["exposed_pta"][0]["pta"]
        )
        disability_future = rpwd_disability(projected["right"], projected["left"])

    return {
        "available": True,
        "interval_years": round(interval, 2),
        "horizon_years": horizon_years,
        "right": right,
        "left": left,
        "disability_now": disability_now,
        "disability_projected": disability_future,
        "method": "Linear extrapolation of the measured shift rate vs an "
                  "age-only (ISO 7029-style) scenario",
        "caveat": "Illustrative projection from two measurements — a "
                  "prevention-counseling aid, not a validated prognosis.",
    }
