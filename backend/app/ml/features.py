"""MODULE 2b — Feature engineering shared by training and inference.

19 features per ear:
  - 6 raw AC thresholds (250–8000 Hz)
  - 5 adjacent-frequency slopes (dB per octave step)
  - low-frequency average (250/500/1k), high-frequency average (2k/4k/8k)
  - 4k notch depth: AC@4k − mean(AC@2k, AC@8k)
  - 5 per-frequency air-bone gaps (250–4000 Hz; 0 when BC untested)
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]
BC_FREQS = [250, 500, 1000, 2000, 4000]

FEATURE_NAMES: List[str] = (
    [f"ac_{f}" for f in AC_FREQS]
    + [f"slope_{f1}_{f2}" for f1, f2 in zip(AC_FREQS, AC_FREQS[1:])]
    + ["low_avg", "high_avg", "notch_4k"]
    + [f"abg_{f}" for f in BC_FREQS]
)

#: Which audiogram frequencies each feature "speaks about" — used to
#: aggregate model importances into per-frequency explanation weights.
FEATURE_FREQS: List[List[int]] = (
    [[f] for f in AC_FREQS]
    + [[f1, f2] for f1, f2 in zip(AC_FREQS, AC_FREQS[1:])]
    + [[250, 500, 1000], [2000, 4000, 8000], [4000]]
    + [[f] for f in BC_FREQS]
)


def impute_ac(ac: Dict[int, Optional[float]]) -> Dict[int, float]:
    """Fill untested AC frequencies by nearest-neighbor interpolation.

    The classifier needs all 6 AC values; clinically, adjacent frequencies
    are the best available estimate for an untested one.
    """
    known = {f: v for f, v in ac.items() if v is not None}
    if not known:
        return {f: 0.0 for f in AC_FREQS}
    out: Dict[int, float] = {}
    for i, f in enumerate(AC_FREQS):
        if f in known:
            out[f] = float(known[f])
        else:
            left = next((AC_FREQS[j] for j in range(i - 1, -1, -1) if AC_FREQS[j] in known), None)
            right = next((AC_FREQS[j] for j in range(i + 1, 6) if AC_FREQS[j] in known), None)
            if left and right:
                out[f] = (known[left] + known[right]) / 2
            else:
                out[f] = float(known[left if left else right])
    return out


def build_features(
    ac: Dict[int, Optional[float]], bc: Dict[int, Optional[float]]
) -> np.ndarray:
    """Numeric ac/bc (NR already mapped to 120, None = untested) -> (19,)."""
    a = impute_ac(ac)
    vec = [a[f] for f in AC_FREQS]
    vec += [a[f2] - a[f1] for f1, f2 in zip(AC_FREQS, AC_FREQS[1:])]
    vec.append(np.mean([a[250], a[500], a[1000]]))
    vec.append(np.mean([a[2000], a[4000], a[8000]]))
    vec.append(a[4000] - (a[2000] + a[8000]) / 2)
    for f in BC_FREQS:
        b = bc.get(f)
        vec.append(0.0 if b is None else a[f] - float(b))
    return np.asarray(vec, dtype=float)


def features_from_dataframe(df) -> np.ndarray:
    """Vectorized feature build for the training CSV."""
    rows = []
    for _, r in df.iterrows():
        ac = {f: r[f"ac_{f}"] for f in AC_FREQS}
        bc = {f: r[f"bc_{f}"] for f in BC_FREQS}
        rows.append(build_features(ac, bc))
    return np.vstack(rows)
