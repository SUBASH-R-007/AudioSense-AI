"""Validation, bulk photo ingestion and bulk report export."""
from __future__ import annotations

import io
import time
import zipfile
from typing import List

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.clinical import rules
from app.clinical.safety import safety_review
from app.clinical.triage import sort_worklist, triage_case, worklist_summary
from app.ml import classifier
from app.models.schemas import EarData
from app.services import vision
from app.services.validation import validate_csv

router = APIRouter(prefix="/api")


@router.post("/validate")
async def validate(file: UploadFile = File(...)):
    """Measure agreement against expert-labelled audiograms."""
    raw = await file.read()
    try:
        return validate_csv(raw)
    except Exception as exc:
        raise HTTPException(400, f"could not process the labelled CSV: {exc}")


@router.post("/batch-photos")
async def batch_photos(files: List[UploadFile] = File(...)):
    """Digitize and interpret a stack of paper audiograms in one pass.

    The realistic bottleneck in an Indian ENT department is not the
    interpretation — it is that the audiograms are on paper in a folder.
    This turns the folder into a triaged worklist.
    """
    started = time.perf_counter()
    cases, failures = [], []

    for f in files:
        image = await f.read()
        extracted = vision.digitize(image)
        if not extracted.get("ok"):
            failures.append({"file": f.filename, "error": extracted.get("error")})
            continue

        right = extracted["right"]
        left = extracted["left"]
        rr = rules.analyze_test(right["ac"], right["bc"], left["ac"], left["bc"])
        ml = {"right": None, "left": None}
        try:
            ml = {
                "right": classifier.classify_ear(right["ac"], right["bc"], explain=False),
                "left": classifier.classify_ear(left["ac"], left["bc"], explain=False),
            }
        except FileNotFoundError:
            pass

        safety = safety_review(
            EarData(ac=right["ac"], bc=right["bc"]),
            EarData(ac=left["ac"], bc=left["bc"]),
        )
        triage = triage_case({"safety": safety, "rules": rr, "ml": ml, "battery": {}})

        def summarize(side):
            ear, m = rr[side], ml[side]
            return {
                "pta": (ear.get("ac_pta") or {}).get("value"),
                "grade": (ear.get("who_grade") or {}).get("grade"),
                "type": ear.get("type"),
                "provisional": ear.get("provisional"),
                "pattern": m.get("pattern_label") if m else None,
                "confidence": m.get("confidence") if m else None,
                "ood": m.get("ood") if m else None,
            }

        disability = rr.get("disability") or {}
        cases.append({
            "file": f.filename,
            "name": f.filename.rsplit(".", 1)[0],
            "age": "", "occupation": "",
            "method": extracted.get("method"),
            "warnings": extracted.get("warnings", []),
            "thresholds": {"right": right, "left": left},
            "right": summarize("right"),
            "left": summarize("left"),
            "binaural_disability_pct": disability.get("binaural_pct"),
            "benchmark_disability": disability.get("benchmark_disability"),
            "urgent": safety["has_urgent"],
            "alerts": [a["title"] for a in safety["alerts"]
                       if a["level"] in ("emergency", "urgent")],
            "triage": triage,
        })

    total_s = time.perf_counter() - started
    return {
        "count": len(cases),
        "failed": failures,
        "results": sort_worklist(cases),
        "worklist": worklist_summary(cases) if cases else {"total": 0},
        "performance": {
            "photos": len(files),
            "digitized": len(cases),
            "total_seconds": round(total_s, 2),
            "seconds_per_photo": round(total_s / len(files), 2) if files else None,
        },
        "human_in_the_loop": (
            "Extracted thresholds are suggestions. Open any case to confirm the "
            "values before issuing an interpretation."
        ),
    }


@router.post("/bulk-reports")
def bulk_reports(payload: dict = Body(...)):
    """Every case in a batch as one ZIP of PDF reports."""
    from app.services.pdf import build_pdf
    from app.services.report import generate_offline

    cases = payload.get("cases") or []
    if not cases:
        raise HTTPException(400, "no cases supplied")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, case in enumerate(cases, start=1):
            analysis = case.get("analysis") or {}
            patient = analysis.get("patient") or {"name": case.get("name", f"case_{i}")}
            bundle = generate_offline(analysis)
            pdf_bytes = build_pdf({
                "patient": patient, "analysis": analysis, "report_bundle": bundle,
            })
            safe = str(patient.get("name") or f"case_{i}").replace(" ", "_")
            zf.writestr(f"{i:03d}_{safe}.pdf", pdf_bytes)

    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="AudioSense_reports.zip"'},
    )
