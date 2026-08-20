"""Tuning fork tests: Rinne, Weber, Bing, ABC/Schwabach and Gelle."""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.clinical import tuning_fork as TF
from app.models.schemas import EarData

router = APIRouter(prefix="/api/tuning-fork")


class RinneEar(BaseModel):
    """One ear's Rinne, keyed by nominal audiometric frequency."""

    #: e.g. {"500": "bc_louder"} — see TF.RINNE_RESPONSES for the vocabulary.
    responses: Dict[int, str] = Field(default_factory=dict)
    #: Whether the NON-test ear was masked. A negative Rinne obtained without
    #: masking cannot be distinguished from transcranial crossover.
    masked: bool = False
    #: clear | obstructed | not_performed. An occluded canal produces a genuine
    #: conductive pattern from a trivial cause.
    otoscopy: str = "not_performed"


class BingEar(BaseModel):
    response: Optional[str] = None          # louder | no_change
    freq: int = 250
    seal_demonstrated: bool = True


class ReserveEar(BaseModel):
    abc: Optional[str] = None               # reduced | normal
    schwabach: Optional[str] = None         # shortened | normal | prolonged
    examiner_normal_hearing: bool = False


class GelleEar(BaseModel):
    response: Optional[str] = None          # quieter | no_change
    freq: int = 500
    vertigo: bool = False
    drum_intact: bool = True


class BatteryRequest(BaseModel):
    right: RinneEar = Field(default_factory=RinneEar)
    left: RinneEar = Field(default_factory=RinneEar)

    #: right | left | midline | none
    weber: Optional[str] = None
    weber_freq: int = 500
    weber_site: str = "glabella_forehead"
    quiet_room: bool = True

    bing: Dict[str, BingEar] = Field(default_factory=dict)
    reserve: Dict[str, ReserveEar] = Field(default_factory=dict)
    gelle: Dict[str, GelleEar] = Field(default_factory=dict)

    #: The patient's own report of the worse ear, recorded BEFORE testing.
    worse_ear_reported: Optional[str] = None

    #: Optional thresholds. When present the audiogram judges the forks.
    right_thresholds: Optional[EarData] = None
    left_thresholds: Optional[EarData] = None


@router.get("/reference")
def reference():
    """The forks, the vocabulary and the criteria, so the UI can state them."""
    return TF.reference()


@router.post("/analyze")
def analyze(req: BatteryRequest):
    """The whole battery, reconciled — and checked against the audiogram."""
    right = TF.analyze_rinne("right", req.right.responses,
                             masked=req.right.masked,
                             otoscopy=req.right.otoscopy) if req.right.responses else None
    left = TF.analyze_rinne("left", req.left.responses,
                            masked=req.left.masked,
                            otoscopy=req.left.otoscopy) if req.left.responses else None

    weber = TF.analyze_weber(req.weber, freq=req.weber_freq,
                             site=req.weber_site, quiet_room=req.quiet_room,
                             worse_ear_reported=req.worse_ear_reported) \
        if req.weber else None

    bing = {e: TF.analyze_bing(e, b.response, freq=b.freq,
                               seal_demonstrated=b.seal_demonstrated)
            for e, b in req.bing.items() if b.response}
    reserve = {e: TF.analyze_bone_reference(
        e, abc=r.abc, schwabach=r.schwabach,
        examiner_normal_hearing=r.examiner_normal_hearing)
        for e, r in req.reserve.items() if r.abc or r.schwabach}
    gelle = {e: TF.analyze_gelle(e, g.response, freq=g.freq, vertigo=g.vertigo,
                                 drum_intact=g.drum_intact)
             for e, g in req.gelle.items() if g.response or g.vertigo}

    battery = TF.tuning_fork_battery(
        right_rinne=right, left_rinne=left, weber=weber,
        right_reserve=reserve.get("right"), left_reserve=reserve.get("left"),
        bing=bing, gelle=gelle, worse_ear_reported=req.worse_ear_reported,
        right_ac=req.right_thresholds.ac if req.right_thresholds else None,
        right_bc=req.right_thresholds.bc if req.right_thresholds else None,
        left_ac=req.left_thresholds.ac if req.left_thresholds else None,
        left_bc=req.left_thresholds.bc if req.left_thresholds else None,
    )

    return {"rinne": {"right": right, "left": left}, "weber": weber,
            "bing": bing or None, "reserve": reserve or None,
            "gelle": gelle or None, **battery}
