"""Extract the labelled otoscopy reference set from 'Otoscopic evaluation.docx'.

The reference document pairs a caption with the images that follow it, and
most of those images are montages: a grid of six or four individual otoscope
views pasted into one picture. Treating a montage as a single training example
throws away most of the data, so this script splits each montage into its
constituent views by finding the black gutters between panels.

Labels come from the document itself, verified visually:

    normal                 clear canal, pearly grey TM, cone of light present
    cerumen_impaction      wax occluding the canal
    otitis_media           red, bulging TM with effusion
    retraction             retracted TM, Eustachian tube dysfunction
    perforation_marginal   perforation touching the annulus
    perforation_central    perforation surrounded by remnant TM
    perforation_attic      pars flaccida defect, cholesteatoma risk
    tumor                  mass in the canal or middle ear

Run:  python -m scripts.extract_otoscope_reference <path-to-docx>
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

DEST = Path(__file__).resolve().parents[1] / "data" / "otoscope_reference"

# Caption-before-image ordering, read from the document and confirmed by eye.
LABELS = {
    "normal": ["image1.jpeg", "image2.jpg", "image4.jpg", "image5.jpg",
               "image6.jpg", "image8.jpg", "image9.jpg", "image11.jpg"],
    "cerumen_impaction": ["image12.jpg", "image13.jpg"],
    "otitis_media": ["image14.jpg", "image15.jpg"],
    "retraction": ["image16.jpg", "image17.jpg"],
    "perforation_marginal": ["image18.jpg", "image19.jpg"],
    "perforation_central": ["image20.jpg", "image21.jpg"],
    "perforation_attic": ["image22.jpg", "image23.jpg"],
    "tumor": ["image24.jpg", "image25.jpg"],
}

#: A panel smaller than this fraction of the montage is a caption or artefact.
MIN_PANEL_FRACTION = 0.04
#: Otoscope views are round; anything far from square is a strip, not a view.
MAX_ASPECT = 2.2

#: Views are stored at this maximum edge, as JPEG. The model resamples to 256
#: pixels regardless, so full-resolution lossless copies buy nothing and cost
#: 33 MB in the repository — this keeps the whole atlas near 2 MB while
#: staying comfortably above what any descriptor here reads.
MAX_EDGE = 512
JPEG_QUALITY = 90


def split_montage(image: np.ndarray) -> list[np.ndarray]:
    """Split a montage into panels, or return the whole image if it is one view.

    Panels in these figures sit on white or black backgrounds with clear
    gutters. Thresholding to "content vs background" and taking connected
    components recovers them without assuming a fixed grid.
    """
    h, w = image.shape[:2]
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Content is anything that is neither near-black gutter nor near-white page.
    content = ((grey > 18) & (grey < 242)).astype(np.uint8) * 255
    content = cv2.morphologyEx(
        content, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, w // 60),) * 2))

    n, _, stats, _ = cv2.connectedComponentsWithStats(content)
    panels = []
    for i in range(1, n):
        x, y, pw, ph, area = stats[i]
        if area < MIN_PANEL_FRACTION * h * w:
            continue
        if pw == 0 or ph == 0:
            continue
        if max(pw / ph, ph / pw) > MAX_ASPECT:
            continue
        pad = 2
        panels.append(image[max(0, y + pad):y + ph - pad,
                            max(0, x + pad):x + pw - pad])

    # One huge component means the picture is already a single otoscope view.
    if len(panels) <= 1:
        return [image]
    return [p for p in panels if p.size and min(p.shape[:2]) >= 64]


def downscale(panel: np.ndarray) -> np.ndarray:
    """Shrink to MAX_EDGE on the long side, leaving smaller panels alone."""
    h, w = panel.shape[:2]
    longest = max(h, w)
    if longest <= MAX_EDGE:
        return panel
    scale = MAX_EDGE / longest
    return cv2.resize(panel, (int(round(w * scale)), int(round(h * scale))),
                      interpolation=cv2.INTER_AREA)


def main(docx_path: str) -> int:
    src = Path(docx_path)
    if not src.exists():
        print(f"not found: {src}")
        return 1

    # Clear previous output file by file. Removing the directory itself fails
    # intermittently under OneDrive, which keeps a handle on synced folders.
    if DEST.exists():
        for old in DEST.rglob("*"):
            if old.is_file():
                try:
                    old.unlink()
                except OSError:
                    pass
    DEST.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(src) as zf:
        media = {Path(n).name: zf.read(n) for n in zf.namelist()
                 if n.startswith("word/media/")}

    seen: set[str] = set()
    totals: dict[str, int] = {}
    for label, files in LABELS.items():
        out_dir = DEST / label
        out_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for name in files:
            blob = media.get(name)
            if blob is None:
                continue
            digest = hashlib.md5(blob).hexdigest()[:8]
            if digest in seen:        # the document reuses several pictures
                continue
            seen.add(digest)

            image = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                continue
            for j, panel in enumerate(split_montage(image)):
                cv2.imwrite(str(out_dir / f"{label}_{digest}_{j:02d}.jpg"),
                            downscale(panel),
                            [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
                count += 1
        totals[label] = count

    print(f"{'class':24s} views")
    for label, count in totals.items():
        print(f"{label:24s} {count:5d}")
    print(f"{'TOTAL':24s} {sum(totals.values()):5d}")
    return 0


if __name__ == "__main__":
    default = r"C:\Users\SUBASH\Downloads\Otoscopic evaluation .docx"
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else default))
