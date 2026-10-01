"""MODULE 2b — Feature engineering shared by training and inference.

19 features per ear:
  - 6 raw AC thresholds (250–8000 Hz)
  - 5 adjacent-frequency slopes (dB per octave step)
  - low-frequency average (250/500/1k), high-frequency average (2k/4k/8k)
  - 4k notch depth: AC@4k − mean(AC@2k, AC@8k)
  - 5 per-frequency air-bone gaps (250–4000 Hz; 0 when BC untested)

Also home to the rule-based gates (coverage, normal limits, plausibility,
Coles notch, normal-average corroboration) that decide whether either
model's label may be shown or used.
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
    are the best available estimate for an untested one. Keys outside the
    six model frequencies are ignored — they have no feature to fill.
    """
    known = {f: v for f, v in ac.items() if v is not None and f in AC_FREQS}
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


# ---------------------------------------------------------------------------
# Rule-based gates applied around both models
#
# The models only ever name one of seven loss configurations, and they will
# name one for any input, however little of it was measured or however
# implausible it is. These deterministic checks decide whether a model label
# may be shown at all, and whether it may be acted on. They take the numeric
# AC dict produced by ``ear_to_numeric`` (NR = 120, untested = None).
# ---------------------------------------------------------------------------

#: Audiometric range accepted anywhere in the app (schemas.EarData).
DB_MIN, DB_MAX = -10.0, 120.0

#: Value ``ear_to_numeric`` substitutes for "No Response".
NR_VALUE = 120.0

#: WHO World Report on Hearing (2021): normal hearing is a four-frequency
#: (0.5/1/2/4 kHz) pure-tone average below 20 dB HL.
NORMAL_PTA_LIMIT = 20.0

#: Upper limit of normal for a single threshold: 20 dB HL, where the BSA
#: Recommended Procedure for pure-tone audiometry (2018) starts "mild" at
#: 21 dB HL. It is the per-frequency limit the rest of the app uses
#: (safety.NORMAL_LIMIT_DB, which the verdict headline applies, and
#: oae.EMISSION_EXPECTED_MAX_DB_HL), so the configuration card can never call
#: an ear "within normal limits" at a threshold the headline calls outside
#: them. Applying it to every tested frequency, not only the PTA four, keeps
#: an ear with an isolated loss at 250 Hz or 8 kHz — outside the PTA — out
#: of the "normal" gate so that the model still describes it.
NORMAL_FREQ_LIMIT = 20.0

PTA_FREQS = [500, 1000, 2000, 4000]

#: A configuration is a shape across the audiogram, so it needs most of the
#: audiogram. Five of the six model frequencies, one of which must be 4 kHz:
#: 4 kHz is what separates a noise notch from a flat or sloping loss, and a
#: value imputed there from its neighbours can never show a notch.
MIN_AC_FREQS_FOR_PATTERN = 5
REQUIRED_AC_FREQS = (4000,)

#: A threshold this much worse than BOTH neighbouring octaves is a reversal,
#: not a slope: either a keying/response error or a finding that must be
#: confirmed before a configuration is read from it. This is a plausibility
#: heuristic for prompting a retest, not a published limit.
OUTLIER_DB = 30.0

#: 4 kHz is where the noise notch sits (Coles, Lutman & Buffin 2000), so a
#: reversal there is an expected configuration; it is treated as a possible
#: error only from 40 dB against both 2 and 8 kHz. Heuristic, as above.
NOTCH_OUTLIER_DB = 40.0

#: A 4 kHz reversal of NOTCH_OUTLIER_DB or more is still a noise notch —
#: and a deeper notch is stronger evidence of noise injury, not weaker — when
#: it meets the Coles et al. (2000) notch with a 4 kHz threshold outside
#: normal limits and stays within the notch shape both models were trained
#: on: at most this many dB worse than the worse of 2 and 8 kHz (the deepest
#: of the 1,714 training noise notches is 50 dB), recovering to 8 kHz by less
#: than NOTCH_RECOVERY_IMPROVEMENT_DB and falling from 2 kHz by less than
#: STEEP_WORSENING_DB. Such a reversal does not withdraw a noise-notch label
#: (``plausibility_reasons``); because a single keying slip makes the same
#: shape, it still carries a request to confirm 4 kHz on retest
#: (``notch_retest_note``). Heuristic bound, like OUTLIER_DB.
NOISE_NOTCH_MAX_REVERSAL_DB = 50.0

#: Two or more adjacent octaves that sit, as a block, this far from BOTH
#: neighbouring octaves — a plateau raised above the curve on either side, or
#: an island of better hearing below it. Two adjacent cells keyed wrongly
#: (10 entered as 100 twice) make exactly this shape, the single-frequency
#: rule cannot see it, and neither model was trained on it: no bounded block
#: in the 12,000 training audiograms, nor in the textbook configurations the
#: tests use (cookie-bite included), reaches 35 dB. The bar is set above the
#: single-frequency one because two adjacent thresholds that agree are less
#: likely to be one slip. A steep step in ONE direction — a precipitous
#: high-frequency loss, a steep rising loss — is not a block and is never
#: flagged by this rule. Plausibility heuristic for prompting a retest, like
#: OUTLIER_DB, not a published limit.
BLOCK_OUTLIER_DB = 40.0

#: A raised block that includes 4 kHz can be a noise notch broadened into the
#: next octave (Coles et al. 2000 place the notch anywhere in 3-6 kHz), so it
#: gets the same extra 10 dB as a single 4 kHz reversal. Heuristic, as above.
NOTCH_BLOCK_OUTLIER_DB = 50.0

#: A threshold that IMPROVES by this much from one octave to the next one
#: up. Only improving steps are checked: a precipitous high-frequency loss
#: can worsen by 50 dB or more within an octave (the ski-slope training
#: curves reach 60 dB from 2 to 4 kHz, and the textbook ones 50 dB), so a
#: steep worsening step is a configuration, not an error. Improving steps
#: are what rising configurations and notch recoveries are made of; none in
#: the training data exceeds 35 dB below 4 kHz, nor 55 dB from 4 to 8 kHz.
#: Heuristic for prompting a retest, like OUTLIER_DB, not a published limit.
STEEP_IMPROVEMENT_DB = 50.0

#: 4 to 8 kHz is where a noise notch recovers, so that step gets the same
#: extra 10 dB as a 4 kHz reversal — unless the same ear also WORSENS by
#: STEEP_IMPROVEMENT_DB within an octave somewhere: a curve that both climbs
#: and falls back that steeply is a reversal. The only training audiograms
#: that do so are two single-frequency 4 kHz notches, which
#: ``isolated_outliers`` already reports. Heuristic, as above.
NOTCH_RECOVERY_IMPROVEMENT_DB = 60.0

#: A threshold that WORSENS by this much from one tested octave to the next
#: one up, between two measured thresholds (a no-response is not a measured
#: step). Precipitous high-frequency losses are real configurations, so the
#: limits sit well above the steepest worsening step in the 12,000 training
#: audiograms — 35 dB from 250 to 500 Hz and from 500 Hz to 1 kHz, 50 dB from
#: 1 to 2 kHz, 60 dB from 2 to 4 kHz, 35 dB from 4 to 8 kHz — and flag none of
#: them. A step beyond them is one neither model has seen, which a single
#: keying slip (5 entered as 75) produces, and on which both have returned a
#: confident, wrong label. Heuristic for prompting a retest, like
#: OUTLIER_DB, not a published limit.
STEEP_WORSENING_DB = {
    (250, 500): 50.0, (500, 1000): 50.0, (1000, 2000): 70.0,
    (2000, 4000): 75.0, (4000, 8000): 60.0,
}

#: Widest spread of measured thresholds an ear can have and still be read as
#: a "flat" configuration. The trained flat audiograms span at most 10 dB; a
#: flat label on thresholds spread over more than this is a forced label,
#: not a description. No published definition of "flat" could be confirmed,
#: so the bar is set well clear of the training data and only ever withholds
#: reliability. Heuristic, like OUTLIER_DB.
FLAT_MAX_SPAN_DB = 40.0

#: Coles, Lutman & Buffin (2000), Clin Otolaryngol 25:264-273, requirement
#: R3: a notch is present when the threshold at 3, 4 and/or 6 kHz is at least
#: 10 dB greater than at 1 or 2 kHz and at 6 or 8 kHz. This app tests neither
#: 3 nor 6 kHz, so the rule is applied at 4 kHz against 1/2 kHz and 8 kHz.
COLES_NOTCH_DB = 10.0


def _fmt_hz(freqs) -> str:
    return ", ".join(f"{f} Hz" for f in freqs)


def coverage(ac: Dict[int, Optional[float]]) -> dict:
    """Which of the six model frequencies were measured, and whether that is
    enough to describe a configuration."""
    tested = [f for f in AC_FREQS if ac.get(f) is not None]
    untested = [f for f in AC_FREQS if ac.get(f) is None]
    missing_required = [f for f in REQUIRED_AC_FREQS if f not in tested]
    adequate = len(tested) >= MIN_AC_FREQS_FOR_PATTERN and not missing_required
    note = None
    if not adequate:
        note = (
            f"insufficient frequencies: {len(tested)} of {len(AC_FREQS)} "
            "air-conduction frequencies tested"
            + (f" ({_fmt_hz(untested)} untested)" if untested else "")
            + f"; at least {MIN_AC_FREQS_FOR_PATTERN}, including 4000 Hz, are "
            "needed to describe the configuration"
        )
    return {
        "tested": tested,
        "untested": untested,
        "adequate": adequate,
        "complete": not untested,
        "note": note,
    }


def pta4(ac: Dict[int, Optional[float]]) -> Optional[float]:
    """Mean of the tested PTA frequencies (0.5/1/2/4 kHz), as the rules
    engine computes it; None when none of the four was tested."""
    vals = [ac[f] for f in PTA_FREQS if ac.get(f) is not None]
    return sum(vals) / len(vals) if vals else None


def within_normal_limits(ac: Dict[int, Optional[float]]) -> bool:
    """True when hearing is normal by WHO 2021 (PTA4 < 20 dB HL) AND no
    tested threshold exceeds the NORMAL_FREQ_LIMIT (20 dB HL) normal limit."""
    vals = [ac[f] for f in AC_FREQS if ac.get(f) is not None]
    pta = pta4(ac)
    return (
        bool(vals) and pta is not None
        and pta < NORMAL_PTA_LIMIT
        and max(vals) <= NORMAL_FREQ_LIMIT
    )


def isolated_outliers(ac: Dict[int, Optional[float]]) -> List[dict]:
    """Thresholds that break away from both neighbouring octaves.

    Interior frequencies: worse than both neighbours by OUTLIER_DB (by
    NOTCH_OUTLIER_DB at 4 kHz), or better than both by OUTLIER_DB. Edge
    frequencies (250 Hz, 8 kHz) have one neighbour, so they count only when
    they jump OUTLIER_DB worse than it while that neighbour is no worse than
    the next one inward — a reversal of the curve, not the end of a slope —
    and the neighbour is not itself an outlier (a 4 kHz typo of 5 dB must
    not make a true 70 dB at 8 kHz look like the error). Only adjacent tested
    octaves are compared.
    """
    interior: Dict[int, dict] = {}
    n = len(AC_FREQS)
    for i in range(1, n - 1):
        f = AC_FREQS[i]
        v, lo, hi = ac.get(f), ac.get(AC_FREQS[i - 1]), ac.get(AC_FREQS[i + 1])
        if v is None or lo is None or hi is None:
            continue
        worse_by = v - max(lo, hi)
        better_by = min(lo, hi) - v
        limit = NOTCH_OUTLIER_DB if f == 4000 else OUTLIER_DB
        if worse_by >= limit:
            interior[f] = {"freq": f, "direction": "worse", "deviation_db": worse_by}
        elif better_by >= OUTLIER_DB:
            interior[f] = {"freq": f, "direction": "better", "deviation_db": better_by}

    edges: Dict[int, dict] = {}
    for i, step in ((0, 1), (n - 1, -1)):
        f = AC_FREQS[i]
        v = ac.get(f)
        nb_f = AC_FREQS[i + step]
        nb, nb2 = ac.get(nb_f), ac.get(AC_FREQS[i + 2 * step])
        if v is None or nb is None or nb2 is None or nb_f in interior:
            continue
        if v - nb >= OUTLIER_DB and nb <= nb2:
            edges[f] = {"freq": f, "direction": "worse", "deviation_db": v - nb}

    found = {**interior, **edges}
    return [found[f] for f in AC_FREQS if f in found]


def outlier_blocks(ac: Dict[int, Optional[float]]) -> List[dict]:
    """Runs of two or more adjacent octaves that break away together from
    both neighbouring octaves.

    A run is flagged when its best threshold is BLOCK_OUTLIER_DB worse than
    the worse of its two neighbours (NOTCH_BLOCK_OUTLIER_DB when the run
    includes 4 kHz), or its worst threshold is BLOCK_OUTLIER_DB better than
    the better neighbour. Every threshold in the run and both neighbours must
    be tested, so a run never reaches 250 Hz or 8 kHz: a run that does has a
    neighbour on one side only, which makes it a slope, not a block. A run
    containing an ``isolated_outliers`` frequency is left to that rule.
    Overlapping runs describe one anomaly; the largest deviation is kept
    (the longer run on a tie).
    """
    singles = {o["freq"] for o in isolated_outliers(ac)}
    candidates: List[dict] = []
    n = len(AC_FREQS)
    for i in range(1, n - 2):
        for j in range(i + 1, n - 1):
            freqs = AC_FREQS[i:j + 1]
            run = [ac.get(f) for f in freqs]
            lo, hi = ac.get(AC_FREQS[i - 1]), ac.get(AC_FREQS[j + 1])
            if lo is None or hi is None or any(v is None for v in run):
                continue
            if singles.intersection(freqs):
                continue
            worse_by = min(run) - max(lo, hi)
            better_by = min(lo, hi) - max(run)
            limit = NOTCH_BLOCK_OUTLIER_DB if 4000 in freqs else BLOCK_OUTLIER_DB
            if worse_by >= limit:
                candidates.append({"freqs": freqs, "direction": "worse",
                                   "deviation_db": worse_by})
            elif better_by >= BLOCK_OUTLIER_DB:
                candidates.append({"freqs": freqs, "direction": "better",
                                   "deviation_db": better_by})
    kept: List[dict] = []
    for c in sorted(candidates, key=lambda c: (-c["deviation_db"], -len(c["freqs"]))):
        if not any(set(c["freqs"]) & set(k["freqs"]) for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda c: AC_FREQS.index(c["freqs"][0]))


def steep_improvements(ac: Dict[int, Optional[float]]) -> List[dict]:
    """Adjacent tested octaves where the threshold improves by
    STEEP_IMPROVEMENT_DB or more (NOTCH_RECOVERY_IMPROVEMENT_DB from 4 to
    8 kHz, unless the ear also worsens that steeply elsewhere). Steps
    touching a frequency already reported by ``isolated_outliers`` or
    ``outlier_blocks`` are left to those rules, which describe the same
    anomaly more precisely."""
    covered = {o["freq"] for o in isolated_outliers(ac)}
    for b in outlier_blocks(ac):
        covered.update(b["freqs"])
    pairs = [(f1, f2) for f1, f2 in zip(AC_FREQS, AC_FREQS[1:])
             if ac.get(f1) is not None and ac.get(f2) is not None]
    steep_worsening = any(ac[f2] - ac[f1] >= STEEP_IMPROVEMENT_DB for f1, f2 in pairs)
    out: List[dict] = []
    for f1, f2 in pairs:
        v1, v2 = ac[f1], ac[f2]
        if {f1, f2} & covered:
            continue
        limit = (NOTCH_RECOVERY_IMPROVEMENT_DB if f1 == 4000 and not steep_worsening
                 else STEEP_IMPROVEMENT_DB)
        if v1 - v2 >= limit:
            out.append({"freqs": [f1, f2], "improvement_db": v1 - v2})
    return out


def steep_worsenings(ac: Dict[int, Optional[float]]) -> List[dict]:
    """Adjacent tested octaves, both measured (not no-response), where the
    threshold worsens by STEEP_WORSENING_DB or more. Steps touching a
    frequency already reported by ``isolated_outliers`` or ``outlier_blocks``
    are left to those rules."""
    covered = {o["freq"] for o in isolated_outliers(ac)}
    for b in outlier_blocks(ac):
        covered.update(b["freqs"])
    out: List[dict] = []
    for (f1, f2), limit in STEEP_WORSENING_DB.items():
        v1, v2 = ac.get(f1), ac.get(f2)
        if v1 is None or v2 is None or v1 >= NR_VALUE or v2 >= NR_VALUE:
            continue
        if {f1, f2} & covered:
            continue
        if v2 - v1 >= limit:
            out.append({"freqs": [f1, f2], "worsening_db": v2 - v1})
    return out


def label_shape_caveat(ac: Dict[int, Optional[float]],
                       pattern: Optional[str]) -> Optional[str]:
    """Why a configuration label does not describe the measured thresholds,
    or None. Only "flat" has a shape simple enough to check by its spread."""
    if pattern != "flat":
        return None
    measured = [v for v in (ac.get(f) for f in AC_FREQS)
                if v is not None and v < NR_VALUE]
    if len(measured) < 2:
        return None
    span = max(measured) - min(measured)
    if span <= FLAT_MAX_SPAN_DB:
        return None
    return (f"the measured thresholds span {span:g} dB, which is not a flat "
            f"configuration (more than {FLAT_MAX_SPAN_DB:g} dB) — the label does "
            "not describe this audiogram")


def noise_notch_reversal(ac: Dict[int, Optional[float]]) -> Optional[dict]:
    """The 4 kHz isolated outlier when it is a deep noise notch, or None.

    It must be a reversal worse than both 2 and 8 kHz that meets the Coles et
    al. (2000) notch with 4 kHz outside normal limits
    (``noise_notch_with_loss``) and stays within the trained notch shape
    (NOISE_NOTCH_MAX_REVERSAL_DB and the two steep-step limits).
    """
    o = next((o for o in isolated_outliers(ac)
              if o["freq"] == 4000 and o["direction"] == "worse"), None)
    if o is None or not noise_notch_with_loss(ac):
        return None
    v2, v4, v8 = ac[2000], ac[4000], ac[8000]
    if (o["deviation_db"] > NOISE_NOTCH_MAX_REVERSAL_DB
            or v4 - v8 >= NOTCH_RECOVERY_IMPROVEMENT_DB
            or v4 - v2 >= STEEP_WORSENING_DB[(2000, 4000)]):
        return None
    return o


def notch_retest_note(ac: Dict[int, Optional[float]],
                      pattern: Optional[str]) -> Optional[str]:
    """For a noise-notch label resting on a deep 4 kHz reversal, the request
    to confirm 4 kHz that goes with it; None otherwise."""
    if pattern != "noise_notch_4k":
        return None
    o = noise_notch_reversal(ac)
    if o is None:
        return None
    return (f"the 4000 Hz threshold is {o['deviation_db']:g} dB worse than both "
            "neighbouring octaves — a deep noise notch by Coles et al. (2000), "
            "and also the shape a single keying slip makes, so confirm 4000 Hz "
            "on retest")


def plausibility_reasons(ac: Dict[int, Optional[float]],
                         pattern: Optional[str] = None) -> List[str]:
    """Reasons an audiogram cannot be taken at face value by either model.

    ``pattern`` is the label being judged. A deep 4 kHz reversal that is a
    noise notch (``noise_notch_reversal``) is not a reason to withdraw a
    noise-notch label — it is the configuration that label names — so it is
    left out for that label only; ``notch_retest_note`` carries its retest
    request. For any other label, or none, it is reported like every other
    isolated outlier.
    """
    reasons: List[str] = []
    vals = {f: v for f, v in ac.items() if v is not None}
    for f, v in sorted(vals.items()):
        if not (DB_MIN <= v <= DB_MAX):
            reasons.append(
                f"threshold {v:g} dB HL at {f} Hz is outside the audiometric "
                f"range {DB_MIN:g}..{DB_MAX:g}")
    tested = [ac[f] for f in AC_FREQS if ac.get(f) is not None]
    if tested and all(v >= NR_VALUE for v in tested):
        reasons.append(
            "no response at any tested frequency — the configuration is not "
            "measurable; confirm the result before interpreting a shape")
    notch = notch_retest_note(ac, pattern) is not None
    for o in isolated_outliers(ac):
        if notch and o["freq"] == 4000 and o["direction"] == "worse":
            continue
        side = "worse" if o["direction"] == "worse" else "better"
        reasons.append(
            f"isolated outlier at {o['freq']} Hz ({o['deviation_db']:g} dB "
            f"{side} than the neighbouring octave"
            + ("s" if o["freq"] not in (AC_FREQS[0], AC_FREQS[-1]) else "")
            + ") — retest this frequency")
    for b in outlier_blocks(ac):
        freqs = [f"{f} Hz" for f in b["freqs"]]
        reasons.append(
            f"the thresholds at {', '.join(freqs[:-1])} and {freqs[-1]} sit "
            f"together {b['deviation_db']:g} dB {b['direction']} than the octave "
            "on either side — a block neither model was trained on, and the "
            "shape adjacent keying errors make; retest these frequencies")
    for s in steep_improvements(ac):
        f1, f2 = s["freqs"]
        reasons.append(
            f"the threshold improves by {s['improvement_db']:g} dB from {f1} Hz "
            f"to {f2} Hz, within one octave — steeper than any rising or "
            "recovering configuration either model was trained on; retest both "
            "frequencies")
    for s in steep_worsenings(ac):
        f1, f2 = s["freqs"]
        reasons.append(
            f"the threshold worsens by {s['worsening_db']:g} dB from {f1} Hz to "
            f"{f2} Hz, within one octave — steeper than any configuration either "
            "model was trained on; retest both frequencies")
    return reasons


def coles_notch_4k(ac: Dict[int, Optional[float]]) -> Optional[bool]:
    """Coles et al. (2000) notch at 4 kHz. None when it cannot be assessed:
    4 kHz or 8 kHz untested, both 1 and 2 kHz untested, or no response at
    4 kHz (the true threshold there is unknown)."""
    v4, v8 = ac.get(4000), ac.get(8000)
    refs = [ac[f] for f in (1000, 2000) if ac.get(f) is not None]
    if v4 is None or v8 is None or not refs or v4 >= NR_VALUE:
        return None
    return v4 - min(refs) >= COLES_NOTCH_DB and v4 - v8 >= COLES_NOTCH_DB


def noise_notch_with_loss(ac: Dict[int, Optional[float]]) -> Optional[bool]:
    """A Coles notch whose 4 kHz threshold is outside normal limits.

    Coles et al. (2000) R1 asks for a high-frequency threshold at least 10 dB
    worse than at 1 or 2 kHz, which the R3 test in ``coles_notch_4k`` already
    implies. Requiring 4 kHz to lie outside the per-frequency normal limit
    (NORMAL_FREQ_LIMIT) as well is this app's addition, not part of Coles: a
    dip between thresholds that are all within normal limits is not called
    noise damage, in a single report or in a screening cohort's notch rate.
    """
    notch = coles_notch_4k(ac)
    if notch is None:
        return None
    return notch and ac[4000] > NORMAL_FREQ_LIMIT


#: Where each configuration puts the loss. In an ear whose four-frequency
#: average is normal, a label is only acted on when every threshold outside
#: normal limits lies inside this region (``normal_average_caveat``).
SHAPE_REGIONS = {
    "rising": (250, 500, 1000),
    "cookie_bite": (500, 1000, 2000),
    "sloping_high_frequency": (2000, 4000, 8000),
    "ski_slope": (2000, 4000, 8000),
}

#: Configurations that cannot coexist with a normal four-frequency average:
#: a flat loss raises the PTA frequencies alike, and a corner audiogram is a
#: profound loss with residual low-frequency hearing.
NO_SHAPE_WITH_NORMAL_AVERAGE = {
    "flat": "a flat configuration is a loss across the frequencies, which a "
            "normal average rules out",
    "corner_audiogram": "a corner audiogram is a profound loss, which a normal "
                        "average rules out",
}

#: A configuration is a shape, so apart from the noise notch it needs the
#: loss at more than one frequency before it is read from an ear whose
#: average is normal; one raised threshold there is an isolated finding to
#: confirm on retest. Heuristic, like OUTLIER_DB, not a published limit.
MIN_ABNORMAL_FOR_SHAPE = 2


def normal_average_caveat(
    ac: Dict[int, Optional[float]], pattern: Optional[str]
) -> Optional[str]:
    """Why a configuration label cannot be acted on in an ear graded Normal
    hearing by WHO 2021 (PTA4 < 20 dB HL) that still has thresholds above the
    NORMAL_FREQ_LIMIT. None when it can, or when the rule does not apply (no
    label, a loss by grade, or every threshold within normal limits — the
    normal gate's case).

    Such an ear has no hearing loss by grade, so the label must be carried by
    the abnormal thresholds themselves:

    - noise notch: the Coles et al. (2000) notch at 4 kHz with 4 kHz outside
      normal limits (``noise_notch_with_loss``). Coles define the notch by a
      dip at the notch frequency (R3), so one abnormal threshold is enough
      when it meets that rule.
    - rising, cookie-bite, sloping, ski-slope: at least
      MIN_ABNORMAL_FOR_SHAPE abnormal thresholds, all inside the region the
      configuration names (SHAPE_REGIONS).
    - flat, corner audiogram, or any label without a region: never.
    """
    if pattern in (None, "normal"):
        return None
    pta = pta4(ac)
    if pta is None or pta >= NORMAL_PTA_LIMIT:
        return None
    abnormal = [f for f in AC_FREQS
                if ac.get(f) is not None and ac[f] > NORMAL_FREQ_LIMIT]
    if not abnormal:
        return None
    lead = (
        f"the four-frequency average ({round(pta, 1):g} dB HL) is within WHO 2021 "
        f"normal limits and only {_fmt_hz(abnormal)} "
        f"{'is' if len(abnormal) == 1 else 'are'} above {NORMAL_FREQ_LIMIT:g} dB HL"
    )
    if pattern == "noise_notch_4k":
        if noise_notch_with_loss(ac):
            return None
        return (lead + " — the 4 kHz dip does not meet, or cannot be assessed "
                "against, the Coles et al. (2000) notch criteria, so no noise "
                "notch is established")
    region = SHAPE_REGIONS.get(pattern)
    if region is None:
        reason = NO_SHAPE_WITH_NORMAL_AVERAGE.get(
            pattern, "this configuration is not defined for a normal average")
        return f"{lead} — {reason}"
    if len(abnormal) < MIN_ABNORMAL_FOR_SHAPE:
        return (lead + " — one raised threshold is an isolated finding, not a "
                "loss configuration; confirm it on retest")
    outside = [f for f in abnormal if f not in region]
    if outside:
        return (lead + f" — {_fmt_hz(outside)} "
                f"{'lies' if len(outside) == 1 else 'lie'} outside the region "
                f"this configuration names ({_fmt_hz(region)})")
    return None
