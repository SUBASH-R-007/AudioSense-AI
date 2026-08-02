"""Evoked potentials and behavioural observation: ABR, MLR, LLR and BOA.

All four run standalone. An ABR on a sleeping newborn, an MLR in a central
processing workup, a P1 latency at a cochlear-implant review, a BOA screen in
a well-baby clinic — none of them arrive with a pure-tone audiogram attached.
"""
from __future__ import annotations

from typing import Dict, List, Optional

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


class ABRSeriesRequest(BaseModel):
    ear: str = "right"
    #: The intensity ladder actually run: [{"intensity": dB nHL, "wave_v": ms}]
    series: List[Dict[str, Optional[float]]] = Field(default_factory=list)


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
    mlr: Optional[MLRRequest] = None
    llr: Optional[LLRRequest] = None


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
            "cm_window_ms": list(aep.CM_WINDOW_MS),
            "norms": [
                {"intensity_db_nhl": level, "psp_db": row["psp"],
                 "waves": {w: {"mean": m, "sd": s, "n": n}
                           for w, (m, s, n) in row["waves"].items()},
                 "interwave": {p: {"mean": m, "sd": s, "n": n}
                               for p, (m, s, n) in row["interwave"].items()}}
                for level, row in sorted(aep.ABR_NORMS.items(), reverse=True)
            ],
            "note": ("Normative means and one standard deviation by stimulus "
                     "intensity. Latency is level-dependent, so a recording is "
                     "only ever compared against its own row."),
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
            "p1_maturation": [
                {"low_months": lo, "high_months": hi, "typical_ms": ms, "band": label}
                for lo, hi, ms, label in aep.LLR_P1_MATURATION
            ],
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
    """One ABR run against the normative row for the intensity used."""
    return aep.analyze_abr(
        waves=req.waves, intensity=req.intensity_db_nhl, ear=req.ear,
        insert_earphones=req.insert_earphones,
        latencies_include_delay=req.latencies_include_delay,
        cm_present=req.cm_present,
    )


@router.post("/aep/abr/threshold")
def abr_threshold(req: ABRSeriesRequest):
    """Estimated threshold from the lowest level with an identifiable Wave V."""
    result = aep.abr_threshold(req.series)
    return result or {"rows": [], "estimated_threshold": None,
                      "message": "No intensity ladder recorded."}


@router.post("/aep/abr/asymmetry")
def abr_asymmetry(payload: Dict[str, ABRRequest]):
    """Interaural Wave V difference between two recorded runs."""
    def run(key: str):
        req = payload.get(key)
        if not req:
            return None
        return aep.analyze_abr(
            waves=req.waves, intensity=req.intensity_db_nhl, ear=key,
            insert_earphones=req.insert_earphones,
            latencies_include_delay=req.latencies_include_delay)

    result = aep.abr_asymmetry(run("right"), run("left"))
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
        abr=aep.analyze_abr(
            waves=req.abr.waves, intensity=req.abr.intensity_db_nhl,
            ear=req.abr.ear, insert_earphones=req.abr.insert_earphones,
            latencies_include_delay=req.abr.latencies_include_delay,
            cm_present=req.abr.cm_present) if req.abr else None,
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
