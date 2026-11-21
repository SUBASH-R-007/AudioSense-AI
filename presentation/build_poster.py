"""Fill the SmartAbility poster template with the AudioSense AI project.

The template's geometry, palette, typography and logos are left exactly as the
organisers supplied them; only the placeholder content is replaced, and the two
zones the template leaves empty (System Architecture, and the screenshot strip)
are filled.

    python -I build_poster.py <template.pptx> <assets_dir> <out.pptx>
"""
import copy
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu, Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from lxml import etree

TEMPLATE, ASSETS, OUT = sys.argv[1], Path(sys.argv[2]), sys.argv[3]

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"a": A}
q = lambda t: f"{{{A}}}{t}"

# ---- the template's own palette, read off its shapes -----------------------
PURPLE = "2E1A87"
GOLD = "F5A800"
INK = "2B2540"
MUTED = "6B6385"
BORDER = "D9CFF5"
RULE = "C9BEEB"
LILAC = "E9E2FA"
LILAC_DEEP = "9C8BD9"
CREAM = "FFF4D6"
CREAM_EDGE = "F2D27A"
WHITE = "FFFFFF"
FONT = "Calibri"

SPC_AFT = 301          # hundredths of a point — the template's paragraph gap
BULLET_MARL = 108900   # EMU — the template's hanging indent


# ===========================================================================
# Text helpers — emit exactly the paragraph XML the template already uses
# ===========================================================================

def _run(text, *, size, bold=False, italic=False, color=INK):
    r = etree.SubElement(etree.Element(q("p")), q("r"))
    rPr = etree.SubElement(r, q("rPr"))
    rPr.set("lang", "en-US")
    rPr.set("sz", str(int(round(size * 100))))
    if bold:
        rPr.set("b", "1")
    if italic:
        rPr.set("i", "1")
    rPr.set("dirty", "0")
    fill = etree.SubElement(rPr, q("solidFill"))
    etree.SubElement(fill, q("srgbClr")).set("val", color)
    for tag in ("latin", "ea", "cs"):
        el = etree.SubElement(rPr, q(tag))
        el.set("typeface", FONT)
        el.set("pitchFamily", "34")
        el.set("charset", {"latin": "0", "ea": "-122", "cs": "-120"}[tag])
    t = etree.SubElement(r, q("t"))
    t.text = text
    return r


def _para(runs, *, bullet=False, align=None, space_after=SPC_AFT, size=9.0):
    p = etree.Element(q("p"))
    pPr = etree.SubElement(p, q("pPr"))
    if bullet:
        pPr.set("marL", str(BULLET_MARL))
        pPr.set("indent", str(-BULLET_MARL))
    else:
        pPr.set("marL", "0")
        pPr.set("indent", "0")
    if align:
        pPr.set("algn", align)
    if space_after is not None:
        spc = etree.SubElement(pPr, q("spcAft"))
        etree.SubElement(spc, q("spcPts")).set("val", str(space_after))
    if bullet:
        etree.SubElement(pPr, q("buSzPct")).set("val", "100000")
        etree.SubElement(pPr, q("buChar")).set("char", "•")
    else:
        etree.SubElement(pPr, q("buNone"))
    for r in runs:
        p.append(r)
    end = etree.SubElement(p, q("endParaRPr"))
    end.set("lang", "en-US")
    end.set("sz", str(int(round(size * 100))))
    end.set("dirty", "0")
    return p


def set_text(shape, paragraphs):
    """Replace a text frame's content. `paragraphs` is a list of dicts:
    {runs: [(text, {size, bold, italic, color})], bullet, align, size}."""
    txBody = shape.text_frame._txBody
    for p in txBody.findall(q("p")):
        txBody.remove(p)
    for spec in paragraphs:
        size = spec.get("size", 9.0)
        runs = [
            _run(text, size=opts.get("size", size), bold=opts.get("bold", False),
                 italic=opts.get("italic", False), color=opts.get("color", INK))
            for text, opts in spec["runs"]
        ]
        txBody.append(_para(
            runs,
            bullet=spec.get("bullet", False),
            align=spec.get("align"),
            space_after=spec.get("space_after", SPC_AFT),
            size=size,
        ))


def plain(text, **opts):
    """A one-run paragraph.

    Alignment, size and spacing belong to the PARAGRAPH, not the run, so they
    are lifted out of the run options here. Leaving align inside the run made
    every plain(..., align=CENTER) silently left-aligned.
    """
    spec = {"runs": [(text, opts)]}
    for key in ("align", "size", "space_after", "bullet"):
        if key in opts:
            spec[key] = opts[key]
    return spec


def lead(label, body, *, size=9.0, label_color=INK, body_color=INK,
         body_italic=False):
    """'Label: body' — the template's recurring two-run paragraph."""
    return {"size": size, "runs": [
        (label, {"bold": True, "color": label_color, "size": size}),
        (body, {"color": body_color, "italic": body_italic, "size": size}),
    ]}


def bullet(text, size=9.0, color=INK):
    return {"bullet": True, "size": size, "runs": [(text, {"size": size, "color": color})]}


def tagged(label, text, size=9.0, space_after=SPC_AFT):
    """A bullet that opens with a bold purple label.

    The template already uses 'Label: body' in sections 1 and 5; extending it
    to the bullet lists gives the eye an entry point on every line instead of
    six interchangeable grey sentences.
    """
    return {"bullet": True, "size": size, "space_after": space_after, "runs": [
        (f"{label}: ", {"bold": True, "color": PURPLE, "size": size}),
        (text, {"color": INK, "size": size}),
    ]}


def tick(text, size=7.0):
    """A tight, unspaced bullet for the dense lists inside the diagram."""
    return {"bullet": True, "size": size, "space_after": 0,
            "runs": [(text, {"size": size, "color": INK})]}


# ===========================================================================
# Shape helpers for the architecture diagram
# ===========================================================================

def box(slide, x, y, w, h, *, fill, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
        radius=0.12, line_w=0.8):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = RGBColor.from_string(line)
        s.line.width = Pt(line_w)
    s.text_frame.word_wrap = True
    return s


def label(slide, x, y, w, h, paragraphs, *, anchor=MSO_ANCHOR.MIDDLE):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    set_text(tb, paragraphs)
    return tb


def arrow(slide, cx, y, h=0.16, w=0.17, color=LILAC_DEEP):
    s = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(cx - w / 2),
                               Inches(y), Inches(w), Inches(h))
    s.shadow.inherit = False
    s.fill.solid()
    s.fill.fore_color.rgb = RGBColor.from_string(color)
    s.line.fill.background()
    return s


# ===========================================================================
# Build
# ===========================================================================

prs = Presentation(TEMPLATE)
slide = prs.slides[0]
sh = list(slide.shapes)

CENTER = "ctr"

# ---- masthead -------------------------------------------------------------
set_text(sh[11], [                                   # PROBLEM STATEMENT / PS-08
    {"align": CENTER, "size": 8.5, "space_after": None,
     "runs": [("PROBLEM STATEMENT", {"bold": True, "color": PURPLE, "size": 8.5})]},
    {"align": CENTER, "size": 27, "space_after": None,
     "runs": [("PS-08", {"bold": True, "color": PURPLE, "size": 27})]},
])

# --- masthead -------------------------------------------------------------
# The template sets the title at 16.5pt with the team line straight under it,
# which reads quietly for something meant to stop a passing clinician. The
# title goes up to 19pt and gains a strapline that says who it is for; the
# three lines are then spaced to fill the band beside the gold PS box.
sh[12].top, sh[12].height = Inches(2.70), Inches(0.42)
set_text(sh[12], [                                                      # title
    {"size": 19, "space_after": None, "runs": [
        ("AudioSense AI", {"bold": True, "color": INK, "size": 19}),
        ("   |   AI-Assisted Pure-Tone Audiometry Interpretation",
         {"bold": True, "color": PURPLE, "size": 17}),
    ]},
])

label(slide, 2.533, 3.13, 8.77, 0.24, [                            # strapline
    {"size": 10.5, "space_after": None, "runs": [
        ("Decision support for the full audiometric battery: diagnosis, RPwD "
         "disability assessment and ENT referral.",
         {"color": INK, "size": 10.5}),
    ]},
])

sh[13].top, sh[13].height = Inches(3.38), Inches(0.38)
set_text(sh[13], [                                                  # team line
    {"size": 10, "space_after": 0, "runs": [
        ("Team: ", {"bold": True, "color": PURPLE, "size": 10}),
        ("Hearizon", {"color": INK, "size": 10}),
        ("     Dept: ", {"bold": True, "color": PURPLE, "size": 10}),
        ("Computer Science and Engineering", {"color": INK, "size": 10}),
        ("     Mentor: ", {"bold": True, "color": PURPLE, "size": 10}),
        ("Mrs. Preethi B", {"color": INK, "size": 10}),
    ]},
    {"size": 10, "space_after": None, "runs": [
        ("Members: ", {"bold": True, "color": PURPLE, "size": 10}),
        ("Subash R, Trishanth G, Varsha S, Vaishnavi Thiruvengadam, "
         "Deveshwar S.", {"color": INK, "size": 10}),
    ]},
])

# ---- 1. Problem Statement -------------------------------------------------
sh[18].height = Inches(1.40)
set_text(sh[18], [
    lead("Statement: ",
         "Audiogram interpretation is slow and depends on scarce expertise, "
         "delaying diagnosis where patient volume is highest. PS-08 asks for "
         "automatic analysis, pattern classification, degree and type, "
         "disability estimation and a generated report."),
    lead("Target users: ",
         "NIEPMD, Chennai. Audiologists and ENT clinicians working up a hearing "
         "loss, assessing disability under the RPwD Act, and screening at "
         "camps."),
    lead("User persona: ",
         "Vignesh Kumar, 26, shipyard welder. His audiogram reads normal, so "
         "routine screening sends him back to the yard. His otoacoustic "
         "emissions are already absent at 4 and 8 kHz, and that damage is "
         "still preventable."),
])

# ---- 2. Need & Gap --------------------------------------------------------
STATS = [
    (24, "1 in 5", "live with hearing loss (WHO, 2021)"),
    (26, "1 : 5 lakh", "audiologists per population, India"),
    (28, "≥ 40%", "RPwD benchmark disability threshold"),
]
for idx, big, cap in STATS:
    set_text(sh[idx], [
        {"align": CENTER, "size": 16.5, "space_after": None,
         "runs": [(big, {"bold": True, "color": PURPLE, "size": 16.5})]},
        {"align": CENTER, "size": 7, "space_after": None,
         "runs": [(cap, {"color": MUTED, "italic": True, "size": 7})]},
    ])

# The card keeps its template height; only the text box grows, so the 0.15in
# gap the template holds between every pair of cards survives.
sh[29].height = Inches(0.74)
set_text(sh[29], [
    lead("Existing solutions: ",
         "Manual reading, generic plotters, single-modality classifiers."),
    lead("Limitations: ",
         "Slow and inconsistent at volume, no cross-check between tests, "
         "accuracy quoted from synthetic data."),
    # safety.py: the steroid window for a sudden sensorineural loss is days,
    # and triage.py exists because a queue read in upload order buries it.
    lead("At stake: ",
         "a sudden loss needs treatment within days, but a queue is read in "
         "order."),
])

# ---- 3. Proposed Solution -------------------------------------------------
set_text(sh[35], [
    {"size": 10, "space_after": None, "runs": [
        ("Concept: ", {"bold": True, "color": PURPLE, "size": 10}),
        ("One request takes thresholds (typed, photographed or measured "
         "in-browser) and returns a WHO 2021 grade, loss type, RPwD "
         "disability percentage, a calibrated ML pattern and a verified "
         "report in about 450 ms.", {"color": INK, "size": 10}),
    ]},
])

# Six single-line bullets fit the template's own card height, so this card
# keeps its gap to the demo band as well. ("every step shown" lives on the
# Certification bullet in section 8, so nothing is lost by dropping it here.)
sh[37].height = Inches(1.28)
set_text(sh[37], [
    tagged("Audiogram", "WHO 2021 grade, air-bone-gap typing, RPwD "
                        "disability %", 9, 200),
    tagged("Otoscopy", "drum photo against an 8-pattern atlas, checked against "
                       "the audiogram", 9, 200),
    tagged("Battery", "tympanometry, OAE, speech audiometry, ABR / MLR / LLR, "
                      "tuning forks", 9, 200),
    tagged("Masking", "decided per frequency, with a dilemma reported rather "
                      "than guessed", 9, 200),
    tagged("Red flags", "sudden and asymmetric loss sorted above everything "
                        "else", 9, 200),
    tagged("ML pattern", "calibrated, with an out-of-distribution flag, gated "
                         "by the rules", 9, 200),
    # 11 Veo-generated clips, one per mechanism. The backend reads the
    # tympanogram and the otoscopy image to pick which one, and every
    # response carries illustration_only, so the poster says so too.
    tagged("Patient explainer", "an AI-generated anatomy clip matched to the "
                                "loss, not a scan", 9, 200),
])

# ---- 4. System Architecture (the template leaves this card empty) ---------
# A real flow diagram, not a stack of bars. The system branches and merges —
# three inputs converge on one gateway, the gateway fans out to two domain
# engines that run side by side, both feed one reconciliation step, and the
# verdict fans out again to four outputs. Orthogonal connectors draw those
# joins; node widths vary with their place in the flow so the eye can follow
# the axis instead of reading six identical full-width boxes.
X0, W = 6.18, 4.94
CX = X0 + W / 2

# The card keeps its template height (bottom 9.282); the diagram is laid out
# to finish inside it, so the 0.15in gap to the Methodology card survives.

LINE = LILAC_DEEP


def wire(x1, y1, x2, y2, *, arrow=False, width=1.0):
    """One orthogonal segment. Elbows are drawn as two calls, which keeps the
    routing explicit and avoids PowerPoint re-routing a bent connector."""
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1),
                                   Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = RGBColor.from_string(LINE)
    c.line.width = Pt(width)
    if arrow:
        ln = c.line._get_or_add_ln()
        tail = etree.SubElement(ln, q("tailEnd"))
        tail.set("type", "triangle")
        tail.set("w", "med")
        tail.set("len", "med")
    return c


def fan(parent_x, from_y, bus_y, targets, to_y):
    """Branch: drop from the parent, run a bus, drop into each target."""
    wire(parent_x, from_y, parent_x, bus_y)
    wire(min(targets + [parent_x]), bus_y, max(targets + [parent_x]), bus_y)
    for tx in targets:
        wire(tx, bus_y, tx, to_y, arrow=True)


def merge(sources, from_y, bus_y, child_x, to_y):
    """Merge: lift from each source, run a bus, drop into the child."""
    for sx in sources:
        wire(sx, from_y, sx, bus_y)
    wire(min(sources + [child_x]), bus_y, max(sources + [child_x]), bus_y)
    wire(child_x, bus_y, child_x, to_y, arrow=True)


def node(x, y, w, h, lines, *, fill=WHITE, line=RULE, size=7.5, bold=False,
         color=INK):
    box(slide, x, y, w, h, fill=fill, line=line)
    paras = []
    for i, (text, opts) in enumerate(lines):
        paras.append({"size": opts.get("size", size), "space_after": 0,
                      "align": CENTER, "runs": [(text, {
                          "size": opts.get("size", size),
                          "bold": opts.get("bold", bold),
                          "italic": opts.get("italic", False),
                          "color": opts.get("color", color)})]})
    label(slide, x + 0.05, y, w - 0.10, h, paras)


# --- row 1: the three things a clinician brings ---------------------------
IN_W, IN_GAP, IN_Y, IN_H = 1.52, 0.19, 4.44, 0.34
in_cx = [X0 + i * (IN_W + IN_GAP) + IN_W / 2 for i in range(3)]
for i, text in enumerate(["Thresholds: typed, photo,\nor in-browser",
                          "Otoscope image", "History & symptoms"]):
    node(X0 + i * (IN_W + IN_GAP), IN_Y, IN_W, IN_H,
         [(t, {}) for t in text.split("\n")], size=7)

# --- row 2: the gateway ---------------------------------------------------
API_W, API_Y, API_H = 3.30, 4.98, 0.38
merge(in_cx, IN_Y + IN_H, 4.90, CX, API_Y)
node(CX - API_W / 2, API_Y, API_W, API_H, [
    ("FastAPI  ·  24 routers, 72 endpoints", {"size": 8, "bold": True,
                                                   "color": WHITE}),
    ("default-closed auth middleware", {"size": 6.5, "color": "D8D0F0",
                                        "italic": True}),
], fill=PURPLE, line=PURPLE)

# --- row 3: the two engines, side by side ---------------------------------
COL_W, COL_GAP, COL_Y, COL_H = 2.30, 0.34, 5.60, 1.30
X1 = X0 + COL_W + COL_GAP
col_cx = [X0 + COL_W / 2, X1 + COL_W / 2]
fan(CX, API_Y + API_H, 5.48, col_cx, COL_Y)

box(slide, X0, COL_Y, COL_W, COL_H, fill="F5F2FC", line=RULE)
label(slide, X0 + 0.10, COL_Y + 0.07, COL_W - 0.20, 0.20,
      [plain("DETERMINISTIC CLINICAL CORE", size=7, bold=True, color=PURPLE)])
label(slide, X0 + 0.10, COL_Y + 0.30, COL_W - 0.20, COL_H - 0.54, [
    tick("WHO 2021 grade · air-bone-gap type"),
    tick("RPwD Gazette disability %"),
    tick("Masking, decided per frequency"),
    tick("8-type tympanometry · OAE"),
    tick("Speech · ABR/MLR/LLR · forks"),
    tick("Red-flag safety · triage"),
], anchor=MSO_ANCHOR.TOP)
label(slide, X0 + 0.10, COL_Y + COL_H - 0.24, COL_W - 0.20, 0.20,
      [plain("pure functions, each citing its guideline", size=6.5,
             italic=True, color=MUTED)])

box(slide, X1, COL_Y, COL_W, COL_H, fill=CREAM, line=CREAM_EDGE)
label(slide, X1 + 0.10, COL_Y + 0.07, COL_W - 0.20, 0.20,
      [plain("MACHINE LEARNING LAYER", size=7, bold=True, color="8A6400")])
label(slide, X1 + 0.10, COL_Y + 0.30, COL_W - 0.20, COL_H - 0.54, [
    tick("RandomForest audiogram pattern"),
    tick("Calibration + out-of-distribution flag"),
    tick("Otoscopy match, 62-view atlas"),
    tick("Deep-ensemble second opinion"),
    tick("Counterfactual explanations"),
], anchor=MSO_ANCHOR.TOP)
label(slide, X1 + 0.10, COL_Y + COL_H - 0.24, COL_W - 0.20, 0.20,
      [plain("models shipped in the image (12 MB)", size=6.5,
             italic=True, color=MUTED)])

# The one relationship a vertical stack cannot show: the rules constrain the
# model, rather than the two simply running in parallel.
GATE_Y = COL_Y + COL_H / 2
wire(X0 + COL_W, GATE_Y, X1, GATE_Y, arrow=True)
label(slide, X0 + COL_W, GATE_Y - 0.19, COL_GAP, 0.13,
      [plain("gates", size=5, italic=True, color=MUTED, align=CENTER)])

# --- row 4: reconciliation, then the call ---------------------------------
BAT_W, BAT_Y, BAT_H = 3.80, 7.12, 0.34
merge(col_cx, COL_Y + COL_H, 7.02, CX, BAT_Y)
node(CX - BAT_W / 2, BAT_Y, BAT_W, BAT_H,
     [("Cross-modal battery: do the tests agree?",
       {"size": 8.5, "bold": True, "color": PURPLE})],
     fill=LILAC, line=LILAC_DEEP)

VER_W, VER_Y, VER_H = 3.80, 7.72, 0.34
wire(CX, BAT_Y + BAT_H, CX, VER_Y, arrow=True)
node(CX - VER_W / 2, VER_Y, VER_W, VER_H,
     [("Verdict  ·  triage priority  ·  auto-release vs review",
       {"size": 8.5, "bold": True, "color": PURPLE})],
     fill=GOLD, line=GOLD)

# --- row 5: what comes out ------------------------------------------------
OUT_W, OUT_GAP, OUT_Y, OUT_H = 1.16, 0.096, 8.42, 0.34
out_cx = [X0 + i * (OUT_W + OUT_GAP) + OUT_W / 2 for i in range(4)]
fan(CX, VER_Y + VER_H, 8.22, out_cx, OUT_Y)
for i, text in enumerate(["Verified report", "PDF + QR handout", "ENT referral",
                          "Patient counselling"]):
    node(X0 + i * (OUT_W + OUT_GAP), OUT_Y, OUT_W, OUT_H, [(text, {})], size=7)

label(slide, X0, 8.90, W, 0.22, [
    {"size": 6.5, "space_after": 0, "align": CENTER, "runs": [
        ("Offline-first, with no API keys. Visits persist to SQLite. Six "
         "optional LLM providers, each falling back to the offline engine.",
         {"size": 6.5, "italic": True, "color": MUTED})]},
])

# ---- 5. Methodology & Tech Stack -----------------------------------------
# The template's own text box overhangs this card by 0.28in, which clipped the
# last line against the card edge. Give the card the height its content needs
# and hold the text inside it.
sh[54].height = Inches(0.70)          # the card keeps its template height
# --- the consultation, as the app actually sequences it -------------------
# The template ships four generic chevrons (Research / Design / Develop /
# Deploy) that say nothing about this project. The seven steps below are the
# real ones, taken from frontend/src/lib/flow.js, which is the single
# definition the sidebar, the step footer and the progress logic all read.
for idx in range(46, 54):                        # the four template chevrons
    sh[idx]._element.getparent().remove(sh[idx]._element)

STEPS = ["Patient details", "Signs & symptoms", "Otoscopy",
         "Pure-tone audiometry", "Immittance, emissions & speech",
         "Evoked potentials", "Results"]
STEP_W, STEP_STEP, STEP_Y, STEP_H = 0.753, 0.693, 9.96, 0.40
for i, text in enumerate(STEPS):
    x = 6.197 + i * STEP_STEP
    filled = i % 2 == 0
    chev = box(slide, x, STEP_Y, STEP_W, STEP_H,
               fill=PURPLE if filled else GOLD,
               line=PURPLE if filled else GOLD, shape=MSO_SHAPE.CHEVRON)
    # A chevron's default notch and point are half its height deep, which ate
    # the first and last characters of every label. Shallower arrows still
    # nest (the 0.084in point clears the 0.06in overlap) and leave room to read.
    chev.adjustments[0] = 0.22
    label(slide, x + 0.13, STEP_Y, STEP_W - 0.23, STEP_H,
          [plain(text, size=6.5, bold=True, align=CENTER,
                 color=WHITE if filled else PURPLE)])

sh[54].top, sh[54].height = Inches(10.46), Inches(0.80)
set_text(sh[54], [
    lead("Build method: ",
         "each guideline is encoded as a pure function and proved by a "
         "conformance sweep, then piloted with NIEPMD clinicians."),
    lead("Tech stack: ",
         "FastAPI · scikit-learn · OpenCV · SQLite  |  React 18 "
         "· Vite 6 · Tailwind 4  |  Docker + Vercel. Validated by "
         "2,094 automated tests."),
])

# ---- 6. Prototype / Demo --------------------------------------------------
set_text(sh[58], [
    {"size": 15, "space_after": None, "runs": [
        ("Prototype / Demo: Live Website", {"bold": True, "color": PURPLE, "size": 15}),
        ("      screenshots from the running build",
         {"color": MUTED, "size": 8.5}),
    ]},
])

# Captured with the app's own nav hidden and at a tighter viewport, so the UI
# fills the thumbnail at readable size instead of being a 1400px page shrunk
# into 5 cm. Three screens at 2.95in rather than four at 2.27in: a poster is
# read at a metre, and a fourth thumbnail nobody can resolve is worth less
# than a third one they can. The tympanogram is still named in sections 3-5.
SHOTS = [
    ("shot1_verdict_n.jpg", "The verdict, above the evidence"),
    ("shot2_audiogram_n.jpg", "Audiogram, graded, typed and classified"),
    ("shot3_otoscopy_n.jpg", "Otoscopy against the reference atlas"),
    ("shot4_video_n.jpg", "The anatomy clip the clinician plays"),
]
SHOT_W, SHOT_ASPECT = 2.25, 1.95
SHOT_H = round(SHOT_W / SHOT_ASPECT, 3)          # 1.154
SHOT_X0, SHOT_GAP, SHOT_Y = 0.58, 0.14, 12.02
sh[55].height = Inches(1.988)                    # Shape 73 — band bottom 13.45
for idx in (81, 82, 83, 84):                     # the template's placeholders
    sh[idx]._element.getparent().remove(sh[idx]._element)
for i, (name, caption) in enumerate(SHOTS):
    x = SHOT_X0 + i * (SHOT_W + SHOT_GAP)
    pic = slide.shapes.add_picture(str(ASSETS / name), Inches(x), Inches(SHOT_Y),
                                   Inches(SHOT_W), Inches(SHOT_H))
    pic.line.color.rgb = RGBColor.from_string(RULE)
    pic.line.width = Pt(0.75)
    label(slide, x, SHOT_Y + SHOT_H + 0.03, SHOT_W, 0.16,
          [plain(caption, size=7, color=MUTED, align=CENTER)])

QR_SIZE = 0.95
QR_X = SHOT_X0 + 4 * (SHOT_W + SHOT_GAP) + 0.06
sh[85]._element.getparent().remove(sh[85]._element)
slide.shapes.add_picture(str(ASSETS / "qr_site.png"), Inches(QR_X),
                         Inches(SHOT_Y + (SHOT_H - QR_SIZE) / 2 - 0.05),
                         Inches(QR_SIZE), Inches(QR_SIZE))
sh[86].left, sh[86].top = Inches(QR_X - 0.20), Inches(SHOT_Y + SHOT_H - 0.14)
sh[86].width = Inches(QR_SIZE + 0.33)
set_text(sh[86], [plain("audio-sense-ai.vercel.app", size=6.5, bold=True,
                        color=PURPLE, align=CENTER)])

# --- sections 7-9 move down to clear the band, and gain a fifth line ------
LOWER_DELTA = 13.60 - 13.491
for idx in range(59, 74):
    sh[idx].top = Emu(sh[idx].top + Inches(LOWER_DELTA))
for idx in (59, 64, 69):                         # the three cards
    sh[idx].height = Inches(1.545)
for idx in (63, 68, 73):                         # their bullet lists
    sh[idx].height = Inches(0.86)

# ---- 7 / 8 / 9 ------------------------------------------------------------
# Every line here is sized to sit on ONE line at 8pt in a 2.98in column, with
# the paragraph gap tightened to 2pt, so the three cards read as one band.
TIGHT = 200
set_text(sh[63], [
    tagged("Offline", "installable PWA, runs with no connectivity", 8, TIGHT),
    tagged("Six languages", "counselling read aloud, or sent by QR", 8, TIGHT),
    tagged("Plain verdict", "one sentence, placed above the evidence", 8,
           TIGHT),
    tagged("Counselling", "the family sees the clip and hears the loss", 8,
           TIGHT),
    tagged("Paper intake", "photographed audiograms become editable", 8, TIGHT),
])

set_text(sh[68], [
    tagged("Speed", "about 450 ms per audiogram, 89 a minute", 8, TIGHT),
    tagged("Triage", "2 of 8 flagged, 6 drafts auto-releasable", 8, TIGHT),
    tagged("Certification", "every RPwD step is shown and auditable", 8,
           TIGHT),
    tagged("Follow-up", "visits compared, OSHA shift and forecast", 8, TIGHT),
    tagged("Alignment", "SDG 3, 8 and 10", 8, TIGHT),
])

set_text(sh[73], [
    tagged("Design", "the clinical core gates the ML layer", 8, TIGHT),
    tagged("Cross-checks", "a disagreement between tests is a finding", 8,
           TIGHT),
    tagged("Immittance", "eight types, curve rebuilt from four numbers", 8,
           TIGHT),
    tagged("Screening", "a browser staircase with silent catch trials", 8,
           TIGHT),
    tagged("Next", "clinical validation and the CDSCO SaMD pathway", 8,
           TIGHT),
])

# ---- footer strip ---------------------------------------------------------
set_text(sh[75], [
    {"size": 9, "space_after": None,
     "runs": [("Acknowledgement", {"bold": True, "color": PURPLE, "size": 9})]},
    {"size": 7.5, "space_after": None, "runs": [
        ("Mrs. Preethi B. for her guidance, and NIEPMD clinicians for the "
         "reference documents and pilot testing.", {"color": INK, "size": 7.5}),
    ]},
])

# The template leaves the middle of this strip empty; the project's own
# disclaimer belongs on the poster, not only in the app.
label(slide, 4.12, 15.37, 4.00, 0.52, [
    {"size": 7.5, "space_after": None, "runs": [
        ("AI-assisted interpretation; final diagnosis requires a qualified "
         "audiologist.", {"bold": True, "color": INK, "size": 7.5})]},
])

set_text(sh[76], [
    {"size": 9, "space_after": None,
     "runs": [("Contact", {"bold": True, "color": PURPLE, "size": 9})]},
    {"size": 7.5, "space_after": None, "runs": [
        ("subash.r.2024.cse@rajalakshmi.edu.in", {"color": INK, "size": 7.5})]},
])

# strip QR -> the live site
strip = sh[77]
s_left, s_top = strip.left, strip.top
s_size = min(strip.width, strip.height)
strip._element.getparent().remove(strip._element)
sh[78]._element.getparent().remove(sh[78]._element)   # the "QR" caption
slide.shapes.add_picture(str(ASSETS / "qr_site.png"), s_left, s_top,
                         s_size, s_size)

set_text(sh[80], [
    {"align": CENTER, "size": 10, "space_after": None, "runs": [
        ("Empowering Abilities", {"bold": True, "color": WHITE, "size": 10}),
        ("   •   ", {"bold": True, "color": GOLD, "size": 10}),
        ("Driving Innovation", {"bold": True, "color": WHITE, "size": 10}),
        ("   •   ", {"bold": True, "color": GOLD, "size": 10}),
        ("Building an Inclusive Future", {"bold": True, "color": WHITE, "size": 10}),
    ]},
])

prs.save(OUT)
print(f"wrote {OUT}")
