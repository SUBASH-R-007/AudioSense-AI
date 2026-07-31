"""MODULE 3 endpoint: audiogram photo -> extracted thresholds."""
from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.services import vision

router = APIRouter(prefix="/api")


@router.post("/digitize")
async def digitize(file: UploadFile = File(...)):
    image_bytes = await file.read()
    result = vision.digitize(image_bytes)
    result["human_in_the_loop"] = (
        "Extracted values are suggestions — confirm/edit them in the entry "
        "grid before analysis."
    )
    return result
