"""Image descriptors for otoscope views — OpenCV and NumPy only.

Why hand-built features rather than a convolutional network: the labelled
reference set that ships with this repository is 62 images across 8 classes.
A network trained on that would memorise it. Features that encode what a
clinician actually looks at — how red the drum is, whether the cone of light
is there, whether there is a hole and where it sits — generalise from tens of
examples instead of tens of thousands, and every one of them can be shown to
the user as a number they can argue with.

The same feature vector is used when the much larger Kaggle otoscope dataset
is present (see ``scripts/train_otoscopy.py``); only the training data
changes, not the representation.

Every descriptor is:
  * computed inside the otoscope's circular field of view, so the black
    surround never contributes,
  * normalised for exposure, because otoscope brightness varies wildly, and
  * rotation-aware only where rotation is clinically meaningful (the attic is
    superior, a marginal perforation touches the rim), otherwise
    rotation-invariant.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

#: Working resolution. Large enough for texture, small enough to stay fast.
WORK_SIZE = 256

#: Ordered feature names — the model depends on this order, so append only.
FEATURE_NAMES: List[str] = []


def _register(names: List[str]) -> List[str]:
    FEATURE_NAMES.extend(names)
    return names


# --------------------------------------------------------------------------
# field of view
# --------------------------------------------------------------------------
def field_of_view(bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Crop to the illuminated otoscope circle and return (image, mask).

    Otoscope photographs are a bright disc on a black surround. Including the
    surround would make "how dark is this image" a function of how zoomed-out
    the camera was, which is meaningless. Some datasets ship images already
    cropped to the disc; the fallback covers that case.
    """
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grey, (9, 9), 0)
    # Otsu separates "lit" from "surround" without a magic constant.
    _, lit = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    lit = cv2.morphologyEx(lit, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))

    # Take the OUTLINE of the lit region and fill it. Using the thresholded
    # pixels directly would punch a hole in the mask wherever the view is
    # dark — which is precisely where a perforation is. Masking out the
    # perforation before looking for perforations is how this went wrong
    # first time round.
    contours, _ = cv2.findContours(lit, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = grey.shape
    if contours:
        biggest = max(contours, key=cv2.contourArea)
        x, y, cw, ch = cv2.boundingRect(biggest)
        area = cv2.contourArea(biggest)
        # Only trust the crop when the disc is a substantial, roughly square
        # part of the frame; otherwise the image is already cropped, or the
        # threshold latched onto a specular highlight.
        if area > 0.12 * h * w and 0.5 < cw / max(ch, 1) < 2.0:
            filled = np.zeros_like(lit)
            cv2.drawContours(filled, [biggest], -1, 255, thickness=cv2.FILLED)
            crop = bgr[y:y + ch, x:x + cw]
            mask = filled[y:y + ch, x:x + cw]
            if min(crop.shape[:2]) >= 32:
                return crop, mask
    return bgr, np.full(grey.shape, 255, np.uint8)


def prepare(bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Crop, resize to the working square, and return (image, boolean mask)."""
    crop, mask = field_of_view(bgr)
    img = cv2.resize(crop, (WORK_SIZE, WORK_SIZE), interpolation=cv2.INTER_AREA)
    msk = cv2.resize(mask, (WORK_SIZE, WORK_SIZE), interpolation=cv2.INTER_NEAREST)

    # An inscribed circle guards against a rectangular fallback mask letting
    # in dark corners that the classifier would read as perforation.
    circle = np.zeros((WORK_SIZE, WORK_SIZE), np.uint8)
    cv2.circle(circle, (WORK_SIZE // 2, WORK_SIZE // 2), WORK_SIZE // 2 - 2, 255, -1)
    msk = cv2.bitwise_and(msk, circle)
    if msk.sum() < 0.05 * 255 * WORK_SIZE * WORK_SIZE:
        msk = circle
    return img, msk > 0


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def _rings(mask: np.ndarray) -> List[np.ndarray]:
    """Three concentric zones: centre, mid, periphery.

    Position carries diagnosis. A hole in the middle is a central
    perforation; the same hole at the rim is a marginal one.
    """
    yy, xx = np.mgrid[0:WORK_SIZE, 0:WORK_SIZE]
    c = (WORK_SIZE - 1) / 2.0
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (WORK_SIZE / 2.0)
    return [mask & (r < 0.4), mask & (r >= 0.4) & (r < 0.75), mask & (r >= 0.75)]


def _quadrants(mask: np.ndarray) -> List[np.ndarray]:
    """Superior / inferior halves and left / right halves.

    The pars flaccida — where attic disease lives — is superior. Splitting on
    image axes is a coarse proxy, but the reference views are consistently
    oriented and it measurably separates attic from central defects.
    """
    h = WORK_SIZE // 2
    sup, inf = np.zeros_like(mask), np.zeros_like(mask)
    sup[:h, :], inf[h:, :] = mask[:h, :], mask[h:, :]
    left, right = np.zeros_like(mask), np.zeros_like(mask)
    left[:, :h], right[:, h:] = mask[:, :h], mask[:, h:]
    return [sup, inf, left, right]


def _stats(values: np.ndarray) -> List[float]:
    if values.size == 0:
        return [0.0, 0.0]
    return [float(values.mean()), float(values.std())]


# --------------------------------------------------------------------------
# descriptors
# --------------------------------------------------------------------------
def _colour_block(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """Colour, exposure-normalised, globally and by zone."""
    bgr = img.astype(np.float32) / 255.0
    b, g, r = bgr[..., 0], bgr[..., 1], bgr[..., 2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hue, sat, val = hsv[..., 0] * 2.0, hsv[..., 1] / 255.0, hsv[..., 2] / 255.0

    inside = mask
    lum = np.clip((r + g + b) / 3.0, 1e-3, None)
    # Chromaticity rather than raw channels: a dim photo of a red drum is
    # still a red drum.
    redness = (r - (g + b) / 2.0) / lum
    yellowness = ((r + g) / 2.0 - b) / lum

    feats: List[float] = []
    feats += _stats(redness[inside])
    feats += _stats(yellowness[inside])
    feats += _stats(sat[inside])
    feats += _stats(val[inside])
    # Hue histogram over the range otoscope images actually occupy.
    hist, _ = np.histogram(hue[inside], bins=8, range=(0, 360))
    total = max(hist.sum(), 1)
    feats += list((hist / total).astype(float))

    for zone in _rings(inside):
        feats += _stats(redness[zone])[:1] + _stats(val[zone])[:1]
    for zone in _quadrants(inside):
        feats += _stats(redness[zone])[:1] + _stats(val[zone])[:1]

    named = {
        "redness": round(float(redness[inside].mean()) if inside.any() else 0.0, 4),
        "yellowness": round(float(yellowness[inside].mean()) if inside.any() else 0.0, 4),
        "saturation": round(float(sat[inside].mean()) if inside.any() else 0.0, 4),
        "brightness": round(float(val[inside].mean()) if inside.any() else 0.0, 4),
    }
    return feats, named


_register(
    ["redness_mean", "redness_sd", "yellow_mean", "yellow_sd",
     "sat_mean", "sat_sd", "val_mean", "val_sd"]
    + [f"hue_hist_{i}" for i in range(8)]
    + [f"ring{i}_{k}" for i in range(3) for k in ("redness", "val")]
    + [f"quad{i}_{k}" for i in range(4) for k in ("redness", "val")]
)


def _light_reflex(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """The cone of light: the single most specific sign of a normal drum.

    A healthy tympanic membrane reflects the otoscope lamp as a bright,
    low-saturation wedge in the antero-inferior quadrant. Effusion, retraction
    and perforation all destroy or displace it.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    val, sat = hsv[..., 2].astype(np.float32), hsv[..., 1].astype(np.float32)
    inside_vals = val[mask]
    if inside_vals.size == 0:
        return [0.0, 0.0, 0.0, 0.0], {"cone_of_light": 0.0}

    # Relative threshold: "bright for this image", not "bright in absolute
    # terms", because otoscope exposure is not standardised.
    cut = np.percentile(inside_vals, 96)
    bright = ((val >= max(cut, 150)) & (sat < 90) & mask).astype(np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    n, labels, stats, cents = cv2.connectedComponentsWithStats(bright)
    area_frac, radial, elong, count = 0.0, 0.0, 0.0, 0.0
    if n > 1:
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        area = float(stats[idx, cv2.CC_STAT_AREA])
        area_frac = area / max(float(mask.sum()), 1.0)
        cx, cy = cents[idx]
        c = (WORK_SIZE - 1) / 2.0
        radial = float(np.hypot(cx - c, cy - c) / (WORK_SIZE / 2.0))
        bw, bh = stats[idx, cv2.CC_STAT_WIDTH], stats[idx, cv2.CC_STAT_HEIGHT]
        elong = float(max(bw, bh) / max(min(bw, bh), 1))
        # Many small speculars (wet, irregular surface) read differently from
        # one clean wedge.
        count = float(sum(1 for i in range(1, n)
                          if stats[i, cv2.CC_STAT_AREA] > 0.001 * mask.sum()))

    feats = [area_frac, radial, min(elong, 6.0) / 6.0, min(count, 12.0) / 12.0]
    return feats, {"cone_of_light": round(area_frac, 4),
                   "reflex_offset": round(radial, 4)}


_register(["reflex_area", "reflex_radial", "reflex_elongation", "reflex_count"])


def _dark_defect(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """Dark regions: a perforation is a hole through which nothing reflects.

    Reported by position as well as size, because central, marginal and attic
    defects differ chiefly in where they sit.
    """
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    inside = grey[mask]
    if inside.size == 0:
        return [0.0] * 6, {"dark_fraction": 0.0}

    median = float(np.median(inside))
    dark = ((grey < median * 0.45) & mask).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    frac = float(dark.sum()) / max(float(mask.sum()), 1.0)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(dark)
    biggest, radial, superior, solidity = 0.0, 0.0, 0.0, 0.0
    if n > 1:
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        area = float(stats[idx, cv2.CC_STAT_AREA])
        biggest = area / max(float(mask.sum()), 1.0)
        cx, cy = cents[idx]
        c = (WORK_SIZE - 1) / 2.0
        radial = float(np.hypot(cx - c, cy - c) / (WORK_SIZE / 2.0))
        superior = float((c - cy) / (WORK_SIZE / 2.0))  # +1 top, -1 bottom
        bw, bh = stats[idx, cv2.CC_STAT_WIDTH], stats[idx, cv2.CC_STAT_HEIGHT]
        solidity = area / max(float(bw * bh), 1.0)

    feats = [frac, biggest, radial, (superior + 1) / 2, solidity,
             float(min(n - 1, 10)) / 10.0]
    return feats, {"dark_fraction": round(frac, 4),
                   "defect_size": round(biggest, 4),
                   "defect_offset": round(radial, 4),
                   "defect_superior": round(superior, 4)}


_register(["dark_fraction", "dark_biggest", "dark_radial", "dark_superior",
           "dark_solidity", "dark_count"])


def _texture(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """Surface texture separates smooth membrane from granular wax and polyp."""
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(grey, cv2.CV_32F, ksize=3)
    gx = cv2.Sobel(grey, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(grey, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx ** 2 + gy ** 2)
    edges = cv2.Canny(cv2.GaussianBlur(grey, (3, 3), 0), 60, 160)

    inside = mask
    feats = [
        float(np.log1p(lap[inside].var())) / 10.0,
        float(magnitude[inside].mean()) / 255.0,
        float(magnitude[inside].std()) / 255.0,
        float((edges > 0)[inside].mean()),
    ]
    # Gradient-orientation histogram: radial vessel streaking in an inflamed
    # drum looks different from the uniform grain of wax.
    ang = (np.arctan2(gy, gx) + np.pi) * (180 / np.pi)
    strong = inside & (magnitude > np.percentile(magnitude[inside], 75)) \
        if inside.any() else inside
    hist, _ = np.histogram(ang[strong], bins=6, range=(0, 360))
    feats += list((hist / max(hist.sum(), 1)).astype(float))

    return feats, {"texture_energy": round(feats[1], 4),
                   "edge_density": round(feats[3], 4)}


_register(["lap_var", "grad_mean", "grad_sd", "edge_density"]
          + [f"orient_hist_{i}" for i in range(6)])


def _occlusion(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """How much of the view is filled by opaque brown/tan material.

    Cerumen has a narrow, distinctive hue band; separating it explicitly
    stops "dark and textured" from being confused with a perforation.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0] * 2.0, hsv[..., 1] / 255.0, hsv[..., 2] / 255.0
    wax = ((hue >= 8) & (hue <= 55) & (sat > 0.35) & (val > 0.12) & (val < 0.75) & mask)
    debris = ((hue >= 8) & (hue <= 60) & (sat > 0.25) & (val < 0.30) & mask)
    frac = float(wax.sum()) / max(float(mask.sum()), 1.0)
    feats = [frac, float(debris.sum()) / max(float(mask.sum()), 1.0)]

    # Wax fills the canal, so it tends to be one large blob rather than
    # scattered flecks.
    blob = 0.0
    n, _, stats, _ = cv2.connectedComponentsWithStats(wax.astype(np.uint8))
    if n > 1:
        blob = float(stats[1:, cv2.CC_STAT_AREA].max()) / max(float(mask.sum()), 1.0)
    feats.append(blob)
    return feats, {"wax_fraction": round(frac, 4), "wax_blob": round(blob, 4)}


_register(["wax_fraction", "debris_fraction", "wax_blob"])


def _vascularity(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """Injected vessels — the sign that distinguishes inflamed from merely pink."""
    bgr = img.astype(np.float32)
    r, g = bgr[..., 2], bgr[..., 1]
    excess_red = cv2.GaussianBlur(r - g, (3, 3), 0)
    strong = ((excess_red > 30) & mask)
    frac = float(strong.sum()) / max(float(mask.sum()), 1.0)

    # Vessels are thin: opening with a larger kernel removes them, and the
    # difference is a direct measure of fine red structure.
    thin = cv2.morphologyEx(strong.astype(np.uint8), cv2.MORPH_OPEN,
                            np.ones((7, 7), np.uint8))
    vessel_frac = frac - float(thin.sum()) / max(float(mask.sum()), 1.0)
    return [frac, max(vessel_frac, 0.0)], {
        "erythema": round(frac, 4), "vascular_streaking": round(max(vessel_frac, 0.0), 4)}


_register(["erythema", "vascular_streaking"])


def _translucency(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """Can middle-ear landmarks be seen through the drum?

    A normal membrane is translucent — the malleus handle shows through as a
    mid-scale linear structure. Effusion and sclerosis make it opaque, which
    shows up as a loss of mid-frequency structure while fine noise remains.
    """
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    fine = cv2.GaussianBlur(grey, (3, 3), 0)
    coarse = cv2.GaussianBlur(grey, (21, 21), 0)
    band = np.abs(fine - coarse)
    inside = mask
    energy = float(band[inside].mean()) / 255.0 if inside.any() else 0.0

    # Longest straight edge: the malleus handle is the only reliably linear
    # feature on a healthy drum.
    edges = cv2.Canny(cv2.GaussianBlur(
        cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0), 40, 120)
    edges = cv2.bitwise_and(edges, edges, mask=mask.astype(np.uint8) * 255)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30,
                            minLineLength=WORK_SIZE // 5, maxLineGap=6)
    longest = 0.0
    if lines is not None:
        longest = max(
            float(np.hypot(x2 - x1, y2 - y1)) for x1, y1, x2, y2 in lines[:, 0]
        ) / WORK_SIZE
    return [energy, min(longest, 1.0),
            float(len(lines)) / 40.0 if lines is not None else 0.0], {
        "structure_visible": round(energy, 4),
        "landmark_line": round(min(longest, 1.0), 4)}


_register(["band_energy", "longest_line", "line_count"])


# --------------------------------------------------------------------------
# spatial layout
# --------------------------------------------------------------------------
# The summary descriptors above answer "what does this ear look like". They
# cannot answer "where on the drum", and for otoscopy that is most of the
# diagnosis: the same dark defect is a central perforation in the middle of
# the pars tensa, a marginal one at the annulus, and an attic one superiorly.
# The blocks below encode position explicitly. Measured on the reference set,
# adding them lifted leave-one-image-out top-1 accuracy by roughly ten points
# over the summary descriptors alone.

POLAR_RINGS, POLAR_SECTORS = 6, 12
RADIAL_BINS = 10
COLOUR_SEGMENTS = 3


def _polar_grid(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:WORK_SIZE, 0:WORK_SIZE]
    c = (WORK_SIZE - 1) / 2.0
    radius = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (WORK_SIZE / 2.0)
    # Angle measured with the image "up" as 0.25, so superior sectors are a
    # fixed range and the attic keeps a stable address.
    angle = (np.arctan2(-(yy - c), xx - c) + np.pi) / (2 * np.pi)
    return radius, angle


def _polar_map(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """Mean Lab colour and edge energy in a radius x sector grid."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(grey, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(grey, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx ** 2 + gy ** 2)
    radius, angle = _polar_grid(mask)

    lightness = lab[..., 0]
    # Standardised per image: absolute brightness is a property of the lamp.
    mean = float(lightness[mask].mean()) if mask.any() else 0.0
    sd = float(lightness[mask].std()) + 1e-3

    feats: List[float] = []
    for i in range(POLAR_RINGS):
        for j in range(POLAR_SECTORS):
            cell = (mask
                    & (radius >= i / POLAR_RINGS) & (radius < (i + 1) / POLAR_RINGS)
                    & (angle >= j / POLAR_SECTORS) & (angle < (j + 1) / POLAR_SECTORS))
            if cell.sum() < 4:
                feats += [0.0, 0.0, 0.0, 0.0]
                continue
            feats += [
                float((lightness[cell].mean() - mean) / sd),
                float(lab[..., 1][cell].mean() - 128) / 40.0,
                float(lab[..., 2][cell].mean() - 128) / 40.0,
                float(magnitude[cell].mean()) / 255.0,
            ]
    return feats, {}


_register([f"polar_r{i}_s{j}_{k}"
           for i in range(POLAR_RINGS) for j in range(POLAR_SECTORS)
           for k in ("L", "a", "b", "grad")])


def _radial_profile(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, Any]]:
    """Brightness and colour as a function of distance from the centre.

    "Dark in the middle, pale at the rim" is a central perforation; the
    reverse is a shadowed canal wall. A single mean cannot tell them apart.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    radius, _ = _polar_grid(mask)
    lightness = lab[..., 0]
    mean = float(lightness[mask].mean()) if mask.any() else 0.0
    sd = float(lightness[mask].std()) + 1e-3

    feats: List[float] = []
    profile: List[float] = []
    for i in range(RADIAL_BINS):
        cell = mask & (radius >= i / RADIAL_BINS) & (radius < (i + 1) / RADIAL_BINS)
        if cell.sum() < 4:
            feats += [0.0, 0.0, 0.0]
            profile.append(0.0)
            continue
        norm = float((lightness[cell].mean() - mean) / sd)
        feats += [norm, float(lab[..., 1][cell].mean() - 128) / 40.0,
                  float(lightness[cell].std() / sd)]
        profile.append(round(norm, 3))
    return feats, {"radial_lightness": profile}


_register([f"radial{i}_{k}" for i in range(RADIAL_BINS) for k in ("L", "a", "Lsd")])


def _colour_segments(img: np.ndarray, mask: np.ndarray) -> Tuple[List[float], Dict[str, float]]:
    """Split the view into three colour regions and describe where each sits.

    This is the closest thing here to "find the hole": clustering separates
    membrane from defect from canal wall without needing a threshold, and the
    radial and vertical centroid of the darkest cluster is what distinguishes
    central from marginal from attic.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    points = lab[mask]
    empty = [0.0] * (COLOUR_SEGMENTS * 5)
    if len(points) < COLOUR_SEGMENTS * 10:
        return empty, {}

    # k-means seeding is random, and a clinical tool that returns a different
    # answer for the same image on a second run is not one anyone should
    # trust. Fixing the seed makes the whole pipeline reproducible.
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
    _, labels, centres = cv2.kmeans(points, COLOUR_SEGMENTS, None, criteria, 3,
                                    cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    radius, _ = _polar_grid(mask)
    yy = np.mgrid[0:WORK_SIZE, 0:WORK_SIZE][0]
    c = (WORK_SIZE - 1) / 2.0
    height = (-(yy - c) / (WORK_SIZE / 2.0))[mask]
    r_in = radius[mask]

    feats: List[float] = []
    named: Dict[str, float] = {}
    # Darkest cluster first, so feature k always means the same thing.
    for rank, idx in enumerate(np.argsort(centres[:, 0])):
        sel = labels == idx
        frac = float(sel.mean())
        r_mean = float(r_in[sel].mean()) if sel.any() else 0.0
        h_mean = float(height[sel].mean()) if sel.any() else 0.0
        feats += [frac, float(centres[idx, 0]) / 255.0,
                  float(centres[idx, 1] - 128) / 40.0, r_mean, h_mean]
        if rank == 0:
            named["dark_region_fraction"] = round(frac, 4)
            named["dark_region_radius"] = round(r_mean, 4)
            named["dark_region_height"] = round(h_mean, 4)
    return feats, named


_register([f"seg{i}_{k}" for i in range(COLOUR_SEGMENTS)
           for k in ("frac", "L", "a", "radius", "height")])


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def extract(bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Feature vector plus the human-readable subset shown in the UI."""
    img, mask = prepare(bgr)
    vector: List[float] = []
    named: Dict[str, Any] = {}
    for block in (_colour_block, _light_reflex, _dark_defect, _texture,
                  _occlusion, _vascularity, _translucency,
                  _polar_map, _radial_profile, _colour_segments):
        values, labels = block(img, mask)
        vector.extend(values)
        named.update(labels)
    arr = np.nan_to_num(np.asarray(vector, dtype=np.float32),
                        nan=0.0, posinf=0.0, neginf=0.0)
    return arr, named


def image_quality(bgr: np.ndarray) -> dict:
    """Is this image good enough to interpret?

    Returning "I cannot read this" is a better answer than a confident label
    on a blurred, dark or off-target photo — and phone otoscope images are
    frequently all three.
    """
    img, mask = prepare(bgr)
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(grey, cv2.CV_64F).var())
    exposure = float(grey[mask].mean()) / 255.0 if mask.any() else 0.0
    clipped = float((grey[mask] > 250).mean()) if mask.any() else 0.0
    coverage = float(mask.mean())

    issues: List[str] = []
    if blur < 45:
        issues.append("Image is blurred — hold the scope steady and refocus.")
    if exposure < 0.18:
        issues.append("Image is under-exposed — the drum is too dark to read.")
    if exposure > 0.85 or clipped > 0.22:
        issues.append("Image is over-exposed — glare is hiding the membrane.")
    if coverage < 0.15:
        issues.append("Very little of the frame is illuminated — move closer to the canal.")

    return {
        "usable": not issues,
        "issues": issues,
        "blur": round(blur, 1),
        "exposure": round(exposure, 3),
        "clipped_fraction": round(clipped, 3),
        "coverage": round(coverage, 3),
    }


def decode(data: bytes) -> np.ndarray | None:
    """Bytes to BGR image, or None if it is not a readable image."""
    arr = np.frombuffer(data, np.uint8)
    if arr.size == 0:
        return None
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)
