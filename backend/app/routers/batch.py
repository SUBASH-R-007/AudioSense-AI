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
from app.ml.features import COLES_NOTCH_DB, NORMAL_FREQ_LIMIT, noise_notch_with_loss
from app.models.schemas import AC_FREQS, BC_FREQS, EarData, ear_to_numeric

router = APIRouter(prefix="/api")


#: Valid threshold range in dB HL, matching EarData's own validator
#: (schemas.py:91). Checked here as well as there so a bad cell is reported
#: with its row and column instead of surfacing as a pydantic error deep in
#: the loop — where it used to abort the whole upload.
DB_MIN, DB_MAX = -10, 120


def _cell(row, col):
    """Parse one cell. Returns (value, complaint); exactly one is not None."""
    if col not in row or pd.isna(row[col]) or str(row[col]).strip() == "":
        return None, None
    v = str(row[col]).strip().upper()
    if v == "NR":
        return "NR", None
    try:
        n = int(float(v))
    except ValueError:
        return None, f"{col} = {str(row[col]).strip()!r} is not a number, NR or blank"
    if not (DB_MIN <= n <= DB_MAX):
        return None, f"{col} = {n} is outside {DB_MIN}..{DB_MAX} dB HL"
    return n, None


def _thresholds(row, prefix, freqs):
    """Thresholds for one ear and one transducer, plus any bad cells found."""
    out, bad = {}, []
    for f in freqs:
        v, complaint = _cell(row, f"{prefix}_{f}")
        if complaint:
            bad.append(complaint)
        elif v is not None:
            out[f] = v
    return out, bad


@router.post("/batch")
async def batch(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str)
    except Exception as exc:
        raise HTTPException(400, f"could not parse CSV: {exc}")

    results = []
    errors: List[dict] = []
    timings: List[float] = []
    batch_started = time.perf_counter()
    for i, row in df.iterrows():
        case_started = time.perf_counter()
        r_ac, bad_r_ac = _thresholds(row, "r_ac", AC_FREQS)
        r_bc, bad_r_bc = _thresholds(row, "r_bc", BC_FREQS)
        l_ac, bad_l_ac = _thresholds(row, "l_ac", AC_FREQS)
        l_bc, bad_l_bc = _thresholds(row, "l_bc", BC_FREQS)

        # A screening camp uploads hundreds of rows typed by hand. One bad
        # cell used to raise inside the loop and abort the entire file with a
        # bare 500, throwing away every good row and naming neither the row
        # nor the column. Report the offending row and carry on with the rest.
        bad = bad_r_ac + bad_r_bc + bad_l_ac + bad_l_bc
        if bad:
            errors.append({"row": int(i) + 1,
                           "name": str(row.get("name", f"Row {int(i)+1}")),
                           "problems": bad})
            continue

        # Backstop for anything the range check above does not anticipate. A
        # malformed row is worth one error entry, never the whole upload.
        try:
            rr = rules.analyze_test(r_ac, r_bc, l_ac, l_bc)

            ml = {"right": None, "left": None}
            try:
                ml = {"right": classifier.classify_ear(r_ac, r_bc, explain=False),
                      "left": classifier.classify_ear(l_ac, l_bc, explain=False)}
            except FileNotFoundError:
                pass

            acs = {"right": r_ac, "left": l_ac}

            def summarize(side):
                ear, m = rr[side], ml[side]
                return {
                    "pta": (ear.get("ac_pta") or {}).get("value"),
                    "grade": (ear.get("who_grade") or {}).get("grade"),
                    "type": ear.get("type"),
                    "provisional": ear.get("provisional"),
                    "pattern": m.get("pattern_label") if m else None,
                    "pattern_key": m.get("pattern") if m else None,
                    "pattern_reliable": m.get("reliable") if m else None,
                    "reliability_note": m.get("reliability_note") if m else None,
                    "confidence": m.get("confidence") if m else None,
                    "ood": m.get("ood") if m else None,
                    # Rule-based, independent of the classifier: the cohort
                    # notch rate must not inherit the model's forced labels.
                    # None = not assessable from the tested frequencies.
                    "noise_notch": noise_notch_with_loss(
                        ear_to_numeric(acs[side])),
                }

            disability = rr.get("disability") or {}
            safety = safety_review(
                EarData(ac=r_ac, bc=r_bc), EarData(ac=l_ac, bc=l_bc)
            )
            # Triage needs the same shape the single-case endpoint produces.
            triage = triage_case({"safety": safety, "rules": rr, "ml": ml,
                                  "battery": {}})
        except Exception as exc:
            errors.append({"row": int(i) + 1,
                           "name": str(row.get("name", f"Row {int(i)+1}")),
                           "problems": [f"could not be interpreted: {exc}"]})
            continue

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
            # False when the percentage is a provisional estimate (e.g. a PTA
            # frequency untested) that cannot go on a certificate.
            "disability_certifiable": (disability.get("certifiable", True)
                                       if disability else None),
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
        # Rows that could not be interpreted, named so they can be corrected
        # and re-uploaded. Empty for a clean file.
        "errors": errors,
        "skipped": len(errors),
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
    benchmark_provisional = [r for r in benchmark
                             if r.get("disability_certifiable") is False]
    urgent = [r for r in results if r.get("urgent")]

    # Noise notch in either ear = early occupational damage signal. Counted
    # from the thresholds by the Coles, Lutman & Buffin (2000) notch rule
    # with the 4 kHz threshold outside normal limits — never from the
    # classifier label: the model has no normal class, so its label would
    # count normal-hearing ears with a 5 dB wobble at 4 kHz as notched.
    def has_notch(r):
        return any(r[s].get("noise_notch") is True for s in ("right", "left"))

    def notch_assessable(r):
        return any(r[s].get("noise_notch") is not None for s in ("right", "left"))
    notch = [r for r in results if has_notch(r)]
    assessable = [r for r in results if notch_assessable(r)]

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
    # "Needs review" is the triage decision each row carries — the same one
    # the worklist counts — so a provisional type, a validity alert or a
    # benchmark percentage is counted, not only an atypical pattern.
    review = [r for r in results if (r.get("triage") or {}).get("review_required")]

    return {
        "total": total,
        "impaired": len(impaired),
        "impaired_pct": round(100 * len(impaired) / total, 1),
        "benchmark_disability": len(benchmark),
        "benchmark_pct": round(100 * len(benchmark) / total, 1),
        # Of those, how many rest on a percentage that cannot be certified
        # as measured — they need retesting before a certification camp.
        "benchmark_not_certifiable": len(benchmark_provisional),
        "urgent_referrals": len(urgent),
        "noise_notch": len(notch),
        "noise_notch_pct": round(100 * len(notch) / total, 1),
        # People with at least one ear in which the notch rule could be
        # applied (4 kHz, 8 kHz and 1 or 2 kHz tested). Screening sets that
        # skip 8 kHz cannot show a notch, so a low rate there means "not
        # measured", not "absent".
        "noise_notch_assessable": len(assessable),
        "noise_notch_definition": (
            f"4 kHz threshold at least {COLES_NOTCH_DB:g} dB worse than at 1 or 2 kHz "
            f"and than at 8 kHz (Coles, Lutman & Buffin 2000), and above "
            f"{NORMAL_FREQ_LIMIT:g} dB HL"
        ),
        "needs_review": len(review),
        "atypical_pattern": len(ood),
        "provisional_type": len(provisional),
        "by_age_band": by_age,
        "by_grade": dict(sorted(by_grade.items(), key=lambda kv: -kv[1])),
        "headline": (
            f"{round(100 * len(notch) / total)}% of this cohort shows a 4 kHz noise "
            "notch with hearing loss at 4 kHz (Coles et al. 2000 criteria) — the "
            "audiometric signature of noise exposure; take noise-exposure histories."
        ) if len(notch) / total >= 0.15 else (
            f"{round(100 * len(impaired) / total)}% of this cohort has measurable "
            "hearing loss (PTA ≥ 20 dB HL)."
        ),
    }
