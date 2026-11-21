"""MODULE 3 endpoints: audiogram photo, or a whole scanned report.

Two entry points, because they are two different documents and conflating
them loses information either way:

``/api/digitize``        a photograph OF A CHART. The audiogram fills the
                         frame; the job is symbols to numbers.
``/api/digitize/report`` a REPORT PAGE — letterhead, patient details, the
                         chart somewhere in the middle, and the printed
                         results and impression underneath. The chart is
                         located on the page and digitized, and the printed
                         fields are read or handed back as crops to confirm.

The chart endpoint is untouched by the report one: a clinician who has a
photo of a chart should not have to go through page-layout analysis to read
it, and the chart path is the one with a ground-truth regression test behind
it.
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services import report_scan, vision

router = APIRouter(prefix="/api")

#: Same ceiling as the otoscopy upload. A phone photo of an A4 page at full
#: resolution is a few megabytes; 12 MB is generous and bounded.
MAX_BYTES = 12 * 1024 * 1024


@router.post("/digitize")
async def digitize(file: UploadFile = File(...)):
    image_bytes = await file.read()
    result = vision.digitize(image_bytes)
    result["human_in_the_loop"] = (
        "Extracted values are suggestions — confirm/edit them in the entry "
        "grid before analysis."
    )
    return result


@router.post("/digitize/report")
async def digitize_report(file: UploadFile = File(...)):
    """Read a scanned audiometry report: the audiogram and the printed fields.

    See ``app.services.report_scan`` for the three reading paths and why a
    field that could not be read comes back absent rather than blank.
    """
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, "empty upload")
    if len(image_bytes) > MAX_BYTES:
        raise HTTPException(
            413, f"file larger than {MAX_BYTES // (1024 * 1024)} MB")
    result = report_scan.scan(image_bytes)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "could not read that page"))
    return result


@router.get("/digitize/report/capability")
def report_capability():
    """What this instance can read off a report page, before one is uploaded.

    The UI asks first so it can set expectations honestly: with no OCR and no
    vision provider the printed fields have to be typed, and saying so up
    front is better than letting a clinician upload a page and find out.
    """
    from app.services.ai_config import PROVIDERS, get_config
    from app.services import llm_provider

    ocr, why = report_scan.ocr_available()
    cfg = get_config()
    llm = (llm_provider.ai_enabled()
           and PROVIDERS[cfg.provider]["supports_vision"])
    return {
        "chart": True,
        "ocr": ocr,
        "ocr_note": why,
        "llm_vision": llm,
        "llm_provider": cfg.provider if llm else None,
        "fields_automatic": bool(ocr or llm),
        "note": (
            "The audiogram is read from its symbols offline, with no key and "
            "no network." + (
                " The printed fields are read automatically as well."
                if (ocr or llm) else
                " The printed fields are shown as crops of the page for you to "
                "confirm — nothing is guessed from them.")),
    }
