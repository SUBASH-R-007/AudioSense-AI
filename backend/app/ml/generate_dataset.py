"""MODULE 2a — Synthetic audiogram dataset generator.

Synthesizes 12,000 labelled single-ear audiograms across 7 clinically
recognized configurations, with ±5 dB jitter and 5 dB quantization to
mimic real audiometric measurement. Each row: pattern label, AC thresholds
at 250–8000 Hz, BC thresholds at 250–4000 Hz.

Run:  python -m app.ml.generate_dataset
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]
BC_FREQS = [250, 500, 1000, 2000, 4000]
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

PATTERNS = [
    "flat",
    "sloping_high_frequency",
    "ski_slope",
    "rising",
    "noise_notch_4k",
    "cookie_bite",
    "corner_audiogram",
]

rng = np.random.default_rng(42)


def _base_curve(pattern: str) -> np.ndarray:
    """Idealized AC thresholds for one ear, indexed by AC_FREQS."""
    u = rng.uniform
    if pattern == "flat":
        level = u(25, 75)
        return np.full(6, level)
    if pattern == "sloping_high_frequency":
        # Gradual presbycusis-style downward slope.
        start, total_drop = u(10, 30), u(30, 55)
        return start + total_drop * np.linspace(0, 1, 6) ** 1.3
    if pattern == "ski_slope":
        # Normal lows, precipitous drop above 1 kHz.
        low = u(5, 20)
        return np.array([low, low + u(0, 5), low + u(0, 10),
                         low + u(30, 45), u(70, 95), u(75, 100)])
    if pattern == "rising":
        # Low-frequency loss improving toward highs (e.g. Ménière, some conductives).
        low, high = u(40, 65), u(10, 25)
        return np.linspace(low, high, 6)
    if pattern == "noise_notch_4k":
        # Normal-ish with a carved notch at 4 kHz, 8 kHz recovery.
        base = u(5, 25)
        notch = base + u(25, 45)
        return np.array([base, base + u(0, 5), base + u(0, 5),
                         base + u(0, 10), notch, base + u(0, 15)])
    if pattern == "cookie_bite":
        # U-shape: mid frequencies worst (classic hereditary SNHL).
        edge, mid = u(10, 25), u(40, 65)
        half = (mid + edge) / 2
        return np.array([edge, half, mid, mid - u(0, 10), half, edge + u(0, 10)])
    if pattern == "corner_audiogram":
        # Residual low-frequency hearing only; highs at/beyond limits.
        start = u(75, 100)
        return np.array([start, start + u(5, 15), min(120, start + u(15, 30)),
                         120, 120, 120])
    raise ValueError(pattern)


def _quantize(x: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x / 5) * 5, -10, 120)


def synth_ear(pattern: str) -> dict:
    ac = _base_curve(pattern) + rng.uniform(-5, 5, 6)
    ac = _quantize(ac)

    # BC follows AC (sensorineural) with a small physiologic gap; ~30% of
    # flat/rising cases get a true conductive component instead. Bone
    # vibrator output is limited to ~70 dB HL.
    gap = rng.uniform(0, 7, 5)
    if pattern in ("flat", "rising") and rng.random() < 0.30:
        gap = rng.uniform(15, 40, 5)
    bc = _quantize(np.minimum(ac[:5] - gap, 70))

    row = {"pattern": pattern}
    row.update({f"ac_{f}": ac[i] for i, f in enumerate(AC_FREQS)})
    row.update({f"bc_{f}": bc[i] for i, f in enumerate(BC_FREQS)})
    return row


def generate(n_total: int = 12_000) -> pd.DataFrame:
    per_class = n_total // len(PATTERNS)
    rows = [synth_ear(p) for p in PATTERNS for _ in range(per_class)]
    # Top up to exactly n_total with random patterns.
    while len(rows) < n_total:
        rows.append(synth_ear(PATTERNS[rng.integers(len(PATTERNS))]))
    df = pd.DataFrame(rows).sample(frac=1, random_state=42).reset_index(drop=True)
    return df


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = generate()
    out = DATA_DIR / "dataset.csv"
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} rows -> {out}")
    print(df["pattern"].value_counts())
