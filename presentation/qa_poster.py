"""Geometric QA on the built poster — same idea as presentation/qa.py.

Flags shapes off the slide, text that cannot fit its own box, and overlapping
text boxes. Deliberately generous on glyph width so only real overflow trips.
"""
import sys
from pptx import Presentation
from pptx.util import Emu

DECK = sys.argv[1]
prs = Presentation(DECK)
SLIDE_W = Emu(prs.slide_width).inches
SLIDE_H = Emu(prs.slide_height).inches
MARGIN = 0.30

CHAR_W = 0.465   # average glyph width as a fraction of font size (Calibri)
LINE_H = 1.21

inches = lambda v: Emu(v).inches if v is not None else 0.0


def est_lines(tf, width_in):
    """Wrapped line count for a text frame of this width."""
    lines = 0
    for para in tf.paragraphs:
        text = "".join(r.text for r in para.runs)
        if not text.strip():
            lines += 1
            continue
        size = max((r.font.size.pt for r in para.runs if r.font.size), default=10)
        bullet_pad = 0.16 if para._pPr is not None and para._pPr.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}buChar"
        ) is not None else 0.0
        usable = max(0.2, width_in - bullet_pad)
        per_line = max(1, int((usable * 72) / (size * CHAR_W)))
        lines += max(1, -(-len(text) // per_line))
    return lines


def est_height(tf, width_in):
    total = 0.0
    for para in tf.paragraphs:
        text = "".join(r.text for r in para.runs)
        size = max((r.font.size.pt for r in para.runs if r.font.size), default=10)
        bullet_pad = 0.16 if para._pPr is not None and para._pPr.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}buChar"
        ) is not None else 0.0
        usable = max(0.2, width_in - bullet_pad)
        per_line = max(1, int((usable * 72) / (size * CHAR_W)))
        n = max(1, -(-len(text) // per_line)) if text.strip() else 1
        total += n * size * LINE_H / 72.0
        spc = para._pPr.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}spcAft"
        ) if para._pPr is not None else None
        if spc is not None:
            pts = spc.find("{http://schemas.openxmlformats.org/drawingml/2006/main}spcPts")
            if pts is not None:
                total += int(pts.get("val")) / 100.0 / 72.0
    return total


problems, warnings = [], []
texts = []

for slide in prs.slides:
    for shape in slide.shapes:
        x, y = inches(shape.left), inches(shape.top)
        w, h = inches(shape.width), inches(shape.height)
        name = shape.name

        if x < -0.01 or y < -0.01 or x + w > SLIDE_W + 0.01 or y + h > SLIDE_H + 0.01:
            problems.append(f"OFF-SLIDE  {name!r} ({x:.2f},{y:.2f}) {w:.2f}x{h:.2f}")
        elif x < MARGIN - 0.01 or y < MARGIN - 0.01 or \
                x + w > SLIDE_W - MARGIN + 0.01 or y + h > SLIDE_H - MARGIN + 0.01:
            warnings.append(f"tight margin  {name!r} ({x:.2f},{y:.2f}) {w:.2f}x{h:.2f}")

        if shape.has_text_frame and shape.text_frame.text.strip():
            tf = shape.text_frame
            inner_w = w - inches(tf.margin_left) - inches(tf.margin_right)
            inner_h = h - inches(tf.margin_top) - inches(tf.margin_bottom)
            need = est_height(tf, inner_w)
            if need > inner_h + 0.02:
                problems.append(
                    f"OVERFLOW   {name!r} needs {need:.2f}in in {inner_h:.2f}in "
                    f"({est_lines(tf, inner_w)} lines) :: "
                    f"{tf.text[:70]!r}")
            elif need > inner_h - 0.03:
                warnings.append(
                    f"snug       {name!r} needs {need:.2f}in in {inner_h:.2f}in :: "
                    f"{tf.text[:50]!r}")
            texts.append((name, x, y, w, h, tf.text[:40]))

# overlapping text boxes
for i in range(len(texts)):
    n1, x1, y1, w1, h1, t1 = texts[i]
    for j in range(i + 1, len(texts)):
        n2, x2, y2, w2, h2, t2 = texts[j]
        ox = min(x1 + w1, x2 + w2) - max(x1, x2)
        oy = min(y1 + h1, y2 + h2) - max(y1, y2)
        if ox > 0.05 and oy > 0.05:
            area = ox * oy
            if area > 0.04:
                warnings.append(
                    f"text overlap {n1!r} x {n2!r} = {area:.2f}in^2 :: "
                    f"{t1!r} / {t2!r}")

print(f"Slide {SLIDE_W:.3f} x {SLIDE_H:.3f} in — {len(prs.slides[0].shapes)} shapes")
print(f"\n{len(problems)} PROBLEM(S)")
for p in problems:
    print("  " + p)
print(f"\n{len(warnings)} warning(s)")
for w in warnings:
    print("  " + w)
