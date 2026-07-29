"""MODULE 3 — Snap-to-digitize: paper audiogram photo -> thresholds.

Offline-first pipeline (no API key required):
  1. Grid detection — morphological extraction of long horizontal/vertical
     lines, clustered into gridline positions, giving the pixel ->
     (frequency, dB HL) coordinate mapping.
  2. Symbol detection — HSV color masks isolate right-ear (red O / [) and
     left-ear (blue X / ]) marks; connected components near a frequency
     column are AC symbols, components offset beside a column are BC
     brackets (clinical charts draw brackets beside the AC symbol).
  3. Values snap to the 5 dB grid; per-value confidence reflects snap
     distance. All values land in the editable entry grid for human
     confirmation before analysis (human-in-the-loop).

Assumes a reasonably clean, roughly axis-aligned chart with standard
colors (red = right, blue = left) — true for the bundled samples and for
typical phone photos of printed charts.

When API mode is active with a vision-capable provider, the LLM path runs
instead and OpenCV remains the automatic fallback.
"""
from __future__ import annotations

import base64
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.services import llm_provider
from app.services.ai_config import PROVIDERS, get_config

AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]
BC_FREQS = [250, 500, 1000, 2000, 4000]
DB_TOP, DB_BOTTOM = -10, 120  # inverted clinical y-axis


# ---------------------------------------------------------------- OpenCV ---

def _cluster_positions(positions: np.ndarray, gap: int) -> List[int]:
    """Collapse consecutive pixel rows/cols into single line centers."""
    if positions.size == 0:
        return []
    groups, start, prev = [], positions[0], positions[0]
    for p in positions[1:]:
        if p - prev > gap:
            groups.append((start + prev) // 2)
            start = p
        prev = p
    groups.append((start + prev) // 2)
    return [int(g) for g in groups]


def _detect_grid(gray: np.ndarray) -> Optional[dict]:
    """Find gridline positions; return the pixel->(freq,dB) mapping."""
    h, w = gray.shape
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10
    )

    horiz = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (w // 8, 1))
    )
    vert = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 8))
    )

    row_hits = np.where(horiz.sum(axis=1) / 255 > w * 0.35)[0]
    col_hits = np.where(vert.sum(axis=0) / 255 > h * 0.35)[0]
    rows = _cluster_positions(row_hits, gap=4)
    cols = _cluster_positions(col_hits, gap=4)

    if len(cols) < 6 or len(rows) < 8:
        return None

    # Frequency columns: 6 evenly spaced vertical gridlines. The plot may
    # also show box spines half a step outside — detect and drop them.
    if len(cols) >= 8:
        inner = cols[1:-1]
        spacing_inner = np.diff(inner)
        if len(inner) == 6 and spacing_inner.std() < spacing_inner.mean() * 0.25:
            cols = inner
    if len(cols) != 6:
        # Keep the 6 most evenly spaced consecutive lines.
        best, best_score = cols[:6], float("inf")
        for i in range(len(cols) - 5):
            cand = cols[i : i + 6]
            d = np.diff(cand)
            score = d.std() / (d.mean() + 1e-9)
            if score < best_score:
                best, best_score = cand, score
        cols = best

    # dB rows: gridlines every 10 dB from -10 (top) to 120 (bottom).
    y_top, y_bottom = rows[0], rows[-1]
    if y_bottom - y_top < h * 0.3:
        return None

    return {
        "freq_x": dict(zip(AC_FREQS, cols)),
        "y_top": y_top,
        "y_bottom": y_bottom,
        "col_spacing": float(np.mean(np.diff(cols))),
    }


def _y_to_db(y: float, grid: dict) -> float:
    frac = (y - grid["y_top"]) / (grid["y_bottom"] - grid["y_top"])
    return DB_TOP + frac * (DB_BOTTOM - DB_TOP)


def _color_components(img_bgr: np.ndarray, color: str) -> List[Tuple[float, float, int]]:
    """(cx, cy, area) of connected components for red or blue marks."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    if color == "red":
        mask = cv2.inRange(hsv, (0, 60, 60), (10, 255, 255)) | cv2.inRange(
            hsv, (165, 60, 60), (180, 255, 255)
        )
    else:
        mask = cv2.inRange(hsv, (95, 60, 60), (135, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    n, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
    out = []
    min_area = max(20, img_bgr.shape[0] * img_bgr.shape[1] // 60000)
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area >= min_area:
            out.append((float(centroids[i][0]), float(centroids[i][1]), area))
    return out


def digitize_opencv(image_bytes: bytes) -> dict:
    """Extract right/left AC+BC thresholds from a chart photo."""
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "error": "could not decode image"}
    if img.shape[1] > 1600:
        scale = 1600 / img.shape[1]
        img = cv2.resize(img, None, fx=scale, fy=scale)

    grid = _detect_grid(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    if grid is None:
        return {
            "ok": False,
            "error": "could not locate the audiogram grid — try a straighter, "
                     "better-lit photo, or enter values manually",
        }

    result = {
        "right": {"ac": {}, "bc": {}},
        "left": {"ac": {}, "bc": {}},
        "confidence": {"right": {"ac": {}, "bc": {}}, "left": {"ac": {}, "bc": {}}},
    }
    warnings: List[str] = []
    spacing = grid["col_spacing"]

    for ear, color in (("right", "red"), ("left", "blue")):
        # bucket: (conduction, freq) -> best (area, db, conf)
        best: Dict[Tuple[str, int], Tuple[int, int, float]] = {}
        for cx, cy, area in _color_components(img, color):
            freq = min(AC_FREQS, key=lambda f: abs(grid["freq_x"][f] - cx))
            dx = abs(grid["freq_x"][freq] - cx) / spacing
            if dx < 0.18:
                conduction = "ac"
            elif dx < 0.48:
                conduction = "bc"
                if freq not in BC_FREQS:
                    continue
            else:
                continue
            db_raw = _y_to_db(cy, grid)
            db = int(np.clip(round(db_raw / 5) * 5, -10, 120))
            conf = round(max(0.3, 1.0 - abs(db_raw - db) / 5 * 0.6 - dx * 0.3), 2)
            key = (conduction, freq)
            if key not in best or area > best[key][0]:
                best[key] = (area, db, conf)
        for (conduction, freq), (_, db, conf) in best.items():
            result[ear][conduction][freq] = db
            result["confidence"][ear][conduction][freq] = conf
        missing = [f for f in AC_FREQS if f not in result[ear]["ac"]]
        if missing:
            warnings.append(f"{ear} ear: no AC symbol found at {missing} Hz")

    found = sum(len(result[e]["ac"]) + len(result[e]["bc"]) for e in ("right", "left"))
    if found == 0:
        return {"ok": False, "error": "no red/blue audiogram symbols detected"}

    return {"ok": True, "method": "opencv", **result, "warnings": warnings}


# ------------------------------------------------------------- LLM vision --

VISION_PROMPT = """You are reading a pure-tone audiogram chart photograph.
Standard clinical notation: RIGHT ear = RED, circle O for air conduction (AC),
bracket [ for bone conduction (BC). LEFT ear = BLUE, cross X for AC,
bracket ] for BC. X axis: frequency 250, 500, 1000, 2000, 4000, 8000 Hz.
Y axis: hearing level dB HL, -10 at top to 120 at bottom, gridlines every 10 dB.

Read every symbol's position and return STRICT JSON only (no prose):
{
  "right": {"ac": {"250": <dB>, ...}, "bc": {"250": <dB>, ...}},
  "left":  {"ac": {...}, "bc": {...}},
  "confidence": {"right": {"ac": {"250": <0-1>, ...}, "bc": {...}}, "left": {...}}
}
Rules: dB values snapped to nearest 5. BC only up to 4000 Hz. Omit
frequencies with no symbol. Confidence reflects how clearly you can read
each symbol. Output ONLY the JSON object."""


def digitize(image_bytes: bytes) -> dict:
    """Route to LLM vision when enabled, else (or on failure) OpenCV."""
    cfg = get_config()
    if llm_provider.ai_enabled() and PROVIDERS[cfg.provider]["supports_vision"]:
        try:
            b64 = base64.b64encode(image_bytes).decode()
            reply = llm_provider.call_llm(
                VISION_PROMPT, image_b64=b64, image_mime="image/png"
            )
            data = llm_provider.extract_json(reply)
            out = {
                "ok": True,
                "method": f"llm:{cfg.provider}",
                "right": _intkeys(data.get("right", {})),
                "left": _intkeys(data.get("left", {})),
                "confidence": {
                    "right": _intkeys(data.get("confidence", {}).get("right", {})),
                    "left": _intkeys(data.get("confidence", {}).get("left", {})),
                },
                "warnings": [],
            }
            return out
        except Exception as exc:
            fallback = digitize_opencv(image_bytes)
            if fallback.get("ok"):
                fallback["warnings"] = fallback.get("warnings", []) + [
                    f"AI vision failed ({str(exc)[:120]}) — used offline OpenCV extraction"
                ]
                fallback["method"] = "opencv (AI fallback)"
            return fallback
    return digitize_opencv(image_bytes)


def _intkeys(d: dict) -> dict:
    out = {}
    for conduction in ("ac", "bc"):
        vals = d.get(conduction, {})
        out[conduction] = {int(k): v for k, v in vals.items()}
    return out
