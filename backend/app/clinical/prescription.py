"""Hearing-aid gain prescription (NAL-R) for the aided simulator preview.

Implements the NAL-R insertion-gain formula (Byrne & Dillon, 1986,
*Ear and Hearing* 7:257-265), the classic linear prescription still used
as a teaching and first-fit reference:

    X      = 0.05 x (H500 + H1000 + H2000)
    IG(f)  = X + 0.31 x H(f) + k(f)

where H(f) is the air-conduction threshold in dB HL and k(f) is a
frequency-dependent constant. The formula is applied at every tested band
of an ear with hearing loss — including bands that are themselves within
normal limits, because the X term carries the prescription there — and a
negative result is set to zero (an aid does not attenuate). Gains are also
capped at a physically realistic maximum.

This drives the "with hearing aid" state of the simulator and the aided
Speech Intelligibility Index. It is a *linear first-fit reference*, not a
substitute for real-ear-verified fitting by an audiologist.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import AC_FREQS, ThresholdValue, ear_to_numeric

#: NAL-R frequency constants k(f), dB (Byrne & Dillon 1986). The published
#: constants stop at 6000 Hz; 8000 Hz carries the 4-6 kHz value of -2.
NAL_R_K = {250: -17, 500: -8, 1000: 1, 2000: -1, 4000: -2, 8000: -2}

#: Maximum insertion gain a real wearable device can deliver before
#: feedback/output limits dominate.
MAX_GAIN_DB = 45.0

#: Lower edge of hearing loss: WHO (2021) World Report on Hearing grades
#: hearing below 20 dB HL as normal. This decides candidacy only — an ear in
#: which no tested threshold reaches 20 dB HL is not fitted at all. It is NOT
#: a per-band cut-off: within a candidate ear NAL-R prescribes gain at every
#: band, normal or not (Byrne & Dillon 1986).
NORMAL_LIMIT_DB = 20.0


#: The three frequencies of the NAL-R X term (Byrne & Dillon 1986).
NAL_R_X_FREQS = (500, 1000, 2000)


def amplification_candidate(ac: Dict[int, Optional[ThresholdValue]]) -> bool:
    """Whether any tested threshold reaches the hearing-loss range."""
    return any(v is not None and v >= NORMAL_LIMIT_DB
               for v in ear_to_numeric(ac).values())


def x_term_frequencies(ac: Dict[int, Optional[ThresholdValue]]) -> List[int]:
    """Which of 500/1000/2000 Hz were tested, i.e. what the X term rests on."""
    numeric = ear_to_numeric(ac)
    return [f for f in NAL_R_X_FREQS if numeric.get(f) is not None]


def nal_r_gains(ac: Dict[int, Optional[ThresholdValue]]) -> Dict[int, float]:
    """Prescribed insertion gain per audiometric frequency, dB."""
    numeric = ear_to_numeric(ac)
    three_fa = [numeric.get(f) for f in (500, 1000, 2000)]
    known = [v for v in three_fa if v is not None]
    if not known or not amplification_candidate(ac):
        return {f: 0.0 for f in AC_FREQS}
    x = 0.05 * sum(known) * (3 / len(known))  # scale if a frequency is missing

    gains: Dict[int, float] = {}
    for f in AC_FREQS:
        h = numeric.get(f)
        if h is None:
            gains[f] = 0.0
            continue
        # Negative NAL-R targets (typically 250/500 Hz of a sloping loss) are
        # set to zero rather than prescribed as attenuation.
        gain = x + 0.31 * h + NAL_R_K[f]
        gains[f] = round(min(MAX_GAIN_DB, max(0.0, gain)), 1)
    return gains


def aided_thresholds(
    ac: Dict[int, Optional[ThresholdValue]],
    gains: Optional[Dict[int, float]] = None,
) -> Dict[int, Optional[float]]:
    """Effective thresholds with the aid on: threshold minus insertion gain.

    Aided thresholds never improve past 0 dB HL — amplification restores
    audibility, it does not create better-than-normal hearing.
    """
    gains = gains if gains is not None else nal_r_gains(ac)
    numeric = ear_to_numeric(ac)
    out: Dict[int, Optional[float]] = {}
    for f in AC_FREQS:
        v = numeric.get(f)
        out[f] = None if v is None else round(max(0.0, v - gains.get(f, 0.0)), 1)
    return out


def verify_fitting(
    ac: Dict[int, Optional[ThresholdValue]],
    aided: Dict[int, Optional[ThresholdValue]],
) -> Optional[dict]:
    """Compare measured aided thresholds against the NAL-R target.

    Functional gain = unaided threshold − aided threshold. A fitting is
    judged on-target when it lands within 10 dB of the prescription, the
    tolerance commonly accepted in real-ear verification. Under-fitting at
    high frequencies is the single most common failure in practice, and it
    is exactly where speech intelligibility is won or lost.
    """
    if not aided:
        return None
    if amplification_candidate(ac) and not x_term_frequencies(ac):
        # Without the X term there is no NAL-R target, and judging measured
        # gain against the placeholder zeros would call any working aid
        # "over target".
        return {
            "bands": [], "mean_abs_deviation": None, "on_target": None,
            "off_target_freqs": [], "tolerance_db": 10,
            "summary": ("The fitting cannot be verified: NAL-R targets need the "
                        "unaided 500, 1000 and 2000 Hz thresholds, and none was "
                        "tested."),
            "action": "Test 500, 1000 and 2000 Hz unaided, then verify again.",
        }
    unaided_n = ear_to_numeric(ac)
    aided_n = ear_to_numeric(aided)
    targets = nal_r_gains(ac)

    bands, deviations = [], []
    for f in AC_FREQS:
        u, a = unaided_n.get(f), aided_n.get(f)
        if u is None or a is None:
            continue
        measured = round(u - a, 1)
        target = targets.get(f, 0.0)
        deviation = round(measured - target, 1)
        deviations.append(abs(deviation))
        bands.append({
            "freq": f, "unaided": u, "aided": a,
            "functional_gain": measured, "target_gain": target,
            "deviation": deviation,
            "status": ("on target" if abs(deviation) <= 10
                       else "under target" if deviation < 0 else "over target"),
        })
    if not bands:
        return None

    off = [b for b in bands if b["status"] != "on target"]
    under_high = [b for b in bands if b["freq"] >= 2000 and b["status"] == "under target"]
    return {
        "bands": bands,
        "mean_abs_deviation": round(sum(deviations) / len(deviations), 1),
        "on_target": not off,
        "off_target_freqs": [b["freq"] for b in off],
        "tolerance_db": 10,
        "summary": (
            "Aided thresholds match the NAL-R prescription within 10 dB at every "
            "frequency — the fitting is verified."
            if not off else
            "Fitting is "
            + ", ".join(f"{b['deviation']:+g} dB {b['status'].split()[0]} at {b['freq']} Hz"
                        for b in off[:4])
            + "."
        ),
        "action": (
            "Increase high-frequency gain — under-fitting above 2 kHz is the usual "
            "cause of 'I hear but can't understand'."
            if under_high else None
        ),
    }


def prescribe(ac: Dict[int, Optional[ThresholdValue]]) -> dict:
    """Full prescription bundle for the UI and the audio graph."""
    gains = nal_r_gains(ac)
    candidate = amplification_candidate(ac)
    x_freqs = x_term_frequencies(ac)
    # NAL-R cannot be computed without its X term: an ear with a loss but no
    # 500/1000/2000 Hz threshold is a candidate the formula cannot fit, which
    # is a different statement from "no gain is needed".
    prescribable = candidate and bool(x_freqs)
    if not candidate:
        note = (f"No tested threshold reaches {NORMAL_LIMIT_DB:g} dB HL (WHO 2021: "
                "normal hearing), so no amplification is indicated and no gain "
                "is prescribed.")
    elif not prescribable:
        note = ("Hearing loss is present, but NAL-R needs the 500, 1000 and "
                "2000 Hz thresholds and none was tested, so no gain can be "
                "prescribed. Test those frequencies before fitting; the zero "
                "gains shown are not a prescription.")
    else:
        note = ("First-fit reference only; real fittings require real-ear "
                "verification by an audiologist.")
        if len(x_freqs) < len(NAL_R_X_FREQS):
            missing = [f for f in NAL_R_X_FREQS if f not in x_freqs]
            note += (" The NAL-R X term is estimated from "
                     + "/".join(str(f) for f in x_freqs) + " Hz alone (the untested "
                     + "/".join(str(f) for f in missing) + " Hz is taken as the mean "
                     "of the tested ones); test it to confirm the prescription.")
    return {
        "method": "NAL-R (Byrne & Dillon 1986) linear insertion gain",
        "gains": gains,
        "aided_thresholds": aided_thresholds(ac, gains),
        "max_gain_db": MAX_GAIN_DB,
        "candidate": candidate,
        "prescribable": prescribable,
        "x_term_freqs": x_freqs,
        "note": note,
    }
