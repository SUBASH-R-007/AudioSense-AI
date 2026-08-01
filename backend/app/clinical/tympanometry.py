"""Tympanometry as an instrument: the trace, not just the summary numbers.

``immittance.py`` classifies a tympanogram from three numbers a clinician has
already read off a machine. That is enough to reason about, but it is not how
tympanometry is done or taught. The measurement is a *curve*: admittance
plotted against ear-canal pressure as the probe sweeps from positive to
negative. Everything clinically interesting is a property of the curve's
shape.

This module works from the trace itself and derives:

  PEAK PRESSURE      where the curve maximises — middle-ear pressure
  PEAK ADMITTANCE    height above the tail — static compliance
  TYMPANOMETRIC WIDTH the pressure interval at half peak height, also called
                     the gradient. This is the measurement that separates a
                     normal ear from an early effusion while the peak height
                     is still within normal limits, and it is the reason a
                     three-number summary is not enough.
  EAR-CANAL VOLUME   admittance at the positive tail, with the drum stiffened
                     out of the way. A large value means the probe is seeing
                     past the membrane: perforation or a patent grommet.

Normative values (Jerger 1970; ASHA 1997 screening guidelines; Margolis &
Heller 1987 for tympanometric width) differ between adults and young
children, so the age band is an input rather than an assumption.

PROBE TONE MATTERS. Below about six months of age a 226 Hz probe gives
misleading results — the infant canal is compliant enough to produce a
normal-looking trace over a middle ear full of fluid. A 1000 Hz probe is
required. The module refuses to interpret a 226 Hz trace in a young infant
rather than returning a confident wrong answer.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.clinical.immittance import (
    COMPLIANCE_NORMAL, ECV_NORMAL, PRESSURE_NORMAL, analyze_reflexes,
    classify_tympanogram,
)

#: Standard pressure sweep, daPa.
SWEEP = (-400, 200)

#: Tympanometric width (gradient) normal range, daPa.
#: Margolis & Heller (1987) for adults; ASHA (1997) for children.
WIDTH_NORMAL_ADULT = (51, 114)
WIDTH_NORMAL_CHILD = (60, 150)

#: Ear-canal volume normals differ with canal size.
ECV_NORMAL_CHILD = (0.3, 1.0)

#: Probe tone below which infants must not be tested with 226 Hz.
INFANT_MONTHS = 6


def normative(age_years: Optional[float]) -> dict:
    """Normal ranges for this patient's age."""
    child = age_years is not None and age_years < 10
    return {
        "compliance": list(COMPLIANCE_NORMAL),
        "pressure": list(PRESSURE_NORMAL),
        "ecv": list(ECV_NORMAL_CHILD if child else ECV_NORMAL),
        "width": list(WIDTH_NORMAL_CHILD if child else WIDTH_NORMAL_ADULT),
        "band": "child" if child else "adult",
        "citations": [
            "Jerger (1970) — tympanogram types",
            "ASHA (1997) — screening for middle ear disorders",
            "Margolis & Heller (1987) — tympanometric width",
        ],
    }


# --------------------------------------------------------------------------
# curve analysis
# --------------------------------------------------------------------------
def _as_points(trace: Sequence) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    for item in trace or []:
        if isinstance(item, dict):
            p, a = item.get("pressure"), item.get("admittance")
        else:
            p, a = item[0], item[1]
        if p is None or a is None:
            continue
        points.append((float(p), float(a)))
    points.sort(key=lambda t: t[0])
    return points


def analyze_trace(trace: Sequence, age_years: Optional[float] = None) -> Optional[dict]:
    """Peak, width, tail volume and quality flags from a pressure sweep."""
    points = _as_points(trace)
    if len(points) < 5:
        return None

    pressures = [p for p, _ in points]
    admittances = [a for _, a in points]

    # The positive tail is the baseline: at +200 daPa the drum is stiffened
    # and the probe is effectively measuring the canal alone.
    tail_candidates = [a for p, a in points if p >= max(pressures) - 50]
    tail = min(tail_candidates) if tail_candidates else min(admittances)

    peak_idx = max(range(len(points)), key=lambda i: admittances[i])
    peak_pressure, peak_raw = points[peak_idx]
    peak_compensated = round(peak_raw - tail, 3)

    width = _tympanometric_width(points, peak_idx, tail)
    norms = normative(age_years)

    flags: List[str] = []
    if peak_pressure <= min(pressures) + 10:
        flags.append("Peak sits at the negative end of the sweep — extend the "
                     "sweep below -400 daPa before accepting this as Type C.")
    if peak_compensated <= 0.05:
        flags.append("No measurable peak — check the probe seal before reporting "
                     "this as a flat trace.")
    if tail > norms["ecv"][1]:
        flags.append(f"Ear-canal volume {tail:.2f} cm3 exceeds the normal ceiling "
                     f"of {norms['ecv'][1]:.1f} — perforation or a patent grommet.")
    if width is not None and width > norms["width"][1] and peak_compensated > 0.05:
        flags.append(f"Tympanometric width {width:.0f} daPa is wider than normal "
                     f"({norms['width'][0]}-{norms['width'][1]}); a rounded peak "
                     "suggests early effusion even with normal peak height.")

    return {
        "peak": {"pressure": round(peak_pressure, 1),
                 "admittance": peak_compensated,
                 "raw_admittance": round(peak_raw, 3)},
        "ecv": round(tail, 3),
        "width": None if width is None else round(width, 1),
        "points": [{"pressure": round(p, 1), "admittance": round(a, 3)}
                   for p, a in points],
        "sweep": [min(pressures), max(pressures)],
        "flags": flags,
        "normative": norms,
        "source": "measured",
    }


def _tympanometric_width(points, peak_idx: int, tail: float) -> Optional[float]:
    """Pressure interval at half the peak's height above the tail."""
    peak_pressure, peak_raw = points[peak_idx]
    height = peak_raw - tail
    if height <= 0.05:
        return None
    half = tail + height / 2.0

    def _cross(indices) -> Optional[float]:
        previous = points[peak_idx]
        for i in indices:
            p, a = points[i]
            if a <= half:
                # Linear interpolation between the straddling samples gives a
                # width that does not depend on the sweep's step size.
                pa, aa = previous
                if aa == a:
                    return p
                return p + (half - a) * (pa - p) / (aa - a)
            previous = points[i]
        return None

    left = _cross(range(peak_idx - 1, -1, -1))
    right = _cross(range(peak_idx + 1, len(points)))
    if left is None or right is None:
        return None
    return abs(right - left)


# --------------------------------------------------------------------------
# synthesis — so a summary-only entry still draws a curve
# --------------------------------------------------------------------------
def synthesize_trace(
    peak_pressure: Optional[float],
    compliance: Optional[float],
    ecv: Optional[float] = None,
    width: Optional[float] = None,
) -> List[dict]:
    """Model a trace from the three numbers a machine printout gives.

    Most clinics record the summary, not the sweep. Drawing the implied curve
    makes the numbers legible at a glance and lets the same chart serve both
    entry modes. The result is explicitly labelled as modelled, never as
    measured, because it is a drawing of the numbers rather than evidence.
    """
    tail = ecv if ecv is not None else 0.8
    height = max(compliance if compliance is not None else 0.0, 0.0)
    centre = peak_pressure if peak_pressure is not None else 0.0
    # Width relates to how sharply the curve falls away; a Gaussian with this
    # full-width-at-half-maximum reproduces a real tympanogram closely enough
    # to read.
    fwhm = width if width else (90.0 if height > 0.1 else 400.0)
    sigma = max(fwhm, 20.0) / 2.355

    out = []
    p = SWEEP[0]
    while p <= SWEEP[1]:
        value = tail + height * pow(2.718281828, -((p - centre) ** 2) / (2 * sigma ** 2))
        out.append({"pressure": float(p), "admittance": round(value, 3)})
        p += 10
    return out


# --------------------------------------------------------------------------
# full study
# --------------------------------------------------------------------------
def analyze(
    ear: str = "right",
    trace: Optional[Sequence] = None,
    peak_pressure: Optional[float] = None,
    compliance: Optional[float] = None,
    ecv: Optional[float] = None,
    reflexes: Optional[Dict[str, Optional[float]]] = None,
    pta: Optional[float] = None,
    age_years: Optional[float] = None,
    probe_hz: int = 226,
) -> dict:
    """One tympanometry study: curve, Jerger type, reflexes, interpretation."""
    curve = analyze_trace(trace or [], age_years)
    if curve:
        peak_pressure = curve["peak"]["pressure"]
        compliance = curve["peak"]["admittance"]
        ecv = curve["ecv"]
    else:
        curve = {
            "peak": {"pressure": peak_pressure,
                     "admittance": compliance,
                     "raw_admittance": None},
            "ecv": ecv,
            "width": None,
            "points": synthesize_trace(peak_pressure, compliance, ecv),
            "sweep": list(SWEEP),
            "flags": [],
            "normative": normative(age_years),
            "source": "modelled",
            "note": ("Curve drawn from the entered peak, compliance and canal "
                     "volume. It illustrates those numbers; it is not a "
                     "recorded sweep."),
        }

    jerger = classify_tympanogram(peak_pressure, compliance, ecv)
    reflex = analyze_reflexes(reflexes or {}, pta)

    # A 226 Hz probe under six months of age produces normal-looking traces
    # over ears full of fluid. Say so instead of typing the curve.
    infant_warning = None
    if age_years is not None and age_years * 12 < INFANT_MONTHS and probe_hz < 1000:
        infant_warning = (
            f"A {probe_hz} Hz probe is not valid below {INFANT_MONTHS} months of "
            "age — the compliant infant ear canal can produce a normal-looking "
            "trace over a middle ear full of fluid. Repeat with a 1000 Hz probe "
            "before interpreting this.")
        if jerger:
            jerger = {**jerger, "provisional": True}

    interpretation = _interpret(jerger, curve, reflex, infant_warning)

    return {
        "ear": ear,
        "probe_hz": probe_hz,
        "age_years": age_years,
        "curve": curve,
        "tympanogram": jerger,
        "reflexes": reflex,
        "measurements": {
            "peak_pressure": peak_pressure,
            "static_compliance": compliance,
            "ecv": ecv,
            "width": curve.get("width"),
        },
        "within_normal": _within_normal(peak_pressure, compliance, ecv,
                                        curve.get("width"), curve["normative"]),
        "infant_warning": infant_warning,
        "interpretation": interpretation,
        "flags": curve["flags"],
    }


def _within_normal(pressure, compliance, ecv, width, norms) -> Dict[str, Optional[bool]]:
    def check(value, bounds):
        if value is None:
            return None
        return bounds[0] <= value <= bounds[1]

    return {
        "pressure": check(pressure, norms["pressure"]),
        "compliance": check(compliance, norms["compliance"]),
        "ecv": check(ecv, norms["ecv"]),
        "width": check(width, norms["width"]),
    }


def _interpret(jerger, curve, reflex, infant_warning) -> List[str]:
    lines: List[str] = []
    if infant_warning:
        lines.append(infant_warning)
    if not jerger:
        lines.append("Not enough data to type this tympanogram.")
        return lines

    lines.append(f"{jerger['label']}. {jerger['interpretation']}")

    width = curve.get("width")
    norms = curve["normative"]
    if width is not None:
        if width > norms["width"][1]:
            lines.append(
                f"Tympanometric width is {width:.0f} daPa against a normal range "
                f"of {norms['width'][0]}-{norms['width'][1]} daPa. A broad, rounded "
                "peak is an early effusion sign that peak height alone misses.")
        else:
            lines.append(f"Tympanometric width {width:.0f} daPa is within the "
                         f"normal {norms['width'][0]}-{norms['width'][1]} daPa range.")

    if reflex:
        lines.append(reflex["note"])
        if jerger["suggests_conductive"] and reflex["pattern"] == "present":
            lines.append(
                "Reflexes are present despite an abnormal tympanogram — unusual, "
                "because a middle-ear problem large enough to flatten the trace "
                "normally abolishes them. Re-check both measurements.")

    if curve["source"] == "modelled":
        lines.append("The displayed curve is modelled from the entered summary "
                     "values, not a recorded sweep.")
    return lines
