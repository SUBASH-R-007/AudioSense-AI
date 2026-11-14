"""Tympanometry and OAE as standalone instruments.

These endpoints exist alongside /api/analyze rather than inside it. A clinic
often runs immittance or emissions on their own — a newborn screen, a
post-grommet check, an occupational monitoring visit — with no pure-tone
audiogram to attach them to. Requiring a full test record to interpret a
tympanogram would make the tool useless in exactly those settings.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.clinical import dpoae, tympanometry
from app.models.schemas import OAEPoint

router = APIRouter(prefix="/api")


class TracePoint(BaseModel):
    pressure: float
    #: None where the trace left the instrument's range. A Type Add sweep has
    #: no reading at its centre, and rejecting the point would make the one
    #: type defined by that gap impossible to submit.
    admittance: Optional[float] = None
    off_scale: bool = False


class TympanometryRequest(BaseModel):
    ear: str = "right"
    probe_hz: int = 226
    age_years: Optional[float] = None
    #: Full pressure sweep. When absent, the summary values below are used
    #: and the curve is modelled from them.
    trace: List[TracePoint] = Field(default_factory=list)
    #: The four values a tympanometer prints, for manual entry when the sweep
    #: itself was not exported: peak pressure (daPa), static compliance (mmho),
    #: ear-canal volume (ml) and gradient.
    peak_pressure: Optional[float] = None
    compliance: Optional[float] = None
    ecv: Optional[float] = None
    gradient: Optional[float] = Field(default=None, ge=0, le=1)
    reflexes: Dict[str, Optional[float]] = Field(default_factory=dict)
    pta: Optional[float] = None
    #: A tympanogram type recorded straight off a printout, used when neither
    #: a sweep nor the summary values are available. See
    #: ``tympanometry.analyze`` for what the type alone can and cannot give.
    recorded_type: Optional[str] = None


class OAERequest(BaseModel):
    ear: str = "right"
    kind: str = "dpoae"
    protocol: str = "screening"
    points: List[OAEPoint] = Field(default_factory=list)
    #: Air-conduction thresholds, so absent emissions above the OAE ceiling
    #: can be marked uninformative instead of counted as damage.
    ac: Dict[int, Optional[float]] = Field(default_factory=dict)
    #: How many of the tested frequencies must pass. Honoured only for the
    #: ``custom`` protocol — a published protocol's pass count is part of its
    #: criterion, and overriding it would put a standard's name on a decision
    #: it did not make (see ``dpoae.resolve_protocol``).
    required: Optional[int] = Field(default=None, ge=0, le=32)
    #: Outcome-only entry: the one word a screening instrument prints, used
    #: when no per-frequency points were recorded.
    recorded_outcome: Optional[str] = None
    outcome_note: str = Field(default="", max_length=500)
    #: Which frequencies an outcome-only screen covered, where known.
    freqs: List[int] = Field(default_factory=list)


@router.get("/tympanometry/reference")
def tympanometry_reference(age_years: Optional[float] = None):
    """All eight types with plotted curves, normal ranges and the criteria table.

    The curves are generated from the numeric criteria rather than reproduced
    from the reference document's figures, which come from several sources and
    disagree on axes, scales and even units. One consistent set on one pair of
    axes, each traceable to the row that produced it.
    """
    from app.clinical.immittance import REFLEX_SL_NORMAL

    reference = tympanometry.reference_curves(age_years)
    return {
        "sweep": list(tympanometry.SWEEP),
        "adult": tympanometry.normative(30),
        "child": tympanometry.normative(5),
        "reflex_sl_normal": list(REFLEX_SL_NORMAL),
        "types": [
            {"type": key, "label": entry["label"], "shape": entry["shape"],
             "detail": ", ".join(entry["disorders"]) + ".",
             "disorders": entry["disorders"],
             "suggests_conductive": entry["suggests_conductive"]}
            for key, entry in tympanometry.TYMPANOGRAM_TYPES.items()
        ],
        "curves": reference["curves"],
        "type_b_by_volume": [
            {"band": band, **entry}
            for band, entry in tympanometry.TYPE_B_BY_VOLUME.items()
        ],
        "criteria": {
            "pressure": list(tympanometry.PRESSURE_NORMAL),
            "compliance_adult": list(tympanometry.COMPLIANCE_NORMAL_ADULT),
            "compliance_child": list(tympanometry.COMPLIANCE_NORMAL_CHILD),
            "ecv_adult": list(tympanometry.ECV_NORMAL_ADULT),
            "ecv_child": list(tympanometry.ECV_NORMAL_CHILD),
            "gradient_min": tympanometry.GRADIENT_NORMAL_MIN,
            "flat_max": tympanometry.FLAT_ADMITTANCE_MAX,
            "off_scale": tympanometry.OFF_SCALE_ADMITTANCE,
        },
        "citations": list(tympanometry.CITATIONS),
        "gradient_formula": (
            "GR = (Ytm − Y±50) ÷ Ytm, where Ytm is the compensated peak "
            "admittance and Y±50 the mean 50 daPa either side of it. A sharp "
            "peak scores high; a rounded one scores low. "
            f"{tympanometry.GRADIENT_NORMAL_MIN:g} is used as a heuristic "
            "cut-off, not a published norm."),
        "gradient_basis": tympanometry.GRADIENT_BASIS,
        "infant_note": (
            f"Below {tympanometry.INFANT_MONTHS} months a 226 Hz probe can look "
            "normal over a middle ear full of fluid. Use a 1000 Hz probe."),
        "high_frequency": {
            "types": [{"type": key, **entry}
                      for key, entry in tympanometry.HIGH_FREQUENCY_TYPES.items()],
            "newborn_admittance_p5": tympanometry.HF_NEWBORN_ADMITTANCE_P5,
            "newborn_admittance_p95": tympanometry.HF_NEWBORN_ADMITTANCE_P95,
            "sweep_dapa": [tympanometry.HF_SWEEP_MIN_DAPA,
                           tympanometry.HF_SWEEP_MAX_DAPA],
            "citations": list(tympanometry.HIGH_FREQUENCY_CITATIONS),
        },
        "off_scale_climb_allowance": tympanometry.OFF_SCALE_CLIMB_ALLOWANCE,
    }


@router.post("/tympanometry/analyze")
def tympanometry_analyze(req: TympanometryRequest):
    """Type, curve, tympanometric width and reflexes for one ear."""
    return tympanometry.analyze(
        ear=req.ear,
        trace=[p.model_dump() for p in req.trace],
        peak_pressure=req.peak_pressure,
        compliance=req.compliance,
        ecv=req.ecv,
        reflexes=req.reflexes,
        pta=req.pta,
        age_years=req.age_years,
        probe_hz=req.probe_hz,
        gradient=req.gradient,
        recorded_type=req.recorded_type,
    )


@router.get("/oae/reference")
def oae_reference():
    """Test frequencies, protocols and the cochlear map behind the plot."""
    return {
        "frequencies": dpoae.DP_FREQS,
        "protocols": [{"key": k, **v} for k, v in dpoae.PROTOCOLS.items()],
        "cochlear_regions": dpoae.COCHLEAR_REGION,
        #: Frequencies a clinic may reasonably add to the standard set. The
        #: set is not a limit — any frequency gets a cochlear place from the
        #: Greenwood map — these are just the ones worth offering as chips.
        "extra_frequencies": [500, 750, 1250, 5000, 7000, 10000, 12000],
        "custom_protocols": sorted(dpoae.CUSTOM_PROTOCOLS),
        "outcomes": sorted(set(dpoae.OUTCOME_ALIASES.values())),
        "noise_floor_ceiling": dpoae.NOISE_FLOOR_CEILING_DB,
        "ceiling_db_hl": dpoae.OAE_CEILING_DB_HL,
        "note": ("Emissions disappear above about "
                 f"{dpoae.OAE_CEILING_DB_HL:g} dB HL, so their absence at a "
                 "worse threshold carries no extra information."),
    }


@router.post("/oae/analyze")
def oae_analyze(req: OAERequest):
    """DP-gram, pass/refer against the chosen protocol, and cochlear profile.

    Two entry modes. With ``points``, the full gram: per-frequency verdicts,
    the cochlear place of each dropout and the comparison against the
    audiogram. With ``recorded_outcome`` alone, the screening decision as the
    instrument printed it — recorded faithfully, and explicitly not carrying
    the per-frequency inferences it cannot support.
    """
    return dpoae.analyze(
        ear=req.ear,
        points=[p.model_dump() for p in req.points],
        protocol=req.protocol,
        ac_numeric={int(k): v for k, v in (req.ac or {}).items()},
        kind=req.kind,
        required=req.required,
        recorded_outcome=req.recorded_outcome,
        outcome_note=req.outcome_note,
        freqs=req.freqs,
    )
