"""Auditory evoked potentials: ABR, MLR and LLR.

Three recordings of the same ascending pathway, separated by when they happen
after the stimulus and therefore by how far up the pathway they are generated:

    ABR    0-10 ms      eighth nerve and brainstem
    MLR    10-80 ms     thalamus and thalamocortical radiations, primary cortex
    LLR    50-350 ms    auditory cortex and association areas

Together they cover periphery to cortex, which is why a case that stops at the
ABR can miss a lesion above the brainstem entirely.

ABR is the workhorse: it estimates behavioural thresholds in infants and in
anyone who cannot give a voluntary response, and it detects retrocochlear
disease. Wave V is the component used for both, because it survives to the
lowest intensities — earlier waves disappear as level drops while Wave V is
still identifiable near threshold.

WHAT MAKES A LATENCY ABNORMAL. An absolute latency means nothing without the
intensity it was recorded at: Wave V sits near 5.4 ms at 90 dB nHL and near
7.5 ms at 20 dB. Every comparison here is against the normative mean for the
intensity actually used, expressed in standard deviations, and both the 2 SD
and 3 SD limits are reported because clinics differ on which they treat as the
cut-off.

INTERPEAK LATENCIES MATTER MORE THAN ABSOLUTE ONES. A conductive loss delays
everything equally and leaves I-V unchanged; a retrocochlear lesion stretches
the intervals. So I-III, III-V and I-V are the values that separate "quieter"
from "slower", and the interaural Wave V difference is the classic asymmetry
check.

Sources: ABR normative table and figures from the supplied reference (Table
2-3, normal females 20-30 years); MLR parameters and abnormal patterns from
the supplied seminar (Hall 2007; Katz et al.; Musiek & Baran); LLR parameters
from the supplied reference (Atcherson & Stoody 2012; Hall 2007; Katz 2015).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

# ==========================================================================
# ABR
# ==========================================================================
#: Delay between stimulus and the zero point for latency calculation when
#: insert earphones are used, ms. The reference figures carry it explicitly;
#: forgetting it shifts every wave by almost a millisecond and turns a normal
#: trace into a delayed one.
INSERT_DELAY_MS = 0.9

ABR_WAVES = ["I", "II", "III", "IV", "V", "VI"]
ABR_INTERWAVE = ["I-III", "III-V", "I-V"]

#: Table 2-3 from the supplied reference: absolute and interwave latency
#: means with one standard deviation, by stimulus intensity, for normal-hearing
#: females aged 20-30. ``n`` is the number of subjects contributing to each
#: value — it falls sharply at low intensities and for the minor waves, which
#: is why a "missing" Wave I at 40 dB nHL is unremarkable.
#:
#: Structure: intensity -> {"psp": dB peak SPL, "waves": {wave: (mean, sd, n)},
#:                          "interwave": {pair: (mean, sd, n)}}
ABR_NORMS: Dict[int, dict] = {
    90: {"psp": 126,
         "waves": {"I": (1.53, .11, 14), "II": (2.53, .09, 14), "III": (3.58, .09, 14),
                   "IV": (4.56, .17, 14), "V": (5.37, .12, 14), "VI": (7.09, .39, 14)},
         "interwave": {"I-III": (2.05, .14, 14), "III-V": (1.79, .14, 14),
                       "I-V": (3.84, .16, 14)}},
    80: {"psp": 116,
         "waves": {"I": (1.62, .12, 14), "II": (2.68, .11, 14), "III": (3.68, .08, 14),
                   "IV": (4.68, .22, 11), "V": (5.47, .12, 14), "VI": (7.29, .17, 13)},
         "interwave": {"I-III": (2.06, .11, 14), "III-V": (1.79, .09, 14),
                       "I-V": (3.85, .14, 14)}},
    70: {"psp": 106,
         "waves": {"I": (1.82, .17, 14), "II": (2.79, .12, 14), "III": (3.85, .13, 14),
                   "IV": (4.92, .24, 11), "V": (5.64, .16, 14), "VI": (7.31, .19, 9)},
         "interwave": {"I-III": (2.03, .11, 14), "III-V": (1.79, .12, 14),
                       "I-V": (3.82, .11, 14)}},
    60: {"psp": 96,
         "waves": {"I": (2.04, .20, 9), "II": (2.98, .15, 6), "III": (4.06, .21, 10),
                   "IV": (5.11, .31, 9), "V": (5.88, .25, 14), "VI": (7.34, .31, 9)},
         "interwave": {"I-III": (2.02, .12, 8), "III-V": (1.72, .10, 10),
                       "I-V": (3.75, .11, 9)}},
    50: {"psp": 86,
         "waves": {"I": (2.43, .17, 4), "II": (3.69, .10, 2), "III": (4.60, .23, 13),
                   "IV": (5.43, .25, 5), "V": (6.19, .32, 14), "VI": (8.24, .34, 2)},
         "interwave": {"I-III": (2.02, .19, 4), "III-V": (1.56, .18, 13),
                       "I-V": (3.64, .19, 4)}},
    40: {"psp": 76,
         "waves": {"I": (3.01, .25, 4), "II": (4.05, .18, 2), "III": (4.94, .25, 7),
                   "IV": (5.65, .49, 5), "V": (6.65, .32, 14)},
         "interwave": {"I-III": (1.85, .14, 4), "III-V": (1.71, .14, 7),
                       "I-V": (3.60, .11, 4)}},
    30: {"psp": 66,
         "waves": {"III": (5.45, .30, 7), "V": (7.24, .42, 14)},
         "interwave": {"III-V": (1.74, .26, 7)}},
    20: {"psp": 56,
         "waves": {"III": (5.56, .57, 2), "V": (7.52, .63, 7)},
         "interwave": {"III-V": (1.88, .23, 2)}},
}

#: Interaural Wave V latency difference above which asymmetry is significant.
ABR_INTERAURAL_V_MS = 0.4
#: A cochlear microphonic appears in the first millisecond. Present CM with an
#: absent or grossly abnormal ABR is the auditory neuropathy picture.
CM_WINDOW_MS = (0.0, 1.0)
#: ABR amplitudes are tiny — this is the expected range, µV.
ABR_AMPLITUDE_UV = (0.1, 1.0)

ABR_PROTOCOL = {
    "stimulus": "100 µs click",
    "recording_window_ms": 10,
    "clinically_useful_waves": ["I", "III", "V"],
    "threshold_wave": "V",
    "typical_intensities_db_nhl": [40, 80],
    "click_rates_per_s": [17.7, 57.7],
    "amplitude_uv": list(ABR_AMPLITUDE_UV),
    "note": ("Wave V persists to the lowest intensities while earlier waves "
             "disappear, which is why threshold estimation follows Wave V."),
}


def _nearest_intensity(intensity: float) -> int:
    """The normative row to compare against.

    Latency depends on level, so a 75 dB recording compared against the 90 dB
    row would look delayed when it is not.
    """
    return min(ABR_NORMS, key=lambda k: abs(k - intensity))


def _z(value: float, mean: float, sd: float) -> float:
    return round((value - mean) / sd, 2) if sd else 0.0


def _limits(mean: float, sd: float) -> dict:
    return {
        "mean": mean, "sd": sd,
        "sd2": [round(mean - 2 * sd, 2), round(mean + 2 * sd, 2)],
        "sd3": [round(mean - 3 * sd, 2), round(mean + 3 * sd, 2)],
    }


def analyze_abr(
    waves: Dict[str, Optional[float]],
    intensity: float = 80,
    ear: str = "right",
    insert_earphones: bool = True,
    latencies_include_delay: bool = True,
    cm_present: Optional[bool] = None,
) -> dict:
    """One ABR run: absolute latencies, interpeak intervals, and what they mean.

    ``latencies_include_delay`` says whether the recorded values still contain
    the 0.9 ms insert-earphone delay. If they do it is removed before
    comparison, because the normative table is expressed without it.
    """
    row_key = _nearest_intensity(intensity)
    row = ABR_NORMS[row_key]
    correction = (INSERT_DELAY_MS
                  if insert_earphones and latencies_include_delay else 0.0)

    absolute: List[dict] = []
    corrected: Dict[str, float] = {}
    for wave in ABR_WAVES:
        raw = waves.get(wave)
        if raw is None:
            absolute.append({"wave": wave, "recorded": None, "present": False,
                             "norm": _limits(*row["waves"][wave][:2])
                             if wave in row["waves"] else None,
                             "expected_at_this_level": wave in row["waves"]})
            continue
        value = round(float(raw) - correction, 2)
        corrected[wave] = value
        norm = row["waves"].get(wave)
        entry = {"wave": wave, "recorded": float(raw), "latency": value,
                 "present": True, "expected_at_this_level": norm is not None}
        if norm:
            mean, sd, n = norm
            z = _z(value, mean, sd)
            entry.update({
                "norm": _limits(mean, sd), "n": n, "z": z,
                "within_2sd": abs(z) <= 2, "within_3sd": abs(z) <= 3,
                "delayed": z > 2,
            })
        absolute.append(entry)

    interwave: List[dict] = []
    for pair in ABR_INTERWAVE:
        a, b = pair.split("-")
        if a not in corrected or b not in corrected:
            interwave.append({"pair": pair, "value": None, "present": False})
            continue
        value = round(corrected[b] - corrected[a], 2)
        norm = row["interwave"].get(pair)
        entry = {"pair": pair, "value": value, "present": True}
        if norm:
            mean, sd, n = norm
            z = _z(value, mean, sd)
            entry.update({"norm": _limits(mean, sd), "n": n, "z": z,
                          "within_2sd": abs(z) <= 2, "within_3sd": abs(z) <= 3,
                          "prolonged": z > 2})
        interwave.append(entry)

    findings: List[str] = []
    flags: List[str] = []

    wave_v = next((w for w in absolute if w["wave"] == "V"), None)
    if not wave_v or not wave_v["present"]:
        flags.append("wave_v_absent")
        findings.append(
            f"No Wave V at {intensity:g} dB nHL. Wave V is the last component to "
            "disappear, so its absence at a high level is the significant finding "
            "— repeat at maximum output before concluding.")

    prolonged = [e for e in interwave if e.get("prolonged")]
    if prolonged:
        flags.append("interpeak_prolonged")
        findings.append(
            "Prolonged " + ", ".join(e["pair"] for e in prolonged) +
            " interpeak latency. A conductive loss delays every wave equally and "
            "leaves the intervals intact, so a stretched interval points above "
            "the cochlea — retrocochlear until excluded.")

    delayed_only = [e for e in absolute
                    if e.get("delayed") and not any(x.get("prolonged")
                                                    for x in interwave)]
    if delayed_only and not prolonged:
        findings.append(
            "Absolute latencies are prolonged with normal interpeak intervals — "
            "the pattern of a conductive or cochlear loss shifting the whole "
            "response later, not of a neural lesion.")

    if cm_present:
        flags.append("cochlear_microphonic_present")
        findings.append(
            f"Cochlear microphonic present in the first {CM_WINDOW_MS[1]:g} ms. "
            "With an absent or grossly abnormal ABR this is auditory neuropathy "
            "spectrum disorder — the outer hair cells work and the neural "
            "response does not.")

    return {
        "ear": ear,
        "intensity_db_nhl": intensity,
        "norm_row_db_nhl": row_key,
        "norm_row_psp": row["psp"],
        "insert_delay_removed": correction > 0,
        "insert_delay_ms": correction,
        "absolute": absolute,
        "interwave": interwave,
        "cm_present": cm_present,
        "flags": flags,
        "findings": findings,
        "protocol": dict(ABR_PROTOCOL),
        "note": ("Latencies are compared against the normative row for the "
                 f"intensity used ({row_key} dB nHL), because Wave V moves from "
                 "about 5.4 ms at 90 dB to 7.5 ms at 20 dB. An absolute latency "
                 "without its intensity is uninterpretable."),
    }


def abr_asymmetry(right: Optional[dict], left: Optional[dict]) -> Optional[dict]:
    """Interaural Wave V difference — the classic retrocochlear screen."""
    def wave_v(side):
        if not side:
            return None
        entry = next((w for w in side["absolute"] if w["wave"] == "V"), None)
        return entry.get("latency") if entry and entry.get("present") else None

    r, l = wave_v(right), wave_v(left)
    if r is None or l is None:
        return None
    difference = round(abs(r - l), 2)
    significant = difference > ABR_INTERAURAL_V_MS
    return {
        "right_wave_v": r, "left_wave_v": l,
        "difference": difference,
        "criterion": ABR_INTERAURAL_V_MS,
        "significant": significant,
        "poorer_ear": ("right" if r > l else "left") if significant else None,
        "message": (
            f"Wave V differs between ears by {difference:g} ms, beyond the "
            f"{ABR_INTERAURAL_V_MS:g} ms criterion. Investigate the ear with the "
            "later response for retrocochlear pathology."
            if significant else
            f"Interaural Wave V difference {difference:g} ms is within the "
            f"{ABR_INTERAURAL_V_MS:g} ms criterion."),
    }


def abr_threshold(series: Sequence[dict]) -> Optional[dict]:
    """Estimated behavioural threshold from the lowest level with a Wave V.

    ``series``: [{"intensity": dB nHL, "wave_v": latency or None}] — the
    intensity ladder actually run. The estimate is the lowest level at which a
    reproducible Wave V was identified, and it is a *minimum response level*
    for the electrophysiological response, which sits close to but not on the
    behavioural threshold.
    """
    rows = sorted(
        ({"intensity": float(r["intensity"]),
          "wave_v": r.get("wave_v"),
          "present": r.get("wave_v") is not None}
         for r in series or []),
        key=lambda r: r["intensity"])
    if not rows:
        return None

    present = [r for r in rows if r["present"]]
    if not present:
        return {
            "rows": rows, "estimated_threshold": None, "no_response": True,
            "message": (f"No Wave V at any level tested, down to "
                        f"{max(r['intensity'] for r in rows):g} dB nHL. Repeat at "
                        "maximum output before reporting an absent response."),
        }

    lowest = min(present, key=lambda r: r["intensity"])
    # Latency-intensity behaviour separates conductive from cochlear loss: a
    # conductive loss shifts the whole function later without changing its
    # slope, a cochlear loss steepens it near threshold.
    highest = max(present, key=lambda r: r["intensity"])
    shift = (round(lowest["wave_v"] - highest["wave_v"], 2)
             if lowest["wave_v"] is not None and highest["wave_v"] is not None
             and lowest is not highest else None)

    return {
        "rows": rows,
        "estimated_threshold": lowest["intensity"],
        "no_response": False,
        "wave_v_at_threshold": lowest["wave_v"],
        "latency_shift_ms": shift,
        "message": (
            f"Wave V identifiable to {lowest['intensity']:g} dB nHL, which is the "
            "estimated electrophysiological threshold. It approximates the "
            "behavioural threshold and is not a substitute for it."),
    }


# ==========================================================================
# MLR
# ==========================================================================
#: Peak: (low ms, high ms, polarity, generator)
MLR_NORMS: Dict[str, dict] = {
    "Na": {"range": (15, 20), "polarity": "negative",
           "generator": "Thalamus / thalamocortical radiations"},
    "Pa": {"range": (24, 32), "polarity": "positive",
           "generator": "Primary auditory cortex (Heschl's gyrus)"},
    "Nb": {"range": (35, 42), "polarity": "negative",
           "generator": "Auditory cortex (continued activation)"},
    "Pb": {"range": (48, 56), "polarity": "positive",
           "generator": "Auditory cortex / association areas"},
}
MLR_PEAKS = list(MLR_NORMS)

MLR_PROTOCOL = {
    "window_ms": [10, 80],
    "analysis_window_ms": 100,
    "stimulus": "Clicks or tone bursts, 70-80 dB nHL",
    "filter_hz": [10, 200],
    "electrodes": "Non-inverting Cz; inverting A1/A2; ground Fpz",
    "sweeps": [500, 1000],
    "patient_state": "Awake, relaxed, minimal muscle tension",
    "primary_peak": "Pa",
    "note": ("Pa is the largest and most repeatable component and anchors "
             "interpretation. Post-auricular muscle activity can overlap the "
             "early components, which is why relaxation matters."),
}

#: The abnormal patterns named in the supplied seminar, with their correlates.
MLR_PATTERNS: Dict[str, dict] = {
    "delayed_all": {
        "label": "Delayed absolute latencies",
        "description": ("All major peaks occur later than their normative "
                        "ranges — overall slowing along the thalamocortical "
                        "pathway rather than a problem at one site."),
        "causes": ["Diffuse white matter or demyelinating pathology",
                   "Maturational delay in paediatric recordings",
                   "Sedation or anaesthesia during testing"],
    },
    "delayed_pa": {
        "label": "Delayed Pa latency",
        "description": ("Pa alone is prolonged beyond 24-32 ms while Na and "
                        "later components remain relatively preserved — a more "
                        "localised disruption."),
        "causes": ["Focal dysfunction of the primary auditory cortex",
                   "Disruption along thalamocortical radiations"],
    },
    "absent_na": {
        "label": "Absent Na",
        "description": ("No reproducible Na across repeated recordings. Na is "
                        "generated at the thalamic level and is inherently less "
                        "robust than Pa, so its absence needs care."),
        "causes": ["Thalamic-level pathology in some cases",
                   "Technical: poor montage, high impedance, myogenic artifact",
                   "Normal inter-subject variability — Na is less reliable than Pa"],
    },
    "reduced_amplitude": {
        "label": "Reduced amplitudes",
        "description": ("Peak-to-peak amplitudes, especially Na-Pa, are smaller "
                        "than expected — reduced neural synchrony or fewer "
                        "synchronously firing generators."),
        "causes": ["Cortical dysfunction reducing synchronous firing",
                   "High-frequency hearing loss lowering neural synchrony",
                   "Myogenic contamination or excessive sedation"],
    },
    "prolonged_interpeak": {
        "label": "Prolonged interpeak latencies",
        "description": ("Intervals between successive peaks are increased even "
                        "when absolute latencies are near normal — slowed "
                        "transmission between generator sites."),
        "causes": ["Demyelination affecting thalamocortical conduction",
                   "Disrupted synaptic transmission between relay stations",
                   "Subtle delays not evident from absolute latency alone"],
    },
    "disorganized": {
        "label": "Poorly defined / disorganised waves",
        "description": ("Peaks lack clear repeatable morphology across "
                        "replications, making peak identification unreliable."),
        "causes": ["Post-auricular muscle artifact from poor relaxation",
                   "High electrode impedance or technical issues",
                   "Neurological dysfunction disrupting cortical synchrony"],
    },
    "asymmetric": {
        "label": "Asymmetrical MLR",
        "description": ("A marked amplitude or latency difference between "
                        "hemispheres or recording sites for equivalent "
                        "stimulation."),
        "causes": ["Unilateral or lateralised lesion along the pathway or cortex",
                   "Asymmetric hearing loss reducing synchrony from one ear",
                   "Site-specific cortical dysfunction"],
    },
    "polarity_reversal": {
        "label": "Reversal of polarity",
        "description": ("The expected Na-Pa-Nb-Pb negative-positive sequence "
                        "appears inverted."),
        "causes": ["Reversed or swapped electrode connections — exclude first",
                   "Atypical generator orientation in rare cases",
                   "Equipment or channel-configuration errors"],
    },
}

#: Amplitude below which Na-Pa counts as reduced, µV.
MLR_NA_PA_MIN_UV = 0.5
#: Interhemispheric amplitude ratio beyond which the MLR is asymmetric.
MLR_ASYMMETRY_RATIO = 2.0


def analyze_mlr(peaks: Dict[str, Optional[float]],
                amplitudes: Optional[Dict[str, float]] = None,
                ear: str = "right",
                opposite_amplitudes: Optional[Dict[str, float]] = None,
                sedated: bool = False) -> dict:
    """One MLR run against the normative windows, with pattern recognition."""
    amplitudes = amplitudes or {}
    rows: List[dict] = []
    for name in MLR_PEAKS:
        spec = MLR_NORMS[name]
        low, high = spec["range"]
        value = peaks.get(name)
        if value is None:
            rows.append({"peak": name, "latency": None, "present": False,
                         "range": [low, high], "polarity": spec["polarity"],
                         "generator": spec["generator"]})
            continue
        value = float(value)
        rows.append({
            "peak": name, "latency": value, "present": True,
            "range": [low, high], "polarity": spec["polarity"],
            "generator": spec["generator"],
            "within_range": low <= value <= high,
            "delayed": value > high,
            "early": value < low,
        })

    present = [r for r in rows if r["present"]]
    delayed = [r for r in present if r.get("delayed")]
    na_pa = None
    if peaks.get("Na") is not None and peaks.get("Pa") is not None:
        na_pa = round(float(peaks["Pa"]) - float(peaks["Na"]), 1)

    na_pa_amp = amplitudes.get("Na-Pa")
    patterns: List[dict] = []

    def add(key: str, detail: str = "") -> None:
        entry = dict(MLR_PATTERNS[key])
        entry["key"] = key
        if detail:
            entry["detail"] = detail
        patterns.append(entry)

    if len(delayed) >= 3:
        add("delayed_all", f"{len(delayed)} of {len(present)} peaks beyond range.")
    elif any(r["peak"] == "Pa" and r.get("delayed") for r in rows):
        pa = next(r for r in rows if r["peak"] == "Pa")
        add("delayed_pa", f"Pa at {pa['latency']:g} ms against 24-32 ms.")

    if peaks.get("Na") is None and peaks.get("Pa") is not None:
        add("absent_na", "Pa identified but no reproducible Na.")

    if na_pa_amp is not None and na_pa_amp < MLR_NA_PA_MIN_UV:
        add("reduced_amplitude",
            f"Na-Pa {na_pa_amp:g} µV, below {MLR_NA_PA_MIN_UV:g} µV.")

    if opposite_amplitudes and na_pa_amp:
        other = opposite_amplitudes.get("Na-Pa")
        if other:
            ratio = max(na_pa_amp, other) / max(min(na_pa_amp, other), 1e-6)
            if ratio >= MLR_ASYMMETRY_RATIO:
                add("asymmetric",
                    f"Na-Pa amplitude ratio {ratio:.1f}:1 between sides.")

    findings: List[str] = []
    if sedated and delayed:
        findings.append(
            "Sedation was recorded. Sedation and anaesthesia delay and flatten "
            "the MLR, so a delayed trace under sedation is not evidence of "
            "pathology on its own.")
    if not present:
        findings.append("No MLR peaks identified — check montage, impedance and "
                        "patient relaxation before interpreting.")
    elif peaks.get("Pa") is None:
        findings.append(
            "Pa was not identified. It is the largest and most repeatable "
            "component, so its absence is a technical question before it is a "
            "clinical one.")

    return {
        "ear": ear,
        "peaks": rows,
        "na_pa_interval": na_pa,
        "na_pa_amplitude_uv": na_pa_amp,
        "patterns": patterns,
        "abnormal": bool(patterns),
        "findings": findings,
        "protocol": dict(MLR_PROTOCOL),
        "note": ("The MLR bridges the ABR and the LLR, covering the "
                 "thalamocortical pathway that a brainstem response cannot "
                 "reach."),
    }


# ==========================================================================
# LLR
# ==========================================================================
LLR_NORMS: Dict[str, dict] = {
    "P1": {"range": (40, 60), "typical": 50, "polarity": "positive"},
    "N1": {"range": (90, 150), "typical": 100, "polarity": "negative"},
    "P2": {"range": (160, 200), "typical": 180, "polarity": "positive"},
    "N2": {"range": (300, 350), "typical": 325, "polarity": "negative"},
}
LLR_PEAKS = list(LLR_NORMS)

LLR_PROTOCOL = {
    "window_ms": [50, 350],
    "sequence": "P1 → N1 → P2 → N2",
    "most_stable": "N1-P2 complex, especially N1",
    "amplitude_uv": {"n1_or_p2_each": 5, "n1_p2_peak_to_peak": 10},
    "low_pass_hz": "30-40 recommended (as low as 15 possible, but distorts)",
    "high_pass_hz": "0.1 recommended; should not exceed 1",
    "filter_slope": "12 dB/octave",
    "stimulus": ("Any abrupt acoustic onset, offset or change; tone bursts or "
                 "speech stimuli"),
    "reliability": "Good test-retest for both latency and amplitude",
    "generators": ("Predominantly cortical; more superficial than earlier "
                   "potentials, which is why amplitudes are larger"),
}

#: P1 latency shortens as the cortex matures. The supplied reference gives a
#: prominent P1 near 120 ms at 18 months, reaching adult-like values by
#: puberty. This is the basis of the P1 biomarker used in cochlear-implant
#: candidacy: a P1 that stays infantile means the cortex is not being
#: stimulated.
LLR_P1_MATURATION = [
    (0, 12, 140, "Infant — P1 prominent and late"),
    (12, 36, 120, "Toddler — P1 near 120 ms at 18 months"),
    (36, 84, 95, "Preschool / early school age"),
    (84, 144, 75, "School age — approaching adult values"),
    (144, 1200, 55, "Puberty onwards — adult-like morphology and latency"),
]


def expected_p1_latency(age_months: Optional[float]) -> Optional[dict]:
    """Age-appropriate P1 latency, and the band it came from."""
    if age_months is None:
        return None
    for low, high, typical, label in LLR_P1_MATURATION:
        if low <= age_months < high:
            return {"typical_ms": typical, "band": label,
                    "age_range_months": [low, high]}
    return None


def analyze_llr(peaks: Dict[str, Optional[float]],
                amplitudes: Optional[Dict[str, float]] = None,
                age_months: Optional[float] = None,
                ear: str = "right") -> dict:
    """One LLR run: the P1-N1-P2-N2 sequence against its normative windows."""
    amplitudes = amplitudes or {}
    rows: List[dict] = []
    for name in LLR_PEAKS:
        spec = LLR_NORMS[name]
        low, high = spec["range"]
        value = peaks.get(name)
        if value is None:
            rows.append({"peak": name, "latency": None, "present": False,
                         "range": [low, high], "polarity": spec["polarity"]})
            continue
        value = float(value)
        rows.append({
            "peak": name, "latency": value, "present": True,
            "range": [low, high], "polarity": spec["polarity"],
            "within_range": low <= value <= high,
            "delayed": value > high, "early": value < low,
        })

    n1_p2 = None
    if peaks.get("N1") is not None and peaks.get("P2") is not None:
        n1_p2 = round(float(peaks["P2"]) - float(peaks["N1"]), 1)

    findings: List[str] = []
    flags: List[str] = []

    # The P1 maturation check — the reason an LLR is run on a child at all.
    maturation = None
    p1 = peaks.get("P1")
    expected = expected_p1_latency(age_months)
    if p1 is not None and expected:
        delta = round(float(p1) - expected["typical_ms"], 1)
        delayed = delta > 20
        maturation = {
            "p1_latency": float(p1), "expected": expected["typical_ms"],
            "band": expected["band"], "difference": delta, "delayed": delayed,
        }
        if delayed:
            flags.append("cortical_maturation_delayed")
            findings.append(
                f"P1 at {float(p1):g} ms against an age-typical "
                f"{expected['typical_ms']:g} ms ({expected['band']}). A P1 that "
                "stays infantile indicates the auditory cortex is not receiving "
                "adequate stimulation — the biomarker used in cochlear-implant "
                "candidacy and in judging the benefit of amplification.")
        else:
            findings.append(
                f"P1 latency is appropriate for age ({expected['band']}).")

    n1_p2_amp = amplitudes.get("N1-P2")
    if n1_p2_amp is not None and n1_p2_amp < 3:
        flags.append("low_amplitude")
        findings.append(
            f"N1-P2 amplitude {n1_p2_amp:g} µV is small against a typical "
            "10 µV peak-to-peak with moderately intense stimuli.")

    if peaks.get("N1") is None:
        flags.append("n1_absent")
        findings.append(
            "N1 was not identified. It is the most stable component of the "
            "response, so its absence is a technical question first.")

    delayed_peaks = [r for r in rows if r.get("delayed")]
    if len(delayed_peaks) >= 2:
        flags.append("cortical_delay")
        findings.append(
            "Multiple cortical components are prolonged — slowed processing "
            "above the thalamus. Correlate with the MLR and imaging.")

    return {
        "ear": ear,
        "age_months": age_months,
        "peaks": rows,
        "n1_p2_interval": n1_p2,
        "n1_p2_amplitude_uv": n1_p2_amp,
        "maturation": maturation,
        "flags": flags,
        "findings": findings,
        "protocol": dict(LLR_PROTOCOL),
        "note": ("The LLR is state-dependent: attention, arousal and sedation "
                 "all change it, so a poor response in a drowsy patient is not "
                 "a cortical finding."),
    }


# ==========================================================================
# the battery
# ==========================================================================
def aep_battery(abr: Optional[dict] = None, mlr: Optional[dict] = None,
                llr: Optional[dict] = None) -> dict:
    """Where along the pathway the three recordings localise a problem.

    The value of running all three is that they bracket the lesion. A normal
    ABR with an abnormal MLR puts the problem above the brainstem; both normal
    with an abnormal LLR puts it at the cortex. Neither conclusion is available
    from any one recording.
    """
    levels = []
    if abr:
        abnormal = bool(abr.get("flags"))
        levels.append({"test": "ABR", "level": "Eighth nerve and brainstem",
                       "window_ms": [0, 10], "abnormal": abnormal})
    if mlr:
        levels.append({"test": "MLR",
                       "level": "Thalamus, thalamocortical radiations, primary cortex",
                       "window_ms": [10, 80], "abnormal": bool(mlr.get("abnormal"))})
    if llr:
        levels.append({"test": "LLR", "level": "Auditory cortex and association areas",
                       "window_ms": [50, 350], "abnormal": bool(llr.get("flags"))})

    if not levels:
        return {"available": False,
                "note": "No evoked-potential recordings entered."}

    abnormal = [l for l in levels if l["abnormal"]]
    normal_below = [l for l in levels if not l["abnormal"]]

    if not abnormal:
        headline = (f"All {len(levels)} recording"
                    f"{'s' if len(levels) > 1 else ''} within normal limits — the "
                    "pathway is intact as far as they reach.")
    elif len(levels) == 1:
        headline = (f"{abnormal[0]['test']} abnormal. Run the other levels to "
                    "bracket where the problem sits.")
    else:
        lowest_abnormal = abnormal[0]
        below = [l["test"] for l in normal_below
                 if levels.index(l) < levels.index(lowest_abnormal)]
        headline = (
            f"{lowest_abnormal['test']} abnormal"
            + (f" with a normal {' and '.join(below)} below it — the problem sits "
               f"at or above {lowest_abnormal['level'].lower()}."
               if below else
               f" — involvement at {lowest_abnormal['level'].lower()}."))

    return {
        "available": True,
        "levels": levels,
        "abnormal_levels": [l["test"] for l in abnormal],
        "headline": headline,
        "note": ("ABR, MLR and LLR sample the same pathway at increasing "
                 "heights. Running one alone can only exclude problems at that "
                 "height."),
    }
