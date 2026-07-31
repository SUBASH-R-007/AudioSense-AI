"""Render realistic paper-audiogram photos for the Snap-to-Digitize demo.

Produces samples/audiogram_photo_1.png (noise notch) and
samples/audiogram_photo_2.png (presbycusis) plus ground_truth.json used by
the digitizer regression test. Clinical notation: right ear red (O = AC,
[ = BC), left ear blue (X = AC, ] = BC), inverted dB axis.

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


if __name__ == "__main__":
    for name, case in CASES.items():
        draw(name, case)
    truth = {name: {ear: case[ear] for ear in ("right", "left")}
             for name, case in CASES.items()}
    (SAMPLES / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(f"wrote 2 sample photos + ground_truth.json -> {SAMPLES}")
