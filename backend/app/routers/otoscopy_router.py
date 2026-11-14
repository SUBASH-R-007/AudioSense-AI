"""Otoscopy endpoints: read an image, compare it against the reference set."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.otoscopy import features as F
from app.otoscopy import model as M
from app.otoscopy.taxonomy import CATEGORY, CLASSES, TAXONOMY, URGENCY
from app.services.state_paths import state_dir

router = APIRouter(prefix="/api/otoscopy")

#: Refuse anything larger before it reaches OpenCV.
MAX_BYTES = 12 * 1024 * 1024

#: Clinician overrides, appended one JSON object per line. Kept separate from
#: data/feedback.jsonl, which holds audiogram-pattern corrections: that file's
#: statistics map every label through the audiogram classifier's PATTERN_LABELS,
#: so an otoscopic class written into it would be counted as an audiogram
#: configuration and quietly corrupt both tallies.
CORRECTIONS_FILE = "otoscopy_corrections.jsonl"


def corrections_path() -> Path:
    """Resolved at call time, not import — see ``state_paths`` for why.

    A constant here would freeze whatever AUDIOSENSE_STATE_DIR happened to be
    when this module was first imported, which is the bug that module's
    docstring exists to warn about.
    """
    return state_dir() / CORRECTIONS_FILE


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
    validation = card.get("validation") or {}
    grouped = validation.get("protocol") == "source_photograph"
    limits = [
        "Trained on a small labelled reference set, so it offers the closest "
        "reference pattern rather than a diagnosis.",
        ("Accuracy is reported holding out every view cut from the same source "
         "photograph (" + f"{card.get('n_images', '?')} views from "
         f"{card.get('n_source_photographs', '?')} pictures); the view-level "
         "figure is kept only as validation_optimistic."
         if grouped else
         "No accuracy measured with whole source photographs held out is "
         "available for this model; any view-level figure is optimistic."),
    ]
    # The per-class failures on unseen photographs (marginal, attic and
    # central perforation, retraction, mass) are named in the card's own
    # reliability note, measured rather than restated here.
    if card.get("reliability_note"):
        limits.append(card["reliability_note"])
    limits.append("A photograph cannot exclude disease behind wax, blood or a "
                  "partially visible membrane.")
    return {
        "trained": M.model_available(),
        **card,
        "limits": limits,
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
    media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".webp": "image/webp", ".gif": "image/gif"}.get(path.suffix.lower())
    if media is None:
        raise HTTPException(404, "not found")
    # The atlas page loads these with crossOrigin and also fetches them for
    # the guided tour. Starlette's CORS middleware adds "Vary: Origin" only
    # when the request carries an Origin, so a copy cached from a plain
    # <img> load could otherwise be served to a later CORS request without
    # its CORS headers; Vary and revalidation keep the two apart.
    return FileResponse(path, media_type=media,
                        headers={"Vary": "Origin", "Cache-Control": "no-cache"})


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


class CorrectionRequest(BaseModel):
    """A clinician replacing the model's pattern with what they actually saw."""

    #: The result returned by /analyze, passed back whole. Sending the result
    #: rather than re-uploading the image means the correction costs no second
    #: decode and the measurements, image quality and reference matches are
    #: preserved exactly as they were computed.
    result: dict
    corrected: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=1000)
    clinician: str = Field(default="", max_length=128)
    #: Optional /api/analyze payload, so the cross-check against the audiogram
    #: and tympanogram is recomputed against the corrected pattern in the same
    #: round trip.
    analysis: Optional[dict] = None


@router.post("/correct")
def correct_prediction(req: CorrectionRequest):
    """Override the predicted pattern, and re-derive everything from it.

    The response is the same shape as /analyze, so the client swaps it in
    whole and every panel — clinical consequence, concordance, the disease
    differential drawn from the image — follows the clinician's reading
    instead of the model's. See ``model.apply_correction`` for why the
    override has to reach that far rather than just relabelling the heading.

    The override is also appended to ``otoscopy_corrections.jsonl``: an
    expert label on a real photograph is the scarcest thing this model lacks,
    and the measured 27% top-1 means most uploads should produce one.
    """
    if req.corrected not in TAXONOMY:
        raise HTTPException(
            422, f"unknown otoscopic pattern '{req.corrected}' — expected one "
                 f"of: {', '.join(CLASSES)}")
    if not (req.result or {}).get("prediction"):
        raise HTTPException(422, "result is not an otoscopy analysis response")

    try:
        corrected = M.apply_correction(req.result, req.corrected, note=req.note)
    except ValueError as exc:  # pragma: no cover — guarded above
        raise HTTPException(422, str(exc)) from exc

    side = req.result.get("side")
    side = side if side in ("right", "left") else "right"
    corrected["concordance"] = M.concordance(corrected, req.analysis, side)
    corrected["side"] = side
    corrected["filename"] = req.result.get("filename")

    # Logged after the correction is built, so a malformed request never
    # reaches the training record. A write failure must not lose the
    # clinician's correction from the screen, so it is reported in the
    # response rather than raised.
    stored, store_error = True, None
    try:
        path = corrections_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "recorded": datetime.now(timezone.utc).isoformat(),
            "side": side,
            "filename": req.result.get("filename"),
            "model_label": (req.result.get("prediction") or {}).get("label"),
            "model_confidence": (req.result.get("prediction") or {}).get("confidence"),
            "model_certainty": (req.result.get("prediction") or {}).get("certainty"),
            "corrected": req.corrected,
            "agreed_with_model": corrected["correction"]["agreed_with_model"],
            "note": req.note,
            "clinician": req.clinician,
            # The descriptors the classifier actually saw. With these, a
            # correction is retrainable without keeping the photograph — which
            # matters, because the photograph is patient data and the feature
            # vector is not.
            "measurements": req.result.get("measurements") or {},
            "quality": (req.result.get("quality") or {}).get("usable"),
            "model_fingerprint": ((req.result.get("model") or {})
                                  .get("training_fingerprint")),
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        stored, store_error = False, str(exc)

    corrected["correction"]["stored"] = stored
    if store_error:
        corrected["correction"]["store_error"] = (
            "The correction is applied here but could not be saved for "
            f"retraining: {store_error}")
    return corrected


@router.get("/corrections")
def correction_stats():
    """How often the classifier is overridden — the honest accuracy signal.

    The model card's 27% comes from 62 views of 22 reference pictures. This
    counts real uploads corrected by real clinicians, which is the figure that
    will eventually replace it.
    """
    entries = []
    path = corrections_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    agreed = sum(1 for e in entries if e.get("agreed_with_model"))
    by_label: dict = {}
    for e in entries:
        key = e.get("corrected", "unknown")
        by_label[key] = by_label.get(key, 0) + 1
    return {
        "total": len(entries),
        "confirmed": agreed,
        "overridden": len(entries) - agreed,
        # Only meaningful once there are enough of them to mean anything; a
        # percentage over three cases invites exactly the overclaiming the
        # rest of this app avoids.
        "model_agreement_pct": (round(100 * agreed / len(entries), 1)
                                if len(entries) >= 20 else None),
        "by_corrected_pattern": {
            TAXONOMY.get(k, {}).get("name", k): v
            for k, v in sorted(by_label.items())
        },
        "note": ("Clinician-confirmed patterns on real uploads, appended to "
                 "otoscopy_corrections.jsonl. An agreement rate is withheld "
                 "until there are at least 20 of them."),
    }
