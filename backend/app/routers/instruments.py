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
    admittance: float


class TympanometryRequest(BaseModel):
    ear: str = "right"
    probe_hz: int = 226
    age_years: Optional[float] = None
    #: Full pressure sweep. When absent, the summary values below are used
    #: and the curve is modelled from them.
    trace: List[TracePoint] = Field(default_factory=list)
    peak_pressure: Optional[float] = None
    compliance: Optional[float] = None
    ecv: Optional[float] = None
    reflexes: Dict[str, Optional[float]] = Field(default_factory=dict)
    pta: Optional[float] = None


class OAERequest(BaseModel):
    ear: str = "right"
    kind: str = "dpoae"
    protocol: str = "screening"
    points: List[OAEPoint] = Field(default_factory=list)
    #: Air-conduction thresholds, so absent emissions above the OAE ceiling
    #: can be marked uninformative instead of counted as damage.
    ac: Dict[int, Optional[float]] = Field(default_factory=dict)


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
            "peak scores high; a rounded one scores low. Normal > 0.2."),
        "infant_note": (
            f"Below {tympanometry.INFANT_MONTHS} months a 226 Hz probe can look "
            "normal over a middle ear full of fluid. Use a 1000 Hz probe."),
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
    )


@router.get("/oae/reference")
def oae_reference():
    """Test frequencies, protocols and the cochlear map behind the plot."""
    return {
        "frequencies": dpoae.DP_FREQS,
        "protocols": [{"key": k, **v} for k, v in dpoae.PROTOCOLS.items()],
        "cochlear_regions": dpoae.COCHLEAR_REGION,
        "noise_floor_ceiling": dpoae.NOISE_FLOOR_CEILING_DB,
        "ceiling_db_hl": dpoae.OAE_CEILING_DB_HL,
        "note": ("Emissions disappear above about "
                 f"{dpoae.OAE_CEILING_DB_HL:g} dB HL, so their absence at a "
                 "worse threshold carries no extra information."),
    }


@router.post("/oae/analyze")
def oae_analyze(req: OAERequest):
    """DP-gram, pass/refer against the chosen protocol, and cochlear profile."""
    return dpoae.analyze(
        ear=req.ear,
        points=[p.model_dump() for p in req.points],
        protocol=req.protocol,
        ac_numeric={int(k): v for k, v in (req.ac or {}).items()},
        kind=req.kind,
    )
