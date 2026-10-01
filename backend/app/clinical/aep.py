"""Auditory evoked potentials: ABR, MLR and LLR.

Three recordings of the same ascending pathway, separated by when they happen
after the stimulus and therefore by how far up the pathway they are generated:

    ABR    0-10 ms      eighth nerve and brainstem
    MLR    10-80 ms     thalamus and thalamocortical radiations, primary cortex
    LLR    50-350 ms    auditory cortex and association areas

Together they cover periphery to cortex, which is why a case that stops at the
ABR can miss a lesion above the brainstem entirely.

ABR is the workhorse: it estimates hearing levels in infants and in anyone who
cannot give a voluntary response, and it detects retrocochlear disease. Wave V
is the component used for both, because it survives to the lowest intensities
— earlier waves disappear as level drops while Wave V is still identifiable
near threshold.

WHAT MAKES A LATENCY ABNORMAL. An absolute latency means nothing without the
intensity it was recorded at: Wave V sits near 5.4 ms at 90 dB nHL and near
7.5 ms at 20 dB. Every absolute latency is compared against the normative mean
for the intensity actually used (interpolated between table rows), expressed
in standard deviations. ACNS Guideline 9C (2008, section VI) puts the customary
limit at 2.5 or 3 SD from an age-matched control mean; the table here comes
from 14 young women, so it is narrow and female-only, and the module calls a
latency delayed only beyond 3 SD (with an allowance for male sex) and reports
the 2-3 SD zone as borderline rather than as normal.

INTERPEAK LATENCIES MATTER MORE THAN ABSOLUTE ONES. A conductive loss delays
everything equally and leaves I-V unchanged; a retrocochlear lesion stretches
the intervals. So I-III, III-V and I-V are the values that separate "quieter"
from "slower". They are judged against published adult clinical upper limits,
not against the 14-subject table, whose SDs would call a normal man's I-V
retrocochlear; an I-V beyond the adult 95% limit but inside the clinical one
is borderline. A delayed absolute latency is itself an abnormal ABR, and where
the delay begins decides what it means: with Wave I itself late and I-V
normal it is the peripheral pattern; with Wave I on time the delay arises
after it, and even inside the interval limits retrocochlear pathology cannot
be excluded; with Wave I absent the intervals cannot be measured and the same
applies.

Sources: ABR normative table from the supplied reference (Table 2-3, normal
females 20-30 years); abnormality criteria from ACNS Guideline 9C (2008);
interpeak limits from Chiappa, Gladstone & Young 1979 and Misra & Kalita 2008;
the adult I-V 95% limits, the corrected interaural Wave V limit and the
sensation-level rule from Lightfoot 1992/1993 as set out in the BSA
Recommended Procedure for the neurological ABR (2019); the Selters &
Brackmann (1977) correction and its 0.2 ms criterion;
clinical patterns, eHL corrections and the cochlear-microphonic rule from
de Jager, "Auditory Brainstem Response (ABR) in Clinical Practice", Open Access
Guide to Audiology and Hearing Aids for Otolaryngologists; MLR parameters and
abnormal patterns from the supplied seminar (Hall 2007; Katz et al.; Musiek &
Baran); LLR parameters from the supplied reference (Atcherson & Stoody 2012;
Hall 2007; Katz 2015); P1 maturation from Sharma, Dorman & Spahr 2002.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

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
#: The waves an ABR is read on (ACNS Guideline 9C, section V: "Records are
#: analyzed primarily for the presence of waves I, III, and V"). II, IV and VI
#: are reported but never raise a flag on their own.
ABR_KEY_WAVES = ("I", "III", "V")

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

#: Absolute latencies: beyond 3 SD of the intensity-matched mean is delayed,
#: between 2 and 3 SD is borderline. ACNS Guideline 9C (2008, section VI):
#: "it is customary to interpret as abnormal peak latencies, interpeak
#: intervals, and amplitude ratios that are beyond 2.5 or 3 standard deviations
#: from the mean of an age-matched control sample". The wider of the two is
#: used because the table's SDs come from 14 subjects of one sex and age band.
ABR_DELAYED_Z = 3.0
ABR_BORDERLINE_Z = 2.0

#: The table is female-only. "Females have a slightly decreased latency of the
#: later waves (about 0.15 milliseconds)" — Stone et al. 2009, J Clin
#: Neurophysiol 26:167-175, citing Burkard & Sims 2001, Hall 2007 and Picton
#: 1990. For a man the expected III-VI are moved this much later; with sex
#: unknown the allowance is granted before calling a delay, and the zone it
#: covers is reported as borderline instead of normal.
ABR_LATER_WAVES = ("III", "IV", "V", "VI")
ABR_MALE_LATER_WAVE_SHIFT_MS = 0.15

#: Adult upper limits of normal for the interpeak intervals, ms (click, high
#: intensity). Intervals barely move with level ("Reduction in stimulus
#: intensity primarily causes latency prolongation of individual response
#: components without major alteration of interpeak intervals" — ACNS 9C,
#: section VIII), so one limit serves every row.
#:   I-III 2.5 and I-V 4.5: Misra & Kalita, Clinical Neurophysiology, 2nd ed.
#:     2008, as cited by Gathe et al. 2014, J Clin Diagn Res 8(6):BC16-18 (an
#:     Indian adult normative study).
#:   III-V 2.4: Chiappa, Gladstone & Young 1979 (Arch Neurol 36:81-87; 50
#:     normal adults), mean 1.9 +/- 0.18 ms as tabulated by Gathe et al. 2014,
#:     plus the 3 SD of ACNS 9C = 2.44.
#: Chiappa's I-III (2.1 +/- 0.15) and I-V (4.0 +/- 0.23) give 2.55 and 4.69 at
#: 3 SD, so the limits used are the stricter of the two published sources.
ABR_IPL_UPPER_MS: Dict[str, float] = {"I-III": 2.5, "III-V": 2.4, "I-V": 4.5}

#: Adult upper 95% confidence limit of the I-V interval by sex, ms: Lightfoot
#: 1992 (95 men and 94 women, ENT patients aged 13-81 without neurological
#: disease, 80 dB nHL clicks), as tabulated in the BSA Recommended Procedure
#: for the neurological ABR (2019), Table 1 — women 3.98 +/- 0.22 ms, CL 4.34;
#: men 4.12 +/- 0.20 ms, CL 4.46. BSA section 7.7.1 calls an adult I-V "around
#: 4.4 ms" borderline abnormal. An I-V between this limit and the clinical limit
#: above is reported as borderline, never as normal, and it is never the normal
#: interval a peripheral reading rests on. Only I-V carries this tier: "if the
#: I-V IPL is available, it alone should be used in defining nABR test outcome"
#: (BSA 2019 section 7.7, after Lightfoot 1992), because judging every interval
#: at its 95% limit degrades specificity. Sex unknown takes the women's limit.
ABR_I_V_CL95_MS: Dict[str, float] = {"female": 4.34, "male": 4.46}

#: Adult norms only: "Age-specific norms must be used for BAEP studies in
#: subjects younger than 3 years" (ACNS 9C, section IV). Under that age a
#: latency beyond the adult limits is indeterminate, never delayed — infant
#: latencies are longer — while one inside them is inside the infant's too.
ABR_ADULT_NORMS_FROM_MONTHS = 36

#: Wave I is in every one of the 14 reference ears only from 70 dB nHL up (9 of
#: 14 at 60, 4 at 50), so only there is its absence worth a remark.
ABR_WAVE_I_RELIABLE_FROM_DB_NHL = 70

#: Interaural Wave V latency difference above which asymmetry is significant
#: when no hearing-loss correction could be made. De Jager: neurological ABRs
#: are symmetrical when "interaural wave V latencies [are] within 0.4 ms of each
#: other". Only valid between runs at the same stimulus level, because Wave V
#: moves with level.
ABR_INTERAURAL_V_MS = 0.4
#: Selters & Brackmann 1977 (Arch Otolaryngol 103:181-187) hearing-loss
#: correction for the interaural Wave V comparison: 0.1 ms is subtracted from
#: an ear's Wave V for every 10 dB of hearing loss at 4 kHz above 50 dB HL. It
#: is applied per complete 10 dB step, so the correction never exceeds what the
#: rule allows and the screen errs towards sensitivity.
SELTERS_BRACKMANN = {"from_db_hl": 50, "step_db": 10, "ms_per_step": 0.1}
#: A corrected difference is judged against the criteria published for a
#: corrected difference, not against the uncorrected 0.4 ms:
#:   beyond 0.37 ms is significant — the upper 95% limit of the hearing-loss-
#:     corrected interaural Wave V difference (Lightfoot 1992; BSA 2019 Table 1:
#:     mean 0, SD 0.19, CL 0.37, "the ILD V assumes a correction for hearing
#:     loss has been made");
#:   beyond 0.2 ms is Selters & Brackmann's own criterion ("If the difference is
#:     greater than 0.2 ms after compensating for hearing loss at 4 kHz, the
#:     test result is positive" — Don, Kwong & Tanaka 2011, Audiol Neurotol,
#:     PMC3169358). Between the two the result is borderline: positive by the
#:     original criterion, inside the 95% limit, so neither symmetric nor
#:     clearly asymmetric.
ABR_INTERAURAL_V_CORRECTED_MS = 0.37
ABR_INTERAURAL_V_SB_MS = 0.2
#: "Absolute latency measurements must not be relied on in cases of severe or
#: profound hearing loss where the sensation level of the click stimulus is
#: less than 10 dB (referenced to the patient's 4 kHz audiometric threshold)"
#: — BSA 2019 section 7.6, after Lightfoot 1993. Below it the interaural
#: comparison is refused rather than corrected.
ABR_MIN_SENSATION_LEVEL_DB = 10
#: A cochlear microphonic appears in the first millisecond and inverts with
#: stimulus polarity. With no repeatable neural waves it is the auditory
#: neuropathy picture (de Jager: a CM "with no repeatable waves thereafter ...
#: may be indicative of ANSD"); beside a grossly abnormal ABR the later peaks
#: may be the CM ringing on, so ANSD is not excluded until the waves are shown
#: to be repeatable and not to invert.
CM_WINDOW_MS = (0.0, 1.0)
#: ABR amplitudes are tiny — this is the expected range, µV.
ABR_AMPLITUDE_UV = (0.1, 1.0)

#: Typical corrections from an ABR threshold in dB nHL to an estimated
#: behavioural hearing level in dB eHL, subtracted from the nHL value (de
#: Jager, "Correction factors for threshold estimation"). De Jager is explicit
#: that they are "specific to your equipment, your protocol and setting" and
#: should come from the clinic's own young normal-hearing adults; they are
#: reported as typical values, and the click figure is a range.
ABR_EHL_CORRECTION_DB = {
    "tone_burst": {500: 20, 1000: 15, 2000: 10, 4000: 10},
    "nb_chirp": {500: 15, 1000: 10, 2000: 5, 4000: 5},
    "click": (0, 5),
    "ce_chirp": (0, 0),
}
ABR_STIMULI = tuple(ABR_EHL_CORRECTION_DB)

ABR_PROTOCOL = {
    "stimulus": "100 µs click",
    "recording_window_ms": 10,
    "clinically_useful_waves": list(ABR_KEY_WAVES),
    "threshold_wave": "V",
    "typical_intensities_db_nhl": [40, 80],
    "click_rates_per_s": [17.7, 57.7],
    "amplitude_uv": list(ABR_AMPLITUDE_UV),
    "note": ("Wave V persists to the lowest intensities while earlier waves "
             "disappear, which is why threshold estimation follows Wave V."),
}


def _norm_row(intensity: float) -> Tuple[dict, dict]:
    """The normative values to compare against, and where they came from.

    Latency depends on level, so a 75 dB recording compared against the 90 dB
    row would look delayed when it is not, and against the 80 dB row it is
    still judged against a louder stimulus than was used. Between two table
    rows each mean and SD is interpolated linearly in dB; a wave enters the
    blend only if both rows carry it, and ``n`` is the smaller of the two.
    Outside the table the nearest row is used and the result says so.
    """
    levels = sorted(ABR_NORMS)
    intensity = float(intensity)
    if intensity in ABR_NORMS or intensity <= levels[0] or intensity >= levels[-1]:
        key = min(levels, key=lambda k: abs(k - intensity))
        return ABR_NORMS[key], {
            "rows": [key], "interpolated": False,
            "outside_table": intensity < levels[0] or intensity > levels[-1],
        }

    below = max(l for l in levels if l < intensity)
    above = min(l for l in levels if l > intensity)
    f = (intensity - below) / (above - below)
    a, b = ABR_NORMS[below], ABR_NORMS[above]

    def blend(x: dict, y: dict) -> dict:
        return {k: (round(x[k][0] + f * (y[k][0] - x[k][0]), 3),
                    round(x[k][1] + f * (y[k][1] - x[k][1]), 3),
                    min(x[k][2], y[k][2]))
                for k in x if k in y}

    row = {"psp": round(a["psp"] + f * (b["psp"] - a["psp"]), 1),
           "waves": blend(a["waves"], b["waves"]),
           "interwave": blend(a["interwave"], b["interwave"])}
    return row, {"rows": [below, above], "interpolated": True,
                 "outside_table": False}


def _sex_key(sex: Optional[str]) -> Optional[str]:
    """'female', 'male', or None when the record does not say."""
    s = (sex or "").strip().lower()
    if s in ("f", "female", "woman", "girl"):
        return "female"
    if s in ("m", "male", "man", "boy"):
        return "male"
    return None


def _z(value: float, mean: float, sd: float) -> float:
    return round((value - mean) / sd, 2) if sd else 0.0


def _limits(mean: float, sd: float) -> dict:
    return {
        "mean": mean, "sd": sd,
        "sd2": [round(mean - 2 * sd, 2), round(mean + 2 * sd, 2)],
        "sd3": [round(mean - 3 * sd, 2), round(mean + 3 * sd, 2)],
    }


def _wave_list(entries: List[dict]) -> str:
    return ", ".join(f"Wave {e['wave']} {e['latency']:g} ms (z {e['z']:+g})"
                     for e in entries)


def analyze_abr(
    waves: Dict[str, Optional[float]],
    intensity: float = 80,
    ear: str = "right",
    insert_earphones: bool = True,
    latencies_include_delay: bool = True,
    cm_present: Optional[bool] = None,
    sex: Optional[str] = None,
    age_months: Optional[float] = None,
) -> dict:
    """One ABR run: absolute latencies, interpeak intervals, and what they mean.

    ``latencies_include_delay`` says whether the recorded values still contain
    the 0.9 ms insert-earphone delay. If they do it is removed before
    comparison, because the normative table is expressed without it.
    """
    row, row_meta = _norm_row(intensity)
    correction = (INSERT_DELAY_MS
                  if insert_earphones and latencies_include_delay else 0.0)
    sex_key = _sex_key(sex)
    infant = age_months is not None and age_months < ABR_ADULT_NORMS_FROM_MONTHS

    absolute: List[dict] = []
    corrected: Dict[str, float] = {}
    for wave in ABR_WAVES:
        raw = waves.get(wave)
        norm = row["waves"].get(wave)
        if raw is None:
            absolute.append({"wave": wave, "recorded": None, "present": False,
                             "norm": _limits(*norm[:2]) if norm else None,
                             "expected_at_this_level": norm is not None})
            continue
        value = round(float(raw) - correction, 2)
        corrected[wave] = value
        entry = {"wave": wave, "recorded": float(raw), "latency": value,
                 "present": True, "expected_at_this_level": norm is not None}
        if norm:
            mean, sd, n = norm
            z = _z(value, mean, sd)
            later = wave in ABR_LATER_WAVES
            allowance = (ABR_MALE_LATER_WAVE_SHIFT_MS
                         if later and sex_key != "female" else 0.0)
            border_allowance = allowance if sex_key == "male" else 0.0
            upper = round(mean + allowance + ABR_DELAYED_Z * sd, 2)
            border = round(mean + border_allowance + ABR_BORDERLINE_Z * sd, 2)
            delayed = value > upper
            entry.update({
                "norm": _limits(mean, sd), "n": n, "z": z,
                "within_2sd": abs(z) <= 2, "within_3sd": abs(z) <= 3,
                "upper_limit": upper, "sex_allowance_ms": allowance,
                "delayed": delayed,
                "borderline": (not delayed) and value > border,
            })
        absolute.append(entry)

    i_v_cl95 = ABR_I_V_CL95_MS["male" if sex_key == "male" else "female"]
    interwave: List[dict] = []
    for pair in ABR_INTERWAVE:
        a, b = pair.split("-")
        limit = ABR_IPL_UPPER_MS[pair]
        cl95 = i_v_cl95 if pair == "I-V" else None
        if a not in corrected or b not in corrected:
            interwave.append({"pair": pair, "value": None, "present": False,
                              "upper_limit": limit, "upper_95_cl": cl95})
            continue
        value = round(corrected[b] - corrected[a], 2)
        entry = {"pair": pair, "value": value, "present": True,
                 "upper_limit": limit, "upper_95_cl": cl95,
                 "prolonged": value > limit,
                 "borderline": cl95 is not None and cl95 < value <= limit}
        norm = row["interwave"].get(pair)
        if norm:
            mean, sd, n = norm
            z = _z(value, mean, sd)
            entry.update({"norm": _limits(mean, sd), "n": n, "z": z,
                          "within_2sd": abs(z) <= 2, "within_3sd": abs(z) <= 3})
        interwave.append(entry)

    findings: List[str] = []
    flags: List[str] = []
    interpretation = "normal"

    present = set(corrected)
    ipl = {e["pair"]: e for e in interwave}
    by_wave = {e["wave"]: e for e in absolute}
    prolonged = [e for e in interwave if e.get("prolonged")]
    i_v_borderline = bool(ipl["I-V"].get("borderline"))
    delayed = [e for e in absolute
               if e.get("delayed") and e["wave"] in ABR_KEY_WAVES]
    borderline = [e for e in absolute
                  if e.get("borderline") and e["wave"] in ABR_KEY_WAVES]

    if "V" not in present:
        flags.append("wave_v_absent")
        interpretation = "absent"
        findings.append(
            f"No Wave V at {intensity:g} dB nHL. Wave V is the last component to "
            "disappear, so its absence at a high level is the significant finding "
            "— repeat at maximum output before concluding.")

    if infant and (prolonged or delayed or borderline or i_v_borderline):
        # Not a delay and not a pass: the adult table cannot say which. The
        # size of the excess is stated so a gross delay is not read as the
        # ordinary immaturity of a normal infant.
        if interpretation == "normal":
            interpretation = "indeterminate_age"
        excess = [f"Wave {e['wave']} {e['latency']:g} ms, "
                  f"{e['latency'] - e['upper_limit']:+.2f} ms against the adult limit"
                  for e in delayed] + [
                  f"{e['pair']} {e['value']:g} ms, "
                  f"{e['value'] - e['upper_limit']:+.2f} ms against the adult limit"
                  for e in prolonged]
        findings.append(
            f"At {age_months:g} months these latencies lie outside the adult "
            "normal range" + (f" ({'; '.join(excess)})" if excess else "") + ". Adult "
            "norms do not apply under 3 years — infant ABR latencies and "
            "intervals are longer and mature over the first years (ACNS "
            "Guideline 9C; BSA 2019 section 7.7.1) — so the adult table can call "
            "this neither delayed nor normal. Compare the trace with age-specific "
            "reference data before reporting it, and do not assume maturation "
            "explains a delay of this size until that has been done.")
    else:
        if prolonged:
            flags.append("interpeak_prolonged")
            interpretation = "retrocochlear"
            detail = ", ".join(f"{e['pair']} {e['value']:g} ms (limit "
                               f"{e['upper_limit']:g})" for e in prolonged)
            findings.append(
                "Prolonged " + ", ".join(e["pair"] for e in prolonged) +
                f" interpeak latency — {detail}. A conductive loss delays every "
                "wave equally and leaves the intervals intact, so a stretched "
                "interval points above the cochlea — retrocochlear until excluded.")

        if delayed:
            flags.append("absolute_latency_delayed")
            listed = _wave_list(delayed)
            i_v = ipl["I-V"]
            wave_i = by_wave["I"]
            if prolonged:
                findings.append(
                    f"Absolute latencies are also beyond 3 SD: {listed}.")
            elif i_v["present"]:
                # A peripheral loss delays Wave I and carries every later wave
                # with it, leaving I-V intact. Normal intervals alone do not
                # make that pattern: with Wave I on time the delay arises
                # after it, inside the nerve and brainstem, and an I-V near
                # the clinical limit is not an intact interval.
                wave_i_late = bool(wave_i.get("delayed") or wave_i.get("borderline"))
                if wave_i_late and not i_v_borderline:
                    interpretation = "peripheral"
                    findings.append(
                        f"Absolute latencies are prolonged ({listed}); Wave I is "
                        f"itself late (z {wave_i['z']:+g}) and the interpeak "
                        f"intervals are normal (I–V {i_v['value']:g} ms) — the "
                        "pattern of a conductive or cochlear loss shifting the "
                        "whole response later, not of a neural lesion. A delayed "
                        "Wave I is where a conductive component shows first. This "
                        "is an abnormal ABR: confirm the peripheral cause with "
                        "tympanometry and bone-conduction thresholds.")
                else:
                    flags.append("delay_within_i_v")
                    interpretation = "retrocochlear_not_excluded"
                    cl_text = (f"; beyond the adult 95% limit of "
                               f"{i_v['upper_95_cl']:g} ms, Lightfoot 1992"
                               if i_v_borderline else "")
                    if "z" not in wave_i:
                        where = (f"Wave I ({wave_i['latency']:g} ms) has no "
                                 "normative value at this level, so the delay "
                                 "cannot be placed before it.")
                    elif not wave_i_late:
                        where = (f"Wave I is on time ({wave_i['latency']:g} ms, z "
                                 f"{wave_i['z']:+g}), so the delay begins after "
                                 "it, along the eighth nerve and brainstem — a "
                                 "conductive or cochlear loss delays Wave I and "
                                 "carries the later waves with it.")
                    else:
                        where = (f"Wave I is also late (z {wave_i['z']:+g}), a "
                                 "peripheral component, but a peripheral loss "
                                 "leaves I–V intact and this I–V is not, so it "
                                 "does not account for the whole delay.")
                    findings.append(
                        f"{listed} — delayed. {where} The interpeak intervals are "
                        f"inside the adult clinical limits (I–V {i_v['value']:g} ms, "
                        f"limit {i_v['upper_limit']:g}{cl_text}), so this is not a "
                        "frank interpeak prolongation, but it is not the "
                        "peripheral pattern either: retrocochlear pathology "
                        "cannot be excluded. Compare Wave V between the ears at "
                        "the same level, corrected for 4 kHz loss (Selters & "
                        "Brackmann 1977), and correlate with the audiogram and "
                        "tympanometry before deciding on imaging.")
            else:
                flags.append("interpeak_unmeasurable")
                if interpretation == "normal":
                    interpretation = "indeterminate_delay"
                missing = [w for w in ("I", "V") if w not in present]
                findings.append(
                    f"{listed} — delayed, but Wave {' and '.join(missing)} "
                    f"{'was' if len(missing) == 1 else 'were'} not identified, so "
                    "the I–V interval, the measure that separates a peripheral "
                    "delay from a neural one, could not be measured. A conductive "
                    "or cochlear loss and a retrocochlear lesion can both produce "
                    "this, so retrocochlear pathology cannot be excluded. Resolve "
                    "Wave I (a higher intensity or slower rate, de Jager; an "
                    "ear-canal electrode, ACNS Guideline 9C section VIII) and "
                    "correlate with the audiogram and tympanometry before "
                    "attributing the delay to the periphery." + (
                        " III–V is within limits, which argues against an "
                        "upper-brainstem delay but says nothing about the eighth "
                        "nerve." if ipl["III-V"]["present"] else ""))
        elif (borderline or i_v_borderline) and not prolonged:
            if interpretation == "normal":
                interpretation = "borderline"
            if borderline:
                findings.append(
                    f"{_wave_list(borderline)} — past the 2 SD limit but inside the "
                    "3 SD limit for this intensity: borderline, neither within normal "
                    "limits nor clearly delayed. The norms are from women aged 20–30; men run "
                    "about 0.15 ms later in the later waves and latencies lengthen with "
                    "age (Stone et al. 2009), so compare against sex- and age-matched "
                    "norms or repeat before calling it either way.")
            if i_v_borderline:
                i_v = ipl["I-V"]
                whose = {"female": "women's", "male": "men's"}.get(
                    sex_key, f"women's, as sex is not recorded; the men's is "
                             f"{ABR_I_V_CL95_MS['male']:g} ms")
                findings.append(
                    f"I–V {i_v['value']:g} ms is beyond the adult 95% limit of "
                    f"{i_v['upper_95_cl']:g} ms ({whose}; Lightfoot 1992, BSA 2019 "
                    f"Table 1) though inside the {i_v['upper_limit']:g} ms clinical "
                    "limit — BSA regards an adult I–V around 4.4 ms as borderline "
                    "abnormal. Not a normal result: compare Wave V between the ears "
                    "at the same level and repeat before calling it either way.")

    if ("I" not in present and "V" in present
            and intensity >= ABR_WAVE_I_RELIABLE_FROM_DB_NHL
            and "interpeak_unmeasurable" not in flags):
        findings.append(
            f"Wave I was not identified at {intensity:g} dB nHL, where every "
            "reference ear shows it, so I–III and I–V cannot be measured and "
            "eighth-nerve conduction is not assessed. This is common with a "
            "high-frequency cochlear loss; resolve Wave I if retrocochlear "
            "pathology is in question.")

    if cm_present:
        if "V" not in present:
            flags.append("cochlear_microphonic_present")
            interpretation = "ansd"
            findings.append(
                f"Cochlear microphonic present in the first {CM_WINDOW_MS[1]:g} ms "
                "with no Wave V. A microphonic with no repeatable neural waves is "
                "the picture of auditory neuropathy spectrum disorder — the outer "
                "hair cells work and the neural response does not. Before "
                "concluding, confirm the CM inverts with stimulus polarity and "
                "exclude residual low-frequency cochlear function behind a severe "
                "high-frequency loss with a 500 Hz tone-burst ABR (de Jager).")
        elif flags or interpretation != "normal":
            # The module cannot see whether the later peaks repeated or
            # inverted, so beside an ABR that is not normal ANSD stays open.
            if flags:
                flags.append("cochlear_microphonic_abnormal_abr")
            findings.append(
                "A cochlear microphonic was recorded beside an ABR that is not "
                "normal, so auditory neuropathy spectrum disorder is not excluded. "
                "Neural waves repeat and keep their latency when stimulus polarity "
                "is reversed, and repeatable waves are evidence of neural synchrony "
                "(de Jager); peaks that invert with polarity or do not repeat may "
                "be the microphonic ringing on rather than neural waves, which is "
                "the ANSD picture. Record rarefaction and condensation runs "
                "separately to tell them apart before reading these latencies.")
        else:
            findings.append(
                "A cochlear microphonic was recorded alongside a Wave V at a normal "
                "latency. The CM is a normal pre-neural hair-cell potential, and "
                "repeatable neural waves are evidence of neural synchrony, so — "
                "provided Wave V repeated and did not invert with stimulus "
                "polarity — this is not the auditory neuropathy pattern (de Jager).")

    if flags:
        status = "abnormal"
    elif interpretation == "borderline":
        status = "borderline"
    elif interpretation == "indeterminate_age":
        status = "indeterminate"
    else:
        status = "normal"

    if row_meta["interpolated"]:
        basis = (f"interpolated between the {row_meta['rows'][0]} and "
                 f"{row_meta['rows'][1]} dB nHL rows")
        row_label: float = float(intensity)
    else:
        basis = f"the {row_meta['rows'][0]} dB nHL row"
        row_label = row_meta["rows"][0]
        if row_meta["outside_table"]:
            basis += (f" — {intensity:g} dB nHL is outside the table, so the "
                      "nearest row stands in for it")

    return {
        "ear": ear,
        "intensity_db_nhl": intensity,
        "norm_row_db_nhl": row_label,
        "norm_rows_db_nhl": row_meta["rows"],
        "norm_interpolated": row_meta["interpolated"],
        "norm_outside_table": row_meta["outside_table"],
        "norm_row_psp": row["psp"],
        "insert_delay_removed": correction > 0,
        "insert_delay_ms": correction,
        "sex": sex_key,
        "age_months": age_months,
        "absolute": absolute,
        "interwave": interwave,
        "interpeak_limits_ms": dict(ABR_IPL_UPPER_MS),
        "i_v_upper_95_cl_ms": i_v_cl95,
        # Without Wave I the eighth nerve is not assessed by this run alone;
        # BSA 2019 (section 7.7) then turns to the interaural Wave V.
        "i_v_measured": bool(ipl["I-V"]["present"]),
        "cm_present": cm_present,
        "flags": flags,
        "status": status,
        "interpretation": interpretation,
        "findings": findings,
        "protocol": dict(ABR_PROTOCOL),
        "note": ("Absolute latencies are compared against the normative values "
                 f"for the intensity used ({basis}), because Wave V moves from "
                 "about 5.4 ms at 90 dB to 7.5 ms at 20 dB. An absolute latency "
                 "without its intensity is uninterpretable. Interpeak intervals "
                 "are judged against adult upper limits (I–III 2.5, III–V 2.4, "
                 f"I–V 4.5 ms), with I–V beyond the adult 95% limit ({i_v_cl95:g} "
                 "ms) borderline; a delay is called peripheral only when Wave I "
                 "is itself late. Under 3 years age-specific norms are needed."),
    }


def _sign(x: float) -> int:
    """-1, 0 or +1, with latencies equal to the hundredth counted as equal."""
    return (x > 1e-9) - (x < -1e-9)


def _selters_brackmann_ms(threshold_4k: Optional[float]) -> Optional[float]:
    """Wave V correction for one ear's 4 kHz hearing loss, ms (or None)."""
    if threshold_4k is None:
        return None
    excess = float(threshold_4k) - SELTERS_BRACKMANN["from_db_hl"]
    if excess <= 0:
        return 0.0
    steps = math.floor(excess / SELTERS_BRACKMANN["step_db"])
    return round(steps * SELTERS_BRACKMANN["ms_per_step"], 2)


def abr_asymmetry(right: Optional[dict], left: Optional[dict],
                  right_threshold_4k: Optional[float] = None,
                  left_threshold_4k: Optional[float] = None) -> Optional[dict]:
    """Interaural Wave V difference — the classic retrocochlear screen.

    Returns None when either ear lacks a Wave V. Runs at different stimulus
    levels are refused rather than compared: Wave V shortens as level rises
    (5.88 ms at 60 dB nHL against 5.37 ms at 90 in the reference table), so
    two perfectly normal ears recorded 30 dB apart differ by 0.5 ms. So is an
    ear whose 4 kHz threshold leaves the click under 10 dB SL. With both 4 kHz
    thresholds the difference is corrected and judged against the corrected
    limits (0.37 ms, borderline from 0.2); without them, against 0.4 ms.
    """
    def wave_v(side):
        if not side:
            return None
        entry = next((w for w in side["absolute"] if w["wave"] == "V"), None)
        return entry.get("latency") if entry and entry.get("present") else None

    r, l = wave_v(right), wave_v(left)
    if r is None or l is None:
        return None

    r_level, l_level = right.get("intensity_db_nhl"), left.get("intensity_db_nhl")
    if r_level is None or l_level is None or abs(float(r_level) - float(l_level)) > 1e-6:
        return {
            "available": False, "comparable": False, "status": "not_comparable",
            "right_wave_v": r, "left_wave_v": l,
            "right_intensity_db_nhl": r_level, "left_intensity_db_nhl": l_level,
            "difference": None, "significant": None, "borderline": None,
            "poorer_ear": None, "criterion": None,
            "note": (f"Not comparable: the right ear was recorded at {r_level:g} dB "
                     f"nHL and the left at {l_level:g}. Wave V latency depends on "
                     "stimulus level, so an interaural difference is only "
                     "interpretable between runs at the same level — record both "
                     "ears at one intensity."
                     if r_level is not None and l_level is not None else
                     "Not comparable: the stimulus level of one run is unknown."),
        }

    # A click barely above a severe 4 kHz loss gives a late Wave V in a normal
    # nerve, and no correction rescues it (BSA 2019 section 7.6).
    low_sl = [(side, thr) for side, thr in (("right", right_threshold_4k),
                                            ("left", left_threshold_4k))
              if thr is not None
              and float(r_level) - float(thr) < ABR_MIN_SENSATION_LEVEL_DB]
    if low_sl:
        listed = " and ".join(f"the {side} ear's 4 kHz threshold is {thr:g} dB HL"
                              for side, thr in low_sl)
        return {
            "available": False, "comparable": False,
            "status": "not_interpretable",
            "right_wave_v": r, "left_wave_v": l,
            "right_intensity_db_nhl": r_level, "left_intensity_db_nhl": l_level,
            "difference": None, "significant": None, "borderline": None,
            "poorer_ear": None, "criterion": None,
            "note": (f"Not interpretable: {listed}, so the {r_level:g} dB nHL click "
                     f"is less than {ABR_MIN_SENSATION_LEVEL_DB} dB above it. At so "
                     "low a sensation level Wave V is late in a neurologically "
                     "normal ear and no hearing-loss correction makes it "
                     "comparable — absolute latencies must not be relied on (BSA "
                     "2019 section 7.6, Lightfoot 1993). This is not a symmetric "
                     "result: repeat that ear at a higher level if tolerated, use "
                     "the I–V interval if Wave I can be recorded, or go to "
                     "imaging if retrocochlear pathology is in question."),
        }

    r_corr = _selters_brackmann_ms(right_threshold_4k)
    l_corr = _selters_brackmann_ms(left_threshold_4k)
    corrected = r_corr is not None and l_corr is not None
    raw_difference = round(abs(r - l), 2)
    r_judged = round(r - r_corr, 2) if corrected else r
    l_judged = round(l - l_corr, 2) if corrected else l
    difference = round(abs(r_judged - l_judged), 2)
    if corrected:
        criterion = ABR_INTERAURAL_V_CORRECTED_MS
        significant = difference > criterion
        borderline = (not significant) and difference > ABR_INTERAURAL_V_SB_MS
    else:
        criterion = ABR_INTERAURAL_V_MS
        significant = difference > criterion
        borderline = False
    status = ("asymmetric" if significant else
              "borderline" if borderline else "symmetric")
    later = ("right" if r_judged > l_judged else "left") if difference else None

    limitations: List[str] = []
    if corrected:
        limitations.append(
            "Corrected for hearing loss after Selters & Brackmann (1977): 0.1 ms "
            "per 10 dB of 4 kHz loss above 50 dB HL "
            f"(right {r_corr:g} ms, left {l_corr:g} ms), and judged against the "
            f"{ABR_INTERAURAL_V_CORRECTED_MS:g} ms upper 95% limit of a corrected "
            "difference (Lightfoot 1992; BSA 2019 Table 1); Selters & Brackmann's "
            f"own criterion is {ABR_INTERAURAL_V_SB_MS:g} ms, so a corrected "
            "difference between the two is borderline. The correction is for "
            "cochlear loss with an average degree of recruitment; a conductive "
            "component delays Wave V by itself and is not covered by it.")
        before, after_corr = _sign(r - l), _sign(r_judged - l_judged)
        if after_corr and after_corr != before:
            limitations.append(
                "The correction reverses which ear is later: before it "
                + ("the two ears were equal" if not before else
                   f"the {'right' if before > 0 else 'left'} ear was later")
                + ". Selters & "
                "Brackmann assumes an average degree of recruitment and can "
                "over-correct a steep or atypical loss (BSA 2019 section 7.6) — "
                "check each ear's Wave V against the norms for its level, or "
                "balance the levels by ABLB at 4 kHz, before acting on the "
                "direction.")
    else:
        limitations.append(
            "No hearing-loss correction applied — the 4 kHz thresholds of both "
            "ears are needed (Selters & Brackmann 1977). A cochlear loss can "
            "itself delay Wave V in one ear, and a conductive loss always does, "
            "so read any difference against the audiogram before attributing it "
            "to the nerve (ACNS Guideline 9C, criterion 5).")
    limitations.append(
        "Blind to a bilateral lesion, which delays both ears equally.")

    after = " after hearing-loss correction" if corrected else ""
    if significant:
        message = (f"Wave V differs between ears by {difference:g} ms{after}, beyond "
                   f"the {criterion:g} ms criterion. Investigate the ear with the "
                   "later response for retrocochlear pathology.")
    elif borderline:
        message = (f"Wave V differs between ears by {difference:g} ms{after}: "
                   f"beyond Selters & Brackmann's {ABR_INTERAURAL_V_SB_MS:g} ms "
                   f"criterion but inside the {criterion:g} ms upper 95% limit of "
                   "corrected differences in adults without neurological disease "
                   "(Lightfoot 1992) — borderline, neither symmetric nor clearly "
                   "asymmetric, and not a finding on its own. Repeat both ears and "
                   "weigh it with the I–V intervals, the audiogram and the "
                   "clinical picture before deciding on imaging.")
    else:
        message = (f"Interaural Wave V difference {difference:g} ms{after} is within "
                   f"the {criterion:g} ms criterion.")

    return {
        "available": True, "comparable": True,
        "intensity_db_nhl": r_level,
        "right_wave_v": r, "left_wave_v": l,
        "right_wave_v_judged": r_judged, "left_wave_v_judged": l_judged,
        "uncorrected_difference": raw_difference,
        "difference": difference,
        "criterion": criterion,
        "borderline_from": ABR_INTERAURAL_V_SB_MS if corrected else None,
        "status": status,
        "significant": significant,
        "borderline": borderline,
        "poorer_ear": later if (significant or borderline) else None,
        "hearing_loss_correction": {
            "applied": corrected,
            "right_ms": r_corr, "left_ms": l_corr,
            "right_threshold_4k_db_hl": right_threshold_4k,
            "left_threshold_4k_db_hl": left_threshold_4k,
            "method": ("Selters & Brackmann 1977: 0.1 ms per 10 dB of hearing "
                       "loss at 4 kHz above 50 dB HL"),
        },
        "limitations": limitations,
        "message": message,
    }


def abr_threshold(series: Sequence[dict], stimulus: str = "click",
                  frequency_hz: Optional[float] = None) -> Optional[dict]:
    """The lowest level with a Wave V, in dB nHL, and what it implies in dB eHL.

    ``series``: [{"intensity": dB nHL, "wave_v": latency or None}] — the
    intensity ladder actually run. The result is a *minimum response level*
    for the electrophysiological response in dB nHL. It is not a behavioural
    threshold: the typical nHL-to-eHL correction is reported alongside it (de
    Jager), and it is invalid when neural synchrony is lacking (ANSD).
    """
    rows = sorted(
        ({"intensity": float(r["intensity"]),
          "wave_v": r.get("wave_v"),
          "present": r.get("wave_v") is not None}
         for r in series or []),
        key=lambda r: r["intensity"])
    if not rows:
        return None

    stimulus = stimulus if stimulus in ABR_STIMULI else "click"
    caveat = ("An ABR threshold is not a hearing threshold where neural synchrony "
              "is lacking — in auditory neuropathy it says nothing about "
              "behavioural hearing (de Jager).")

    present = [r for r in rows if r["present"]]
    if not present:
        return {
            "rows": rows, "estimated_threshold": None,
            "estimated_threshold_db_nhl": None, "unit": "dB nHL",
            "stimulus": stimulus, "frequency_hz": frequency_hz,
            "ehl": None, "no_response": True, "caveat": caveat,
            "message": (f"No Wave V at any level tested, down to "
                        f"{max(r['intensity'] for r in rows):g} dB nHL. Repeat at "
                        "maximum output before reporting an absent response."),
        }

    lowest = min(present, key=lambda r: r["intensity"])
    nhl = lowest["intensity"]
    # Latency-intensity behaviour separates conductive from cochlear loss: a
    # conductive loss shifts the whole function later without changing its
    # slope, a cochlear loss steepens it near threshold.
    highest = max(present, key=lambda r: r["intensity"])
    shift = (round(lowest["wave_v"] - highest["wave_v"], 2)
             if lowest["wave_v"] is not None and highest["wave_v"] is not None
             and lowest is not highest else None)

    table = ABR_EHL_CORRECTION_DB[stimulus]
    if isinstance(table, dict):
        freq = int(round(frequency_hz)) if frequency_hz is not None else None
        corr = table.get(freq) if freq is not None else None
        if corr is not None:
            ehl = {"estimate_db_ehl": nhl - corr, "range_db_ehl": None,
                   "correction_db": corr}
            ehl_text = (f"With the typical {corr} dB {stimulus.replace('_', ' ')} "
                        f"correction at {freq} Hz that is an estimated {nhl - corr:g} "
                        "dB eHL.")
        else:
            ehl = {"estimate_db_ehl": None, "range_db_ehl": None,
                   "correction_db": None}
            ehl_text = ("No typical correction is published for this stimulus "
                        "frequency, so the result stays in dB nHL.")
    else:
        lo, hi = table
        ehl = {"estimate_db_ehl": None if hi != lo else nhl - lo,
               "range_db_ehl": [nhl - hi, nhl - lo], "correction_db": list(table)}
        if stimulus == "click":
            ehl_text = (f"The typical click correction is {lo}–{hi} dB, an "
                        f"estimated {nhl - hi:g}–{nhl - lo:g} dB eHL — and a click "
                        "reflects the 2–4 kHz region only, so it says nothing about "
                        "low-frequency hearing.")
        else:
            ehl_text = (f"The typical broadband CE-chirp correction is {lo} dB, "
                        f"an estimated {nhl - lo:g} dB eHL.")
    ehl.update({"source": ("de Jager, ABR in Clinical Practice — typical values; "
                           "derive your own from young normal-hearing adults on "
                           "your equipment")})

    return {
        "rows": rows,
        "estimated_threshold": nhl,
        "estimated_threshold_db_nhl": nhl,
        "unit": "dB nHL",
        "stimulus": stimulus,
        "frequency_hz": frequency_hz,
        "ehl": ehl,
        "no_response": False,
        "wave_v_at_threshold": lowest["wave_v"],
        "latency_shift_ms": shift,
        "caveat": caveat,
        "message": (
            f"Wave V identifiable to {nhl:g} dB nHL — the electrophysiological "
            f"threshold, in dB nHL. {ehl_text} It approximates the behavioural "
            "threshold and is not a substitute for it."),
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

    # No peaks at all is not a normal MLR: nothing was read.
    status = ("abnormal" if patterns else
              "indeterminate" if not present else "normal")

    return {
        "ear": ear,
        "peaks": rows,
        "na_pa_interval": na_pa,
        "na_pa_amplitude_uv": na_pa_amp,
        "patterns": patterns,
        "abnormal": bool(patterns),
        "status": status,
        "findings": findings,
        "protocol": dict(MLR_PROTOCOL),
        "note": ("The MLR bridges the ABR and the LLR, covering the "
                 "thalamocortical pathway that a brainstem response cannot "
                 "reach."),
    }


# ==========================================================================
# LLR
# ==========================================================================
#: Adult windows. They do not describe a child's response: the immature LLR
#: is dominated by a large, late P1, and N1 does not emerge as a separate
#: component until late childhood (see LLR_ADULT_MORPHOLOGY_FROM_MONTHS).
LLR_NORMS: Dict[str, dict] = {
    "P1": {"range": (40, 60), "typical": 50, "polarity": "positive"},
    "N1": {"range": (90, 150), "typical": 100, "polarity": "negative"},
    "P2": {"range": (160, 200), "typical": 180, "polarity": "positive"},
    "N2": {"range": (300, 350), "typical": 325, "polarity": "negative"},
}
LLR_PEAKS = list(LLR_NORMS)

#: Below this age the adult N1/P2/N2 windows are not applied and an absent N1
#: is not a finding. N1 "begins to reliably appear" only between about 7 and
#: 11 years, while P1 and N2 dominate the child's waveform (Ponton et al.
#: 2000, Clin Neurophysiol 111:220-236).
LLR_ADULT_MORPHOLOGY_FROM_MONTHS = 144

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

#: P1 latency shortens as the cortex matures, and a P1 that stays late for age
#: means the cortex is not being stimulated — the biomarker used in
#: cochlear-implant candidacy. Normal development after Sharma, Dorman & Spahr
#: 2002 (Ear Hear 23:532-539), fitted to 136 normal-hearing listeners aged
#: 0.1-20 years: "latency = 155.6 + (-32.746)*(LN(Age))", age in years,
#: R^2 = 0.78. The paper gives the 95% confidence limits only graphically
#: (Figs 1 and 2); read off Figure 2 they lie a near-constant 32 ms either side
#: of the fit from 1 to 20 years. Delayed means beyond that upper limit; inside
#: it a P1 is normal for age however far it sits from the mean.
P1_FIT_INTERCEPT_MS = 155.6
P1_FIT_SLOPE_MS = -32.746
P1_CI95_HALF_WIDTH_MS = 32.0
P1_NORM_AGE_YEARS = (0.1, 20.0)

#: Below 1 year the same limits are read off the steepest part of Figure 2,
#: where a pixel spans several milliseconds: about +29/-35 ms at 3 months and
#: +30/-34 ms at 9 months, the 32 ms width within that reading's precision
#: but not confirmed by it. The fit itself also falls by 32.746 / age ms per
#: year of age there — over 5 ms a month at 6 months — so the verdict turns on
#: the exact (for a preterm infant, corrected) age. A verdict under this age
#: is therefore marked provisional, with that reason, rather than asserted.
P1_INFANT_PROVISIONAL_BELOW_YEARS = 1.0


def _p1_infant_caveat(age_years: float) -> str:
    """Why a P1 verdict under 1 year is provisional, with the slope at that age."""
    per_month = abs(P1_FIT_SLOPE_MS) / age_years / 12.0
    return (f"Under 1 year the 95% limits are read from the steepest part of "
            "Sharma et al.'s Figure 2, only to within about 3 ms, and the normal "
            "P1 shortens by about "
            f"{per_month:.1f} ms a month at this age — so the result depends on "
            "the exact age (corrected age for a preterm infant). Treat it as "
            "provisional and confirm with a repeat recording before acting on it.")
P1_SOURCE = ("Sharma, Dorman & Spahr 2002, Ear Hear 23:532 — normal-hearing "
             "fit 155.6 − 32.746·ln(age in years), 95% limits ±32 ms")


def _p1_band(age_years: float) -> str:
    if age_years < 1:
        return "Infant — P1 prominent and late"
    if age_years < 3:
        return "Toddler — P1 shortening rapidly"
    if age_years < 5:
        return "Preschool"
    if age_years < 12:
        return "School age — P1 still shortening"
    if age_years <= P1_NORM_AGE_YEARS[1]:
        return "Adolescent — approaching adult values"
    return "Adult — judged against the 20-year end of the normative curve"


def expected_p1_latency(age_months: Optional[float]) -> Optional[dict]:
    """Age-appropriate P1 latency with its 95% range (Sharma et al. 2002)."""
    if age_months is None:
        return None
    age_years = float(age_months) / 12.0
    low_age, high_age = P1_NORM_AGE_YEARS
    if age_years < low_age:
        return {"assessable": False, "typical_ms": None, "upper_95_ms": None,
                "lower_95_ms": None, "age_years": round(age_years, 3),
                "band": "Under 0.1 years — younger than the normative sample",
                "source": P1_SOURCE}
    judged_age = min(age_years, high_age)
    typical = P1_FIT_INTERCEPT_MS + P1_FIT_SLOPE_MS * math.log(judged_age)
    provisional = age_years < P1_INFANT_PROVISIONAL_BELOW_YEARS
    return {
        "assessable": True,
        "typical_ms": round(typical, 1),
        "upper_95_ms": round(typical + P1_CI95_HALF_WIDTH_MS, 1),
        "lower_95_ms": round(typical - P1_CI95_HALF_WIDTH_MS, 1),
        "age_years": round(age_years, 2),
        "beyond_normative_ages": age_years > high_age,
        "band": _p1_band(age_years),
        "source": P1_SOURCE,
        "provisional": provisional,
        "provisional_note": _p1_infant_caveat(age_years) if provisional else None,
    }


def p1_maturation_curve() -> List[dict]:
    """The normative curve at representative ages, for display."""
    out = []
    for years in (0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 10, 12, 15, 20):
        e = expected_p1_latency(years * 12)
        out.append({"age_years": years, "typical_ms": e["typical_ms"],
                    "upper_95_ms": e["upper_95_ms"],
                    "lower_95_ms": e["lower_95_ms"], "band": e["band"]})
    return out


def analyze_llr(peaks: Dict[str, Optional[float]],
                amplitudes: Optional[Dict[str, float]] = None,
                age_months: Optional[float] = None,
                ear: str = "right") -> dict:
    """One LLR run: the P1-N1-P2-N2 sequence against its normative windows."""
    amplitudes = amplitudes or {}
    expected = expected_p1_latency(age_months)
    child = (age_months is not None
             and age_months < LLR_ADULT_MORPHOLOGY_FROM_MONTHS)
    # P1 is judged against the 95% range of the normal-hearing curve whenever
    # the age is known and covered, and past 20 years against the curve's
    # 20-year end — the same range the maturation check below uses, so the
    # table row and the maturation verdict can never disagree, and the range
    # does not jump at the 20th birthday. The adult window is the fallback
    # only when no age is recorded.
    p1_band = None
    adult_p1 = bool(expected and expected.get("beyond_normative_ages"))
    if expected and expected["assessable"]:
        p1_band = (expected["lower_95_ms"], expected["upper_95_ms"])

    rows: List[dict] = []
    for name in LLR_PEAKS:
        spec = LLR_NORMS[name]
        low, high = spec["range"]
        basis: Optional[str] = "adult window"
        if name == "P1" and p1_band:
            low, high = p1_band
            basis = ("95% range at the 20-year end of the normal curve (Sharma "
                     "et al. 2002)" if adult_p1 else
                     "95% range for age (Sharma et al. 2002)")
        elif child:
            basis = None
        value = peaks.get(name)
        row = {"peak": name, "range": [low, high], "polarity": spec["polarity"],
               "basis": basis, "window_applies": basis is not None}
        if value is None:
            row.update({"latency": None, "present": False})
            rows.append(row)
            continue
        value = float(value)
        row.update({"latency": value, "present": True})
        if basis is None:
            row.update({"within_range": None, "delayed": None, "early": None})
        else:
            row.update({"within_range": low <= value <= high,
                        "delayed": value > high, "early": value < low})
        rows.append(row)

    n1_p2 = None
    if peaks.get("N1") is not None and peaks.get("P2") is not None:
        n1_p2 = round(float(peaks["P2"]) - float(peaks["N1"]), 1)

    findings: List[str] = []
    flags: List[str] = []
    indeterminate = False

    # The P1 maturation check — the reason an LLR is run on a child at all.
    maturation = None
    p1 = peaks.get("P1")
    if p1 is not None and expected:
        p1 = float(p1)
        if not expected["assessable"]:
            indeterminate = True
            maturation = {"p1_latency": p1, "assessable": False,
                          "expected": None, "upper_95": None, "lower_95": None,
                          "band": expected["band"], "difference": None,
                          "delayed": None, "early": None, "source": P1_SOURCE}
            findings.append(
                f"P1 cannot be judged for maturation at {age_months:g} months: the "
                "normative curve starts at 0.1 years (Sharma et al. 2002). Repeat "
                "the recording when the infant is older rather than reading it "
                "against an extrapolated norm.")
        else:
            typical = expected["typical_ms"]
            upper, lower = expected["upper_95_ms"], expected["lower_95_ms"]
            delta = round(p1 - typical, 1)
            delayed = p1 > upper
            early = p1 < lower
            maturation = {
                "p1_latency": p1, "assessable": True, "expected": typical,
                "upper_95": upper, "lower_95": lower,
                "band": expected["band"], "difference": delta,
                "delayed": delayed, "early": early, "source": P1_SOURCE,
                # Past 20 years maturation is complete: the curve's end is a
                # latency reference, not a maturation measure, and the implant
                # biomarker (a child's P1 delayed for age) does not apply.
                "adult": adult_p1,
                # Under 1 year: limits and age both less certain
                # (P1_INFANT_PROVISIONAL_BELOW_YEARS).
                "provisional": bool(expected.get("provisional")),
                "provisional_note": expected.get("provisional_note"),
            }
            findings_before = len(findings)
            if adult_p1:
                if delayed:
                    findings.append(
                        f"P1 at {p1:g} ms is later than the upper 95% limit of "
                        f"{upper:g} ms at the 20-year end of the normal-hearing "
                        "curve (Sharma et al. 2002). Cortical maturation is "
                        "complete in an adult, so this is a latency finding, not "
                        "a maturation one — read it with N1–P2, the hearing "
                        "levels and the patient's state.")
                else:
                    findings.append(
                        f"P1 at {p1:g} ms is within the 95% range {lower:g}–"
                        f"{upper:g} ms at the 20-year end of the normal-hearing "
                        "curve; in an adult maturation is complete, so this is a "
                        "latency check only.")
            elif delayed:
                flags.append("cortical_maturation_delayed")
                findings.append(
                    f"P1 at {p1:g} ms lies beyond the upper 95% limit of "
                    f"{upper:g} ms for this age (normal-hearing mean {typical:g} "
                    f"ms; {expected['band']}; Sharma et al. 2002). A P1 delayed "
                    "for age indicates the auditory cortex is not receiving "
                    "adequate stimulation — the biomarker used in cochlear-implant "
                    "candidacy and in judging the benefit of amplification.")
            elif early:
                findings.append(
                    f"P1 at {p1:g} ms is earlier than the 95% range for age "
                    f"({lower:g}–{upper:g} ms). That is not delayed maturation; "
                    "check the recorded age and the peak identification.")
            else:
                findings.append(
                    f"P1 latency is appropriate for age — {p1:g} ms within the "
                    f"95% range {lower:g}–{upper:g} ms ({expected['band']}).")
            if maturation["provisional"] and len(findings) > findings_before:
                findings[-1] = f"{findings[-1]} {maturation['provisional_note']}"

    n1_p2_amp = amplitudes.get("N1-P2")
    if n1_p2_amp is not None and n1_p2_amp < 3:
        flags.append("low_amplitude")
        findings.append(
            f"N1-P2 amplitude {n1_p2_amp:g} µV is small against a typical "
            "10 µV peak-to-peak with moderately intense stimuli.")

    any_peak = any(r["present"] for r in rows)
    if not any_peak:
        # Nothing was read, so there is no N1 to call absent and no normal
        # result either.
        indeterminate = True
        findings.append(
            "No LLR peaks identified — check the recording, the patient's "
            "arousal and attention, and the stimulus before interpreting.")
    elif peaks.get("N1") is None:
        if child:
            findings.append(
                "N1 was not identified. At this age that is expected: the "
                "immature response is dominated by P1 and N2, and N1 only "
                "emerges reliably between about 7 and 11 years (Ponton et al. "
                "2000) — not a finding.")
        else:
            flags.append("n1_absent")
            findings.append(
                "N1 was not identified. It is the most stable component of the "
                "response, so its absence is a technical question first.")

    delayed_peaks = [r for r in rows if r.get("delayed")]
    lone_late = False
    if len(delayed_peaks) >= 2:
        flags.append("cortical_delay")
        findings.append(
            "Multiple cortical components are prolonged — slowed processing "
            "above the thalamus. Correlate with the MLR and imaging.")
    elif delayed_peaks and "cortical_maturation_delayed" not in flags:
        # One component outside its window: not the multi-component slowing
        # above, and not a normal result either — the row says "late", so the
        # run cannot say "normal".
        lone_late = True
        late = delayed_peaks[0]
        if late["peak"] != "P1" or not adult_p1:
            findings.append(
                f"{late['peak']} at {late['latency']:g} ms is later than its "
                f"window ({late['range'][0]:g}–{late['range'][1]:g} ms). A single "
                "late component is not the multi-component slowing of a cortical "
                "delay, but it is not a normal result either: check the peak "
                "identification and the patient's state, and repeat.")

    status = ("abnormal" if flags else
              "indeterminate" if indeterminate else
              "borderline" if lone_late else "normal")

    return {
        "ear": ear,
        "age_months": age_months,
        "peaks": rows,
        "n1_p2_interval": n1_p2,
        "n1_p2_amplitude_uv": n1_p2_amp,
        "maturation": maturation,
        "flags": flags,
        "status": status,
        "findings": findings,
        "protocol": dict(LLR_PROTOCOL),
        "note": ("The LLR is state-dependent: attention, arousal and sedation "
                 "all change it, so a poor response in a drowsy patient is not "
                 "a cortical finding."),
    }


# ==========================================================================
# the battery
# ==========================================================================
_STATUS_RANK = {"normal": 0, "borderline": 1, "indeterminate": 2, "abnormal": 3}

_ABR_DETAIL = {
    "retrocochlear": "prolonged interpeak interval — retrocochlear until excluded",
    "peripheral": ("delayed absolute latencies from Wave I on, with normal "
                   "interpeak intervals — conductive or cochlear pattern"),
    "retrocochlear_not_excluded": ("delay arising after Wave I, intervals inside "
                                   "the clinical limits — retrocochlear pathology "
                                   "cannot be excluded"),
    "indeterminate_delay": ("delayed with the interpeak intervals unmeasurable — "
                            "retrocochlear pathology cannot be excluded"),
    "absent": "no Wave V",
    "ansd": "cochlear microphonic with no Wave V — auditory neuropathy pattern",
    "borderline": "absolute latency or I–V borderline against the reference",
    "indeterminate_age": ("beyond adult limits under 3 years — needs "
                          "age-specific norms"),
}


def _abr_status(run: dict) -> str:
    """A run's status, tolerating results stored before ``status`` existed."""
    return run.get("status") or ("abnormal" if run.get("flags") else "normal")


def _abr_i_v_measured(run: dict) -> bool:
    """Whether the run measured I-V, read from the intervals themselves."""
    return any(e.get("pair") == "I-V" and e.get("present")
               for e in run.get("interwave") or [])


def _abr_has_wave_v(run: dict) -> bool:
    return any(e.get("wave") == "V" and e.get("present")
               for e in run.get("absolute") or [])


def aep_battery(abr: Optional[dict] = None, mlr: Optional[dict] = None,
                llr: Optional[dict] = None,
                abr_other_ear: Optional[dict] = None) -> dict:
    """Where along the pathway the three recordings localise a problem.

    The value of running all three is that they bracket the lesion. A normal
    ABR with an abnormal MLR puts the problem above the brainstem; both normal
    with an abnormal LLR puts it at the cortex. Neither conclusion is available
    from any one recording — and none is available from a level that is
    borderline or indeterminate, which is reported as such, never as normal.
    """
    levels = []
    limitations: List[str] = []
    abr_runs = [r for r in (abr, abr_other_ear) if r]
    if abr_runs:
        ears = [{"ear": r.get("ear"), "status": _abr_status(r),
                 "interpretation": r.get("interpretation"),
                 "flags": list(r.get("flags") or []),
                 "i_v_measured": _abr_i_v_measured(r)} for r in abr_runs]
        worst = max(ears, key=lambda e: _STATUS_RANK.get(e["status"], 0))

        def ear_detail(e: dict) -> str:
            text = _ABR_DETAIL[e["interpretation"]]
            if "cochlear_microphonic_abnormal_abr" in e["flags"]:
                text += "; cochlear microphonic — auditory neuropathy not excluded"
            return f"{e['ear']}: {text}" if len(ears) > 1 else text

        details = [ear_detail(e) for e in ears
                   if e.get("interpretation") in _ABR_DETAIL]
        # A Wave V at a normal latency with no Wave I says the brainstem
        # response arrived on time; it does not test the eighth nerve. BSA 2019
        # (section 7.7): "Where wave I is absent and wave V is recorded the ILD
        # V should be used."
        unassessed = [r.get("ear") for r in abr_runs
                      if _abr_has_wave_v(r) and not _abr_i_v_measured(r)]
        if unassessed:
            limitations.append(
                f"Wave I was not identified in the {' and '.join(unassessed)} ABR, "
                "so that run did not assess eighth-nerve conduction: compare Wave "
                "V between the ears at the same level before excluding "
                "retrocochlear pathology (BSA 2019 section 7.7).")
        levels.append({"test": "ABR", "level": "Eighth nerve and brainstem",
                       "window_ms": [0, 10], "status": worst["status"],
                       "abnormal": worst["status"] == "abnormal",
                       "peripheral": all(e.get("interpretation") == "peripheral"
                                         for e in ears
                                         if e["status"] == "abnormal"),
                       "ears": ears, "detail": "; ".join(details) or None})
    if mlr:
        status = mlr.get("status") or ("abnormal" if mlr.get("abnormal") else "normal")
        levels.append({"test": "MLR",
                       "level": "Thalamus, thalamocortical radiations, primary cortex",
                       "window_ms": [10, 80], "status": status,
                       "abnormal": status == "abnormal",
                       "detail": ", ".join(p["label"].lower()
                                           for p in mlr.get("patterns") or [])
                       or None})
    if llr:
        status = llr.get("status") or ("abnormal" if llr.get("flags") else "normal")
        levels.append({"test": "LLR", "level": "Auditory cortex and association areas",
                       "window_ms": [50, 350], "status": status,
                       "abnormal": status == "abnormal",
                       "detail": ", ".join(f.replace("_", " ")
                                           for f in llr.get("flags") or []) or None})

    if not levels:
        return {"available": False,
                "note": "No evoked-potential recordings entered."}

    abnormal = [l for l in levels if l["status"] == "abnormal"]
    uncertain = [l for l in levels if l["status"] in ("borderline", "indeterminate")]

    def described(l: dict) -> str:
        return f"{l['test']} {l['status']}" + (f" ({l['detail']})" if l.get("detail") else "")

    if not abnormal and not uncertain:
        headline = (f"All {len(levels)} recording"
                    f"{'s' if len(levels) > 1 else ''} within normal limits"
                    + (" as far as they reach — but " + limitations[0]
                       if limitations else
                       " — the pathway is intact as far as they reach."))
    elif not abnormal:
        headline = ("Not a normal result: " + "; ".join(described(l) for l in uncertain)
                    + ". No level is clearly abnormal, but a borderline or "
                    "indeterminate level cannot be called intact — confirm it "
                    "before relying on the battery.")
    else:
        lowest = abnormal[0]
        idx = levels.index(lowest)
        below_normal = [l["test"] for l in levels[:idx] if l["status"] == "normal"]
        below_uncertain = [l for l in levels[:idx]
                           if l["status"] in ("borderline", "indeterminate")]
        if lowest["test"] == "ABR" and lowest.get("peripheral"):
            headline = (f"ABR abnormal ({lowest['detail']}). The delay arises "
                        "before the brainstem — confirm the peripheral cause with "
                        "tympanometry and bone conduction.")
        elif len(levels) == 1:
            headline = (described(lowest)
                        + ". Run the other levels to bracket where the problem sits.")
        elif below_uncertain:
            headline = (f"{lowest['test']} abnormal above a "
                        + " and ".join(f"{l['status']} {l['test']}"
                                       for l in below_uncertain)
                        + " — the level below is not confirmed intact, so the "
                        "problem cannot yet be placed above it.")
        elif below_normal:
            headline = (f"{lowest['test']} abnormal with a normal "
                        f"{' and '.join(below_normal)} below it — the problem sits "
                        f"at or above {lowest['level'].lower()}.")
        else:
            headline = (f"{described(lowest)} — involvement at "
                        f"{lowest['level'].lower()}.")
        # Every abnormal level is named, not only the lowest. One above an
        # abnormal level receives its input through it, so it cannot place a
        # separate problem by itself.
        above = abnormal[1:]
        if above:
            headline += (" Also abnormal above it: "
                         + "; ".join(described(l) for l in above)
                         + " — read through the abnormal level below, so not "
                         "localised on its own.")

    return {
        "available": True,
        "levels": levels,
        "abnormal": bool(abnormal),
        "abnormal_levels": [l["test"] for l in abnormal],
        "uncertain_levels": [l["test"] for l in uncertain],
        "limitations": limitations,
        "headline": headline,
        "note": ("ABR, MLR and LLR sample the same pathway at increasing "
                 "heights. Running one alone can only exclude problems at that "
                 "height."),
    }
