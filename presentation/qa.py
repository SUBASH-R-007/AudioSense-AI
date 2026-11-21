"""Geometric QA on the built deck.

No LibreOffice here, so instead of eyeballing renders this measures the things
a render would reveal: shapes off the slide, text that cannot fit its box,
text boxes overlapping each other, and edge margins.
"""
import sys

from pptx import Presentation
from pptx.util import Emu

DECK = sys.argv[1] if len(sys.argv) > 1 else "AudioSense-AI-Pilot-Review.pptx"
SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.5

# Average glyph width as a fraction of font size, for a proportional sans.
# Deliberately generous (a real line fits a bit more), so this flags only
# genuine overflow rather than every tight box.
CHAR_W = 0.50
LINE_H = 1.22


def inches(v):
    return Emu(v).inches if v is not None else 0.0


def est_lines(text, width_in, size_pt):
    """Rough wrapped-line count for a run of text in a box of this width."""
    if not text.strip():
        return 0
    per_line = max(1, int((width_in * 72) / (size_pt * CHAR_W)))
    lines = 0
    for para in text.split("\n"):
        lines += max(1, -(-len(para) // per_line))
    return lines


prs = Presentation(DECK)
problems = []

for idx, slide in enumerate(prs.slides, 1):
    boxes = []
    for sh in slide.shapes:
        x, y = inches(sh.left), inches(sh.top)
        w, h = inches(sh.width), inches(sh.height)

        # 1. Off the slide entirely, or hanging over an edge.
        if x < -0.01 or y < -0.01 or x + w > SLIDE_W + 0.01 or y + h > SLIDE_H + 0.01:
            problems.append(
                f"slide {idx}: OFF-SLIDE  '{(sh.name or '')[:22]}' "
                f"at ({x:.2f},{y:.2f}) {w:.2f}x{h:.2f}")

        if not sh.has_text_frame:
            continue
        text = sh.text_frame.text
        if not text.strip():
            continue

        # Largest font in the shape drives the fit estimate.
        size = 12.0
        for p in sh.text_frame.paragraphs:
            for r in p.runs:
                if r.font.size:
                    size = max(size, r.font.size.pt)

        # 2. Text that cannot fit its own box.
        need = est_lines(text, w, size) * size * LINE_H / 72.0
        if need > h + 0.06:
            problems.append(
                f"slide {idx}: OVERFLOW?  \"{text.strip()[:38]}...\" "
                f"needs ~{need:.2f}\" in {h:.2f}\" (font {size:.0f}pt, w {w:.2f}\")")

        # 3. Inside the safe margin?
        if x < MARGIN - 0.01 or y < MARGIN - 0.01 \
                or x + w > SLIDE_W - MARGIN + 0.01 or y + h > SLIDE_H - MARGIN + 0.01:
            problems.append(
                f"slide {idx}: MARGIN     \"{text.strip()[:30]}\" "
                f"at ({x:.2f},{y:.2f}) extends to ({x + w:.2f},{y + h:.2f})")

        boxes.append((x, y, w, h, text.strip()[:26]))

    # 4. Text boxes overlapping each other by a visible amount.
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax, ay, aw, ah, at = boxes[i]
            bx, by, bw, bh, bt = boxes[j]
            ox = min(ax + aw, bx + bw) - max(ax, bx)
            oy = min(ay + ah, by + bh) - max(ay, by)
            if ox > 0.12 and oy > 0.12:
                problems.append(
                    f"slide {idx}: OVERLAP    \"{at}\" x \"{bt}\" "
                    f"({ox:.2f}\" x {oy:.2f}\")")

print(f"{len(prs.slides)} slides checked")
if problems:
    print(f"\n{len(problems)} issue(s):")
    for p in problems:
        print("  " + p)
else:
    print("\nNo geometry problems found.")
