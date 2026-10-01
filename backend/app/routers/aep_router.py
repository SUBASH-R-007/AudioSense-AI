"""Evoked potentials and behavioural observation: ABR, MLR, LLR and BOA.

All four run standalone. An ABR on a sleeping newborn, an MLR in a central
processing workup, a P1 latency at a cochlear-implant review, a BOA screen in
a well-baby clinic — none of them arrive with a pure-tone audiogram attached.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.clinical import aep, boa

router = APIRouter(prefix="/api")


class ABRRequest(BaseModel):
    ear: str = "right"
    intensity_db_nhl: float = 80
    #: Wave label -> latency in ms. Absent waves are simply omitted.
    waves: Dict[str, Optional[float]] = Field(default_factory=dict)
    insert_earphones: bool = True
    #: Whether the recorded latencies still contain the insert delay.
    latencies_include_delay: bool = True
    cm_present: Optional[bool] = None
    #: The normative table is female-only; a man's later waves run about
    #: 0.15 ms later. Unknown sex is handled conservatively, not assumed.
    sex: Optional[str] = None
    #: Under 36 months the adult latency limits do not apply.
    age_months: Optional[float] = Field(default=None, ge=0)
    #: This ear's 4 kHz air-conduction threshold, dB HL. Used only by the
    #: interaural comparison: for the Selters & Brackmann correction, and to
    #: refuse a click less than 10 dB above it (BSA 2019 section 7.6).
    threshold_4k_db_hl: Optional[float] = None


class ABRSeriesRequest(BaseModel):
    ear: str = "right"
    #: The intensity ladder actually run: [{"intensity": dB nHL, "wave_v": ms}]
    series: List[Dict[str, Optional[float]]] = Field(default_factory=list)
    #: Decides which nHL-to-eHL correction is typical.
    stimulus: Literal["click", "tone_burst", "nb_chirp", "ce_chirp"] = "click"
    #: Tone-burst / narrow-band chirp frequency, Hz.
    frequency_hz: Optional[float] = None


class MLRRequest(BaseModel):
    ear: str = "right"
    peaks: Dict[str, Optional[float]] = Field(default_factory=dict)
    amplitudes: Dict[str, float] = Field(default_factory=dict)
    opposite_amplitudes: Dict[str, float] = Field(default_factory=dict)
    sedated: bool = False


class LLRRequest(BaseModel):
    ear: str = "right"
    peaks: Dict[str, Optional[float]] = Field(default_factory=dict)
    amplitudes: Dict[str, float] = Field(default_factory=dict)
    age_months: Optional[float] = None


class BOARequest(BaseModel):
    age_months: float = Field(ge=0, le=60)
    observed_level_db_spl: Optional[float] = None
    responses: List[str] = Field(default_factory=list)
    observers: int = Field(default=1, ge=1, le=4)
    presentations: Optional[int] = None


class BatteryRequest(BaseModel):
    abr: Optional[ABRRequest] = None
    #: The second ear's ABR, when both were recorded. The ABR level is only
    #: as normal as its worse ear.
    abr_other_ear: Optional[ABRRequest] = None
    mlr: Optional[MLRRequest] = None
    llr: Optional[LLRRequest] = None


def _run_abr(req: Optional[ABRRequest], ear: Optional[str] = None) -> Optional[dict]:
    if req is None:
        return None
    return aep.analyze_abr(
        waves=req.waves, intensity=req.intensity_db_nhl, ear=ear or req.ear,
        insert_earphones=req.insert_earphones,
        latencies_include_delay=req.latencies_include_delay,
        cm_present=req.cm_present, sex=req.sex, age_months=req.age_months,
    )


@router.get("/aep/reference")
def aep_reference():
    """Protocols, normative windows and the pathway each test reaches."""
    return {
        "abr": {
            "protocol": aep.ABR_PROTOCOL,
            "waves": aep.ABR_WAVES,
            "interwave": aep.ABR_INTERWAVE,
            "insert_delay_ms": aep.INSERT_DELAY_MS,
            "interaural_v_criterion_ms": aep.ABR_INTERAURAL_V_MS,
            "interaural_v_corrected_criterion_ms": aep.ABR_INTERAURAL_V_CORRECTED_MS,
            "interaural_v_selters_brackmann_ms": aep.ABR_INTERAURAL_V_SB_MS,
            "interaural_hearing_loss_correction": aep.SELTERS_BRACKMANN,
            "min_sensation_level_db": aep.ABR_MIN_SENSATION_LEVEL_DB,
            "cm_window_ms": list(aep.CM_WINDOW_MS),
            "interpeak_upper_limits_ms": aep.ABR_IPL_UPPER_MS,
            "i_v_upper_95_cl_ms": aep.ABR_I_V_CL95_MS,
            "delayed_beyond_sd": aep.ABR_DELAYED_Z,
            "borderline_beyond_sd": aep.ABR_BORDERLINE_Z,
            "male_later_wave_allowance_ms": aep.ABR_MALE_LATER_WAVE_SHIFT_MS,
            "adult_norms_from_months": aep.ABR_ADULT_NORMS_FROM_MONTHS,
            "ehl_corrections_db": {
                k: ({str(f): c for f, c in v.items()} if isinstance(v, dict) else list(v))
                for k, v in aep.ABR_EHL_CORRECTION_DB.items()},
            "norms": [
                {"intensity_db_nhl": level, "psp_db": row["psp"],
                 "waves": {w: {"mean": m, "sd": s, "n": n}
                           for w, (m, s, n) in row["waves"].items()},
                 "interwave": {p: {"mean": m, "sd": s, "n": n}
                               for p, (m, s, n) in row["interwave"].items()}}
                for level, row in sorted(aep.ABR_NORMS.items(), reverse=True)
            ],
            "note": ("Normative means and one standard deviation by stimulus "
                     "intensity, interpolated between rows for intermediate "
                     "levels. Absolute latencies are delayed beyond 3 SD and "
                     "borderline between 2 and 3 SD (ACNS Guideline 9C); the "
                     "interpeak intervals are judged against adult clinical "
                     "upper limits rather than this 14-subject table, with I–V "
                     "beyond the adult 95% limit (Lightfoot 1992; BSA 2019) "
                     "borderline."),
        },
        "mlr": {
            "protocol": aep.MLR_PROTOCOL,
            "peaks": [{"peak": k, "range_ms": list(v["range"]),
                       "polarity": v["polarity"], "generator": v["generator"]}
                      for k, v in aep.MLR_NORMS.items()],
            "patterns": [{"key": k, **v} for k, v in aep.MLR_PATTERNS.items()],
        },
        "llr": {
            "protocol": aep.LLR_PROTOCOL,
            "peaks": [{"peak": k, "range_ms": list(v["range"]),
                       "typical_ms": v["typical"], "polarity": v["polarity"]}
                      for k, v in aep.LLR_NORMS.items()],
            "p1_model": {
                "intercept_ms": aep.P1_FIT_INTERCEPT_MS,
                "slope_ms_per_ln_year": aep.P1_FIT_SLOPE_MS,
                "ci95_half_width_ms": aep.P1_CI95_HALF_WIDTH_MS,
                "age_range_years": list(aep.P1_NORM_AGE_YEARS),
                "source": aep.P1_SOURCE,
            },
            "p1_maturation": aep.p1_maturation_curve(),
            "adult_morphology_from_months": aep.LLR_ADULT_MORPHOLOGY_FROM_MONTHS,
        },
        "pathway": [
            {"test": "ABR", "window_ms": [0, 10],
             "level": "Eighth nerve and brainstem"},
            {"test": "MLR", "window_ms": [10, 80],
             "level": "Thalamus, thalamocortical radiations, primary cortex"},
            {"test": "LLR", "window_ms": [50, 350],
             "level": "Auditory cortex and association areas"},
        ],
    }


@router.post("/aep/abr")
def abr(req: ABRRequest):
    """One ABR run against the normative values for the intensity used."""
    return _run_abr(req)


@router.post("/aep/abr/threshold")
def abr_threshold(req: ABRSeriesRequest):
    """Lowest level with an identifiable Wave V, in dB nHL, with its eHL estimate."""
    result = aep.abr_threshold(req.series, stimulus=req.stimulus,
                               frequency_hz=req.frequency_hz)
    return result or {"rows": [], "estimated_threshold": None,
                      "estimated_threshold_db_nhl": None, "unit": "dB nHL",
                      "message": "No intensity ladder recorded."}


@router.post("/aep/abr/asymmetry")
def abr_asymmetry(payload: Dict[str, ABRRequest]):
    """Interaural Wave V difference between two runs at the same level."""
    right, left = payload.get("right"), payload.get("left")
    result = aep.abr_asymmetry(
        _run_abr(right, "right"), _run_abr(left, "left"),
        right_threshold_4k=right.threshold_4k_db_hl if right else None,
        left_threshold_4k=left.threshold_4k_db_hl if left else None)
    return result or {"available": False,
                      "note": "Needs an identifiable Wave V in both ears."}


@router.post("/aep/mlr")
def mlr(req: MLRRequest):
    """One MLR run, with the abnormal patterns it matches."""
    return aep.analyze_mlr(
        peaks=req.peaks, amplitudes=req.amplitudes, ear=req.ear,
        opposite_amplitudes=req.opposite_amplitudes or None,
        sedated=req.sedated)


@router.post("/aep/llr")
def llr(req: LLRRequest):
    """One LLR run, including the P1 cortical-maturation check."""
    return aep.analyze_llr(peaks=req.peaks, amplitudes=req.amplitudes,
                           age_months=req.age_months, ear=req.ear)


@router.post("/aep/battery")
def battery(req: BatteryRequest):
    """All three together — which level of the pathway the problem sits at."""
    return aep.aep_battery(
        abr=_run_abr(req.abr),
        abr_other_ear=_run_abr(req.abr_other_ear),
        mlr=aep.analyze_mlr(
            peaks=req.mlr.peaks, amplitudes=req.mlr.amplitudes,
            ear=req.mlr.ear, sedated=req.mlr.sedated) if req.mlr else None,
        llr=aep.analyze_llr(
            peaks=req.llr.peaks, amplitudes=req.llr.amplitudes,
            age_months=req.llr.age_months, ear=req.llr.ear) if req.llr else None,
    )


@router.get("/boa/reference")
def boa_reference():
    """Age bands, response repertoire and the limits of the technique."""
    return boa.boa_reference()


@router.post("/boa/analyze")
def boa_analyze(req: BOARequest):
    """One BOA observation against the age-appropriate response level."""
    return boa.analyze_boa(
        age_months=req.age_months,
        observed_level_db_spl=req.observed_level_db_spl,
        responses=req.responses, observers=req.observers,
        presentations=req.presentations)
