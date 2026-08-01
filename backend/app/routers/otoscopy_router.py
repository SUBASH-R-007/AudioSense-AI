"""Otoscopy endpoints: read an image, compare it against the reference set."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.otoscopy import features as F
from app.otoscopy import model as M
from app.otoscopy.taxonomy import CATEGORY, CLASSES, TAXONOMY, URGENCY

router = APIRouter(prefix="/api/otoscopy")

#: Refuse anything larger before it reaches OpenCV.
MAX_BYTES = 12 * 1024 * 1024


@router.get("/reference")
def reference_atlas():
    """The labelled reference patterns, with counts and example images.

    This is the atlas the clinician compares against, and the exact material
    the classifier was trained on — showing both from one endpoint keeps the
    two from drifting apart.
    """
    found, _ = M.scan_directory(M.REFERENCE_DIR)
    classes = []
    for label in CLASSES:
        paths = found.get(label, [])
        classes.append({
            "label": label,
            **TAXONOMY[label],
            "category": CATEGORY[label],
            "urgency": URGENCY[label],
            "count": len(paths),
            "images": [M.reference_url(str(p.relative_to(M.DATA_DIR)))
                       for p in paths[:8]],
        })
    return {
        "classes": classes,
        "total_images": sum(len(v) for v in found.values()),
        "source": ("Labelled views extracted from the clinical reference document "
                   "'Otoscopic evaluation', split panel by panel."),
        "kaggle_present": M.KAGGLE_DIR.exists(),
    }


@router.get("/model")
def model_info():
    """Model card — provenance and measured accuracy, stated plainly."""
    card = M.model_card()
    return {
        "trained": M.model_available(),
        **card,
        "limits": [
            "Trained on a small labelled reference set, so it offers a ranked "
            "differential rather than a diagnosis.",
            "Accuracy is reported leave-one-image-out; no augmented copy of a "
            "test image was ever in its own training fold.",
            "Retraction has too few reference views to be learned at all and "
            "the model does not currently detect it.",
            "A photograph cannot exclude disease behind wax, blood or a "
            "partially visible membrane.",
        ],
        "improve": ("Add the public otoscope dataset — see "
                    "scripts/fetch_otoscope_dataset.py — then re-run "
                    "python -m scripts.train_otoscopy. Nothing else changes."),
    }


@router.get("/image/{label}/{filename}")
def reference_image(label: str, filename: str):
    """Serve one reference view so the UI can show it beside the patient's."""
    if label not in TAXONOMY:
        raise HTTPException(404, "unknown pattern")
    root = (M.REFERENCE_DIR / label).resolve()
    path = (root / filename).resolve()
    # Reject anything that escapes the reference directory.
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "not found")
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media)


@router.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    side: str = Form("right"),
    analysis: Optional[str] = Form(None),
):
    """Read one tympanic-membrane image.

    ``analysis`` is an optional JSON body from /api/analyze. When supplied,
    the response also says whether the picture and the test battery agree —
    which is the finding that does not depend on the classifier being right.
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"image larger than {MAX_BYTES // (1024 * 1024)} MB")

    image = F.decode(data)
    if image is None:
        raise HTTPException(400, "could not decode that file as an image")

    if not M.model_available():
        raise HTTPException(
            503,
            "otoscopy model not trained — run: python -m scripts.train_otoscopy")

    result = M.predict(image)

    battery = None
    if analysis:
        try:
            battery = json.loads(analysis)
        except json.JSONDecodeError:
            battery = None
    result["concordance"] = M.concordance(
        result, battery, side if side in ("right", "left") else "right")
    result["side"] = side
    result["filename"] = file.filename
    return result
