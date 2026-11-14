"""Audiogram symbol recognition — the shape decides the ear, not the colour.

WHY THIS MODULE EXISTS. The digitizer used to find symbols with two HSV
masks: saturated red meant the right ear, saturated blue the left. That works
on a colour printout and fails completely on everything else — a photocopy, a
fax, a scan saved in greyscale, a chart drawn in one pen, a thermal printout
from the audiometer itself. On any of those the old pipeline reported "no
red/blue audiogram symbols detected", which is not a near-miss: it is the
whole feature unavailable for what is probably the commonest kind of paper
audiogram in a district hospital.

The ear is not a colour. It is a SYMBOL, and the symbol set is standard
(ASHA; BSA Recommended Procedure, pure-tone audiometry):

    ear      air conduction        bone conduction
             unmasked  masked      unmasked  masked
    right    O         triangle    <         [
    left     X         square      >         ]

There is a geometric regularity in the bone-conduction set that makes it
tractable: every RIGHT-ear mark opens to the right, and every LEFT-ear mark
opens to the left. (The convention places right-ear bone symbols to the left
of the frequency line and left-ear symbols to its right, each opening back
toward the line.) So for those four, the OPENING DIRECTION gives the ear and
the presence of a vertical spine gives masked-versus-unmasked:

    [  spine on the left,  serifs opening right   -> right, masked
    <  apex  on the left,  strokes opening right  -> right, unmasked
    ]  spine on the right, serifs opening left    -> left, masked
    >  apex  on the right, strokes opening left   -> left, unmasked

The four air-conduction marks are closed shapes and are separated by where
their ink sits relative to the bounding box: a circle runs through the edge
midpoints and misses the corners; a cross does the opposite; a square hits
both; a triangle hits the bottom corners and the top edge midpoint only.

NOTHING HERE GUESSES. A mark whose features do not clearly match one symbol
comes back as ``unknown`` with its measurements attached, so the caller can
report "a mark was found at 4000 Hz that could not be identified" instead of
filing it under whichever class scored a hair higher. On a clinical document
being transcribed for a human to confirm, a labelled ``unknown`` is worth
more than a confident coin flip.

Colour is still used where it exists — see ``vision.py`` — but as
CORROBORATION for a shape decision rather than as the decision itself.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

#: label -> (ear, conduction, masked). The complete standard set this module
#: recognises. ``vision.py`` maps these onto threshold entries.
SYMBOL_MEANING: Dict[str, Tuple[str, str, bool]] = {
    "O": ("right", "ac", False),
    "triangle": ("right", "ac", True),
    "X": ("left", "ac", False),
    "square": ("left", "ac", True),
    "<": ("right", "bc", False),
    "[": ("right", "bc", True),
    ">": ("left", "bc", False),
    "]": ("left", "bc", True),
}

#: How each symbol is written in a report, for the UI and the warnings.
SYMBOL_NAME: Dict[str, str] = {
    "O": "O (right air, unmasked)",
    "triangle": "△ (right air, masked)",
    "X": "X (left air, unmasked)",
    "square": "□ (left air, masked)",
    "<": "< (right bone, unmasked)",
    "[": "[ (right bone, masked)",
    ">": "> (left bone, unmasked)",
    "]": "] (left bone, masked)",
    "unknown": "unidentified mark",
}

#: Below this the shape decision is not trusted and the label is ``unknown``.
#: Set high on purpose: a wrong ear is a wrong audiogram, and the caller has a
#: colour signal and an x-offset convention to fall back on.
MIN_SHAPE_CONFIDENCE = 0.55


# ==========================================================================
# geometric features
# ==========================================================================

def _ink_fraction(mask: np.ndarray, y0: float, y1: float,
                  x0: float, x1: float) -> float:
    """Fraction of a sub-rectangle of the bounding box that is ink.

    Bounds are fractions of the box, so the measure is scale-free: the same
    number comes back whether the symbol was photographed at 12 pixels across
    or 60.
    """
    h, w = mask.shape
    r0, r1 = int(round(y0 * h)), max(int(round(y1 * h)), int(round(y0 * h)) + 1)
    c0, c1 = int(round(x0 * w)), max(int(round(x1 * w)), int(round(x0 * w)) + 1)
    patch = mask[r0:min(r1, h), c0:min(c1, w)]
    if patch.size == 0:
        return 0.0
    return float(patch.mean())


def _row_mean_x(mask: np.ndarray, y0: float, y1: float) -> Optional[float]:
    """Mean x of the ink in a horizontal band, as a fraction of the width."""
    h, w = mask.shape
    r0, r1 = int(round(y0 * h)), max(int(round(y1 * h)), int(round(y0 * h)) + 1)
    band = mask[r0:min(r1, h), :]
    if band.size == 0 or band.sum() == 0:
        return None
    xs = np.nonzero(band)[1]
    return float(xs.mean() / max(w - 1, 1))


def _column_coverage(mask: np.ndarray, x0: float, x1: float) -> float:
    """Fraction of ROWS that have any ink inside a vertical strip.

    This is what separates a spine from an apex. A ``[`` has ink in its
    leftmost strip on nearly every row; a ``<`` has ink there only on the few
    rows around its point.
    """
    h, w = mask.shape
    c0, c1 = int(round(x0 * w)), max(int(round(x1 * w)), int(round(x0 * w)) + 1)
    strip = mask[:, c0:min(c1, w)]
    if strip.size == 0:
        return 0.0
    return float((strip.sum(axis=1) > 0).mean())


def features(mask: np.ndarray) -> dict:
    """Scale-free shape descriptors for one symbol, cropped to its bounds.

    ``mask`` is a boolean or 0/1 array of just this component's pixels.
    """
    mask = (np.asarray(mask) > 0).astype(np.uint8)
    h, w = mask.shape
    area = float(mask.sum())
    if area == 0 or h < 3 or w < 3:
        return {"degenerate": True}

    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP,
                                           cv2.CHAIN_APPROX_SIMPLE)
    external = max(contours, key=cv2.contourArea) if contours else None
    perimeter = cv2.arcLength(external, True) if external is not None else 0.0
    hull_area = cv2.contourArea(cv2.convexHull(external)) if external is not None else 0.0
    poly_area = cv2.contourArea(external) if external is not None else 0.0

    # A hole means the stroke closes on itself: O, square and triangle have
    # one, X and the brackets do not. Taken from the contour hierarchy rather
    # than an Euler number so a nick in the stroke from gridline removal does
    # not flip the answer: a child contour of any size counts.
    has_hole = False
    if hierarchy is not None and len(contours) > 1:
        # hierarchy[0][i] = [next, prev, first_child, parent]
        for i, node in enumerate(hierarchy[0]):
            if node[3] != -1 and cv2.contourArea(contours[i]) > 0.02 * h * w:
                has_hole = True
                break

    circularity = (4 * math.pi * poly_area / (perimeter ** 2)
                   if perimeter > 0 else 0.0)
    vertices = 0
    if external is not None and perimeter > 0:
        approx = cv2.approxPolyDP(external, 0.045 * perimeter, True)
        vertices = len(approx)

    # Corners versus edge midpoints — the air-conduction discriminator.
    #
    # THE CORNER PROBE HAS TO BE TIGHT. A circle inscribed in its bounding box
    # comes within 0.146 of each corner (0.5 − 0.5/√2), so a probe box of the
    # 0.32 used for the edges catches the ring as well as a square's actual
    # corner, and O and □ become indistinguishable — which is how O was read
    # as □ every time. At 0.16 the ring falls outside the box while a square's
    # corner and a cross's arm tip are both squarely inside it.
    tight = 0.16
    corners = [
        _ink_fraction(mask, 0, tight, 0, tight),
        _ink_fraction(mask, 0, tight, 1 - tight, 1),
        _ink_fraction(mask, 1 - tight, 1, 0, tight),
        _ink_fraction(mask, 1 - tight, 1, 1 - tight, 1),
    ]
    # The edge probes are deliberately LONG along their own edge: a gridline
    # removed through the middle of a symbol takes out a few rows, and a probe
    # only as tall as it is wide can lose most of its ink to that. Audiogram
    # values are multiples of 5 dB and gridlines run every 10, so a symbol
    # sitting on a line is the common case, not the awkward one.
    band = 0.18
    edges = [
        _ink_fraction(mask, 0, band, 0.3, 0.7),            # top
        _ink_fraction(mask, 1 - band, 1, 0.3, 0.7),        # bottom
        _ink_fraction(mask, 0.3, 0.7, 0, band),            # left
        _ink_fraction(mask, 0.3, 0.7, 1 - band, 1),        # right
    ]

    x_top = _row_mean_x(mask, 0.0, 0.26)
    x_mid = _row_mean_x(mask, 0.37, 0.63)
    x_bot = _row_mean_x(mask, 0.74, 1.0)

    return {
        "degenerate": False,
        "height": h,
        "width": w,
        "aspect": w / h,
        "fill": area / (h * w),
        "solidity": poly_area / hull_area if hull_area > 0 else 0.0,
        "has_hole": has_hole,
        "circularity": circularity,
        "vertices": vertices,
        "corner_ink": float(np.mean(corners)),
        "corner_min": float(np.min(corners)),
        "edge_ink": float(np.mean(edges)),
        "corners": corners,
        "edges": edges,
        "x_top": x_top,
        "x_mid": x_mid,
        "x_bot": x_bot,
        # Opening direction: positive means the top and bottom of the mark sit
        # to the right of its middle, i.e. it opens rightward.
        "open_right": (None if None in (x_top, x_mid, x_bot)
                       else ((x_top + x_bot) / 2) - x_mid),
        "left_spine": _column_coverage(mask, 0.0, 0.26),
        "right_spine": _column_coverage(mask, 0.74, 1.0),
        "centre_ink": _ink_fraction(mask, 0.38, 0.62, 0.38, 0.62),
    }


# ==========================================================================
# classification
# ==========================================================================

def _score_bracket_family(f: dict) -> Dict[str, float]:
    """Scores for ``[``, ``]``, ``<`` and ``>``.

    Two independent decisions, each scored on its own evidence:
      WHICH EAR     the opening direction
      MASKED?       a full-height spine on the closed side, or just an apex
    """
    out: Dict[str, float] = {}
    opening = f.get("open_right")
    if opening is None:
        return out

    # The opening has to be decisive relative to the mark's own width. A
    # shift of less than ~8% of the width is noise, not a direction.
    strength = min(abs(opening) / 0.18, 1.0)
    if strength < 0.25:
        return out

    opens_right = opening > 0
    # The closed side is the one the mark opens away from.
    spine = f["left_spine"] if opens_right else f["right_spine"]
    # A spine covers nearly every row; an apex touches only the middle few.
    spine_score = min(max((spine - 0.45) / 0.35, 0.0), 1.0)
    apex_score = min(max((0.62 - spine) / 0.35, 0.0), 1.0)

    # A closed shape is never a bracket, and a bracket is taller than wide.
    shape_ok = 1.0
    if f["has_hole"]:
        shape_ok *= 0.25
    if f["aspect"] > 1.15:
        shape_ok *= 0.45

    masked_label = "[" if opens_right else "]"
    unmasked_label = "<" if opens_right else ">"
    out[masked_label] = strength * spine_score * shape_ok
    out[unmasked_label] = strength * apex_score * shape_ok
    return out


def _score_air_family(f: dict) -> Dict[str, float]:
    """Scores for ``O``, ``X``, ``triangle`` and ``square``.

    All four are roughly as wide as they are tall, so they are separated by
    WHERE the ink sits in the bounding box rather than by its outline, which
    gridline removal and photographic blur both distort.
    """
    out: Dict[str, float] = {}
    aspect = f["aspect"]
    # Strongly non-square marks are brackets, not air symbols.
    if not (0.55 <= aspect <= 1.8):
        return out
    squareness = min(max(1.0 - abs(1.0 - aspect) / 0.55, 0.0), 1.0)

    corners, edges = f["corners"], f["edges"]
    corner_ink, edge_ink = f["corner_ink"], f["edge_ink"]
    # How many of the four tight corners carry real ink. This is the cleanest
    # single number in the family: 4 for a square or a cross, 0 for a circle,
    # 2 (the bottom pair) for a triangle.
    filled_corners = sum(1 for c in corners if c > 0.12)
    edge_present = sum(1 for e in edges if e > 0.10)

    # O — a ring: every edge midpoint inked, no corner inked, a closed stroke
    # round a clear middle. Circularity separates it from a square outline
    # (1.0 against 0.79) and so does the vertex count.
    o_score = squareness * min(max((edge_ink - corner_ink) / 0.14, 0.0), 1.0)
    o_score *= min(max((4 - filled_corners) / 3.0, 0.0), 1.0)
    o_score *= min(max((edge_present - 1) / 2.0, 0.0), 1.0)
    o_score *= (1.0 if f["has_hole"] else 0.55)
    o_score *= min(max((f["circularity"] - 0.5) / 0.3, 0.35), 1.0)
    # A ring is still a ring with the connector polyline drawn through it:
    # the line puts ink across the middle, but the arcs either side of it
    # still enclose a hole. Only ink in the middle of a shape that closes
    # round NOTHING argues against a circle.
    o_score *= (0.3 if (f["centre_ink"] > 0.35 and not f["has_hole"]) else 1.0)
    out["O"] = o_score

    # X — two diagonals: all four corners inked, the edge midpoints empty,
    # ink crossing the centre, no hole.
    x_score = squareness * min(max((corner_ink - edge_ink) / 0.12, 0.0), 1.0)
    x_score *= 1.0 if filled_corners == 4 else 0.3 if filled_corners == 3 else 0.0
    x_score *= min(max((2 - edge_present) / 2.0, 0.0), 1.0)
    x_score *= (0.3 if f["has_hole"] else 1.0)
    x_score *= min(max(f["centre_ink"] / 0.18, 0.35), 1.0)
    out["X"] = x_score

    # square — the outline passes through the corners AND the edge midpoints,
    # four vertices, a hole, and it is distinctly less circular than a ring.
    sq_score = squareness * min(max((min(corner_ink, edge_ink) - 0.08) / 0.2, 0.0), 1.0)
    sq_score *= 1.0 if filled_corners >= 3 else 0.0
    sq_score *= min(max((edge_present - 1) / 2.0, 0.0), 1.0)
    sq_score *= (1.0 if f["has_hole"] else 0.5)
    sq_score *= 1.0 if f["vertices"] in (4, 5) else 0.6
    # A perfect ring scores ~1.0 here and a square outline ~0.79; anything
    # above 0.92 is a circle however its corners probe.
    sq_score *= 0.25 if f["circularity"] > 0.92 else 1.0
    sq_score *= (0.4 if f["centre_ink"] > 0.35 else 1.0)
    out["square"] = sq_score

    # triangle (apex up) — the two BOTTOM corners inked, the top corners
    # clear, and ink at the top edge midpoint where the apex sits.
    top_corners = (corners[0] + corners[1]) / 2
    bottom_corners = (corners[2] + corners[3]) / 2
    tri = min(max((bottom_corners - top_corners) / 0.12, 0.0), 1.0)
    tri *= min(max((edges[0] - top_corners) / 0.10, 0.0), 1.0)
    tri_score = squareness * tri
    tri_score *= 1.0 if f["vertices"] in (3, 4) else 0.6
    tri_score *= (1.0 if f["has_hole"] else 0.6)
    out["triangle"] = tri_score

    return out


def classify(mask: np.ndarray) -> dict:
    """Identify one audiogram symbol from its pixels.

    Returns ``{"symbol", "confidence", "ear", "conduction", "masked",
    "scores", "features"}``. ``symbol`` is ``"unknown"`` when nothing scores
    above ``MIN_SHAPE_CONFIDENCE`` or when the two best candidates are too
    close to separate — in which case ``ear`` and ``conduction`` are None and
    the caller decides what to do with a mark it cannot name.
    """
    f = features(mask)
    if f.get("degenerate"):
        return {"symbol": "unknown", "confidence": 0.0, "ear": None,
                "conduction": None, "masked": None, "scores": {},
                "features": f, "reason": "mark too small to measure"}

    scores = {**_score_air_family(f), **_score_bracket_family(f)}
    scores = {k: round(float(v), 3) for k, v in scores.items() if v > 0}
    if not scores:
        return {"symbol": "unknown", "confidence": 0.0, "ear": None,
                "conduction": None, "masked": None, "scores": {},
                "features": f, "reason": "no symbol shape matched"}

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    label, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

    # Two candidates within a hair of each other is not a decision. The margin
    # matters most exactly where a mistake matters most: O against X is the
    # difference between the two ears.
    margin = score - runner_up
    if score < MIN_SHAPE_CONFIDENCE or margin < 0.12:
        return {"symbol": "unknown", "confidence": round(score, 3), "ear": None,
                "conduction": None, "masked": None, "scores": scores,
                "features": f,
                "reason": (f"closest shapes are {ranked[0][0]} and "
                           f"{ranked[1][0] if len(ranked) > 1 else '—'}, too "
                           "similar to separate")}

    ear, conduction, masked = SYMBOL_MEANING[label]
    return {
        "symbol": label,
        "name": SYMBOL_NAME[label],
        # Blend the absolute score with how far clear of the runner-up it is.
        "confidence": round(min(1.0, score * (0.7 + 0.3 * min(margin / 0.3, 1.0))), 3),
        "ear": ear,
        "conduction": conduction,
        "masked": masked,
        "scores": scores,
        "features": f,
    }


# ==========================================================================
# finding the marks
# ==========================================================================

def extract_marks(gray: np.ndarray, grid: dict, min_dim: int = 5,
                  binary: Optional[np.ndarray] = None) -> List[dict]:
    """Every symbol-sized mark inside the plot area, with its own pixel mask.

    ``binary`` overrides the thresholding step with a mask the caller has
    already built — used to run this over ONE EAR'S COLOUR at a time. That
    matters for a case shape cannot solve: when both ears share a threshold,
    the red O and the blue X are drawn at the same point and overlap into a
    blob that is neither symbol. A human reading that chart separates them by
    colour, and so can this; on a greyscale chart the ambiguity is real and is
    reported rather than guessed.

    Three things have to be removed before connected components mean anything:

    GRIDLINES, which otherwise join every symbol on a row into one blob. They
    are taken out morphologically, by the same long-line opening the grid
    detector uses to find them.

    THE CONNECTOR POLYLINE between air-conduction symbols. On a colour chart
    this was invisible to the HSV masks because it is printed pale; in
    greyscale it is as dark as the symbols and welds the whole curve into a
    single component. It is removed by length: a connector segment spans the
    gap between two frequency columns, which is several times longer than any
    symbol is wide, so a Hough transform with a minimum length of half the
    column spacing finds connectors and never a symbol stroke.

    THE AXIS FURNITURE — labels, titles, the legend — which is excluded by
    requiring a mark to sit inside the plotting rectangle.
    """
    h, w = gray.shape
    if binary is None:
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                       cv2.THRESH_BINARY_INV, 15, 10)

    # --- gridlines -------------------------------------------------------
    horiz = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 10, 10), 1)))
    vert = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(h // 10, 10))))
    lines = cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8))
    marks = cv2.bitwise_and(binary, cv2.bitwise_not(lines))

    # --- the connector polyline -----------------------------------------
    #
    # The kernel that pulls out gridlines (w/10 long) also catches a connector
    # segment, because a segment spans a whole column gap — wider than a tenth
    # of the image. That is wanted: the connector has to go, or every symbol on
    # a flat stretch of the curve is welded to its neighbours. What it costs is
    # a cut straight through the symbols at either end, since the connector is
    # drawn from marker centre to marker centre.
    spacing = max(float(grid.get("col_spacing") or 0.0), 1.0)
    min_len = max(int(spacing * 0.5), 12)
    segments = cv2.HoughLinesP(marks, 1, np.pi / 180,
                               threshold=max(int(min_len * 0.6), 10),
                               minLineLength=min_len, maxLineGap=3)
    if segments is not None:
        stroke = np.zeros_like(marks)
        for x1, y1, x2, y2 in segments[:, 0]:
            cv2.line(stroke, (x1, y1), (x2, y2), 255, 2)
        marks = cv2.bitwise_and(marks, cv2.bitwise_not(stroke))

    # Repair the cuts both removals leave in a symbol they passed through.
    #
    # The kernel has to be wider than the gap it bridges. A gridline is one or
    # two pixels, widened to three or four by the dilate above, and a
    # connector adds its own two — so a 3x3 close cannot span either and
    # leaves symbols in halves. This matters constantly rather than
    # occasionally: thresholds are multiples of 5 dB and gridlines run every
    # 10, so a symbol sitting on a line is the rule. A halved circle loses the
    # ink at its left and right edge midpoints, which is precisely the
    # evidence that tells it from a cross.
    marks = cv2.morphologyEx(marks, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    # --- components ------------------------------------------------------
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(marks)
    xs = list(grid["freq_x"].values())
    # A mark belongs to a frequency column: air conduction sits ON the column
    # and bone conduction a quarter of a column beside it. Anything further
    # out is axis furniture — the dB tick labels sit half a column to the left
    # of the 250 Hz line, and a looser bound swept them all in as "marks that
    # could not be identified".
    x_lo, x_hi = min(xs) - spacing * 0.4, max(xs) + spacing * 0.4
    y_lo, y_hi = grid["y_top"] - 6, grid["y_bottom"] + 6
    # A symbol is a fraction of the column spacing across. Anything much
    # bigger is a merged blob or a stray line; anything smaller is speckle.
    max_dim = max(int(spacing * 0.95), 14)

    out: List[dict] = []
    for i in range(1, n):
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        area = int(stats[i, cv2.CC_STAT_AREA])
        cx, cy = float(centroids[i][0]), float(centroids[i][1])
        if not (x_lo <= cx <= x_hi and y_lo <= cy <= y_hi):
            continue
        if area < 12 or bh < min_dim:
            continue

        if bw <= max_dim and bh <= max_dim:
            out.append({
                "cx": cx, "cy": cy, "area": area,
                "bbox": (x, y, bw, bh),
                "mask": (labels[y:y + bh, x:x + bw] == i).astype(np.uint8),
            })
            continue

        # A component wider than half a column is two or more symbols still
        # joined by a connector the removal above did not reach — a diagonal
        # run too short for the Hough minimum, usually. Rather than discard
        # it, cut it at the frequency columns: a symbol can only be on or
        # beside one, so a window around each column isolates it and leaves
        # the connecting stretch outside.
        out.extend(_split_on_columns(labels == i, (x, y, bw, bh), grid, spacing,
                                     min_dim, max_dim))
    return out


def _split_on_columns(component: np.ndarray, bbox, grid: dict, spacing: float,
                      min_dim: int, max_dim: int) -> List[dict]:
    """Recover individual symbols from a run of them joined by a connector."""
    x, y, bw, bh = bbox
    found: List[dict] = []
    half = max(spacing * 0.22, 8.0)
    for freq, col_x in grid["freq_x"].items():
        for offset in (0.0, -0.26, 0.26):
            cx0 = col_x + offset * spacing
            lo, hi = int(round(cx0 - half)), int(round(cx0 + half))
            if hi <= x or lo >= x + bw:
                continue
            window = np.zeros_like(component, dtype=np.uint8)
            window[:, max(lo, 0):hi] = 1
            piece = (component.astype(np.uint8) & window)
            if piece.sum() < 12:
                continue
            n, labels, stats, centroids = cv2.connectedComponentsWithStats(piece)
            for i in range(1, n):
                pw = int(stats[i, cv2.CC_STAT_WIDTH])
                ph = int(stats[i, cv2.CC_STAT_HEIGHT])
                pa = int(stats[i, cv2.CC_STAT_AREA])
                px = int(stats[i, cv2.CC_STAT_LEFT])
                py = int(stats[i, cv2.CC_STAT_TOP])
                if pa < 12 or pw < min_dim or ph < min_dim:
                    continue
                if pw > max_dim or ph > max_dim:
                    continue
                # The window edge can clip a symbol; require the piece to sit
                # clear of both edges so a sliced-off arc is not read as a
                # bracket. A symbol centred on its column always does.
                if px <= max(lo, 0) + 1 or px + pw >= hi - 1:
                    continue
                found.append({
                    "cx": float(centroids[i][0]), "cy": float(centroids[i][1]),
                    "area": pa, "bbox": (px, py, pw, ph),
                    "mask": (labels[py:py + ph, px:px + pw] == i).astype(np.uint8),
                    "from_chain": True,
                })
    # The same symbol can fall inside two overlapping windows.
    unique: List[dict] = []
    for f in sorted(found, key=lambda m: -m["area"]):
        if not any(abs(f["cx"] - u["cx"]) < spacing * 0.12
                   and abs(f["cy"] - u["cy"]) < max(min_dim, 6)
                   for u in unique):
            unique.append(f)
    return unique


def colour_mask(img_bgr: np.ndarray, colour: str) -> np.ndarray:
    """Binary mask of the saturated red or blue ink, for a per-ear pass.

    The saturation and value floors are deliberately low. A faded photocopy
    of a colour chart keeps its hue long after it has lost its vividness, and
    a mark that is recognisably red to a reader should be recognisably red
    here.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    if colour == "red":
        mask = (cv2.inRange(hsv, (0, 50, 50), (12, 255, 255))
                | cv2.inRange(hsv, (164, 50, 50), (180, 255, 255)))
    else:
        mask = cv2.inRange(hsv, (92, 50, 50), (138, 255, 255))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def is_greyscale(img_bgr: np.ndarray, threshold: float = 12.0) -> bool:
    """Whether the image carries usable colour at all.

    Measured as the mean HSV saturation over the pixels dark enough to be
    ink. A pale scan of a colour chart can keep a little saturation
    everywhere, so the question is specifically whether the MARKS are
    coloured — averaging over the whole frame would let a cream-coloured
    paper background answer it.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    ink = gray < max(int(gray.mean()) - 25, 60)
    if ink.sum() < 50:
        return True
    return float(hsv[:, :, 1][ink].mean()) < threshold
