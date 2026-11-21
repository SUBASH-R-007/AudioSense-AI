"""MODULE 3 — Snap-to-digitize: paper audiogram photo -> thresholds.

Offline-first pipeline (no API key required):
  1. Grid detection — morphological extraction of long horizontal/vertical
     lines, clustered into gridline positions, giving the pixel ->
     (frequency, dB HL) coordinate mapping.
  2. Symbol recognition — every symbol-sized mark inside the plot is found
     and IDENTIFIED BY ITS SHAPE (``app.services.symbols``): O, X, triangle,
     square, <, >, [ and ], the standard set. The shape gives the ear, the
     conduction and whether masking was used.
  3. Values snap to the 5 dB grid; per-value confidence reflects snap
     distance, shape confidence and whether colour agreed. All values land
     in the editable entry grid for human confirmation before analysis
     (human-in-the-loop).

THE EAR IS A SYMBOL, NOT A COLOUR, and that is the correction at the centre
of this module. The original pipeline found marks with two HSV masks —
saturated red for the right ear, blue for the left — and so read a colour
printout and nothing else. A photocopy, a greyscale scan, a fax, a chart
drawn in one pen or a thermal printout from the audiometer all came back
"no red/blue audiogram symbols detected", which is not a degraded result
but the feature simply unavailable for what is very likely the commonest
kind of paper audiogram in a district hospital.

Colour has not been discarded: where the marks are coloured it is strong
evidence and it is used, as CORROBORATION of the shape decision and as the
tie-breaker when a shape cannot be identified. Where it disagrees with a
confidently identified symbol, the disagreement is reported rather than
silently resolved — a red X is a chart someone drew wrongly, or a shape the
software has misread, and either way a human should look.

Assumes a reasonably clean, roughly axis-aligned chart. When API mode is
active with a vision-capable provider, the LLM path runs instead and this
pipeline remains the automatic fallback.
"""
from __future__ import annotations

import base64
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.services import llm_provider, symbols
from app.services.ai_config import PROVIDERS, get_config

AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]
BC_FREQS = [250, 500, 1000, 2000, 4000]
DB_TOP, DB_BOTTOM = -10, 120  # inverted clinical y-axis

#: Which ear a mark's colour says it is, where the chart uses colour at all.
#: Only ever used to corroborate or to break a tie — never on its own.
COLOUR_EAR = {"red": "right", "blue": "left"}

#: How much poorer than air conduction a bone threshold may read before it is
#: treated as a misread mark rather than a measurement. Bone conduction tests
#: the cochlea directly, so a genuine negative air-bone gap is only ever
#: test-retest noise: 10 dB is the conventional significance limit for a gap
#: (``rules.ABG_SIGNIFICANT_DB``) and this allows one 5 dB step beyond it.
NEGATIVE_GAP_TOLERANCE_DB = 15

#: The bottom of the chart, in dB HL, where printed furniture lives — the
#: legend, footnotes, a signature line. A real threshold here is rare and is
#: drawn with a no-response arrow, so a marginal shape in this strip needs to
#: be read more confidently than one in the middle of the plot before it is
#: accepted as a measurement.
TEXT_STRIP_DB = 110
TEXT_STRIP_MIN_CONFIDENCE = 0.8


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


def _mark_colour(img_bgr: np.ndarray, mark: dict) -> Optional[str]:
    """"red" | "blue" | None for one mark, from its own pixels only.

    Measured inside the mark's mask rather than its bounding box: the box of
    an X is mostly paper, and averaging that in washes the hue out.
    """
    x, y, w, h = mark["bbox"]
    roi = img_bgr[y:y + h, x:x + w]
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    sel = mark["mask"].astype(bool)
    if sel.sum() < 6:
        return None
    hue = hsv[:, :, 0][sel].astype(np.float32)
    sat = hsv[:, :, 1][sel].astype(np.float32)
    strong = sat > 60
    if strong.mean() < 0.25:
        return None
    hue = hue[strong]
    red = float(((hue <= 12) | (hue >= 165)).mean())
    blue = float(((hue >= 95) & (hue <= 135)).mean())
    if red > 0.55 and red > blue:
        return "red"
    if blue > 0.55 and blue > red:
        return "blue"
    return None


def digitize_opencv(image_bytes: bytes) -> dict:
    """Extract right/left AC+BC thresholds from a chart photo.

    Shape-first: each mark is identified as one of the eight standard
    audiogram symbols, which names the ear and the conduction. Colour, the
    x-offset convention and the mark's size are used to break ties and to
    corroborate, never to decide on their own.
    """
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "error": "could not decode image"}
    if img.shape[1] > 1600:
        scale = 1600 / img.shape[1]
        img = cv2.resize(img, None, fx=scale, fy=scale)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    grid = _detect_grid(gray)
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
        "masked": {"right": {"ac": {}, "bc": {}}, "left": {"ac": {}, "bc": {}}},
    }
    warnings: List[str] = []
    spacing = grid["col_spacing"]
    greyscale = symbols.is_greyscale(img)

    # PASS ONE, always: every mark on the grid, found in greyscale, identified
    # by shape. This is the pass that makes a photocopy readable.
    marks = [{**m, "pass": "shape"} for m in symbols.extract_marks(gray, grid)]

    # PASS TWO, only where the chart is coloured: the same detector run over
    # each ear's ink on its own. Shape cannot separate two symbols drawn at
    # the same point, which happens whenever the ears share a threshold — and
    # equal thresholds are common. One colour at a time, they come apart.
    if not greyscale:
        for colour in ("red", "blue"):
            mask = symbols.colour_mask(img, colour)
            if mask.sum() < 255 * 20:
                continue
            for m in symbols.extract_marks(gray, grid, binary=mask):
                marks.append({**m, "pass": "colour", "colour": colour})

    # (ear, conduction, freq) -> (score, db, conf, symbol)
    best: Dict[Tuple[str, str, int], Tuple[float, int, float, str]] = {}
    unidentified: List[dict] = []
    colour_conflicts: List[str] = []

    for mark in marks:
        cx, cy = mark["cx"], mark["cy"]
        freq = min(AC_FREQS, key=lambda f: abs(grid["freq_x"][f] - cx))
        dx = (cx - grid["freq_x"][freq]) / spacing
        if abs(dx) > 0.5:
            continue

        shape = symbols.classify(mark["mask"])
        # A mark found in the per-ear pass already knows its colour — that is
        # what isolated it — so it is not re-measured against the full image,
        # where the other ear's overlapping ink would muddy the hue.
        colour = (mark.get("colour") if mark.get("pass") == "colour"
                  else (None if greyscale else _mark_colour(img, mark)))
        colour_ear = COLOUR_EAR.get(colour) if colour else None

        ear = shape["ear"]
        conduction = shape["conduction"]
        confidence = shape["confidence"]
        symbol = shape["symbol"]

        if ear is None:
            # The shape could not be named. Colour can still say which ear,
            # and the x-offset convention which conduction — a bone symbol is
            # drawn beside the frequency line, an air symbol on it. That is a
            # weaker reading and is scored as one.
            if colour_ear is None:
                # Only marks that LOOK like a symbol are worth reporting as
                # unidentified. A chart carries legend text and stray ink
                # inside the plot too, and listing every glyph as "a mark we
                # could not read" buries the one that was a real symbol.
                if max((shape.get("scores") or {}).values(), default=0.0) >= 0.25:
                    unidentified.append({
                        "freq": freq, "db": int(np.clip(
                            round(_y_to_db(cy, grid) / 5) * 5, -10, 120)),
                        "reason": shape.get("reason") or "shape not recognised",
                    })
                continue
            ear = colour_ear
            conduction = "ac" if abs(dx) < 0.18 else "bc"
            confidence = 0.4
            symbol = "unknown"
        elif colour_ear is not None and colour_ear != ear:
            # Two independent signals disagreeing is a finding, not something
            # to resolve quietly. The shape is kept — it carries the
            # conduction and the masking too — and the conflict is reported at
            # reduced confidence for the human to settle.
            colour_conflicts.append(
                f"{freq} Hz: the mark is shaped like {symbols.SYMBOL_NAME[symbol]} "
                f"but is drawn in {colour}, which by convention is the "
                f"{colour_ear} ear. Read as {ear} from its shape — check it.")
            confidence = round(confidence * 0.5, 3)

        if conduction == "bc" and freq not in BC_FREQS:
            warnings.append(
                f"{freq} Hz: a bone-conduction symbol was read here, but bone "
                "conduction is not tested above 4000 Hz — ignored.")
            continue

        db_raw = _y_to_db(cy, grid)
        db = int(np.clip(round(db_raw / 5) * 5, -10, 120))
        snap = abs(db_raw - db) / 5
        conf = round(max(0.2, min(1.0, confidence * (1.0 - 0.35 * snap))), 2)
        # Rank candidates for the same slot by shape confidence FIRST, with
        # size only as a tiebreak.
        #
        # This has to be a lexicographic comparison, not a weighted sum. With
        # the two blended, a large merged blob read at 40% confidence
        # outscored the correct bracket read at 98% purely on pixel count, and
        # put a 45 dB bone threshold where the chart said 35. Area is for
        # choosing between two equally convincing reads of the same mark; it
        # must never overturn one.
        # Between two equally confident reads of the same slot, the one found
        # in the per-ear colour pass wins: it was isolated from a single ear's
        # ink, so neither the other ear's overlapping symbol nor the connector
        # polyline is in the pixels that were measured.
        score = (round(confidence, 3), 1 if mark.get("pass") == "colour" else 0,
                 mark["area"])
        key = (ear, conduction, freq)
        if key not in best or score > best[key][0]:
            best[key] = (score, db, conf, symbol)

    for (ear, conduction, freq), (_, db, conf, symbol) in best.items():
        # The bottom strip of a chart is where its PRINTED TEXT goes — the
        # legend, a footnote, the signature line — and a clinical legend often
        # spells the symbol set out literally ("Right: red O / ["), which this
        # detector reads, correctly, as symbols. A real threshold down here is
        # rare and is drawn with a no-response arrow, so a marginal shape at
        # the foot of the plot is far more likely to be a letterform.
        if db >= TEXT_STRIP_DB and conf < TEXT_STRIP_MIN_CONFIDENCE:
            warnings.append(
                f"{ear} ear, {freq} Hz: a mark at {db} dB HL was read as "
                f"{symbols.SYMBOL_NAME.get(symbol, symbol)} but only at "
                f"{conf:.0%} confidence. The foot of a chart usually carries "
                "its printed legend, so this was left out — enter it by hand "
                "if the threshold really is off the scale.")
            continue
        result[ear][conduction][freq] = db
        result["confidence"][ear][conduction][freq] = conf
        meaning = symbols.SYMBOL_MEANING.get(symbol)
        if meaning:
            result["masked"][ear][conduction][freq] = meaning[2]

    # --- physiological sanity ------------------------------------------
    #
    # Bone conduction measures the cochlea directly, so it cannot be
    # materially POORER than air conduction at the same frequency: a negative
    # air-bone gap beyond test-retest variation is not a finding, it is a
    # misread mark. This catches the failure that costs most — a bracket
    # character in a chart's printed legend ("Right: red O / [") sitting low
    # on the plot and read as a 115 dB bone threshold, which would then be
    # typed as a profound mixed loss.
    for ear in ("right", "left"):
        for freq, bc_db in list(result[ear]["bc"].items()):
            ac_db = result[ear]["ac"].get(freq)
            if ac_db is None or bc_db <= ac_db + NEGATIVE_GAP_TOLERANCE_DB:
                continue
            result[ear]["bc"].pop(freq, None)
            result["confidence"][ear]["bc"].pop(freq, None)
            result["masked"][ear]["bc"].pop(freq, None)
            warnings.append(
                f"{ear} ear, {freq} Hz: a bone-conduction mark was read at "
                f"{bc_db} dB HL, {bc_db - ac_db:g} dB poorer than air "
                f"conduction ({ac_db} dB). Bone conduction cannot be that much "
                "worse than air, so the mark was misread and has been dropped "
                "— enter it by hand if the chart really does show one.")

    for ear in ("right", "left"):
        missing = [f for f in AC_FREQS if f not in result[ear]["ac"]]
        if missing:
            warnings.append(f"{ear} ear: no AC symbol found at {missing} Hz")

    # A mark the greyscale pass could not name is not worth reporting if the
    # per-colour pass went on to read that position: the usual cause is two
    # overlapping symbols, which is exactly what the second pass separates.
    filled = {(conduction, freq) for (_, conduction, freq) in best}
    unidentified = [
        u for u in unidentified
        if not any((c, u["freq"]) in filled for c in ("ac", "bc"))
    ]

    if unidentified:
        where = ", ".join(
            f"{u['freq']} Hz near {u['db']} dB" for u in unidentified[:6])
        warnings.append(
            f"{len(unidentified)} mark(s) could not be identified ({where}) — "
            "they were left out rather than guessed at. Enter those values by "
            "hand.")
    warnings.extend(colour_conflicts)
    warnings = list(dict.fromkeys(warnings))

    found = sum(len(result[e]["ac"]) + len(result[e]["bc"]) for e in ("right", "left"))
    if found == 0:
        return {
            "ok": False,
            "error": (
                f"found {len(marks)} mark(s) on the grid but could not identify "
                "any as an audiogram symbol — check the chart uses the standard "
                "set (O X △ □ < > [ ]), or enter the values by hand"
                if marks else
                "no audiogram symbols detected on the grid — try a straighter, "
                "better-lit photo, or enter values manually"),
            "marks_found": len(marks),
        }

    return {
        "ok": True,
        "method": "opencv (symbol shapes)",
        **result,
        "warnings": warnings,
        # What the reader needs to judge the extraction: how the ear was
        # decided, and how much was left on the table.
        "detection": {
            "greyscale": greyscale,
            "colour_used": (not greyscale),
            "marks_found": len(marks),
            "symbols_identified": len(best),
            "unidentified": unidentified,
            "colour_conflicts": len(colour_conflicts),
            "note": ("The chart carries no usable colour, so each ear was "
                     "decided from the symbol shape alone."
                     if greyscale else
                     "Each ear was decided from the symbol shape, with the "
                     "mark's colour checked against it."),
        },
    }


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
                # `or {}`: this dict is parsed out of an LLM reply, so any key
                # may arrive present-but-null. A `{}` default does not fire on
                # that, and the next .get would raise inside the try — landing
                # in the OpenCV fallback below and reporting a vision failure
                # that never happened.
                "right": _intkeys(data.get("right") or {}),
                "left": _intkeys(data.get("left") or {}),
                "confidence": {
                    "right": _intkeys((data.get("confidence") or {}).get("right") or {}),
                    "left": _intkeys((data.get("confidence") or {}).get("left") or {}),
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
