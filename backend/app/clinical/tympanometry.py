"""Tympanometry as an instrument: the trace, the type, and what it implies.

The classification here follows the immittance reference supplied by the
clinical team (source: Gelfand, *Essentials of Audiology*, 4th ed., pp.
187-192), which is more complete than the five-type Jerger scheme in two ways
that change answers:

**Eight types, not five.** Alongside A / As / Ad / B / C it separates

    Add   an extremely deep peak that runs off the instrument scale —
          ossicular discontinuity, where Ad is merely "deep"
    D     a narrow notched peak — hypermobile or scarred membrane
    E     a wide notched peak — ossicular disruption

A notched tympanogram classified as plain Ad loses the distinction between a
scarred drum and a disconnected ossicular chain, which are not the same
referral.

**Type B splits three ways on ear-canal volume, not two.** Normal volume is
fluid behind an intact drum; large volume is a perforation or a patent
grommet; and *small* volume is cerumen occluding the canal or a probe blocked
against the canal wall — an instrument artefact that is otherwise read as
middle-ear disease.

Measured quantities, as the reference lists them:

    ECV   ear-canal volume         children 0.3-1.0 ml,  adults 0.6-2.0 ml
    TPP   tympanometric peak pressure        +50 to -100 daPa
    SA    static acoustic admittance   children 0.35-1.25, adults 0.37-1.66 mmho
    TG    tympanic gradient                  > 0.2

Both shape measures are reported. The gradient is a dimensionless ratio; the
tympanometric width is the same idea expressed in daPa (Margolis & Heller
1987; ASHA 1997). They agree on real traces, and reporting both means the
result is readable against either convention.

PROBE TONE STILL MATTERS. Below six months a 226 Hz probe can produce a
normal-looking trace over a middle ear full of fluid, so the module refuses to
type it rather than returning a confident wrong answer.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

#: Standard pressure sweep, daPa.
SWEEP = (-400, 200)

#: Normal tympanometric peak pressure, daPa — same for children and adults.
PRESSURE_NORMAL = (-100, 50)

#: Static acoustic admittance (compliance), mmho.
COMPLIANCE_NORMAL_ADULT = (0.37, 1.66)
COMPLIANCE_NORMAL_CHILD = (0.35, 1.25)

#: Equivalent ear-canal volume, ml.
ECV_NORMAL_ADULT = (0.6, 2.0)
ECV_NORMAL_CHILD = (0.3, 1.0)

#: Tympanic gradient below this is an abnormally rounded peak.
GRADIENT_NORMAL_MIN = 0.2

#: Tympanometric width normal range, daPa (the daPa expression of the same
#: shape property as the gradient).
WIDTH_NORMAL_ADULT = (51, 114)
WIDTH_NORMAL_CHILD = (60, 150)

#: A peak below this is not measurable — the trace is flat (Type B).
#:
#: The reference gives Type B as "absent / ~0-0.2 mmho" and Type As as "< 0.37"
#: (adult), so the two bands touch at 0.2 and the table alone cannot settle a
#: value sitting on it. The distinguishing feature clinically is whether a peak
#: can be identified at all, so the comparison is strict: exactly 0.2 mmho has
#: a peak, however shallow, and types as As. Values inside AMBIGUOUS_BAND are
#: flagged rather than silently resolved.
FLAT_ADMITTANCE_MAX = 0.2
AMBIGUOUS_BAND = (0.15, 0.25)

#: Compensated admittance beyond which the peak runs off the scale of a
#: clinical instrument, which is what separates Type Add from Type Ad.
OFF_SCALE_ADMITTANCE = 3.0

#: Raw admittance the instrument can actually plot. Above this the pen leaves
#: the paper: a Type Add trace ascends on both sides and never comes back down
#: within the recordable range, so it has NO apex. Points beyond the ceiling
#: are recorded as None rather than as a number, because the instrument did
#: not measure them — drawing a closed peak there would invent an apex the
#: machine never saw.
INSTRUMENT_CEILING_MMHO = 4.0

#: Age below which children's normative bands apply.
CHILD_MAX_AGE_YEARS = 10
#: Probe tone below which infants must not be tested with 226 Hz.
INFANT_MONTHS = 6

#: A notch is only a notch if the dip between two maxima is this deep,
#: as a fraction of the peak height. Shallower ripples are measurement noise.
NOTCH_DEPTH_FRACTION = 0.12
#: Separation between the outer maxima that divides a narrow notch (Type D)
#: from a wide one (Type E), daPa.
NOTCH_WIDE_DAPA = 75.0

#: The reference table, verbatim in substance, with each type's disorders.
TYMPANOGRAM_TYPES: Dict[str, dict] = {
    "A": {
        "label": "Type A — normal peak",
        "shape": "Normal peak",
        "disorders": ["Normal middle-ear function"],
        "suggests_conductive": False,
    },
    "As": {
        "label": "Type As — shallow peak",
        "shape": "Shallow peak",
        "disorders": ["Otosclerosis", "Tympanosclerosis", "Stiff tympanic membrane"],
        "suggests_conductive": True,
    },
    "Ad": {
        "label": "Type Ad — deep peak",
        "shape": "Deep peak",
        "disorders": ["Flaccid tympanic membrane", "Ossicular discontinuity"],
        "suggests_conductive": True,
    },
    "Add": {
        "label": "Type Add — extremely deep peak (off-scale)",
        "shape": "Extremely deep peak, off the instrument scale",
        "disorders": ["Ossicular discontinuity"],
        "suggests_conductive": True,
    },
    "B": {
        "label": "Type B — flat, no measurable peak",
        "shape": "Flat tympanogram",
        "disorders": ["Otitis media with effusion", "Cholesteatoma",
                      "Impacted cerumen", "Tympanic membrane perforation"],
        "suggests_conductive": True,
    },
    "C": {
        "label": "Type C — negative middle-ear pressure",
        "shape": "Peak at markedly negative pressure",
        "disorders": ["Eustachian tube dysfunction"],
        "suggests_conductive": False,
    },
    "D": {
        "label": "Type D — narrow notched peak",
        "shape": "Narrow notched peak",
        "disorders": ["Hypermobile tympanic membrane", "Scarred tympanic membrane"],
        "suggests_conductive": False,
    },
    "E": {
        "label": "Type E — wide notched peak",
        "shape": "Wide notched peak",
        "disorders": ["Ossicular disruption"],
        "suggests_conductive": True,
    },
}

#: Type B means three different things depending on the canal volume, and the
#: small-volume case is an instrument artefact rather than middle-ear disease.
TYPE_B_BY_VOLUME = {
    "small": {
        "interpretation": ("Small ear-canal volume: cerumen occluding the canal, "
                           "or the probe blocked against the canal wall. This is "
                           "an artefact — clear the canal and repeat before "
                           "reporting middle-ear disease."),
        "disorders": ["Impacted cerumen", "Blocked probe"],
    },
    "normal": {
        "interpretation": ("Normal ear-canal volume: middle-ear effusion behind "
                           "an intact drum is the usual cause."),
        "disorders": ["Otitis media with effusion", "Cholesteatoma"],
    },
    "large": {
        "interpretation": ("Large ear-canal volume: the probe is measuring past "
                           "the drum — tympanic membrane perforation or a patent "
                           "ventilation tube."),
        "disorders": ["Tympanic membrane perforation", "Patent ventilation tube"],
    },
}

CITATIONS = [
    "Gelfand, S. A. Essentials of Audiology (4th ed.), pp. 187-192",
    "Jerger (1970) — tympanogram typing",
    "Margolis & Heller (1987); ASHA (1997) — tympanometric width",
]


def normative(age_years: Optional[float]) -> dict:
    """Normal ranges for this patient's age band."""
    child = age_years is not None and age_years < CHILD_MAX_AGE_YEARS
    return {
        "compliance": list(COMPLIANCE_NORMAL_CHILD if child else COMPLIANCE_NORMAL_ADULT),
        "pressure": list(PRESSURE_NORMAL),
        "ecv": list(ECV_NORMAL_CHILD if child else ECV_NORMAL_ADULT),
        "width": list(WIDTH_NORMAL_CHILD if child else WIDTH_NORMAL_ADULT),
        "gradient_min": GRADIENT_NORMAL_MIN,
        "band": "child" if child else "adult",
        "citations": list(CITATIONS),
    }


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------
def volume_band(ecv: Optional[float], norms: dict) -> str:
    if ecv is None:
        return "normal"
    lo, hi = norms["ecv"]
    if ecv < lo:
        return "small"
    if ecv > hi:
        return "large"
    return "normal"


def classify(
    peak_pressure: Optional[float],
    compliance: Optional[float],
    ecv: Optional[float] = None,
    gradient: Optional[float] = None,
    notch: Optional[dict] = None,
    age_years: Optional[float] = None,
    off_scale: bool = False,
) -> Optional[dict]:
    """Assign one of the eight types from the measured quantities.

    Order matters. A flat trace has no peak to describe, so it is settled
    first. An off-scale trace has no apex at all, so it comes next — there is
    no shape left to call notched. Only then does a notch outrank depth,
    because Type D and Type E are notched by definition while Ad is not.
    """
    norms = normative(age_years)
    lo, hi = norms["compliance"]
    band = volume_band(ecv, norms)

    def build(type_key: str, interpretation: str, extra: Optional[dict] = None) -> dict:
        entry = TYMPANOGRAM_TYPES[type_key]
        return {
            "type": type_key,
            "label": entry["label"],
            "shape": entry["shape"],
            "interpretation": interpretation,
            "disorders": list(entry["disorders"]),
            "suggests_conductive": entry["suggests_conductive"],
            "ecv_flag": band,
            "normative": norms,
            **(extra or {}),
        }

    # 1. Off the scale, before anything else. Such a trace has neither a peak
    #    pressure nor a peak admittance to reason about, so every test below
    #    would be asking about a measurement that does not exist.
    if off_scale:
        return build("Add", "The trace runs off the instrument scale — the "
                            "limbs ascend without meeting, so there is no "
                            "measurable peak. This is ossicular discontinuity.",
                     {"off_scale": True})

    if peak_pressure is None and compliance is None:
        return None

    # 2. Flat: no measurable peak. The canal volume decides what it means.
    ambiguous = (compliance is not None
                 and AMBIGUOUS_BAND[0] <= compliance <= AMBIGUOUS_BAND[1])
    flat = compliance is not None and compliance < FLAT_ADMITTANCE_MAX
    if flat or peak_pressure is None:
        split = TYPE_B_BY_VOLUME[band]
        extra = {"disorders": list(split["disorders"])}
        if ambiguous:
            extra["borderline"] = (
                f"Static admittance {compliance:.2f} mmho sits where the flat and "
                "shallow-peak bands meet. Repeat the sweep before committing to "
                "Type B over Type As.")
        return build("B", split["interpretation"], extra)

    # 3. Notched peaks are Type D or E regardless of depth.
    if notch and notch.get("notched"):
        wide = notch.get("width", 0.0) > NOTCH_WIDE_DAPA or (
            compliance is not None and compliance > hi)
        if wide:
            return build("E", "A wide notched peak indicates ossicular disruption.",
                         {"notch": notch})
        return build("D", "A narrow notched peak indicates a hypermobile or "
                          "scarred tympanic membrane.", {"notch": notch})

    # 4. A complete curve whose peak still exceeds the off-scale threshold.
    if compliance is not None and compliance >= OFF_SCALE_ADMITTANCE:
        return build("Add", "Admittance beyond the instrument scale — ossicular "
                            "discontinuity.")

    # 5. Pressure before depth: a peak at -250 daPa is Type C whatever its height.
    if peak_pressure < PRESSURE_NORMAL[0]:
        return build("C", "Negative middle-ear pressure: the Eustachian tube is "
                          "not ventilating. This precedes an effusion and, if a "
                          "retraction pocket forms, cholesteatoma.")

    # 6. Depth against the age-appropriate band.
    if compliance is not None and compliance > hi:
        return build("Ad", "A deep peak indicates a flaccid membrane or an "
                           "ossicular discontinuity.")
    if compliance is not None and compliance < lo:
        extra = {}
        if ambiguous:
            extra["borderline"] = (
                f"Static admittance {compliance:.2f} mmho sits where the shallow-peak "
                "and flat bands meet. Repeat the sweep before committing to "
                "Type As over Type B.")
        return build("As", "A shallow peak indicates reduced middle-ear mobility: "
                           "otosclerosis, tympanosclerosis or a stiffened drum.",
                     extra)

    interpretation = "Normal middle-ear pressure and mobility."
    if gradient is not None and gradient < GRADIENT_NORMAL_MIN:
        interpretation += (f" Gradient {gradient:.2f} is below {GRADIENT_NORMAL_MIN}, "
                           "so the peak is abnormally rounded — an early effusion "
                           "sign that peak height alone misses.")
    return build("A", interpretation)


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


def _interp(points, pressure: float) -> Optional[float]:
    """Admittance at an arbitrary pressure, linearly interpolated."""
    if not points or pressure < points[0][0] or pressure > points[-1][0]:
        return None
    for (p0, a0), (p1, a1) in zip(points, points[1:]):
        if p0 <= pressure <= p1:
            if p1 == p0:
                return a0
            return a0 + (a1 - a0) * (pressure - p0) / (p1 - p0)
    return None


def _tympanic_gradient(points, peak_pressure: float, height: float,
                       tail: float) -> Optional[float]:
    """Dimensionless gradient: how sharply the peak falls away.

        GR = (Ytm - Y+-50) / Ytm

    where Ytm is the compensated peak admittance and Y+-50 the mean compensated
    admittance 50 daPa either side of it. A sharp peak drops away quickly and
    scores high; a broad, rounded peak scores low. Normal is > 0.2, so the
    direction matches the reference table.
    """
    if height <= 0.05:
        return None
    left = _interp(points, peak_pressure - 50)
    right = _interp(points, peak_pressure + 50)
    shoulders = [v - tail for v in (left, right) if v is not None]
    if not shoulders:
        return None
    mean_shoulder = sum(shoulders) / len(shoulders)
    return max(0.0, min(1.0, (height - mean_shoulder) / height))


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
                pa, aa = previous
                if aa == a:
                    return p
                # Interpolate between the straddling samples so the width does
                # not depend on the sweep's step size.
                return p + (half - a) * (pa - p) / (aa - a)
            previous = points[i]
        return None

    left = _cross(range(peak_idx - 1, -1, -1))
    right = _cross(range(peak_idx + 1, len(points)))
    if left is None or right is None:
        return None
    return abs(right - left)


def _detect_notch(points, tail: float, height: float) -> dict:
    """Find a notched (W-shaped) peak — the defining feature of Types D and E.

    A notch is two maxima separated by a dip. The dip has to be deep enough to
    be real: a fraction of the peak height, not a ripple in the sampling.
    """
    if height <= 0.05 or len(points) < 5:
        return {"notched": False}

    maxima = []
    for i in range(1, len(points) - 1):
        prev_a, a, next_a = points[i - 1][1], points[i][1], points[i + 1][1]
        if a >= prev_a and a >= next_a and (a - tail) >= 0.5 * height:
            maxima.append(i)

    # Collapse plateaux: adjacent indices are one maximum, not several.
    grouped: List[int] = []
    for i in maxima:
        if grouped and i - grouped[-1] <= 1:
            continue
        grouped.append(i)
    if len(grouped) < 2:
        return {"notched": False}

    first, last = grouped[0], grouped[-1]
    trough = min(points[i][1] for i in range(first, last + 1))
    dip = min(points[first][1], points[last][1]) - trough
    if dip < NOTCH_DEPTH_FRACTION * height:
        return {"notched": False}

    return {
        "notched": True,
        "peaks": [round(points[i][0], 1) for i in grouped],
        "width": round(abs(points[last][0] - points[first][0]), 1),
        "depth": round(dip, 3),
    }


def _detect_off_scale(trace: Sequence, points: List[Tuple[float, float]]) -> bool:
    """Did the trace leave the instrument's range near its peak?

    Two ways this shows up. Either the recording explicitly marks points as
    off-scale (or leaves them empty), or the measured values themselves reach
    the ceiling. In both cases the limbs ascend and never meet, so there is no
    apex — which is the whole distinction between Type Add and Type Ad.
    """
    for item in trace or []:
        if not isinstance(item, dict):
            continue
        if item.get("off_scale"):
            return True
        # An admittance recorded as empty between two measured points is a
        # gap in the trace, not a missing row at the end of it.
        if item.get("admittance") is None and item.get("pressure") is not None:
            pressures = [p for p, _ in points]
            if pressures and min(pressures) < item["pressure"] < max(pressures):
                return True
    return bool(points) and max(a for _, a in points) >= INSTRUMENT_CEILING_MMHO


def analyze_trace(trace: Sequence, age_years: Optional[float] = None) -> Optional[dict]:
    """Peak, gradient, width, notch and tail volume from a pressure sweep."""
    points = _as_points(trace)
    if len(points) < 5:
        return None
    off_scale = _detect_off_scale(trace, points)

    pressures = [p for p, _ in points]
    admittances = [a for _, a in points]

    # The positive tail is the baseline: at +200 daPa the drum is stiffened and
    # the probe is effectively measuring the canal alone.
    tail_candidates = [a for p, a in points if p >= max(pressures) - 50]
    tail = min(tail_candidates) if tail_candidates else min(admittances)

    peak_idx = max(range(len(points)), key=lambda i: admittances[i])
    peak_pressure, peak_raw = points[peak_idx]
    peak_compensated = round(peak_raw - tail, 3)

    width = _tympanometric_width(points, peak_idx, tail)
    gradient = _tympanic_gradient(points, peak_pressure, peak_raw - tail, tail)
    notch = _detect_notch(points, tail, peak_raw - tail)
    norms = normative(age_years)

    flags: List[str] = []
    if not off_scale and peak_pressure <= min(pressures) + 10:
        flags.append("Peak sits at the negative end of the sweep — extend the "
                     "sweep below -400 daPa before accepting this as Type C.")
    if peak_compensated <= FLAT_ADMITTANCE_MAX:
        flags.append("No measurable peak — check the probe seal before reporting "
                     "this as a flat trace.")
    if tail > norms["ecv"][1]:
        flags.append(f"Ear-canal volume {tail:.2f} ml exceeds the normal ceiling "
                     f"of {norms['ecv'][1]:.1f} — perforation or a patent grommet.")
    if tail < norms["ecv"][0]:
        flags.append(f"Ear-canal volume {tail:.2f} ml is below the normal floor of "
                     f"{norms['ecv'][0]:.1f} — suspect cerumen or a probe blocked "
                     "against the canal wall, not middle-ear disease.")
    if off_scale:
        # With no apex, every peak-derived measure describes nothing. The
        # highest recorded value would understate the admittance and make an
        # off-scale trace look merely deep; a width measured across the gap is
        # not a width; and the pressure of a peak that was never reached is not
        # a peak pressure.
        flags.append(
            f"The trace exceeds the instrument ceiling of "
            f"{INSTRUMENT_CEILING_MMHO:g} mmho and has no recordable peak. "
            "Peak pressure, peak admittance, gradient and width cannot be "
            "measured from it.")
        gradient = width = None
        notch = {"notched": False}
    else:
        if width is not None and width > norms["width"][1] \
                and peak_compensated > FLAT_ADMITTANCE_MAX:
            flags.append(f"Tympanometric width {width:.0f} daPa is wider than normal "
                         f"({norms['width'][0]}-{norms['width'][1]}); a rounded peak "
                         "suggests early effusion even with normal peak height.")
        if gradient is not None and gradient < GRADIENT_NORMAL_MIN \
                and peak_compensated > FLAT_ADMITTANCE_MAX:
            flags.append(f"Tympanic gradient {gradient:.2f} is below the normal "
                         f"minimum of {GRADIENT_NORMAL_MIN:g}.")

    return {
        "peak": {"pressure": None if off_scale else round(peak_pressure, 1),
                 "admittance": None if off_scale else peak_compensated,
                 "raw_admittance": None if off_scale else round(peak_raw, 3),
                 "reached_ceiling": off_scale},
        "ecv": round(tail, 3),
        "width": None if width is None else round(width, 1),
        "gradient": None if gradient is None else round(gradient, 3),
        "notch": notch,
        "off_scale": off_scale,
        "ceiling": INSTRUMENT_CEILING_MMHO,
        "points": _echo_points(trace, points),
        "sweep": [min(pressures), max(pressures)],
        "flags": flags,
        "normative": norms,
        "source": "measured",
    }


def _echo_points(trace: Sequence, points: List[Tuple[float, float]]) -> List[dict]:
    """Return the trace as given, preserving off-scale gaps.

    The gaps are the finding. Dropping them would let a chart join the two
    ascending limbs into an apex that was never recorded.
    """
    if trace and isinstance(trace[0], dict):
        return [{"pressure": round(float(item["pressure"]), 1),
                 "admittance": (None if item.get("admittance") is None
                                else round(float(item["admittance"]), 3)),
                 **({"off_scale": True} if item.get("off_scale")
                    or item.get("admittance") is None else {})}
                for item in trace if item.get("pressure") is not None]
    return [{"pressure": round(p, 1), "admittance": round(a, 3)} for p, a in points]


# --------------------------------------------------------------------------
# synthesis — so a summary-only entry still draws a curve
# --------------------------------------------------------------------------
def synthesize_trace(
    peak_pressure: Optional[float],
    compliance: Optional[float],
    ecv: Optional[float] = None,
    width: Optional[float] = None,
    notched: bool = False,
    notch_width: float = 60.0,
    ceiling: Optional[float] = None,
) -> List[dict]:
    """Model a trace from the numbers a machine printout gives.

    Most clinics record the summary, not the sweep. Drawing the implied curve
    makes the numbers legible at a glance and lets one chart serve both entry
    modes. The result is labelled as modelled, never as measured, because it is
    a drawing of the numbers rather than evidence.
    """
    tail = ecv if ecv is not None else 0.8
    height = max(compliance if compliance is not None else 0.0, 0.0)
    centre = peak_pressure if peak_pressure is not None else 0.0
    fwhm = width if width else (90.0 if height > FLAT_ADMITTANCE_MAX else 400.0)
    sigma = max(fwhm, 20.0) / 2.355

    def bump(p: float, mu: float, s: float) -> float:
        return pow(2.718281828, -((p - mu) ** 2) / (2 * s ** 2))

    out = []
    p = SWEEP[0]
    while p <= SWEEP[1]:
        if notched:
            # Two shoulders either side of the centre produce the W shape that
            # defines Types D and E.
            half = notch_width / 2.0
            narrow = max(sigma * 0.55, 12.0)
            value = tail + height * max(bump(p, centre - half, narrow),
                                        bump(p, centre + half, narrow))
        else:
            value = tail + height * bump(p, centre, sigma)

        if ceiling is not None and value > ceiling:
            # Past the instrument's range there is no reading, so there is no
            # number. Recording None keeps the two limbs from being joined
            # across an apex the machine never measured.
            out.append({"pressure": float(p), "admittance": None,
                        "off_scale": True})
        else:
            out.append({"pressure": float(p), "admittance": round(value, 3)})
        p += 10
    return out


def reference_curves(age_years: Optional[float] = None) -> List[dict]:
    """One canonical curve per type, drawn from the reference criteria.

    The source document illustrates each type with a screenshot; those come
    from several places and disagree on axes, scales and even units. Deriving
    the shapes from the numeric table instead gives one consistent set on one
    pair of axes, and every curve can be traced back to the row that produced
    it.
    """
    norms = normative(age_years)
    lo, hi = norms["compliance"]
    ecv_lo, ecv_hi = norms["ecv"]
    mid_ecv = round((ecv_lo + ecv_hi) / 2, 2)

    specs = [
        ("A", dict(peak_pressure=-10, compliance=round((lo + hi) / 2, 2),
                   ecv=mid_ecv, width=90)),
        ("As", dict(peak_pressure=-10, compliance=round(lo * 0.6, 2),
                    ecv=mid_ecv, width=90)),
        ("Ad", dict(peak_pressure=-10, compliance=round(hi * 1.45, 2),
                    ecv=mid_ecv, width=90)),
        # Deliberately far above the ceiling: the limbs must ascend and leave
        # the plot rather than closing into an apex. Type Ad below the ceiling
        # is what a *closed* deep peak looks like; that contrast is the point.
        ("Add", dict(peak_pressure=-10, compliance=round(INSTRUMENT_CEILING_MMHO * 1.8, 2),
                     ecv=mid_ecv, width=95, ceiling=INSTRUMENT_CEILING_MMHO)),
        ("B", dict(peak_pressure=0, compliance=0.05, ecv=mid_ecv, width=400)),
        ("C", dict(peak_pressure=-220, compliance=round((lo + hi) / 2, 2),
                   ecv=mid_ecv, width=95)),
        ("D", dict(peak_pressure=-10, compliance=round((lo + hi) / 2, 2),
                   ecv=mid_ecv, width=70, notched=True, notch_width=45)),
        ("E", dict(peak_pressure=-10, compliance=round(hi * 1.3, 2),
                   ecv=mid_ecv, width=120, notched=True, notch_width=110)),
    ]

    out = []
    for type_key, spec in specs:
        points = synthesize_trace(**spec)
        entry = TYMPANOGRAM_TYPES[type_key]
        off_scale = any(p.get("off_scale") for p in points)
        out.append({
            "type": type_key,
            "label": entry["label"],
            "shape": entry["shape"],
            "disorders": entry["disorders"],
            "suggests_conductive": entry["suggests_conductive"],
            "peak_pressure": spec["peak_pressure"],
            "compliance": None if off_scale else spec["compliance"],
            "ecv": spec["ecv"],
            "off_scale": off_scale,
            "ceiling": INSTRUMENT_CEILING_MMHO,
            "points": points,
            "volume_variants": (
                [{"band": b, **v} for b, v in TYPE_B_BY_VOLUME.items()]
                if type_key == "B" else []
            ),
        })
    return {"age_band": norms["band"], "normative": norms, "curves": out,
            "sweep": list(SWEEP), "citations": list(CITATIONS)}


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
    """One tympanometry study: curve, type, gradient, reflexes, interpretation."""
    # Imported here rather than at module scope: immittance.py takes its
    # classifier from this module, so a top-level import would close a cycle.
    from app.clinical.immittance import analyze_reflexes

    curve = analyze_trace(trace or [], age_years)
    gradient = notch = None
    off_scale = False
    if curve:
        peak_pressure = curve["peak"]["pressure"]
        compliance = curve["peak"]["admittance"]
        ecv = curve["ecv"]
        gradient = curve["gradient"]
        notch = curve["notch"]
        off_scale = curve["off_scale"]
    else:
        curve = {
            "peak": {"pressure": peak_pressure,
                     "admittance": compliance,
                     "raw_admittance": None},
            "ecv": ecv,
            "width": None,
            "gradient": None,
            "notch": {"notched": False},
            "off_scale": False,
            "ceiling": INSTRUMENT_CEILING_MMHO,
            "points": synthesize_trace(peak_pressure, compliance, ecv),
            "sweep": list(SWEEP),
            "flags": [],
            "normative": normative(age_years),
            "source": "modelled",
            "note": ("Curve drawn from the entered peak, compliance and canal "
                     "volume. It illustrates those numbers; it is not a "
                     "recorded sweep."),
        }

    typed = classify(peak_pressure, compliance, ecv, gradient, notch, age_years,
                     off_scale=off_scale)
    reflex = analyze_reflexes(reflexes or {}, pta)

    infant_warning = None
    if age_years is not None and age_years * 12 < INFANT_MONTHS and probe_hz < 1000:
        infant_warning = (
            f"A {probe_hz} Hz probe is not valid below {INFANT_MONTHS} months of "
            "age — the compliant infant ear canal can produce a normal-looking "
            "trace over a middle ear full of fluid. Repeat with a 1000 Hz probe "
            "before interpreting this.")
        if typed:
            typed = {**typed, "provisional": True}

    return {
        "ear": ear,
        "probe_hz": probe_hz,
        "age_years": age_years,
        "curve": curve,
        "tympanogram": typed,
        "reflexes": reflex,
        "measurements": {
            "peak_pressure": peak_pressure,
            "static_compliance": compliance,
            "ecv": ecv,
            "width": curve.get("width"),
            "gradient": curve.get("gradient"),
        },
        "within_normal": _within_normal(peak_pressure, compliance, ecv,
                                        curve.get("width"), curve.get("gradient"),
                                        curve["normative"]),
        "infant_warning": infant_warning,
        "interpretation": _interpret(typed, curve, reflex, infant_warning),
        "flags": curve["flags"],
    }


def _within_normal(pressure, compliance, ecv, width, gradient, norms
                   ) -> Dict[str, Optional[bool]]:
    def check(value, bounds):
        return None if value is None else bounds[0] <= value <= bounds[1]

    return {
        "pressure": check(pressure, norms["pressure"]),
        "compliance": check(compliance, norms["compliance"]),
        "ecv": check(ecv, norms["ecv"]),
        "width": check(width, norms["width"]),
        "gradient": None if gradient is None else gradient >= GRADIENT_NORMAL_MIN,
    }


def _interpret(typed, curve, reflex, infant_warning) -> List[str]:
    lines: List[str] = []
    if infant_warning:
        lines.append(infant_warning)
    if not typed:
        lines.append("Not enough data to type this tympanogram.")
        return lines

    lines.append(f"{typed['label']}. {typed['interpretation']}")
    if typed["disorders"]:
        lines.append("Associated disorders: " + ", ".join(typed["disorders"]) + ".")

    notch = curve.get("notch") or {}
    if notch.get("notched"):
        lines.append(f"Notched peak: maxima at {notch['peaks']} daPa, "
                     f"{notch['width']:g} daPa apart.")

    gradient, width = curve.get("gradient"), curve.get("width")
    norms = curve["normative"]
    if gradient is not None:
        if gradient < GRADIENT_NORMAL_MIN:
            lines.append(
                f"Tympanic gradient {gradient:.2f} against a normal minimum of "
                f"{GRADIENT_NORMAL_MIN:g}. A broad, rounded peak is an early "
                "effusion sign that peak height alone misses.")
        else:
            lines.append(f"Tympanic gradient {gradient:.2f} is normal "
                         f"(> {GRADIENT_NORMAL_MIN:g}).")
    if width is not None:
        lines.append(f"Tympanometric width {width:.0f} daPa "
                     f"(normal {norms['width'][0]}-{norms['width'][1]}).")

    if reflex:
        lines.append(reflex["note"])
        if typed["suggests_conductive"] and reflex["pattern"] == "present":
            lines.append(
                "Reflexes are present despite an abnormal tympanogram — unusual, "
                "because a middle-ear problem large enough to alter the trace "
                "normally abolishes them. Re-check both measurements.")

    if curve["source"] == "modelled":
        lines.append("The displayed curve is modelled from the entered summary "
                     "values, not a recorded sweep.")
    return lines
