"""Scanned audiometry REPORT -> thresholds plus the printed result fields.

WHAT THIS IS FOR, and how it differs from ``vision.py``. That module reads a
photograph OF A CHART: the audiogram fills the frame, and the whole job is to
turn symbols into numbers. A real clinic does not hand you that. It hands you
a REPORT — one A4 page with the hospital's letterhead, the patient's name and
age, the audiogram somewhere in the middle, and a block of printed results
underneath it: the pure-tone averages, the speech scores, a type and a degree,
a recommendation, a signature. Feeding that page to the chart digitizer finds
the grid if you are lucky and nothing else, and every printed number on it —
the numbers an audiologist already computed and signed — is thrown away.

So this module does three things:

  1. LOCATES THE CHART on the page, so the existing symbol digitizer can be
     pointed at it instead of at the whole sheet.
  2. READS THE PRINTED FIELDS where it is able to, and says plainly when it
     is not.
  3. FINDS THE TEXT REGIONS either way, with their positions, so a clinician
     can be shown the exact crop of the page that holds a field and type what
     it says. That is slower than reading it automatically and far faster
     than retyping a report from scratch, and it never invents a value.

THREE READING PATHS, in descending order of what they can do, and the one
that is available is the one that runs:

  LLM VISION    when API mode is on with a vision-capable provider. Reads the
                whole page, chart and text together.
  TESSERACT     when the optional ``pytesseract`` package AND the tesseract
                binary are both present. Offline, and reads the text block.
                Not a dependency: the import is guarded, the feature simply
                reports itself unavailable, and nothing else changes.
  GUIDED        always. The chart is digitized offline by symbol shape, the
                text regions are located and handed to the UI as crops, and
                the clinician confirms each field.

NOTHING IS EVER GUESSED. A field this module did not read comes back absent
with a reason, not blank-and-implied-zero and not filled from a plausible
default. A scanned report is a clinical document; a transcription error in
one is worse than an empty box, because an empty box gets filled in.
"""
from __future__ import annotations

import base64
import re
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.services import llm_provider, vision
from app.services.ai_config import PROVIDERS, get_config

#: Longest side the page is scaled to before analysis. A4 at 300 dpi is
#: ~3500 px; the grid and the symbols are perfectly readable at 2000 and the
#: morphology is four times cheaper.
MAX_SIDE = 2000

#: Minimum share of the page a candidate chart must cover. Below this it is a
#: table, a logo or a signature box rather than an audiogram.
MIN_CHART_AREA_FRACTION = 0.04


# ==========================================================================
# optional OCR
# ==========================================================================

def ocr_available() -> Tuple[bool, str]:
    """Whether offline OCR can run here, and why not when it cannot.

    Both halves have to be present: the Python wrapper AND the tesseract
    binary it shells out to. Checking only the import is how this kind of
    feature comes to claim it works and then fail on the first upload.
    """
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return False, ("The optional pytesseract package is not installed, so "
                       "the printed text on the page cannot be read "
                       "automatically. The audiogram itself is still read from "
                       "its symbols.")
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception:
        return False, ("pytesseract is installed but the tesseract program it "
                       "needs was not found on this machine, so the printed "
                       "text cannot be read automatically. The audiogram "
                       "itself is still read from its symbols.")
    return True, "Offline OCR available."


# ==========================================================================
# the page
# ==========================================================================

def _decode(image_bytes: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    longest = max(img.shape[:2])
    if longest > MAX_SIDE:
        scale = MAX_SIDE / longest
        img = cv2.resize(img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_AREA)
    return img


def locate_chart(img_bgr: np.ndarray) -> Optional[dict]:
    """Find the audiogram on a page of other content.

    An audiogram is the one thing on a clinical report made of many long
    horizontal AND many long vertical lines crossing each other. A results
    table has horizontal rules and few verticals; a letterhead has neither.
    So the chart is found as the largest region where both line families
    overlap densely.

    Returns the bounding box padded outward, because the digitizer needs the
    axis gridlines at the edges of the plot to build its coordinate mapping,
    and a box cropped exactly to the ink loses them.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 25, 12)

    # Lines long enough to be chart furniture rather than text or a rule in a
    # table. A sixth of the page is short enough to catch a chart that only
    # occupies a third of the sheet, long enough to miss a word.
    h_len = max(w // 6, 30)
    v_len = max(h // 6, 30)
    horiz = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vert = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))

    # THE VERTICAL GRIDLINES ARE THE PLOT BOX, and reading them directly is
    # what makes this reliable. The obvious approach — dilate both line
    # families and intersect them — needs a dilation wider than the column
    # spacing to join the lattice into one region, and the spacing is not
    # known until the chart has been found. With anything smaller the chart
    # comes back as one narrow band per gridline and no single component
    # looks like an audiogram.
    #
    # A report page also makes the two families very unequal: its tables and
    # rules are horizontal, so long HORIZONTAL lines are everywhere and long
    # VERTICAL ones occur essentially only inside the chart. So the vertical
    # lines give both edges and both ends of the plot on their own.
    # The bar is relative to the OPENING length, not the page. A chart that
    # occupies a third of a report page has gridlines a third of the page
    # tall, so requiring them to cover a third of the page's height rejected
    # every real report — the one thing this function exists to read.
    columns = _line_positions(vert.sum(axis=0) / 255.0, v_len * 0.9)
    if len(columns) < 4:
        return None

    spans: List[Tuple[int, int]] = []
    for cx in columns:
        strip = vert[:, max(cx - 2, 0):cx + 3]
        rows = np.nonzero(strip.sum(axis=1))[0]
        if rows.size:
            spans.append((int(rows.min()), int(rows.max())))
    if not spans:
        return None
    # THE FULL EXTENT, not the median, and the asymmetry is deliberate.
    #
    # The crop is handed to the chart digitizer, which re-detects the grid
    # inside it and maps its topmost gridline to -10 dB and its bottom one to
    # 120. A crop that is slightly too LARGE costs nothing — the extra
    # letterhead or results text carries no long lines of its own, so the
    # chart's gridlines still bound what it finds. A crop that is slightly too
    # SMALL is fatal: lose the -10 dB line and the whole dB axis rescales, so
    # every threshold on the page comes out shifted by a constant and looks
    # perfectly plausible. Taking the median of the gridline ends did exactly
    # that on a greyscale page, where symbol ink merges into some lines and
    # shortens their measured span.
    #
    # Lines much shorter than the longest are dropped first, so a fragment the
    # opening happened to keep cannot drag an edge inward.
    longest = max(s[1] - s[0] for s in spans)
    full = [s for s in spans if (s[1] - s[0]) >= longest * 0.6] or spans
    y0 = min(s[0] for s in full)
    y1 = max(s[1] for s in full)
    x0, x1 = min(columns), max(columns)
    if y1 - y0 < h * 0.08 or x1 - x0 < w * 0.2:
        return None

    # The horizontal gridlines have to agree: a plot has many of them inside
    # the box the verticals just described. Without this check a bordered
    # table of a few columns would pass as an audiogram.
    inside = horiz[y0:y1 + 1, x0:x1 + 1]
    rows = _line_positions(inside.sum(axis=1) / 255.0, (x1 - x0) * 0.5)
    if len(rows) < 6:
        return None

    pad_x = int((x1 - x0) * 0.06) + 4
    pad_y = int((y1 - y0) * 0.06) + 4
    bx0, by0 = max(x0 - pad_x, 0), max(y0 - pad_y, 0)
    bx1, by1 = min(x1 + pad_x, w), min(y1 + pad_y, h)
    box = {"x": bx0, "y": by0, "w": bx1 - bx0, "h": by1 - by0,
           "page_w": w, "page_h": h,
           "gridlines": {"vertical": len(columns), "horizontal": len(rows)},
           "area_fraction": round((bx1 - bx0) * (by1 - by0) / (w * h), 3)}
    if box["area_fraction"] < MIN_CHART_AREA_FRACTION:
        return None
    return box


def _line_positions(profile: np.ndarray, min_extent: float) -> List[int]:
    """Centres of the runs in a projection profile that clear ``min_extent``."""
    hits = np.nonzero(profile > min_extent)[0]
    if hits.size == 0:
        return []
    groups, start, prev = [], int(hits[0]), int(hits[0])
    for p in hits[1:]:
        p = int(p)
        if p - prev > 4:
            groups.append((start + prev) // 2)
            start = p
        prev = p
    groups.append((start + prev) // 2)
    return groups


def text_regions(img_bgr: np.ndarray, chart: Optional[dict]) -> List[dict]:
    """Blocks of printed text on the page, outside the chart.

    These are what the UI shows as crops for a clinician to read off. Found
    by the standard route — small components, dilated horizontally so the
    letters of a line merge into a line and the lines of a block into a block
    — because a field and its value sit on the same line and must be cropped
    together to be worth looking at.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 25, 12)

    # Remove the long lines first: a table rule or the chart's own grid would
    # otherwise join every block on the page into one.
    h_len = max(w // 8, 25)
    v_len = max(h // 8, 25)
    lines = cv2.bitwise_or(
        cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))),
        cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))))
    text = cv2.bitwise_and(binary, cv2.bitwise_not(
        cv2.dilate(lines, np.ones((3, 3), np.uint8))))

    # Blank the chart: its symbols and axis labels are not report fields.
    if chart:
        text[chart["y"]:chart["y"] + chart["h"],
             chart["x"]:chart["x"] + chart["w"]] = 0

    merged = cv2.dilate(text, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(w // 45, 12), max(h // 300, 3))))
    merged = cv2.morphologyEx(merged, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (9, 5)))

    n, _, stats, _ = cv2.connectedComponentsWithStats(merged)
    out: List[dict] = []
    for i in range(1, n):
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if bw < w * 0.05 or bh < 8 or bh > h * 0.4:
            continue
        out.append({"x": x, "y": y, "w": bw, "h": bh,
                    "area_fraction": round(bw * bh / (w * h), 4)})
    # Reading order: top to bottom, then left to right within a band.
    out.sort(key=lambda r: (r["y"] // max(int(h * 0.02), 1), r["x"]))
    return out[:40]


# ==========================================================================
# the printed result fields
# ==========================================================================

#: Fields worth lifting off a report, with the labels clinics actually print
#: and how each value is validated. Anything that does not match its pattern
#: is dropped rather than coerced — "PTA: see chart" is not a number.
FIELD_PATTERNS: Dict[str, dict] = {
    "name": {
        "labels": ["patient name", "name of patient", "patient", "name"],
        "kind": "text", "label": "Patient name",
    },
    "age": {
        "labels": ["age", "age/sex", "age / sex"],
        "kind": "int", "min": 0, "max": 120, "label": "Age (years)",
    },
    "sex": {
        "labels": ["sex", "gender"], "kind": "sex", "label": "Sex",
    },
    "test_date": {
        "labels": ["date of test", "test date", "date"],
        "kind": "date", "label": "Test date",
    },
    "right_pta": {
        "labels": ["right pta", "pta right", "pta (right)", "rt pta", "r pta"],
        "kind": "float", "min": -10, "max": 120, "label": "Right PTA (dB HL)",
    },
    "left_pta": {
        "labels": ["left pta", "pta left", "pta (left)", "lt pta", "l pta"],
        "kind": "float", "min": -10, "max": 120, "label": "Left PTA (dB HL)",
    },
    "right_srt": {
        "labels": ["right srt", "srt right", "srt (right)", "rt srt"],
        "kind": "float", "min": -10, "max": 120, "label": "Right SRT (dB HL)",
    },
    "left_srt": {
        "labels": ["left srt", "srt left", "srt (left)", "lt srt"],
        "kind": "float", "min": -10, "max": 120, "label": "Left SRT (dB HL)",
    },
    "right_wrs": {
        "labels": ["right sds", "right wrs", "sds right", "wrs right",
                   "right speech discrimination"],
        "kind": "percent", "label": "Right word recognition (%)",
    },
    "left_wrs": {
        "labels": ["left sds", "left wrs", "sds left", "wrs left",
                   "left speech discrimination"],
        "kind": "percent", "label": "Left word recognition (%)",
    },
    "impression": {
        "labels": ["impression", "diagnosis", "conclusion", "provisional diagnosis"],
        "kind": "text", "label": "Impression",
    },
    "recommendation": {
        "labels": ["recommendation", "advice", "advised", "plan"],
        "kind": "text", "label": "Recommendation",
    },
}

_SEX = {"m": "male", "male": "male", "f": "female", "female": "female"}


def _coerce(kind: str, raw: str, spec: dict) -> Optional[object]:
    """Validate one captured string, or return None rather than guess."""
    value = raw.strip().strip(":-–—").strip()
    if not value:
        return None
    if kind == "text":
        value = re.sub(r"\s+", " ", value)
        return value[:200] if len(value) >= 2 else None
    if kind == "sex":
        return _SEX.get(value.split()[0].lower().strip(".,"))
    if kind == "date":
        m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", value)
        return m.group(0) if m else None
    if kind == "percent":
        m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%?", value)
        if not m:
            return None
        n = float(m.group(1))
        return n if 0 <= n <= 100 else None
    m = re.search(r"(-?\d{1,3}(?:\.\d+)?)", value)
    if not m:
        return None
    n = float(m.group(1))
    if not (spec.get("min", -1e9) <= n <= spec.get("max", 1e9)):
        return None
    return int(round(n)) if kind == "int" else n


def parse_fields(text: str) -> Dict[str, dict]:
    """Pull the labelled fields out of a page of OCR'd text.

    Label-anchored rather than positional: clinics lay reports out however
    they like, but they all print "PTA" next to the pure-tone average. The
    longest matching label wins, so "right pta" is not matched as "pta".
    """
    found: Dict[str, dict] = {}
    if not text:
        return found
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for key, spec in FIELD_PATTERNS.items():
        for label in sorted(spec["labels"], key=len, reverse=True):
            pattern = re.compile(
                r"\b" + re.escape(label).replace(r"\ ", r"\s+") + r"\b\s*[:\-–—]?\s*(.*)",
                re.IGNORECASE)
            hit = None
            for line in lines:
                m = pattern.search(line)
                if m:
                    hit = (m.group(1), line)
                    break
            if hit is None:
                continue
            value = _coerce(spec["kind"], hit[0], spec)
            if value is None:
                continue
            found[key] = {"value": value, "label": spec["label"],
                          "source_line": hit[1][:160], "matched_label": label}
            break
    return found


VISION_PROMPT = """You are reading a photographed or scanned AUDIOMETRY REPORT.
The page contains a pure-tone audiogram chart and printed result text.

Audiogram notation: RIGHT ear = O (air, unmasked), triangle (air, masked),
< (bone, unmasked), [ (bone, masked) — conventionally red. LEFT ear = X (air,
unmasked), square (air, masked), > (bone, unmasked), ] (bone, masked) —
conventionally blue. Charts may be printed in black and white, in which case
the SYMBOL SHAPE alone gives the ear. X axis: 250, 500, 1000, 2000, 4000,
8000 Hz. Y axis: dB HL, -10 at the top to 120 at the bottom.

Return STRICT JSON only, no prose:
{
  "thresholds": {
    "right": {"ac": {"250": <dB>, ...}, "bc": {"250": <dB>, ...}},
    "left":  {"ac": {...}, "bc": {...}}
  },
  "confidence": {"right": {"ac": {"250": <0-1>, ...}, "bc": {...}}, "left": {...}},
  "fields": {
    "name": <string>, "age": <int>, "sex": "male"|"female",
    "test_date": <string>, "right_pta": <number>, "left_pta": <number>,
    "right_srt": <number>, "left_srt": <number>,
    "right_wrs": <number>, "left_wrs": <number>,
    "impression": <string>, "recommendation": <string>
  }
}

Rules: snap dB values to the nearest 5. Bone conduction only up to 4000 Hz.
OMIT any frequency with no symbol and any field not printed on the page — do
NOT invent, infer or carry a value over from the chart into a field or the
other way round. Output ONLY the JSON object."""


def _intkeys(d: dict) -> dict:
    out = {}
    for conduction in ("ac", "bc"):
        vals = (d or {}).get(conduction) or {}
        out[conduction] = {}
        for k, v in vals.items():
            try:
                out[conduction][int(k)] = v
            except (TypeError, ValueError):
                continue
    return out


def _fields_from_vision(raw: dict) -> Dict[str, dict]:
    """Validate an LLM's field block against the same rules as OCR text."""
    out: Dict[str, dict] = {}
    for key, spec in FIELD_PATTERNS.items():
        if key not in (raw or {}):
            continue
        value = _coerce(spec["kind"], str(raw[key]), spec)
        if value is None:
            continue
        out[key] = {"value": value, "label": spec["label"],
                    "source_line": None, "matched_label": None}
    return out


# ==========================================================================
# the whole page
# ==========================================================================

def scan(image_bytes: bytes, *, allow_llm: bool = True) -> dict:
    """Read a scanned audiometry report: the chart, and the printed fields."""
    img = _decode(image_bytes)
    if img is None:
        return {"ok": False, "error": "could not decode that file as an image"}

    chart = locate_chart(img)
    notes: List[str] = []

    # --- the audiogram ---------------------------------------------------
    thresholds: Optional[dict] = None
    if chart:
        crop = img[chart["y"]:chart["y"] + chart["h"],
                   chart["x"]:chart["x"] + chart["w"]]
        ok, buf = cv2.imencode(".png", crop)
        if ok:
            thresholds = vision.digitize_opencv(buf.tobytes())
        if thresholds and not thresholds.get("ok"):
            notes.append(
                "The audiogram was located on the page but its symbols could "
                f"not be read: {thresholds.get('error')}")
    else:
        notes.append(
            "No audiogram chart was found on this page — the grid of crossing "
            "lines an audiogram is made of was not there. If the page really "
            "does carry one, crop to it and use Snap-to-Digitize instead.")

    # --- the printed fields ----------------------------------------------
    fields: Dict[str, dict] = {}
    method = "none"
    cfg = get_config()
    llm_ready = (allow_llm and llm_provider.ai_enabled()
                 and PROVIDERS[cfg.provider]["supports_vision"])

    if llm_ready:
        try:
            reply = llm_provider.call_llm(
                VISION_PROMPT,
                image_b64=base64.b64encode(image_bytes).decode(),
                image_mime="image/png")
            data = llm_provider.extract_json(reply)
            fields = _fields_from_vision(data.get("fields") or {})
            method = f"llm:{cfg.provider}"
            llm_thresholds = _intkeys((data.get("thresholds") or {}).get("right")), \
                _intkeys((data.get("thresholds") or {}).get("left"))
            if any(v for pair in llm_thresholds for v in pair.values()):
                thresholds = {
                    "ok": True,
                    "method": f"llm:{cfg.provider}",
                    "right": llm_thresholds[0],
                    "left": llm_thresholds[1],
                    "confidence": {
                        "right": _intkeys((data.get("confidence") or {}).get("right")),
                        "left": _intkeys((data.get("confidence") or {}).get("left")),
                    },
                    "warnings": [],
                }
        except Exception as exc:
            notes.append(f"AI vision failed ({str(exc)[:120]}) — fell back to "
                         "offline reading.")
            method = "none"

    if method == "none":
        available, why = ocr_available()
        if available:
            try:
                import pytesseract
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                page = pytesseract.image_to_string(gray)
                fields = parse_fields(page)
                method = "tesseract"
            except Exception as exc:
                notes.append(f"Offline OCR failed ({str(exc)[:120]}).")
        else:
            notes.append(why)

    regions = text_regions(img, chart)

    return {
        "ok": True,
        "method": method,
        "page": {"w": img.shape[1], "h": img.shape[0]},
        "chart": chart,
        "thresholds": thresholds,
        "fields": fields,
        # Every field this module knows how to carry, so the UI can show the
        # ones it did NOT read as empty boxes to fill rather than hiding them.
        "expected_fields": [
            {"key": k, "label": v["label"], "kind": v["kind"]}
            for k, v in FIELD_PATTERNS.items()
        ],
        "text_regions": regions,
        "notes": notes,
        "guided": method == "none",
        "human_in_the_loop": (
            "Everything read from this page is a suggestion. Confirm the "
            "thresholds in the entry grid and the fields beside their crops "
            "before anything is analysed or saved."),
    }
