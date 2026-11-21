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
    TG    tympanic gradient                  > 0.2   (heuristic, see GRADIENT_BASIS)

Both shape measures are reported. The gradient is a dimensionless ratio; the
tympanometric width is the same idea expressed in daPa (Margolis & Heller
1987; ASHA 1997). They agree on real traces, and reporting both means the
result is readable against either convention. Only the width has a published
normative range behind it; the gradient cut-off is reported as a heuristic.

PEAK HEIGHT IS A COMPENSATED QUANTITY. Static admittance is the peak minus the
+200 daPa tail, the canal's own contribution removed (ASHA 1997; BSA 2024
§11.1.3). Whether a peak is shallow, deep or off the scale is judged on that
difference and never on the raw reading, which still contains the ear-canal
volume. A perforated ear adds the middle-ear space to the canal — 3-7 ml
(BSA 2024 §11.1.4) — so its flat trace can sit at 4-5 ml; read raw, that
volume looks like a peak running off the scale. A trace with unrecorded
points has left the scale only when both limbs climb toward them fast enough
to pass the Add height there. Anything else — a dropout away from the peak,
or an apex lost while the limbs were still well short of that height — hides
the measurement the type depends on, so the trace is not typed.

PROBE TONE DECIDES WHICH RULES APPLY. Every type and band above is a 226 Hz
criterion. Below six months a 226 Hz probe can produce a normal-looking trace
over a middle ear full of fluid (Baldwin 2006: 226 Hz is invalid below 21
weeks), so such a trace is refused — never typed, never called normal. A
1000 Hz trace is read by the infant method instead: a main peak above the
baseline joining the sweep's tails is a positive peak, and a flat or
trough-shaped trace, or one with no identifiable peak, is abnormal (Baldwin
2006, after Marchant et al. 1986; BSA 2024 §11.2). A positive peak passes only
if it also reaches the newborn pass-fail admittance (Margolis et al. 2003,
measured from the -400 daPa tail to that same peak). Ear-canal volume and
peak pressure are not interpreted at 1000 Hz, so an infant trace never yields
a cerumen, perforation or otosclerosis verdict. A positive peak is only ever
established from recorded points, and an incomplete 1000 Hz trace — a sweep
short of +200 to -400 daPa (BSA 2024 §10.2), or points missing — is never
reported as more than provisional.
"""
from __future__ import annotations

from bisect import bisect_left
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
#: Below this an entered gradient implies a peak too broad to return to
#: baseline within the sweep, so the drawn curve cannot represent it exactly.
GRADIENT_DRAWABLE_MIN = 0.2

#: Where the 0.2 gradient cut-off comes from, stated wherever it is applied.
#: The ratio form of the gradient is Brooks (1968); de Jonge (1986) compared
#: it with other gradient measures in normal ears. The 0.2 cut-off is taken
#: from the clinic's reference table and could not be traced to a normative
#: study — AAA (2020) asks only for a gradient "abnormally reduced (refer to
#: normative data)", and the published effusion criterion (Nozza et al. 1992,
#: < 0.1 mmho) is an absolute gradient, not this ratio. It is therefore a
#: heuristic: it is reported, it never changes the type, and the
#: tympanometric width against Margolis & Heller (1987) is the validated
#: shape criterion.
GRADIENT_BASIS = (
    "Gradient cut-off 0.2 is a heuristic from the clinic's reference table, "
    "not a validated normative criterion; judge peak shape by tympanometric "
    "width (Margolis & Heller 1987).")

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
#: The smallest admittance difference the curve analysis treats as real
#: rather than sampling noise — the floor below which width, gradient and
#: notch are not measured. An engineering margin, not a published norm.
MEASURABLE_MMHO = 0.05

#: Compensated admittance beyond which the peak runs off the scale of a
#: clinical instrument, which is what separates Type Add from Type Ad.
OFF_SCALE_ADMITTANCE = 3.0

#: The admittance a clinical instrument can plot. Above this the pen leaves
#: the paper: a Type Add trace ascends on both sides and never comes back down
#: within the recordable range, so it has NO apex. Points beyond the ceiling
#: are recorded as None rather than as a number, because the instrument did
#: not measure them — drawing a closed peak there would invent an apex the
#: machine never saw.
#:
#: A complete trace (no unrecorded points) is read as having left the scale
#: only when its *compensated* peak reaches this value, i.e. when a peak
#: exists and is that tall. The raw reading includes the canal volume, and a
#: perforated ear's flat 4-5 ml trace is a large volume, not a peak.
INSTRUMENT_CEILING_MMHO = 4.0
#: A trace with unrecorded points is read as having left the scale there only
#: when both limbs climb toward the gap and, continuing to climb, would carry
#: the compensated peak to OFF_SCALE_ADMITTANCE — the height that types a
#: closed curve Add — by the first unrecorded point. A limb whose last
#: recorded step is still steeper than the one before may be assumed to climb
#: at most this many times faster than over that last step. A limb already
#: rounding over toward an apex is credited with no further climb: it must
#: stand at Add height where it was last recorded. A limb that falls short
#: has lost the apex to a dropout rather than to the scale — read as
#: off-scale, one dropped sample at the top of a normal peak would become
#: Type Add, "ossicular discontinuity". The allowance is an engineering
#: margin, not a published norm, and it errs toward leaving a trace untyped:
#: one that fails the test is not typed at all, never typed as something else.
OFF_SCALE_CLIMB_ALLOWANCE = 1.5

#: Age below which children's normative bands apply.
CHILD_MAX_AGE_YEARS = 10
#: Age below which a 226 Hz probe is not interpretable (BSA 2024 §4.1, §10.2:
#: 1000 Hz below 6 months corrected age; Baldwin 2006: 226 Hz invalid below
#: 21 weeks).
INFANT_MONTHS = 6

#: Probe tones. Every type and normative band in this module is a 226 Hz
#: criterion; some older instruments use 220 Hz, hence a band.
STANDARD_PROBE_HZ = 226
STANDARD_PROBE_BAND_HZ = (200, 300)
#: The infant high-frequency probe.
HIGH_PROBE_HZ = 1000
HIGH_PROBE_BAND_HZ = (900, 1100)
#: Age up to which the 1000 Hz probe is the recommended one. JCIH (2019), on
#: the evidence of Hoffman et al. (2013), extended it to 9 months; from 9-12
#: months the 226 Hz probe was the more accurate, and between 6 and 9 months
#: either may be used (AAA 2020 Clinical Guidance, Tympanometry §4).
HIGH_PROBE_MAX_MONTHS = 9

#: Baldwin's 1000 Hz criterion is qualitative — the main peak is above the
#: baseline or it is not (Baldwin 2006; BSA 2024 §11.2). A deflection this
#: small is within the measurement noise of a sweep and is read as no peak,
#: which refers. The same margin decides whether the trace falls away on both
#: sides of a maximum, i.e. whether there is a peak at all rather than a trace
#: still rising when the sweep ends. It is the measurability floor the 226 Hz
#: curve analysis uses for width, gradient and notch — an engineering margin,
#: not a published norm — and clearing it never on its own produces a normal
#: result: a positive peak must also meet HF_NEWBORN_ADMITTANCE_P5.
HF_PEAK_NOISE_MMHO = MEASURABLE_MMHO
#: Margolis et al. (2003), 1 kHz newborn norms (birth to 4 weeks): static
#: admittance from the -400 daPa tail to the peak, 5th-95th percentile
#: 0.60-4.3 mmho, as tabulated in AAA (2020) Clinical Guidance, Table 1. The
#: 5th percentile was the same for NICU and full-term infants, which Margolis
#: et al. offer as a single pass-fail criterion. A positive peak below it does
#: not pass: AAA (2020) Interpretation I.ii.b counts a peak whose static
#: admittance is below the age norm as abnormal. The shape rule alone (BSA
#: 2024 §11.2) would call any positive peak normal; where the two disagree the
#: result is not reported as normal. It is measured to the main peak, never to
#: the trace's highest sample, which on a sloping 1000 Hz trace is often the
#: +200 daPa tail.
HF_NEWBORN_ADMITTANCE_P5 = 0.6
#: The 95th percentile of the same Margolis et al. (2003) norms (AAA 2020
#: Table 1). Above it a positive peak is not "within the newborn norms": AAA
#: (2020) Interpretation I.ii.b counts static admittance indicating
#: hyper-mobility as abnormal, and Reporting 7.B.v reads it as increased
#: middle-ear mobility (ossicular interruption or a tympanic-membrane
#: abnormality), while the shape rule (BSA 2024 §11.2) would call any positive
#: peak normal. Where they disagree the result is not reported as normal. It
#: is not referred on this alone either: unlike the 5th percentile, Margolis
#: et al. do not offer the 95th as a pass-fail criterion.
HF_NEWBORN_ADMITTANCE_P95 = 4.3
#: Kei et al. (2003), 1 kHz, neonates aged 1-6 days: static admittance from
#: the +200 daPa tail to the peak, 5th percentile 0.39 mmho in right ears (AAA
#: 2020 Table 1). Quoted, not applied as a pass mark: it shows that an
#: admittance compensated to the +200 tail runs lower than Margolis's -400
#: measure, so a printed value below HF_NEWBORN_ADMITTANCE_P5 cannot be judged
#: without knowing which tail the instrument compensated to.
HF_KEI_PLUS200_P5_RIGHT = 0.39
#: The 1000 Hz sweep must cover at least +200 to -400 daPa (BSA 2024 §10.2:
#: "the range should be at least from +200 daPa to -400 daPa"); the baseline
#: is drawn between those pressure extremes (§11.2).
HF_SWEEP_MIN_DAPA = -400
HF_SWEEP_MAX_DAPA = 200
#: Pressure either side, daPa, over which a 1000 Hz trace is averaged before
#: its main peak is looked for. BSA 2024 §10.2 warns that infant movement can
#: put a false peak in the trace. A tympanometric peak spans tens of daPa, so
#: averaging three samples at the usual 10 daPa step leaves a real peak
#: essentially intact while cutting a one-sample excursion to a third; at a
#: coarser step the window holds one sample and nothing is averaged. An
#: engineering margin, not a published norm. The peak's admittance is still
#: measured on the recorded samples.
HF_PEAK_SMOOTHING_DAPA = 10.0

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

#: The outcomes of the infant 1000 Hz classification. They are kept apart
#: from the eight 226 Hz types on purpose: an infant trace is never given a
#: Jerger letter, because every letter carries 226 Hz disorders with it. Only
#: "1k-peak" passes; the other two refer.
HIGH_FREQUENCY_TYPES: Dict[str, dict] = {
    "1k-peak": {
        "label": "1000 Hz — positive peak",
        "shape": "Main peak above the baseline joining the sweep's tails",
        "disorders": [],
        "suggests_conductive": False,
    },
    "1k-low-peak": {
        "label": "1000 Hz — positive peak below the newborn admittance criterion",
        "shape": ("Main peak above the baseline, but static admittance below the "
                  "newborn 5th percentile"),
        "disorders": ["Middle-ear effusion", "Other middle-ear dysfunction"],
        "suggests_conductive": True,
    },
    "1k-no-peak": {
        "label": "1000 Hz — no positive peak",
        "shape": ("Flat, trough-shaped (negative peak), or no identifiable main "
                  "peak"),
        "disorders": ["Middle-ear effusion", "Other middle-ear dysfunction"],
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

HIGH_FREQUENCY_CITATIONS = [
    "Baldwin, M. (2006). Int J Audiol 45:417-427 — 1000 Hz trace "
    "classification, after Marchant et al. (1986)",
    "British Society of Audiology (2024). Recommended Procedure: Tympanometry "
    "and Acoustic Reflex Thresholds, §10.2 and §11.2",
    "Margolis et al. (2003). J Am Acad Audiol 14:383-392 — 1 kHz newborn norms; "
    "5th percentile as a single pass-fail criterion; 95th percentile 4.3 mmho",
    "Kei et al. (2003). J Am Acad Audiol 14(1) — 1 kHz neonatal norms, +200 "
    "daPa tail",
    "JCIH (2019); AAA (2020) Clinical Guidance — 1000 Hz probe in infancy; "
    "Interpretation I.ii.b, admittance indicating hypo- or hyper-mobility is "
    "abnormal; Reporting 7.B.v",
]


def normative(age_years: Optional[float]) -> dict:
    """Normal 226 Hz ranges for this patient's age band."""
    child = age_years is not None and age_years < CHILD_MAX_AGE_YEARS
    return {
        "compliance": list(COMPLIANCE_NORMAL_CHILD if child else COMPLIANCE_NORMAL_ADULT),
        "pressure": list(PRESSURE_NORMAL),
        "ecv": list(ECV_NORMAL_CHILD if child else ECV_NORMAL_ADULT),
        "width": list(WIDTH_NORMAL_CHILD if child else WIDTH_NORMAL_ADULT),
        "gradient_min": GRADIENT_NORMAL_MIN,
        "gradient_basis": GRADIENT_BASIS,
        "band": "child" if child else "adult",
        "probe_hz": STANDARD_PROBE_HZ,
        "applicable": True,
        "citations": list(CITATIONS),
    }


def _normative_not_applicable(band: str, note: str,
                              citations: Optional[List[str]] = None) -> dict:
    """The 226 Hz bands withheld, in the same shape as ``normative``.

    The numeric bands are empty rather than filled with 226 Hz numbers,
    because a 226 Hz band printed beside an infant or 1000 Hz result is
    exactly the misreading this exists to prevent.
    """
    return {
        "compliance": [], "pressure": [], "ecv": [], "width": [],
        "gradient_min": None,
        "gradient_basis": None,
        "band": band,
        "probe_hz": None,
        "applicable": False,
        "note": note,
        "citations": list(citations if citations is not None else CITATIONS),
    }


def normative_high_frequency() -> dict:
    """What a 1000 Hz infant trace is judged against: a shape, not bands."""
    out = _normative_not_applicable(
        "infant_1000hz",
        "1000 Hz infant trace: classified by whether the main peak lies above "
        "the baseline joining the sweep's tails (Baldwin 2006; BSA 2024 §11.2), "
        f"and passes only with at least {HF_NEWBORN_ADMITTANCE_P5:g} mmho from "
        "the -400 daPa tail to that peak (Margolis et al. 2003); above "
        f"{HF_NEWBORN_ADMITTANCE_P95:g} mmho, the 95th percentile, it is not "
        "reported as normal. The 226 Hz "
        "pressure, admittance, volume and width bands do not apply, and "
        "ear-canal volume is not interpreted.",
        HIGH_FREQUENCY_CITATIONS)
    out["probe_hz"] = HIGH_PROBE_HZ
    return out


def probe_mode(age_years: Optional[float], probe_hz: Optional[int]) -> str:
    """Which interpretation this probe tone permits at this age.

        jerger                 226 Hz probe at an age where it is valid
        high_frequency         1000 Hz probe — the infant baseline method
        infant_low_probe       226 Hz probe below six months: not interpretable
        infant_probe_unknown   probe not recorded below six months: cannot
                               assume it was the 1000 Hz one
        unsupported_probe      any other probe frequency

    ``probe_hz`` None means "not recorded". At six months and over that is
    read as the standard 226 Hz probe, which is what every clinical
    tympanometer defaults to.
    """
    infant = age_years is not None and age_years * 12 < INFANT_MONTHS
    if probe_hz is None:
        return "infant_probe_unknown" if infant else "jerger"
    if HIGH_PROBE_BAND_HZ[0] <= probe_hz <= HIGH_PROBE_BAND_HZ[1]:
        return "high_frequency"
    if STANDARD_PROBE_BAND_HZ[0] <= probe_hz <= STANDARD_PROBE_BAND_HZ[1]:
        return "infant_low_probe" if infant else "jerger"
    return "unsupported_probe"


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
    probe_hz: Optional[int] = None,
) -> Optional[dict]:
    """Assign one of the eight types from the measured quantities.

    Order matters. A flat trace has no peak to describe, so it is settled
    first, and a known flat admittance outranks any claim that the trace ran
    off the scale — there is no peak to run off it. An off-scale trace has no
    apex at all, so it comes next: there is no shape left to call notched.
    Only then does a notch outrank depth, because Type D and Type E are
    notched by definition while Ad is not.

    Returns None when the type cannot be determined: too little data, a
    peak whose pressure was not recorded (it could be C or not), a pressure
    without an admittance, or a probe/age combination the 226 Hz rules do not
    cover. None is the honest answer there; every type is a clinical claim.
    """
    mode = probe_mode(age_years, probe_hz)
    if mode == "high_frequency":
        return classify_high_frequency(compliance, peak_pressure, age_years)
    if mode != "jerger":
        # A 226 Hz (or unrecorded) probe below six months, or a probe these
        # rules were not written for. There is no type to give.
        return None

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

    ambiguous = (compliance is not None
                 and AMBIGUOUS_BAND[0] <= compliance <= AMBIGUOUS_BAND[1])

    # 1. Flat: no measurable peak. The canal volume decides what it means —
    #    for a perforation, that volume includes the middle-ear space and is
    #    large, which is a volume and not a peak (Jerger 1970; BSA 2024
    #    §11.1.4). A flat trace has no peak pressure, so none is needed.
    if compliance is not None and compliance < FLAT_ADMITTANCE_MAX:
        split = TYPE_B_BY_VOLUME[band]
        extra = {"disorders": list(split["disorders"])}
        if ambiguous:
            extra["borderline"] = (
                f"Static admittance {compliance:.2f} mmho sits where the flat and "
                "shallow-peak bands meet. Repeat the sweep before committing to "
                "Type B over Type As.")
        return build("B", split["interpretation"], extra)

    # 2. Off the scale. Such a trace has neither a peak pressure nor a peak
    #    admittance to reason about, so every test below would be asking about
    #    a measurement that does not exist. The caller only reports off-scale
    #    when a peak exists and either rose past the ceiling or climbs past
    #    Type Add height into points the instrument could not record.
    if off_scale:
        return build("Add", "The trace runs off the instrument scale — the "
                            "limbs ascend without meeting, so there is no "
                            "measurable peak. This is ossicular discontinuity.",
                     {"off_scale": True})

    if compliance is None:
        # A peak pressure without a peak admittance: the depth that separates
        # As, A, Ad and Add is unknown.
        return None

    # 3. Notched peaks are Type D or E regardless of depth.
    if notch and notch.get("notched"):
        wide = notch.get("width", 0.0) > NOTCH_WIDE_DAPA or compliance > hi
        if wide:
            return build("E", "A wide notched peak indicates ossicular disruption.",
                         {"notch": notch})
        return build("D", "A narrow notched peak indicates a hypermobile or "
                          "scarred tympanic membrane.", {"notch": notch})

    # 4. A complete curve whose peak still exceeds the off-scale threshold.
    #    Compensated admittance alone decides this, so the peak pressure is
    #    not needed.
    if compliance >= OFF_SCALE_ADMITTANCE:
        return build("Add", "Admittance beyond the instrument scale — ossicular "
                            "discontinuity.")

    # A peak exists (it is not flat) but its pressure was not recorded. Type
    # B means "no peak", so it is wrong here; and whether this is Type C
    # depends on exactly the number that is missing.
    if peak_pressure is None:
        return None

    # 5. Pressure before depth: a peak at -250 daPa is Type C whatever its height.
    if peak_pressure < PRESSURE_NORMAL[0]:
        return build("C", "Negative middle-ear pressure: the Eustachian tube is "
                          "not ventilating. This precedes an effusion and, if a "
                          "retraction pocket forms, cholesteatoma.")

    # 6. Depth against the age-appropriate band.
    if compliance > hi:
        return build("Ad", "A deep peak indicates a flaccid membrane or an "
                           "ossicular discontinuity.")
    if compliance < lo:
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
        interpretation += (f" Gradient {gradient:.2f} is below the {GRADIENT_NORMAL_MIN:g} "
                           "heuristic cut-off, so the peak may be rounded — an "
                           "early effusion sign that peak height alone misses. "
                           "Check the tympanometric width before acting on it.")
    return build("A", interpretation)


def classify_high_frequency(
    peak_height: Optional[float],
    peak_pressure: Optional[float] = None,
    age_years: Optional[float] = None,
    from_trace: bool = False,
    reaches_sweep_minimum: Optional[bool] = None,
    peak_re_negative_tail: Optional[float] = None,
    rise_without_peak_toward: Optional[float] = None,
    reaches_sweep_maximum: Optional[bool] = None,
    gap: Optional[str] = None,
) -> Optional[dict]:
    """Classify a 1000 Hz infant trace: a passing positive peak, or not.

    Baldwin (2006), adapted from Marchant et al. (1986), as specified by BSA
    (2024) §11.2: draw a baseline between the pressure extremes, identify the
    main peak, and if it lies above the baseline the trace is a positive peak;
    a flat or trough-shaped (negative-peak) trace is abnormal. Peak pressure
    does not matter — "a positive peak at a positive or negative middle-ear
    pressure is classified as normal" — and ear-canal volume is disregarded
    at 1000 Hz. A positive peak passes only if its static admittance also
    meets the Margolis et al. (2003) newborn pass-fail criterion
    (HF_NEWBORN_ADMITTANCE_P5); below it the result is "1k-low-peak".

    ``peak_height`` is the main peak's height above that baseline when
    ``from_trace`` (None when the trace has no main peak), and
    ``peak_re_negative_tail`` is the same peak measured from the -400 daPa
    tail. From summary values ``peak_height`` is the printed static
    admittance: it cannot show whether the peak sits above the baseline, nor
    which tail the instrument compensated to, so a summary result is never
    more than provisional. ``rise_without_peak_toward`` is the sweep end a
    trace rises into without ever turning down.

    ``gap`` describes points the sweep lists without a reading: "apex" when
    the trace climbs toward them from both sides, so the top of the peak was
    not recorded and the peak is read from the highest recorded point beside
    it (its admittance is then a lower bound); "dropout" when it does not, so
    a peak inside them cannot be excluded. A positive peak is only ever
    established from recorded points — an unrecorded stretch is never itself
    read as a peak.

    Normal function is only reported when nothing undermines it. A sweep too
    short to draw the baseline, missing points, a summary-only entry, a trace
    with no identifiable peak, or an age outside the method's range all leave
    the result provisional and say why.
    """
    if from_trace:
        positive = peak_height is not None and peak_height > HF_PEAK_NOISE_MMHO
    else:
        if peak_height is None:
            return None
        positive = peak_height > HF_PEAK_NOISE_MMHO
        if positive and peak_pressure is None:
            # The printout gives an admittance but no peak pressure: whether
            # the instrument found a peak at all cannot be told from these
            # numbers.
            return None

    # The admittance the pass-fail criterion is judged on.
    if not positive:
        admittance = None
    elif from_trace:
        admittance = peak_re_negative_tail
    else:
        admittance = peak_height
    low = admittance is not None and admittance < HF_NEWBORN_ADMITTANCE_P5
    high = admittance is not None and admittance > HF_NEWBORN_ADMITTANCE_P95
    key = "1k-no-peak" if not positive else "1k-low-peak" if low else "1k-peak"

    caveats: List[str] = []
    months = None if age_years is None else age_years * 12
    if months is None:
        caveats.append(
            "Age not recorded. The 1000 Hz criteria are for infants — under 6 "
            "months corrected age (BSA 2024), extended to 9 months by JCIH "
            "(2019).")
    elif months >= HIGH_PROBE_MAX_MONTHS:
        caveats.append(
            f"At {months:g} months the 226 Hz probe is the more accurate "
            "(Hoffman et al. 2013; JCIH 2019), and these infant criteria may "
            "not hold. Repeat at 226 Hz for a typed result.")
    if not from_trace and positive:
        caveats.append(
            "Classified from summary values. Whether the peak lies above the "
            "baseline joining the sweep's tails cannot be seen without the "
            "trace (Baldwin 2006) — confirm it on the printed tympanogram.")
    if from_trace and (reaches_sweep_minimum is False
                       or reaches_sweep_maximum is False):
        caveats.append(
            f"The sweep did not cover {HF_SWEEP_MAX_DAPA:+d} to {HF_SWEEP_MIN_DAPA} "
            "daPa, the minimum range for 1000 Hz infant tympanometry (BSA 2024 "
            "§10.2). The baseline is drawn between those pressure extremes "
            "(§11.2), so it cannot be drawn as specified. Repeat with the full "
            "sweep.")
    # A positive peak whose admittance from the -400 daPa tail could not be
    # measured has not met the Margolis et al. (2003) pass-fail criterion
    # either way; in infant screening a pass that cannot be established is a
    # repeat, never a pass.
    criterion_unmeasured = key == "1k-peak" and from_trace and admittance is None
    if criterion_unmeasured:
        caveats.append(
            f"The admittance from the {HF_SWEEP_MIN_DAPA} daPa tail to the peak "
            "could not be measured, so the newborn pass-fail criterion "
            f"({HF_NEWBORN_ADMITTANCE_P5:g} mmho, Margolis et al. 2003; AAA 2020 "
            "Table 1) was not applied and this is not a pass. Repeat with the "
            "full sweep.")
    if high:
        caveats.append(
            f"Static admittance {'of at least ' if from_trace and gap == 'apex' else ''}"
            f"{admittance:.2f} mmho is above {HF_NEWBORN_ADMITTANCE_P95:g} mmho, "
            "the newborn 95th percentile (Margolis et al. 2003; AAA 2020 Table "
            "1). By shape a positive peak is normal (BSA 2024 §11.2), but AAA "
            "(2020) counts admittance indicating hyper-mobility as abnormal and "
            "reads it as increased middle-ear mobility — ossicular interruption "
            "or a tympanic-membrane abnormality. Check the probe fit and repeat; "
            "if it persists, otoscopy.")
    if from_trace and gap == "apex":
        caveats.append(
            "Points at the top of the trace were not recorded, so the peak the "
            "method classifies on is missing. "
            + (f"The highest recorded point beside them stands {admittance:.2f} "
               f"mmho above the {HF_SWEEP_MIN_DAPA} daPa tail; the apex can only "
               "be higher, but its admittance is unknown. "
               if admittance is not None else "")
            + "Repeat the trace to record the whole peak.")
    elif from_trace and gap == "dropout":
        caveats.append(
            "Points are missing from the sweep where the trace does not rise "
            "toward them. A peak inside the gap cannot be excluded, so the "
            "result read from the recorded points is not final. Repeat the "
            "trace.")
    if not from_trace and low:
        caveats.append(
            f"Margolis's {HF_NEWBORN_ADMITTANCE_P5:g} mmho criterion is measured "
            f"from the {HF_SWEEP_MIN_DAPA} daPa tail. If the instrument "
            "compensated to the +200 daPa tail instead, newborn 5th percentiles "
            f"on that tail are lower (Kei et al. 2003: {HF_KEI_PLUS200_P5_RIGHT:g} "
            "mmho, right ears; AAA 2020 Table 1), so this printed value cannot be "
            "judged without the trace. Read the printed tympanogram before "
            "referring on this number alone.")
    if from_trace and not positive and rise_without_peak_toward is not None:
        caveats.append(
            f"The admittance rises into the {rise_without_peak_toward:+g} daPa end "
            "of the sweep and never turns down, so a peak beyond the swept range "
            "cannot be excluded. Repeat with the full sweep (BSA 2024 §11.2 "
            "allows the negative extreme to reach -600 daPa) before treating "
            "this as a negative trace — but it is not a normal result as "
            "recorded.")

    entry = HIGH_FREQUENCY_TYPES[key]
    volume_note = (" Ear-canal volume and peak pressure are not interpreted at "
                   "1000 Hz (BSA 2024 §11.2).")
    refer_note = (" Repeat the trace to exclude movement artefact; if it "
                  "persists, refer for otoscopy and medical review — middle-ear "
                  "effusion is the usual cause in infancy.")
    if key == "1k-peak" and not caveats:
        interpretation = ("A positive peak above the baseline joining the sweep's "
                          "tails, with static admittance within the newborn "
                          "norms: consistent with normal middle-ear function "
                          "(Baldwin 2006, after Marchant et al. 1986; Margolis "
                          "et al. 2003)." + volume_note)
    elif key == "1k-peak":
        interpretation = ("A positive peak was recorded, but normal middle-ear "
                          "function cannot be confirmed from this result — see "
                          "the caveats." + volume_note)
    elif key == "1k-low-peak" and from_trace and gap == "apex":
        interpretation = (
            f"The highest recorded points beside an unrecorded apex stand "
            f"{admittance:.2f} mmho above the {HF_SWEEP_MIN_DAPA} daPa tail, below "
            f"{HF_NEWBORN_ADMITTANCE_P5:g} mmho, the newborn pass-fail criterion of "
            "Margolis et al. (2003; AAA 2020 Table 1). The apex itself was not "
            "recorded, so the trace cannot pass as recorded." + refer_note
            + volume_note)
    elif key == "1k-low-peak" and from_trace:
        interpretation = (
            f"A positive peak above the baseline, but its static admittance of "
            f"{admittance:.2f} mmho from the {HF_SWEEP_MIN_DAPA} daPa tail is "
            f"below {HF_NEWBORN_ADMITTANCE_P5:g} mmho, the newborn 5th percentile "
            "that Margolis et al. (2003) give as a pass-fail criterion (AAA 2020 "
            "Table 1). By shape alone a positive peak is normal (BSA 2024 §11.2), "
            "but admittance below the age norm is abnormal (AAA 2020), so normal "
            "middle-ear function is not reported." + refer_note + volume_note)
    elif key == "1k-low-peak":
        interpretation = (
            f"The printed static admittance of {admittance:.2f} mmho is below "
            f"{HF_NEWBORN_ADMITTANCE_P5:g} mmho, the newborn pass-fail criterion "
            "of Margolis et al. (2003; AAA 2020 Table 1), so this result does not "
            "pass. Confirm it on the printed trace (see the caveats)." + refer_note
            + volume_note)
    else:
        shape = ("No main peak: the trace rises into the end of the sweep without "
                 "turning down, so there is no positive peak to classify"
                 if from_trace and rise_without_peak_toward is not None else
                 "No positive peak above the baseline — a flat or trough-shaped "
                 "trace")
        interpretation = (
            shape + ", which is abnormal at 1000 Hz (Baldwin 2006; BSA 2024 "
            "§11.2)." + refer_note + " Ear-canal volume is not interpreted at "
            "1000 Hz, so this does not separate effusion from a perforation or a "
            "blocked probe — otoscopy and a probe check do.")

    out = {
        "type": key,
        "label": entry["label"],
        "shape": entry["shape"],
        "interpretation": interpretation,
        "disorders": list(entry["disorders"]),
        "suggests_conductive": entry["suggests_conductive"],
        "ecv_flag": "not_interpreted",
        "normative": normative_high_frequency(),
        "probe_hz": HIGH_PROBE_HZ,
        "criterion": ("Positive main peak above the baseline between the pressure "
                      "extremes = normal; flat, trough-shaped or no identifiable "
                      "peak = abnormal (Baldwin 2006; BSA 2024 §11.2). A positive "
                      f"peak passes only with at least {HF_NEWBORN_ADMITTANCE_P5:g} "
                      f"mmho from the {HF_SWEEP_MIN_DAPA} daPa tail to the peak "
                      "(Margolis et al. 2003; AAA 2020 Table 1); above "
                      f"{HF_NEWBORN_ADMITTANCE_P95:g} mmho, the 95th percentile, "
                      "it is not reported as normal (AAA 2020 Interpretation "
                      "I.ii.b)."),
        "static_admittance": None if admittance is None else round(admittance, 3),
        "refer": key != "1k-peak" or criterion_unmeasured,
    }
    if from_trace and gap == "apex" and admittance is not None:
        out["static_admittance_is_lower_bound"] = True
    if caveats:
        out["provisional"] = True
        out["caveats"] = caveats
    return out


# --------------------------------------------------------------------------
# curve analysis
# --------------------------------------------------------------------------
def _as_points(trace: Sequence) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    for item in trace or []:
        if isinstance(item, dict):
            if item.get("off_scale"):
                # A point marked off the scale has no reading, whatever number
                # it carries: at most that is the instrument's limit.
                continue
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
    admittance 50 daPa either side of it — the ratio form of Brooks (1968). A
    sharp peak drops away quickly and scores high; a broad, rounded peak scores
    low. The reference table's normal "> 0.2" is a heuristic (GRADIENT_BASIS).
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


def _unmeasured_pressures(trace: Sequence) -> List[float]:
    """Pressures the sweep lists without a reading.

    An admittance left empty is unmeasured, and so is a point the recording
    marks as off the scale (``_as_points`` leaves both out).
    """
    out: List[float] = []
    for item in trace or []:
        if isinstance(item, dict):
            p = item.get("pressure")
            unmeasured = bool(item.get("off_scale")) or item.get("admittance") is None
        else:
            p = item[0]
            unmeasured = item[1] is None
        if p is not None and unmeasured:
            out.append(float(p))
    return out


def _limb_climbs_to(points: List[Tuple[float, float]], border: int,
                    outward: int) -> bool:
    """Does the limb on one side of a gap climb to the point bordering it?

    The bordering point must be the highest on its side of the gap (within
    the measurability floor), and the last recorded step into it must still
    be rising. Then the trace's maximum lies in the gap.
    """
    a = points[border][1]
    limb = points[:border + 1] if outward < 0 else points[border:]
    if a < max(v for _, v in limb) - MEASURABLE_MMHO:
        return False
    j = border + outward
    return 0 <= j < len(points) and a > points[j][1] \
        and points[j][0] != points[border][0]


def _climb_reaches_add(points: List[Tuple[float, float]], border: int,
                       outward: int, gap_pressure: float, tail: float) -> bool:
    """Would this limb carry the compensated peak to Type Add height by the
    first unrecorded point? See OFF_SCALE_CLIMB_ALLOWANCE."""
    p_b, a_b = points[border]
    if a_b - tail >= OFF_SCALE_ADMITTANCE:
        return True
    k = border + 2 * outward
    if not 0 <= k < len(points):
        # Too short a limb to tell whether it is still steepening.
        return False
    (p_o, a_o), (p_k, a_k) = points[border + outward], points[k]
    if p_k == p_o:
        return False
    rate = (a_b - a_o) / abs(p_b - p_o)
    if rate <= (a_o - a_k) / abs(p_o - p_k):
        # Already rounding over toward an apex: credited with no further
        # climb, so it must stand at Add height where it was last recorded.
        return False
    reach = a_b - tail + OFF_SCALE_CLIMB_ALLOWANCE * rate * abs(gap_pressure - p_b)
    return reach >= OFF_SCALE_ADMITTANCE


def _classify_gaps(trace: Sequence, points: List[Tuple[float, float]],
                   tail: float) -> Tuple[bool, Optional[str]]:
    """Did the trace leave the instrument's range near its peak?

    Returns ``(off_scale, gap)``. ``gap`` describes the points the sweep
    lists without a reading inside its recorded range:

        "off_scale"  both limbs climb toward them and would reach Type Add
                     height there — the peak left the scale, which is the
                     defining feature of Type Add
        "apex"       both limbs climb toward them but stop short of that —
                     the top of the peak was simply not recorded
        "dropout"    the trace does not climb toward them from both sides —
                     a recording dropout away from the peak
        None         nothing missing

    A gap only counts as off-scale when a peak exists beside it: both
    bordering points stand above the +200 daPa tail by more than a flat
    trace. Off-scale is judged on that compensated height, never on the raw
    reading — a perforation's flat trace at 4-5 ml is canal plus middle-ear
    volume (BSA 2024 §11.1.4), not a peak, and a flat trace does not climb
    toward anything. A dropout or an unrecorded apex can hide the very
    measurement the type depends on, so neither is typed.

    With nothing missing, the trace has left the scale only if its
    compensated peak reaches the instrument ceiling itself.
    """
    pressures = [p for p, _ in points]
    regions: Dict[int, List[float]] = {}
    for g in _unmeasured_pressures(trace):
        if not points or not pressures[0] < g < pressures[-1] or g in pressures:
            continue
        # The recorded point just below the gap; the one just above it follows.
        regions.setdefault(bisect_left(pressures, g) - 1, []).append(g)

    kinds = set()
    for left, gaps in regions.items():
        right = left + 1
        if not (_limb_climbs_to(points, left, -1)
                and _limb_climbs_to(points, right, +1)):
            kinds.add("dropout")
            continue
        peak_beside = (min(points[left][1], points[right][1]) - tail
                       > FLAT_ADMITTANCE_MAX)
        if peak_beside \
                and _climb_reaches_add(points, left, -1, min(gaps), tail) \
                and _climb_reaches_add(points, right, +1, max(gaps), tail):
            kinds.add("off_scale")
        else:
            kinds.add("apex")
    if kinds:
        gap = next(k for k in ("off_scale", "apex", "dropout") if k in kinds)
        return gap == "off_scale", gap

    rise = (max(a for _, a in points) - tail) if points else 0.0
    return rise > FLAT_ADMITTANCE_MAX and rise >= INSTRUMENT_CEILING_MMHO, None


def _smoothed(points: List[Tuple[float, float]]) -> List[float]:
    """Each admittance averaged over the samples within HF_PEAK_SMOOTHING_DAPA."""
    out: List[float] = []
    for p, _ in points:
        window = [a for q, a in points if abs(q - p) <= HF_PEAK_SMOOTHING_DAPA + 1e-9]
        out.append(sum(window) / len(window))
    return out


def _main_peak(points: List[Tuple[float, float]], base,
               values: Optional[List[float]] = None) -> Optional[int]:
    """Index of the 1000 Hz main peak, or None when the trace has none.

    BSA (2024) §11.2 asks the reader to "identify the main peak" — a point the
    trace rises to and falls away from. A candidate is an interior local
    maximum from which the trace falls by more than HF_PEAK_NOISE_MMHO on
    each side before it meets higher ground or the end of the sweep, so a
    sampling ripple is not a peak and neither is a trace still rising when
    the sweep ends. Of the candidates, the main peak is the one standing
    highest above the baseline, the distance the method classifies on.

    ``values`` are the admittances the search runs on — the averaged trace
    (``_smoothed``) — defaulting to the recorded samples.
    """
    values = [a for _, a in points] if values is None else values
    n = len(points)
    best: Optional[Tuple[float, int]] = None
    for i in range(1, n - 1):
        a = values[i]
        if a < values[i - 1] or a < values[i + 1]:
            continue
        falls = []
        for step in (-1, 1):
            lowest, j = a, i + step
            while 0 <= j < n and values[j] <= a:
                lowest = min(lowest, values[j])
                j += step
            falls.append(a - lowest)
        if min(falls) <= HF_PEAK_NOISE_MMHO:
            continue
        height = a - base(points[i][0])
        if best is None or height > best[0]:
            best = (height, i)
    return None if best is None else best[1]


def _baseline_measures(points: List[Tuple[float, float]]) -> dict:
    """The 1000 Hz infant measures: the main peak against the tail baseline.

    BSA (2024) §11.2, after Baldwin (2006): a baseline is drawn between the
    pressure extremes, to the x axis if the trace dips below it; the main
    peak's vertical distance from that line decides positive or negative.
    The newborn admittance criterion is measured to that same main peak from
    the -400 daPa tail (Margolis et al. 2003).

    The peak is looked for on the averaged trace (HF_PEAK_SMOOTHING_DAPA), so
    a one-sample movement artefact is not a main peak, and is then measured
    on the recorded sample it stands on. It counts as above the baseline only
    as far as both the recorded sample and the averaged trace put it there.
    """
    (p_lo, a_lo), (p_hi, a_hi) = points[0], points[-1]
    a_lo, a_hi = max(a_lo, 0.0), max(a_hi, 0.0)
    span = p_hi - p_lo

    def base(p: float) -> float:
        return a_lo if span == 0 else a_lo + (a_hi - a_lo) * (p - p_lo) / span

    deviations = [a - base(p) for p, a in points]
    largest, below = max(deviations), min(deviations)
    negative_tail = _interp(points, float(HF_SWEEP_MIN_DAPA))
    smooth = _smoothed(points)
    main = _main_peak(points, base, smooth)

    rise_toward = None
    if main is None:
        peak_pressure = peak_admittance = above = re_negative_tail = None
        if max(s - base(p) for (p, _), s in zip(points, smooth)) > HF_PEAK_NOISE_MMHO:
            # The trace bulges above the baseline but never turns down: it
            # keeps rising into whichever end it stays level with its maximum.
            top = max(range(len(points)), key=lambda i: smooth[i])
            fall_left = smooth[top] - min(smooth[:top + 1])
            fall_right = smooth[top] - min(smooth[top:])
            rise_toward = p_lo if fall_left <= fall_right else p_hi
    else:
        centre = points[main][0]
        nearby = [i for i, (p, _) in enumerate(points)
                  if abs(p - centre) <= HF_PEAK_SMOOTHING_DAPA + 1e-9]
        peak_pressure, peak_admittance = points[max(nearby, key=lambda i: points[i][1])]
        above = min(peak_admittance - base(peak_pressure),
                    smooth[main] - base(centre))
        re_negative_tail = (None if negative_tail is None
                            else peak_admittance - negative_tail)

    return {
        "baseline": [[round(p_lo, 1), round(a_lo, 3)], [round(p_hi, 1), round(a_hi, 3)]],
        "main_peak_found": main is not None,
        "peak_above_baseline": None if above is None else round(above, 3),
        "peak_pressure": None if peak_pressure is None else round(peak_pressure, 1),
        "peak_admittance": (None if peak_admittance is None
                            else round(peak_admittance, 3)),
        "largest_rise_above_baseline": round(max(largest, 0.0), 3),
        "deepest_below_baseline": round(-below, 3) if below < 0 else 0.0,
        "rise_without_peak_toward": rise_toward,
        "reaches_sweep_minimum": p_lo <= HF_SWEEP_MIN_DAPA,
        "reaches_sweep_maximum": p_hi >= HF_SWEEP_MAX_DAPA,
        "peak_re_negative_tail": (None if re_negative_tail is None
                                  else round(re_negative_tail, 3)),
    }


def analyze_trace(trace: Sequence, age_years: Optional[float] = None,
                  probe_hz: Optional[int] = STANDARD_PROBE_HZ) -> Optional[dict]:
    """Peak, gradient, width, notch and tail volume from a pressure sweep.

    The geometry is measured whatever the probe. What it is *judged* against
    depends on the probe and age (``probe_mode``): only a valid 226 Hz trace
    gets the volume and shape flags, because those flags are 226 Hz criteria.
    """
    points = _as_points(trace)
    if len(points) < 5:
        return None
    mode = probe_mode(age_years, probe_hz)

    pressures = [p for p, _ in points]
    admittances = [a for _, a in points]

    # The positive tail is the baseline: at +200 daPa the drum is stiffened and
    # the probe is effectively measuring the canal alone.
    tail_candidates = [a for p, a in points if p >= max(pressures) - 50]
    tail = min(tail_candidates) if tail_candidates else min(admittances)
    off_scale, gap = _classify_gaps(trace, points, tail)
    if mode == "high_frequency":
        # Type Add is a 226 Hz type, and the +200 daPa tail is not what a
        # 1000 Hz trace is measured from. Missing points are described, and
        # the infant classification decides what they leave undetermined.
        off_scale = False
        gap = "apex" if gap == "off_scale" else gap
    gap_without_peak = gap in ("apex", "dropout")
    # Points the recording itself marks as beyond its range. They are read
    # like any unrecorded point, but the words must not call them a dropout:
    # the instrument said where they went, only not how high.
    marked_off_scale = any(isinstance(item, dict) and item.get("off_scale")
                           for item in trace or [])

    peak_idx = max(range(len(points)), key=lambda i: admittances[i])
    peak_pressure, peak_raw = points[peak_idx]
    peak_compensated = round(peak_raw - tail, 3)

    width = _tympanometric_width(points, peak_idx, tail)
    gradient = _tympanic_gradient(points, peak_pressure, peak_raw - tail, tail)
    notch = _detect_notch(points, tail, peak_raw - tail)
    judged = mode == "jerger"
    if judged:
        norms = normative(age_years)
    elif mode == "high_frequency":
        norms = normative_high_frequency()
    else:
        norms = _normative_not_applicable(
            "not_applicable", _UNTYPED_REASONS.get(mode, ""))
    no_apex = off_scale or gap_without_peak

    flags: List[str] = []
    if judged and not no_apex:
        # A flat trace's highest sample can land anywhere, including the
        # sweep's end; that is not a peak sitting there.
        if peak_compensated > FLAT_ADMITTANCE_MAX \
                and peak_pressure <= min(pressures) + 10:
            flags.append("Peak sits at the negative end of the sweep — extend the "
                         "sweep below -400 daPa before accepting this as Type C.")
        if peak_compensated <= FLAT_ADMITTANCE_MAX:
            flags.append("No measurable peak — check the probe seal before reporting "
                         "this as a flat trace.")
    if judged:
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
            ("Both limbs climb toward the unrecorded points fast enough to pass "
             f"Type Add height ({OFF_SCALE_ADMITTANCE:g} mmho above the tail) "
             "there: the peak runs off the instrument scale and has no "
             "recordable apex. " if gap == "off_scale" else
             f"The trace exceeds the instrument ceiling of "
             f"{INSTRUMENT_CEILING_MMHO:g} mmho and has no recordable peak. ")
            + "Peak pressure, peak admittance, gradient and width cannot be "
            "measured from it.")
    elif mode == "high_frequency" and gap:
        flags.append(
            "Points are missing from the sweep"
            + (" at the top of the trace" if gap == "apex" else
               ", where the trace does not rise toward them")
            + ". The 1000 Hz result is read from the recorded points and is "
            "provisional. Repeat the trace.")
    elif gap == "apex" and marked_off_scale:
        flags.append(
            "The points at the top of the peak are marked beyond the "
            "instrument's range, but the recorded limbs either side are already "
            f"rounding over short of Type Add height ({OFF_SCALE_ADMITTANCE:g} "
            "mmho above the tail), so how far the peak rose — and so whether it "
            "is Type Add — cannot be established from this trace. Read the peak "
            "admittance from an instrument range that records it.")
    elif gap == "apex":
        flags.append(
            "Points are missing at the top of the peak, but the limbs either "
            f"side stop short of Type Add height ({OFF_SCALE_ADMITTANCE:g} mmho "
            "above the tail) — the apex was not recorded, which is a dropout "
            "rather than a peak running off the scale. Peak height and "
            "pressure cannot be measured, so the trace cannot be typed. Repeat "
            "the sweep.")
    elif gap == "dropout":
        flags.append(
            "Points are missing from the sweep but the trace does not rise "
            "toward them — a recording dropout, not a peak running off the "
            "scale. A peak could be hidden in the gap, so the trace cannot be "
            "typed. Repeat the sweep.")
    if no_apex:
        gradient = width = None
        notch = {"notched": False}
    elif judged:
        if width is not None and width > norms["width"][1] \
                and peak_compensated > FLAT_ADMITTANCE_MAX:
            flags.append(f"Tympanometric width {width:.0f} daPa is wider than normal "
                         f"({norms['width'][0]}-{norms['width'][1]}); a rounded peak "
                         "suggests early effusion even with normal peak height.")
        if gradient is not None and gradient < GRADIENT_NORMAL_MIN \
                and peak_compensated > FLAT_ADMITTANCE_MAX:
            flags.append(f"Tympanic gradient {gradient:.2f} is below the "
                         f"{GRADIENT_NORMAL_MIN:g} heuristic cut-off. " + GRADIENT_BASIS)

    high_frequency = None
    if mode == "high_frequency":
        high_frequency = _baseline_measures(points)
        if not (high_frequency["reaches_sweep_minimum"]
                and high_frequency["reaches_sweep_maximum"]):
            flags.append(
                f"The sweep runs from {min(pressures):g} to {max(pressures):g} "
                "daPa. A 1000 Hz infant sweep should cover at least "
                f"{HF_SWEEP_MAX_DAPA:+d} to {HF_SWEEP_MIN_DAPA} daPa (BSA 2024 "
                "§10.2) so the baseline can be drawn from the pressure extremes.")

    return {
        "peak": {"pressure": None if no_apex else round(peak_pressure, 1),
                 "admittance": None if no_apex else peak_compensated,
                 "raw_admittance": None if no_apex else round(peak_raw, 3),
                 "reached_ceiling": off_scale},
        "ecv": round(tail, 3),
        "width": None if width is None else round(width, 1),
        "gradient": None if gradient is None else round(gradient, 3),
        "notch": notch,
        "off_scale": off_scale,
        "gap_without_peak": gap_without_peak,
        "gap": gap,
        "gap_marked_off_scale": bool(gap) and marked_off_scale,
        "ceiling": INSTRUMENT_CEILING_MMHO,
        "points": _echo_points(trace, points),
        "sweep": [min(pressures), max(pressures)],
        "flags": flags,
        "normative": norms,
        "high_frequency": high_frequency,
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
def width_from_gradient(gradient: Optional[float]) -> Optional[float]:
    """Tympanometric width (daPa) that produces a given gradient.

    The inverse of ``_tympanic_gradient`` for a Gaussian peak. With

        GR = 1 − exp(−50² / 2σ²)

    solving for σ and converting to full-width-at-half-maximum gives the width
    that will read back as the requested gradient. This is what lets a
    clinician type GRAD from a machine printout and get a curve whose measured
    gradient is the number they entered, rather than a shape that merely looks
    plausible.

    Exact at and above a gradient of about 0.2. Below that the implied peak is
    so broad it has not returned to baseline by the +200 daPa end of a standard
    sweep, so the drawn curve reads back a little higher than the value
    entered — 0.10 draws as 0.12. The drift is small, one-directional, and
    never lifts an abnormal gradient above the 0.2 threshold, but it is a
    property of the sweep range rather than of the arithmetic, so it is
    reported rather than hidden.
    """
    if gradient is None or not (0 < gradient < 1):
        return None
    from math import log, sqrt

    sigma = sqrt(1250.0 / -log(1.0 - gradient))
    return round(sigma * 2.355, 1)


def synthesize_trace(
    peak_pressure: Optional[float],
    compliance: Optional[float],
    ecv: Optional[float] = None,
    width: Optional[float] = None,
    notched: bool = False,
    notch_width: float = 60.0,
    ceiling: Optional[float] = None,
    gradient: Optional[float] = None,
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
    # An entered gradient takes precedence: it is a measurement, whereas the
    # default width is only a plausible shape.
    fwhm = (width or width_from_gradient(gradient)
            or (90.0 if height > FLAT_ADMITTANCE_MAX else 400.0))
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
#: Why a probe/age combination yields no type, keyed by ``probe_mode``.
_UNTYPED_REASONS = {
    "infant_low_probe": (
        "Not typed. A 226 Hz tympanogram below 6 months of age cannot be "
        "interpreted: the infant ear is mass-dominated and its cartilaginous "
        "canal can return a normal-looking trace over a middle ear full of "
        "fluid (Baldwin 2006; BSA 2024 §4.1). Repeat with a 1000 Hz probe."),
    "infant_probe_unknown": (
        "Not typed. The probe frequency was not recorded, and below 6 months "
        "only a 1000 Hz trace can be interpreted (BSA 2024 §10.2). Record the "
        "probe tone, or repeat with a 1000 Hz probe."),
    "unsupported_probe": (
        "Not typed. The tympanogram types and normal ranges here are 226 Hz "
        "criteria, with a separate 1000 Hz method for infants; no criteria are "
        "implemented for this probe frequency."),
}


def _untyped_reason(mode: str, curve: dict, peak_pressure, compliance) -> Optional[str]:
    """Why no type was given, in words a clinician can act on."""
    if mode in _UNTYPED_REASONS:
        return _UNTYPED_REASONS[mode]
    if curve.get("gap") == "apex" and curve.get("gap_marked_off_scale"):
        return ("Not typed. The points at the top of the peak are marked beyond "
                "the instrument's range, but the recorded limbs either side are "
                "already rounding over short of Type Add height, so the peak "
                "height that decides the type cannot be established from this "
                "trace. Read the peak admittance from an instrument range that "
                "records it.")
    if curve.get("gap") == "apex":
        return ("Not typed. Points at the top of the peak were not recorded, "
                "and the limbs either side stop short of Type Add height, so "
                "the apex was lost to a dropout rather than to the instrument "
                "scale. The peak height and pressure that decide the type are "
                "the missing measurements. Repeat the sweep.")
    if curve.get("gap_without_peak"):
        return ("Not typed. The sweep has an unmeasured gap but does not rise "
                "toward it, so it is neither an off-scale peak nor a flat trace "
                "with confidence — a narrow peak could sit inside the gap. "
                "Repeat the sweep.")
    if peak_pressure is None and compliance is None:
        return None
    if compliance is None:
        return ("Not typed. A peak pressure was entered without a static "
                "admittance, and the admittance is what separates a shallow, "
                "normal, deep and off-scale peak. Enter the static admittance "
                "from the printout.")
    if peak_pressure is None:
        if mode == "high_frequency":
            return ("Not typed. An admittance was entered without a peak "
                    "pressure, so these numbers cannot show whether the "
                    "instrument found a peak at all. Read the result from the "
                    "printed trace.")
        return (f"Not typed. Peak pressure was not recorded. A static admittance "
                f"of {compliance:.2f} mmho means a peak exists, so the trace is "
                "not flat (not Type B), but whether it is Type C depends on the "
                "missing pressure. Enter the peak pressure from the printout.")
    return None


def analyze(
    ear: str = "right",
    trace: Optional[Sequence] = None,
    peak_pressure: Optional[float] = None,
    compliance: Optional[float] = None,
    ecv: Optional[float] = None,
    reflexes: Optional[Dict[str, Optional[float]]] = None,
    pta: Optional[float] = None,
    age_years: Optional[float] = None,
    probe_hz: int = STANDARD_PROBE_HZ,
    gradient: Optional[float] = None,
    recorded_type: Optional[str] = None,
) -> dict:
    """One tympanometry study: curve, type, gradient, reflexes, interpretation.

    Three entry modes, in order of how much they support:

    1. A RECORDED SWEEP (``trace``) — everything: the peak, the gradient, the
       tympanometric width, the notch that separates Types D and E.
    2. THE FOUR PRINTED VALUES (ECV, peak pressure, static compliance,
       gradient) — the curve is modelled from them, and an entered gradient
       shapes it so the drawing reads back as the value that was typed.
    3. THE TYPE ALONE (``recorded_type``) — for a clinic holding nothing but
       "Type C" off a printout or a referral letter. The type is most of what
       a tympanogram contributes to a differential, so it is worth recording;
       what it cannot give is the Type B canal-volume split, the gradient or
       any normative comparison, and the result says so instead of leaving a
       reader to assume a full study.

    A sweep or values always take precedence over a recorded type: they
    support strictly more, so accepting the type beside them could only
    subtract information.

    The probe tone and age choose the rules (``probe_mode``). A 226 Hz trace
    under six months is refused rather than typed; a 1000 Hz trace is read by
    the infant baseline method; anything the rules cannot type comes back with
    ``tympanogram`` None and a ``not_typed`` reason.
    """
    # Imported here rather than at module scope: immittance.py takes its
    # classifier from this module, so a top-level import would close a cycle.
    from app.clinical.immittance import analyze_reflexes, from_recorded_type

    has_values = any(v is not None for v in (peak_pressure, compliance, ecv))
    if recorded_type and not (trace or has_values):
        typed = from_recorded_type(recorded_type)
        reflex = analyze_reflexes(reflexes or {}, pta)
        infant_warning = None
        if typed is None:
            return {
                "ear": ear, "probe_hz": probe_hz,
                "probe_mode": probe_mode(age_years, probe_hz),
                "age_years": age_years, "curve": None, "tympanogram": None,
                "not_typed": (f"'{recorded_type}' is not one of the eight "
                              f"tympanogram types ({', '.join(TYMPANOGRAM_TYPES)})."),
                "reflexes": reflex, "entry_mode": "type",
                "measurements": {}, "within_normal": {},
                "infant_warning": None,
                "interpretation": [], "flags": [],
            }
        caveat = None
        if age_years is not None and age_years < 1.0:
            # Same reasoning as the battery's: with no probe tone recorded
            # alongside a bare type, an infant's normal-looking trace may be
            # a 226 Hz probe reading over an effusion.
            from app.clinical.immittance import INFANT_PROBE_CAVEAT
            caveat = INFANT_PROBE_CAVEAT
            typed = {**typed, "provisional": True,
                     "caveats": [*typed["caveats"], caveat]}
            infant_warning = caveat
        lines = [f"{typed['label']}. {typed['interpretation']}"]
        if typed["disorders"]:
            lines.append("Associated disorders: "
                         + ", ".join(typed["disorders"]) + ".")
        lines.extend(typed["caveats"])
        if reflex:
            lines.append(reflex["note"])
        return {
            "ear": ear,
            "probe_hz": probe_hz,
            "probe_mode": probe_mode(age_years, probe_hz),
            "age_years": age_years,
            # No curve: there is nothing to draw, and drawing a representative
            # shape for the type would be inventing a measurement.
            "curve": None,
            "tympanogram": typed,
            "not_typed": None,
            "reflexes": reflex,
            "entry_mode": "type",
            "measurements": {
                "peak_pressure": None, "static_compliance": None,
                "static_compliance_reference": None, "ecv": None,
                "width": None, "gradient": None,
            },
            "within_normal": {"pressure": None, "compliance": None, "ecv": None,
                              "width": None, "gradient": None},
            "infant_warning": infant_warning,
            "interpretation": lines,
            "flags": [],
        }

    mode = probe_mode(age_years, probe_hz)
    entered_gradient = gradient
    curve = analyze_trace(trace or [], age_years, probe_hz=probe_hz)
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
        if mode == "jerger":
            norms = normative(age_years)
        elif mode == "high_frequency":
            norms = normative_high_frequency()
        else:
            norms = _normative_not_applicable("not_applicable",
                                              _UNTYPED_REASONS.get(mode, ""))
        curve = {
            "peak": {"pressure": peak_pressure,
                     "admittance": compliance,
                     "raw_admittance": None},
            "ecv": ecv,
            "width": width_from_gradient(entered_gradient),
            "gradient": entered_gradient,
            "notch": {"notched": False},
            "off_scale": False,
            "gap_without_peak": False,
            "gap": None,
            "ceiling": INSTRUMENT_CEILING_MMHO,
            "points": synthesize_trace(peak_pressure, compliance, ecv,
                                       gradient=entered_gradient),
            "sweep": list(SWEEP),
            "flags": [],
            "normative": norms,
            "high_frequency": None,
            "source": "modelled",
            "note": ("Curve drawn from the entered peak, compliance and canal "
                     "volume. It illustrates those numbers; it is not a "
                     "recorded sweep."),
            "gradient_note": (
                f"A gradient of {entered_gradient:g} implies a peak too broad to "
                f"return to baseline within the {SWEEP[1]:+g} daPa end of the "
                "sweep, so the drawn curve reads back slightly higher than the "
                "value entered. The reading stays abnormal either way."
                if entered_gradient is not None
                and entered_gradient < GRADIENT_DRAWABLE_MIN else None),
        }

    typed = None
    if mode == "jerger" and not curve.get("gap_without_peak"):
        typed = classify(peak_pressure, compliance, ecv,
                         gradient if gradient is not None else entered_gradient,
                         notch, age_years, off_scale=off_scale, probe_hz=probe_hz)
    elif mode == "high_frequency":
        measures = curve.get("high_frequency")
        if measures:
            # Missing points never stop a 1000 Hz reading: it is taken from
            # the recorded points and the gap leaves it provisional.
            typed = classify_high_frequency(
                measures["peak_above_baseline"], measures["peak_pressure"],
                age_years, from_trace=True,
                reaches_sweep_minimum=measures["reaches_sweep_minimum"],
                reaches_sweep_maximum=measures["reaches_sweep_maximum"],
                peak_re_negative_tail=measures["peak_re_negative_tail"],
                rise_without_peak_toward=measures["rise_without_peak_toward"],
                gap=curve.get("gap"))
            # The 226 Hz peak is the trace's highest sample over the +200
            # tail; on a sloping 1000 Hz trace that is often the tail itself.
            # Report the main peak the verdict was reached on, measured as
            # Margolis et al. (2003) measure it. The +200 daPa admittance is
            # not a volume at 1000 Hz and is disregarded (BSA 2024 §11.2), and
            # width and gradient are 226 Hz shape measures.
            peak_pressure = measures["peak_pressure"]
            compliance = measures["peak_re_negative_tail"]
            ecv = None
        else:
            typed = classify_high_frequency(compliance, peak_pressure, age_years)
    not_typed = None if typed else _untyped_reason(mode, curve, peak_pressure,
                                                   compliance)
    reflex = analyze_reflexes(reflexes or {}, pta)

    infant_warning = None
    if mode == "infant_low_probe":
        infant_warning = (
            f"A {probe_hz} Hz probe is not valid below {INFANT_MONTHS} months of "
            "age — the compliant infant ear canal can produce a normal-looking "
            "trace over a middle ear full of fluid. This trace is not typed; "
            "repeat with a 1000 Hz probe.")
    elif mode == "jerger" and age_years is not None \
            and INFANT_MONTHS <= age_years * 12 < HIGH_PROBE_MAX_MONTHS:
        curve["flags"].append(
            f"At {age_years * 12:g} months JCIH (2019) still recommends a 1000 Hz "
            "probe, and either probe may be used between 6 and 9 months (AAA "
            "2020). A 226 Hz trace can miss an effusion at this age (Hoffman et "
            "al. 2013) — confirm at 1000 Hz if the result will change management.")

    norms = curve["normative"]
    width, shape_gradient = curve.get("width"), curve.get("gradient")
    if curve["source"] != "measured":
        compliance_reference = "as entered from the printout"
    elif mode == "high_frequency":
        width = shape_gradient = None
        compliance_reference = (
            f"{HF_SWEEP_MIN_DAPA} daPa tail to the highest recorded point beside "
            "the unrecorded apex — a lower bound (Margolis et al. 2003)"
            if curve.get("gap") == "apex" else
            f"{HF_SWEEP_MIN_DAPA} daPa tail to the main peak (Margolis et al. 2003)")
    else:
        compliance_reference = "+200 daPa tail to the peak"
    return {
        "ear": ear,
        "probe_hz": probe_hz,
        "probe_mode": mode,
        "age_years": age_years,
        "curve": curve,
        "tympanogram": typed,
        "not_typed": not_typed,
        "reflexes": reflex,
        "entry_mode": "trace" if trace else "values",
        "measurements": {
            "peak_pressure": peak_pressure,
            "static_compliance": compliance,
            "static_compliance_reference": compliance_reference,
            "ecv": ecv,
            "width": width,
            "gradient": shape_gradient,
        },
        "within_normal": _within_normal(peak_pressure, compliance, ecv,
                                        width, shape_gradient, norms),
        "infant_warning": infant_warning,
        "interpretation": _interpret(typed, curve, reflex, infant_warning, not_typed),
        "flags": curve["flags"],
    }


def _within_normal(pressure, compliance, ecv, width, gradient, norms
                   ) -> Dict[str, Optional[bool]]:
    if not norms.get("applicable", True):
        # No 226 Hz band applies to this trace, so no number is "normal".
        return {"pressure": None, "compliance": None, "ecv": None,
                "width": None, "gradient": None}

    def check(value, bounds):
        return None if value is None else bounds[0] <= value <= bounds[1]

    return {
        "pressure": check(pressure, norms["pressure"]),
        "compliance": check(compliance, norms["compliance"]),
        "ecv": check(ecv, norms["ecv"]),
        "width": check(width, norms["width"]),
        "gradient": None if gradient is None else gradient >= GRADIENT_NORMAL_MIN,
    }


def _interpret(typed, curve, reflex, infant_warning,
               not_typed: Optional[str] = None) -> List[str]:
    lines: List[str] = []
    if infant_warning:
        lines.append(infant_warning)
    if not typed:
        if not_typed and not_typed not in lines and not infant_warning:
            lines.append(not_typed)
        elif not infant_warning:
            lines.append("Not enough data to type this tympanogram.")
        return lines

    lines.append(f"{typed['label']}. {typed['interpretation']}")
    if typed["disorders"]:
        lines.append("Associated disorders: " + ", ".join(typed["disorders"]) + ".")
    lines.extend(typed.get("caveats") or [])

    notch = curve.get("notch") or {}
    if notch.get("notched"):
        lines.append(f"Notched peak: maxima at {notch['peaks']} daPa, "
                     f"{notch['width']:g} daPa apart.")

    norms = curve["normative"]
    if norms.get("applicable", True):
        gradient, width = curve.get("gradient"), curve.get("width")
        if gradient is not None:
            if gradient < GRADIENT_NORMAL_MIN:
                lines.append(
                    f"Tympanic gradient {gradient:.2f} against a cut-off of "
                    f"{GRADIENT_NORMAL_MIN:g}. A broad, rounded peak is an early "
                    "effusion sign that peak height alone misses. " + GRADIENT_BASIS)
            else:
                lines.append(f"Tympanic gradient {gradient:.2f} is at or above the "
                             f"{GRADIENT_NORMAL_MIN:g} heuristic cut-off.")
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
