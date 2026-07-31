"""Batch endpoint: CSV of tests -> per-row analysis summaries.

CSV columns: name, age, sex, occupation, test_date, then thresholds as
r_ac_250 ... r_ac_8000, r_bc_250 ... r_bc_4000, l_ac_250 ... l_ac_8000,
l_bc_250 ... l_bc_4000. Values: integer dB, "NR", or blank (untested).
"""
from __future__ import annotations

import io
import statistics
import time
from typing import Dict, List

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.clinical import rules
from app.clinical.safety import safety_review
from app.clinical.triage import sort_worklist, triage_case, worklist_summary
from app.ml import classifier
from app.models.schemas import AC_FREQS, BC_FREQS, EarData

router = APIRouter(prefix="/api")


def _cell(row, col):
    if col not in row or pd.isna(row[col]) or str(row[col]).strip() == "":
        return None
    v = str(row[col]).strip().upper()
    if v == "NR":
        return "NR"
    try:
        return int(float(v))
    except ValueError:
        return None


def _thresholds(row, prefix, freqs):
    out = {}
    for f in freqs:
        v = _cell(row, f"{prefix}_{f}")
        if v is not None:
            out[f] = v
    return out


@router.post("/batch")
async def batch(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str)
    except Exception as exc:
        raise HTTPException(400, f"could not parse CSV: {exc}")

    results = []
    timings: List[float] = []
    batch_started = time.perf_counter()
    for i, row in df.iterrows():
        case_started = time.perf_counter()
        r_ac = _thresholds(row, "r_ac", AC_FREQS)
        r_bc = _thresholds(row, "r_bc", BC_FREQS)
        l_ac = _thresholds(row, "l_ac", AC_FREQS)
        l_bc = _thresholds(row, "l_bc", BC_FREQS)
        rr = rules.analyze_test(r_ac, r_bc, l_ac, l_bc)

        ml = {"right": None, "left": None}
        try:
            ml = {"right": classifier.classify_ear(r_ac, r_bc, explain=False),
                  "left": classifier.classify_ear(l_ac, l_bc, explain=False)}
        except FileNotFoundError:
            pass

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
        safety = safety_review(
            EarData(ac=r_ac, bc=r_bc), EarData(ac=l_ac, bc=l_bc)
        )
        # Triage needs the same shape the single-case endpoint produces.
        triage = triage_case({"safety": safety, "rules": rr, "ml": ml, "battery": {}})
        elapsed_ms = round((time.perf_counter() - case_started) * 1000, 1)
        timings.append(elapsed_ms)

        results.append({
            "row": int(i) + 1,
            "name": str(row.get("name", f"Row {i+1}")),
            "age": str(row.get("age", "")),
            "occupation": str(row.get("occupation", "")),
            "right": summarize("right"),
            "left": summarize("left"),
            "binaural_disability_pct": disability.get("binaural_pct"),
            "benchmark_disability": disability.get("benchmark_disability"),
            "urgent": safety["has_urgent"],
            "alerts": [a["title"] for a in safety["alerts"] if a["level"] in ("emergency", "urgent")],
            "triage": triage,
            "interpretation_ms": elapsed_ms,
        })

    ordered = sort_worklist(results)
    total_s = time.perf_counter() - batch_started
    return {
        "count": len(results),
        "results": ordered,
        "summary": camp_summary(results),
        "worklist": worklist_summary(results),
        "performance": _performance(timings, total_s),
    }


def _performance(timings: List[float], total_s: float) -> dict:
    """Throughput evidence — the claim this project is built on.

    A clinic does not care that interpretation is 'automatic'; it cares
    how many audiograms an hour it clears. These are measured numbers,
    not estimates.
    """
    if not timings:
        return {"cases": 0}
    return {
        "cases": len(timings),
        "total_seconds": round(total_s, 2),
        "mean_ms": round(statistics.mean(timings), 1),
        "median_ms": round(statistics.median(timings), 1),
        "slowest_ms": round(max(timings), 1),
        "cases_per_minute": round(len(timings) / total_s * 60) if total_s > 0 else None,
        "note": ("Measured server-side interpretation time. Manual interpretation of a "
                 "single audiogram by an audiologist typically takes several minutes."),
    }


AGE_BANDS = [(0, 18, "0–17"), (18, 30, "18–29"), (30, 45, "30–44"),
             (45, 60, "45–59"), (60, 200, "60+")]


def camp_summary(results: List[dict]) -> dict:
    """Population-level statistics — turns a screening camp into evidence.

    A per-patient tool answers "does this person need help?"; these numbers
    answer "does this workforce need a hearing-conservation programme?"
    """
    total = len(results)
    if not total:
        return {"total": 0}

    def worse_pta(r):
        vals = [r[s]["pta"] for s in ("right", "left") if r[s]["pta"] is not None]
        return max(vals) if vals else None

    def is_impaired(r):
        p = worse_pta(r)
        return p is not None and p >= 20

    impaired = [r for r in results if is_impaired(r)]
    benchmark = [r for r in results if r["benchmark_disability"]]
    urgent = [r for r in results if r.get("urgent")]

    # Noise-notch pattern in either ear = early occupational damage signal.
    def has_notch(r):
        return any((r[s]["pattern"] or "").startswith("Noise notch") for s in ("right", "left"))
    notch = [r for r in results if has_notch(r)]

    by_age = {}
    for lo, hi, label in AGE_BANDS:
        band = [r for r in results
                if str(r["age"]).strip().isdigit() and lo <= int(r["age"]) < hi]
        if band:
            by_age[label] = {
                "n": len(band),
                "impaired": sum(1 for r in band if is_impaired(r)),
                "impaired_pct": round(100 * sum(1 for r in band if is_impaired(r)) / len(band), 1),
            }

    by_grade: Dict[str, int] = {}
    for r in results:
        for s in ("right", "left"):
            g = r[s]["grade"]
            if g:
                by_grade[g] = by_grade.get(g, 0) + 1

    ood = [r for r in results if any(r[s]["ood"] for s in ("right", "left"))]
    provisional = [r for r in results
                   if any(r[s]["provisional"] for s in ("right", "left"))]

    return {
        "total": total,
        "impaired": len(impaired),
        "impaired_pct": round(100 * len(impaired) / total, 1),
        "benchmark_disability": len(benchmark),
        "benchmark_pct": round(100 * len(benchmark) / total, 1),
        "urgent_referrals": len(urgent),
        "noise_notch": len(notch),
        "noise_notch_pct": round(100 * len(notch) / total, 1),
        "needs_review": len(ood),
        "provisional_type": len(provisional),
        "by_age_band": by_age,
        "by_grade": dict(sorted(by_grade.items(), key=lambda kv: -kv[1])),
        "headline": (
            f"{round(100 * len(notch) / total)}% of this cohort shows a 4 kHz noise "
            "notch — the signature of occupational noise exposure."
        ) if len(notch) / total >= 0.15 else (
            f"{round(100 * len(impaired) / total)}% of this cohort has measurable "
            "hearing loss (PTA ≥ 20 dB HL)."
        ),
    }
