"""The anatomy animation that explains one ear to its owner."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.clinical import anatomy_video as A

router = APIRouter(prefix="/api/anatomy")


class VideoRequest(BaseModel):
    """One ear's worth of evidence. Every field optional, as elsewhere.

    ``otoscopy`` is the whole stored response rather than a bare label, because
    the selection has to read the ``side`` it was filed under before it may act
    on it.
    """

    #: The response from POST /api/analyze.
    analysis: Optional[dict] = None
    #: The response from POST /api/otoscopy/analyze, if an image was taken.
    otoscopy: Optional[dict] = None
    #: Which ear to explain.
    side: str = Field(default="right")


@router.get("/reference")
def reference():
    """The whole clip set and the rules that pick between them.

    Published for the same reason every other reference route in this app is:
    an interface that shows a patient a picture of their ear should be able to
    state, on the same screen, why that picture and not another one.
    """
    return {
        "videos": A.catalogue(),
        "journey": A.JOURNEY,
        "note": A.ILLUSTRATION_NOTE,
        "selection": [
            "A flat (Type B) tympanogram is read through the ear-canal volume: "
            "large means a perforation, small means wax against the probe, "
            "normal means fluid behind an intact drum.",
            "Otoscopy is used only when the image was filed under the same ear.",
            "Type As is a stiff chain; Type Ad, Add and E are a chain that is "
            "too free or disconnected; Type D is a lax or scarred drum; "
            "Type C is a retracted drum.",
            "With no mechanism named, the audiogram type alone is used.",
            "A mixed loss keeps its middle-ear clip and flags the cochlear "
            "component separately.",
        ],
    }


@router.post("/video")
def video(req: VideoRequest):
    """Pick the clip for one ear, with the findings that chose it."""
    return A.select(req.analysis, req.side, req.otoscopy)
