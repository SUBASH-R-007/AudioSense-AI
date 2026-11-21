"""Render realistic paper-audiogram photos for the Snap-to-Digitize demo.

Produces samples/audiogram_photo_1.png (noise notch) and
samples/audiogram_photo_2.png (presbycusis) plus ground_truth.json used by
the digitizer regression test. Clinical notation: right ear red (O = AC,
[ = BC), left ear blue (X = AC, ] = BC), inverted dB axis.

Also produces samples/report_page.png — a WHOLE A4 report, with a
letterhead, the patient's details, the audiogram somewhere in the middle and
the printed results underneath. That is the document a clinic actually hands
over, and it is what /api/digitize/report reads: the chart is located on the
page rather than assumed to fill the frame. A greyscale copy
(report_page_bw.png) ships beside it, because a photocopy is the commonest
form this document arrives in and the symbol-shape detector exists for it.

Run:  python -m scripts.make_samples   (from backend/, venv active)
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]
BC_FREQS = [250, 500, 1000, 2000, 4000]

# Saturated symbol colors (picked up by the HSV masks) vs pale connector
# lines (deliberately below the saturation threshold, like faded print).
RED, PALE_RED = "#d11515", "#f2c4c4"
BLUE, PALE_BLUE = "#1440cc", "#c4cdf2"

CASES = {
    "audiogram_photo_1": {
        "title": "Govt. District Hospital — Audiology Unit",
        "right": {"ac": {250: 15, 500: 15, 1000: 20, 2000: 25, 4000: 60, 8000: 30},
                  "bc": {250: 10, 500: 10, 1000: 15, 2000: 20, 4000: 55}},
        "left": {"ac": {250: 10, 500: 15, 1000: 20, 2000: 30, 4000: 55, 8000: 25},
                 "bc": {250: 10, 500: 10, 1000: 15, 2000: 25, 4000: 50}},
    },
    "audiogram_photo_2": {
        "title": "Sri Meenakshi ENT Clinic — Pure Tone Audiogram",
        "right": {"ac": {250: 20, 500: 25, 1000: 35, 2000: 50, 4000: 65, 8000: 75},
                  "bc": {250: 15, 500: 20, 1000: 30, 2000: 45, 4000: 60}},
        "left": {"ac": {250: 20, 500: 30, 1000: 40, 2000: 55, 4000: 70, 8000: 80},
                 "bc": {250: 15, 500: 25, 1000: 35, 2000: 50, 4000: 65}},
    },
}


def draw(name: str, case: dict) -> None:
    fig, ax = plt.subplots(figsize=(9, 7), dpi=140)
    fig.patch.set_facecolor("#faf7f0")  # aged paper
    ax.set_facecolor("#fdfcf8")

    x = {f: i for i, f in enumerate(AC_FREQS)}
    ax.set_xlim(-0.5, 5.5)
    ax.set_ylim(120, -10)  # inverted clinical axis
    ax.set_xticks(range(6))
    ax.set_xticklabels(["250", "500", "1000", "2000", "4000", "8000"])
    ax.set_yticks(range(-10, 121, 10))
    ax.grid(True, color="#8a8a8a", linewidth=0.7)
    ax.set_xlabel("Frequency (Hz)", fontsize=11)
    ax.set_ylabel("Hearing Level (dB HL)", fontsize=11)
    ax.set_title(case["title"], fontsize=12, pad=12)

    for ear, ac_color, pale, marker in (("right", RED, PALE_RED, "o"),
                                        ("left", BLUE, PALE_BLUE, "x")):
        ac = case[ear]["ac"]
        xs = [x[f] for f in AC_FREQS]
        ys = [ac[f] for f in AC_FREQS]
        ax.plot(xs, ys, color=pale, linewidth=1.6, zorder=2)
        ax.plot(xs, ys, linestyle="none", marker=marker, markersize=13,
                markerfacecolor="none", markeredgecolor=ac_color,
                markeredgewidth=2.6, zorder=3)
        bracket = "[" if ear == "right" else "]"
        offset = -0.25 if ear == "right" else 0.25
        for f, db in case[ear]["bc"].items():
            ax.text(x[f] + offset, db, bracket, color=ac_color, fontsize=15,
                    fontweight="bold", ha="center", va="center", zorder=3)

    ax.text(0.99, 0.02, "Right: red O / [     Left: blue X / ]",
            transform=ax.transAxes, ha="right", fontsize=8, color="#666")
    fig.tight_layout()
    SAMPLES.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAMPLES / f"{name}.png", facecolor=fig.get_facecolor())
    plt.close(fig)


#: The report page's case, and the results a clinic would have printed on it.
#: The printed figures are what an audiologist computed and signed; the app
#: recomputes everything from the thresholds, so the two can be compared.
REPORT_CASE = {
    "right": {"ac": {250: 20, 500: 25, 1000: 35, 2000: 50, 4000: 65, 8000: 75},
              "bc": {250: 15, 500: 20, 1000: 30, 2000: 45, 4000: 60}},
    "left": {"ac": {250: 25, 500: 30, 1000: 40, 2000: 55, 4000: 70, 8000: 80},
             "bc": {250: 20, 500: 25, 1000: 35, 2000: 50, 4000: 65}},
}

REPORT_TEXT = [
    "RESULTS",
    "Right PTA : 43.8 dB HL            Left PTA : 48.8 dB HL",
    "Right SRT : 45 dB HL              Left SRT : 50 dB HL",
    "Right SDS : 88 %                  Left SDS : 84 %",
    "Type : Mixed, both ears           Degree : Moderate",
    "",
    "IMPRESSION : Bilateral moderate mixed hearing loss, worse on the left.",
    "RECOMMENDATION : Binaural hearing aid trial; ENT review for the",
    "conductive component.",
]


def draw_report(name: str, grey: bool = False) -> None:
    """A full A4 report page: letterhead, details, audiogram, printed results."""
    from matplotlib.gridspec import GridSpec

    red = "#333333" if grey else RED
    blue = "#333333" if grey else BLUE

    fig = plt.figure(figsize=(8.27, 11.69), dpi=150)  # A4 portrait
    fig.patch.set_facecolor("#ffffff")
    gs = GridSpec(5, 1, figure=fig, height_ratios=[1.1, 0.9, 4.2, 2.0, 0.7],
                  hspace=0.35, left=0.08, right=0.94, top=0.96, bottom=0.04)

    ax = fig.add_subplot(gs[0]); ax.axis("off")
    ax.text(0.5, 0.78, "SRI MEENAKSHI ENT & AUDIOLOGY CENTRE", ha="center",
            fontsize=14, fontweight="bold")
    ax.text(0.5, 0.45, "12 Gandhi Road, Coimbatore 641001  ·  Tel 0422 244 1100",
            ha="center", fontsize=8.5, color="#444")
    ax.text(0.5, 0.12, "PURE TONE AUDIOMETRY REPORT", ha="center", fontsize=11,
            fontweight="bold")
    ax.axhline(0.02, color="#222", lw=1.2)

    ax = fig.add_subplot(gs[1]); ax.axis("off")
    for i, (left, right) in enumerate([
        ("Patient Name : Rajalakshmi Subramanian", "Date of Test : 14/11/2026"),
        ("Age : 58", "Sex : Female"),
        ("Occupation : Textile mill supervisor", "Referred by : Dr S Natarajan"),
    ]):
        y = 0.82 - i * 0.30
        ax.text(0.0, y, left, fontsize=9.5)
        ax.text(0.55, y, right, fontsize=9.5)

    ax = fig.add_subplot(gs[2])
    x = {f: i for i, f in enumerate(AC_FREQS)}
    ax.set_xlim(-0.5, 5.5)
    ax.set_ylim(120, -10)
    ax.set_xticks(range(6))
    ax.set_xticklabels([str(f) for f in AC_FREQS], fontsize=8)
    ax.set_yticks(range(-10, 121, 10))
    ax.tick_params(labelsize=8)
    ax.grid(True, color="#8a8a8a", linewidth=0.7)
    ax.set_xlabel("Frequency (Hz)", fontsize=9)
    ax.set_ylabel("Hearing Level (dB HL)", fontsize=9)
    for ear, colour, marker, bracket, off in (
            ("right", red, "o", "[", -0.25), ("left", blue, "x", "]", 0.25)):
        ys = [REPORT_CASE[ear]["ac"][f] for f in AC_FREQS]
        ax.plot(list(x.values()), ys, color=colour, lw=1.0, alpha=0.35)
        ax.plot(list(x.values()), ys, ls="none", marker=marker, ms=11,
                markerfacecolor="none", markeredgecolor=colour,
                markeredgewidth=2.2)
        for f, db in REPORT_CASE[ear]["bc"].items():
            ax.text(x[f] + off, db, bracket, color=colour, fontsize=13,
                    fontweight="bold", ha="center", va="center")

    ax = fig.add_subplot(gs[3]); ax.axis("off")
    for i, line in enumerate(REPORT_TEXT):
        ax.text(0.0, 0.95 - i * 0.115, line, fontsize=9.5,
                fontweight="bold" if line == "RESULTS" else "normal")

    ax = fig.add_subplot(gs[4]); ax.axis("off")
    ax.text(0.0, 0.6, "Right: O air / [ bone     Left: X air / ] bone",
            fontsize=7.5, color="#666")
    ax.text(1.0, 0.6, "Audiologist (RCI A-00000)", fontsize=8.5, ha="right")
    ax.plot([0.72, 1.0], [0.95, 0.95], color="#222", lw=0.8)

    SAMPLES.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAMPLES / f"{name}.png", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    for name, case in CASES.items():
        draw(name, case)
    draw_report("report_page")
    draw_report("report_page_bw", grey=True)
    truth = {name: {ear: case[ear] for ear in ("right", "left")}
             for name, case in CASES.items()}
    truth["report_page"] = {ear: REPORT_CASE[ear] for ear in ("right", "left")}
    truth["report_page_bw"] = truth["report_page"]
    (SAMPLES / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(f"wrote 2 sample photos + 2 report pages + ground_truth.json -> {SAMPLES}")
