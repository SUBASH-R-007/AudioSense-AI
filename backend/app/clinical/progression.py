"""MODULE 1.5 — Progression analysis between two dated tests.

Implements OSHA Standard Threshold Shift (29 CFR 1910.95(g)(10)), the OSHA
300 Log recording criterion for hearing loss (29 CFR 1904.10) and ASHA
ototoxicity-monitoring criteria on per-ear air-conduction deltas. Positive
delta = hearing got worse (threshold increased).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.models.schemas import AC_FREQS, ThresholdValue, effective_db, ear_to_numeric

#: Frequencies of the OSHA STS average: 29 CFR 1910.95(g)(10)(i) and
#: 1904.10(b)(1) both define the shift over 2000, 3000 and 4000 Hz.
OSHA_FREQS = [2000, 3000, 4000]

#: The shared audiogram model has no 3000 Hz. Without a 3000 Hz threshold
#: the average is taken over 2000/4000 Hz instead, and the payload says so:
#: the proxy is not the regulatory rule and can disagree with it either way.
OSHA_PROXY_FREQS = [2000, 4000]

#: 1910.95(g)(10)(i): an STS is an average shift of 10 dB or more.
STS_CRITERION_DB = 10.0

#: 29 CFR 1904.10(a): an STS is recordable on the OSHA 300 Log only when the
#: same ear's hearing level, averaged at 2000/3000/4000 Hz, is 25 dB or more
#: above audiometric zero. 1904.10(b)(2)(ii) takes that level from the
#: CURRENT audiogram alone, and 1904.10(b)(3) forbids age-correcting it.
OSHA_RECORDABLE_HL_DB = 25.0

#: Lowest threshold the data model records (schemas: -10..120 dB HL). An
#: untested frequency can be no better than this, which is what lets a
#: partial average sometimes settle the 25 dB question on its own.
MIN_THRESHOLD_DB = -10.0

PROXY_DIVERGENCE_NOTE = (
    "3000 Hz was not supplied, so the average uses 2000/4000 Hz in place of "
    "OSHA's 2000/3000/4000 Hz. The proxy can disagree with the regulatory rule "
    "in both directions: shifts of 0/15/15 dB at 2/3/4 kHz are an STS (average "
    "10 dB) that the proxy misses (7.5 dB), and shifts of 10/0/10 dB are not an "
    "STS (6.7 dB) although the proxy flags them (10 dB). Confirm with the "
    "3000 Hz threshold before recording or dismissing a shift."
)


def ear_deltas(
    baseline: Dict[int, Optional[ThresholdValue]],
    current: Dict[int, Optional[ThresholdValue]],
) -> Dict[int, Optional[float]]:
    """Per-frequency threshold shift (current - baseline), dB. NR -> 120."""
    b, c = ear_to_numeric(baseline), ear_to_numeric(current)
    out: Dict[int, Optional[float]] = {}
    for f in AC_FREQS:
        if b.get(f) is not None and c.get(f) is not None:
            out[f] = round(c[f] - b[f], 1)
        else:
            out[f] = None
    return out


def shift_3k(
    baseline_3k: Optional[ThresholdValue], current_3k: Optional[ThresholdValue],
) -> Optional[float]:
    """3000 Hz threshold shift (current - baseline), dB; None unless both exist."""
    b, c = effective_db(baseline_3k), effective_db(current_3k)
    return None if b is None or c is None else round(c - b, 1)


def _hz(freqs: List[int]) -> str:
    return "/".join(str(f) for f in freqs)


def _freq_label(freqs: List[int]) -> str:
    """2000/4000 -> "2k/4k Hz"; names exactly the frequencies averaged."""
    return "/".join(f"{f // 1000}k" for f in freqs) + " Hz"


def _thresholds(freqs: List[int]) -> str:
    """[3000] -> "3000 Hz threshold"; [2000, 3000] -> "2000/3000 Hz thresholds"."""
    return f"{_hz(freqs)} Hz threshold" + ("s" if len(freqs) > 1 else "")


def _proxy_note(freqs: List[int]) -> str:
    if freqs == OSHA_PROXY_FREQS:
        return PROXY_DIVERGENCE_NOTE
    missing = [f for f in OSHA_FREQS if f not in freqs]
    return (f"{_hz(missing)} Hz {'were' if len(missing) > 1 else 'was'} not "
            f"available, so the average uses {_hz(freqs)} Hz in place of OSHA's "
            "2000/3000/4000 Hz. A partial average can disagree with the regulatory "
            f"rule in both directions; confirm with the {_thresholds(missing)} "
            "before recording or dismissing a shift.")


def _missing_value_needed(
    values: Dict[int, Optional[float]], target: float,
) -> Tuple[Optional[int], Optional[float]]:
    """With exactly one of 2000/3000/4000 Hz missing: that frequency, and the
    value it would need for the three-frequency average to reach ``target``
    (avg >= target  <=>  missing >= 3 x target - sum of the other two)."""
    missing = [f for f in OSHA_FREQS if values.get(f) is None]
    if len(missing) != 1:
        return None, None
    known = sum(values[f] for f in OSHA_FREQS if f != missing[0])
    return missing[0], round(3 * target - known, 1)


def _sts_condition(freq: int, need: float) -> str:
    """When OSHA's 2k/3k/4k average is an STS, given the shift ``need`` that
    the missing frequency must reach (``_missing_value_needed``).

    A need of zero or less means the frequencies compared already carry the
    average to 10 dB: only an improvement at the missing frequency could
    undo it, so that improvement is named instead of a negative "shift of
    -40 dB or more".
    """
    if need > 0:
        return f"only if the {freq} Hz shift is {need:g} dB or more"
    if need == 0:
        return f"unless the {freq} Hz threshold has improved since the baseline"
    return (f"unless the {freq} Hz threshold has improved by more than "
            f"{-need:g} dB since the baseline")


def osha_sts(deltas: Dict[int, Optional[float]],
             delta_3k: Optional[float] = None) -> dict:
    """OSHA Standard Threshold Shift check.

    OSHA 29 CFR 1910.95(g)(10)(i): an STS is an average shift of 10 dB or
    more at 2000, 3000 and 4000 Hz relative to the baseline audiogram. That
    rule is applied whenever all three shifts are known; otherwise the
    average is taken over the frequencies that are, the result is marked as
    a proxy (``determined`` False), and — when only one frequency is missing
    — the shift it would need to make the regulatory average an STS is
    reported, because the proxy can miss a shift as well as over-call one.
    An average shift of exactly 10 dB flags positive (criterion is ">= 10").
    No Appendix F age correction is applied, which 1910.95(g)(10)(ii)
    permits but does not require — so this errs toward flagging.
    """
    values = {2000: deltas.get(2000), 3000: delta_3k, 4000: deltas.get(4000)}
    freqs = [f for f in OSHA_FREQS if values[f] is not None]
    proxy = freqs != OSHA_FREQS
    if not freqs:
        return {"flag": False, "avg_shift": None, "freqs": [],
                "proxy": True, "determined": False, "method": "insufficient data",
                "note": "insufficient data at 2k/3k/4k Hz",
                "missing_freq": None, "missing_shift_needed_db": None,
                "missing_shift_note": None}
    avg = sum(values[f] for f in freqs) / len(freqs)
    out = {
        "flag": avg >= STS_CRITERION_DB,
        "avg_shift": round(avg, 2),
        "freqs": freqs,
        "proxy": proxy,
        "determined": not proxy,
        "method": ("OSHA 29 CFR 1910.95(g)(10)(i), 2000/3000/4000 Hz" if not proxy
                   else f"proxy: {_hz(freqs)} Hz in place of OSHA's 2000/3000/4000 Hz"),
        "criterion": ("average shift ≥ 10 dB at 2000/3000/4000 Hz" if not proxy else
                      f"average shift ≥ 10 dB at {_hz(freqs)} Hz "
                      "(proxy for OSHA 2k/3k/4k)"),
    }
    if proxy:
        missing_freq, needed = _missing_value_needed(values, STS_CRITERION_DB)
        out.update(proxy_note=_proxy_note(freqs), missing_freq=missing_freq,
                   missing_shift_needed_db=needed,
                   missing_shift_note=(
                       "On OSHA's 2k/3k/4k Hz average this is a standard threshold "
                       f"shift {_sts_condition(missing_freq, needed)}."
                       if needed is not None else None))
    return out


def osha_recordability(
    sts: dict,
    current: Dict[int, Optional[ThresholdValue]],
    current_3k: Optional[ThresholdValue] = None,
) -> dict:
    """29 CFR 1904.10(a): does this ear's STS reach the OSHA 300 Log?

    Two conditions, both per ear: an STS, AND a current hearing level of
    25 dB or more above audiometric zero averaged at 2000/3000/4000 Hz in the
    same ear. The hearing level comes from the current audiogram alone
    (1904.10(b)(2)(ii)) — so a current 3000 Hz threshold counts even when no
    baseline 3000 Hz exists to compute a shift — and is never age-corrected
    (1904.10(b)(3)).

    Either condition may rest on a partial average. The case is then settled
    only when the known values decide it whatever the missing one is;
    otherwise ``recordable_if_work_related`` is None and ``status`` says
    whether the conditions are met on the frequencies tested
    ("met_on_proxy") or not ("undetermined"). Two further conditions cannot
    be decided from audiograms and are left to the reader: the shift must be
    work-related (1904.10(b)(5)-(6)), and a retest within 30 days that does
    not confirm it removes the obligation (1904.10(b)(4)).
    """
    c = ear_to_numeric(current)
    levels = {2000: c.get(2000), 3000: effective_db(current_3k), 4000: c.get(4000)}
    freqs = [f for f in OSHA_FREQS if levels[f] is not None]
    hl_proxy = freqs != OSHA_FREQS
    hl = sum(levels[f] for f in freqs) / len(freqs) if freqs else None
    need_freq, need_level = None, None
    if hl is None:
        hl_met: Optional[bool] = None
    elif not hl_proxy:
        hl_met = hl >= OSHA_RECORDABLE_HL_DB
    else:
        need_freq, need_level = _missing_value_needed(levels, OSHA_RECORDABLE_HL_DB)
        # Met whatever the untested threshold is, when even the best possible
        # value there (-10 dB HL) keeps the average at 25 dB HL or more.
        hl_met = True if need_level is not None and need_level <= MIN_THRESHOLD_DB else None
    hl_estimate_met = hl is not None and hl >= OSHA_RECORDABLE_HL_DB

    sts_flag = bool(sts.get("flag"))
    sts_determined = bool(sts.get("determined"))
    if (sts_determined and not sts_flag) or hl_met is False:
        status, recordable = "not_recordable", False
    elif sts_determined and sts_flag and hl_met:
        status, recordable = "recordable", True
    elif sts_flag and hl_estimate_met:
        status, recordable = "met_on_proxy", None
    else:
        status, recordable = "undetermined", None

    return {
        "sts": sts_flag,
        "sts_determined": sts_determined,
        "hearing_level_avg": None if hl is None else round(hl, 1),
        "hearing_level_freqs": freqs,
        "hearing_level_proxy": hl_proxy,
        "hearing_level_criterion_met": hl_met,
        # With one of 2/3/4 kHz untested: the threshold there that would bring
        # the regulatory average to 25 dB HL.
        "hearing_level_missing_freq": need_freq,
        "hearing_level_needed_db": need_level,
        # True/False only when settled; None when 3000 Hz (or another of the
        # three frequencies) is needed to decide. Recordable only if
        # work-related and not refuted by a 30-day retest.
        "recordable_if_work_related": recordable,
        "status": status,
        "determined": status in ("recordable", "not_recordable"),
        "proxy": (not sts_determined) or hl_proxy,
        "criterion": ("29 CFR 1904.10(a): STS and hearing level ≥ 25 dB HL "
                      "averaged at 2000/3000/4000 Hz in the same ear"),
    }


def asha_ototoxicity(
    deltas: Dict[int, Optional[float]],
    baseline: Dict[int, Optional[ThresholdValue]] | None = None,
    current: Dict[int, Optional[ThresholdValue]] | None = None,
    baseline_3k: Optional[ThresholdValue] = None,
    current_3k: Optional[ThresholdValue] = None,
) -> dict:
    """ASHA (1994) ototoxicity-monitoring significant-change criteria.

    A significant ototoxic change is any of:
      (a) >= 20 dB shift at any single test frequency;
      (b) >= 10 dB shift at two ADJACENT test frequencies;
      (c) loss of response ("NR") at three consecutive frequencies where
          responses were previously obtained.

    "Adjacent" and "consecutive" run over the frequencies actually compared.
    When 3000 Hz was tested on both audiograms it sits between 2000 and
    4000 Hz, so those two are no longer adjacent and its own shift counts
    under (a), (b) and (c); without it, 2000 and 4000 Hz are neighbours in
    the octave series this app tests.
    """
    triggers: List[str] = []
    seq: Dict[int, Optional[float]] = dict(deltas)
    order = list(AC_FREQS)
    d3k = shift_3k(baseline_3k, current_3k)
    if d3k is not None:
        seq[3000] = d3k
        order.insert(order.index(4000), 3000)

    for f in order:
        d = seq.get(f)
        if d is not None and d >= 20:
            triggers.append(f"≥20 dB shift at {f} Hz ({d:+g} dB)")

    ordered = [f for f in order if seq.get(f) is not None]
    for f1, f2 in zip(ordered, ordered[1:]):
        if order.index(f2) - order.index(f1) == 1:  # truly adjacent
            if seq[f1] >= 10 and seq[f2] >= 10:
                triggers.append(
                    f"≥10 dB shift at adjacent frequencies {f1}/{f2} Hz "
                    f"({seq[f1]:+g}/{seq[f2]:+g} dB)"
                )

    if baseline is not None and current is not None:
        before = dict(baseline)
        after = dict(current)
        if d3k is not None:
            before[3000], after[3000] = baseline_3k, current_3k
        run = 0
        for f in order:
            had_response = before.get(f) is not None and before.get(f) != "NR"
            lost = after.get(f) == "NR"
            run = run + 1 if (had_response and lost) else 0
            if run == 3:
                triggers.append("loss of response at three consecutive frequencies")
                break

    return {"flag": bool(triggers), "triggers": triggers,
            "criteria": "ASHA 1994 ototoxicity monitoring"}


def compare_ears(baseline_ac, current_ac,
                 baseline_3k: Optional[ThresholdValue] = None,
                 current_3k: Optional[ThresholdValue] = None) -> dict:
    """Full progression analysis for one ear (AC thresholds).

    ``baseline_3k``/``current_3k`` are the optional 3000 Hz thresholds; with
    both present the STS uses OSHA's own 2000/3000/4000 Hz average, and the
    current one alone already completes the recording hearing level.
    """
    deltas = ear_deltas(baseline_ac, current_ac)
    d3k = shift_3k(baseline_3k, current_3k)
    sts = osha_sts(deltas, d3k)
    return {
        "deltas": deltas,
        "delta_3000": d3k,
        "osha_sts": sts,
        "osha_recordable": osha_recordability(sts, current_ac, current_3k),
        "asha_ototoxicity": asha_ototoxicity(deltas, baseline_ac, current_ac,
                                             baseline_3k, current_3k),
        "max_shift": max((d for d in deltas.values() if d is not None), default=None),
    }


def compare_tests(baseline: dict, current: dict) -> dict:
    """Progression for both ears.

    ``baseline``/``current`` are dicts with 'right'/'left' -> {'ac': {...}},
    optionally with 'ac_3000' (the 3000 Hz threshold) per ear.
    """
    result = {
        side: compare_ears(baseline[side]["ac"], current[side]["ac"],
                           baseline[side].get("ac_3000"), current[side].get("ac_3000"))
        for side in ("right", "left")
    }
    result["narrative"] = narrate(result)
    return result


def _missing_freqs(sts: dict, rec: dict) -> List[int]:
    """Frequencies of 2/3/4 kHz that either OSHA test still lacks."""
    have_sts = set(sts.get("freqs") or [])
    have_hl = set(rec.get("hearing_level_freqs") or [])
    return [f for f in OSHA_FREQS if f not in have_sts or f not in have_hl]


def _sts_line(sts: dict, rec: dict) -> str:
    """One sentence on an STS: the shift, then whether it reaches the 300 Log.

    An STS alone is not a recordable case — 29 CFR 1904.10(a) also requires
    the ear's own hearing level to average 25 dB HL or more at 2/3/4 kHz — so
    the sentence never calls a shift recordable without that check, and
    never settles it on a partial average that the missing frequency could
    overturn.
    """
    avg = sts["avg_shift"]
    if sts.get("proxy"):
        line = (f"On the {_freq_label(sts['freqs'])} proxy for OSHA's 2k/3k/4k Hz "
                f"average, this meets the standard threshold shift criterion "
                f"({avg:g} dB average shift)")
    else:
        line = (f"This meets the OSHA standard threshold shift criterion "
                f"({avg:g} dB average shift at 2k/3k/4k Hz)")

    status = rec.get("status")
    hl = rec.get("hearing_level_avg")
    hl_where = _freq_label(rec.get("hearing_level_freqs") or [])
    missing = _missing_freqs(sts, rec)
    if status == "recordable":
        line += (f", and this ear's hearing level averages {hl:g} dB HL at 2k/3k/4k Hz "
                 f"(≥ {OSHA_RECORDABLE_HL_DB:g} dB) — recordable on the OSHA 300 Log if "
                 "the shift is work-related, unless a retest within 30 days does not "
                 "confirm it (29 CFR 1904.10).")
    elif status == "not_recordable":
        line += (f". This ear's hearing level averages {hl:g} dB HL at 2k/3k/4k Hz, below "
                 f"the {OSHA_RECORDABLE_HL_DB:g} dB that 29 CFR 1904.10(a) requires, so it "
                 "does not go on the OSHA 300 Log"
                 + (" — but it is a real shift to act on, not incidental variation."
                    if not sts.get("proxy") else "; the shift itself still needs follow-up."))
    elif status == "met_on_proxy":
        line += (f", and this ear's hearing level averages {hl:g} dB HL at {hl_where} "
                 f"(≥ {OSHA_RECORDABLE_HL_DB:g} dB): both conditions of 29 CFR 1904.10(a) "
                 "are met on the frequencies compared. That rule averages 2000, 3000 "
                 "and 4000 Hz, so the case is recordable on the OSHA 300 Log, if "
                 f"work-related, only once {_hz(missing)} Hz "
                 f"{'have' if len(missing) > 1 else 'has'} been tested on both "
                 "audiograms and the 2k/3k/4k Hz average confirms it.")
    elif hl is None:
        line += (" — whether it reaches the OSHA 300 Log cannot be determined "
                 "without the current hearing level at 2000, 3000 and 4000 Hz.")
    else:
        need, need_freq = rec.get("hearing_level_needed_db"), rec.get("hearing_level_missing_freq")
        line += (f". This ear's hearing level averages {hl:g} dB HL at {hl_where}, below "
                 f"the {OSHA_RECORDABLE_HL_DB:g} dB HL that 29 CFR 1904.10(a) requires, "
                 "but that rule averages 2000, 3000 and 4000 Hz, so whether the case "
                 "goes on the OSHA 300 Log cannot be determined without "
                 f"{_hz(missing)} Hz"
                 + (f": the average would reach {OSHA_RECORDABLE_HL_DB:g} dB HL with a "
                    f"{need_freq} Hz threshold of {need:g} dB HL or more."
                    if need is not None else ".")
                 + " The shift itself still needs follow-up.")

    if sts.get("proxy"):
        need, need_freq = sts.get("missing_shift_needed_db"), sts.get("missing_freq")
        line += (f" The shift rests on {_freq_label(sts['freqs'])} alone, and that proxy "
                 "can both miss and over-call a shift"
                 + (f": on OSHA's 2k/3k/4k Hz average it is a standard threshold shift "
                    f"{_sts_condition(need_freq, need)}."
                    if need is not None else "."))
    return line


def _no_sts_line(sts: dict) -> Optional[str]:
    """For a worsened ear whose OSHA 2k/3k/4k average was fully compared and
    falls short: say so, so that a criterion met on another rule is not read
    as the OSHA shift."""
    if sts.get("flag") or sts.get("proxy") or sts.get("avg_shift") is None:
        return None
    return (f"This does not meet the OSHA standard threshold shift criterion: the "
            f"average shift at 2k/3k/4k Hz is {sts['avg_shift']:g} dB, below "
            f"{STS_CRITERION_DB:g} dB.")


def _proxy_miss_line(sts: dict, short: bool = False) -> Optional[str]:
    """For an ear the proxy did NOT flag: the shift that would make it an STS.

    The proxy errs in both directions, and the direction that matters is the
    miss — a real STS reported as no shift. Without 3000 Hz an unflagged ear
    is "no STS on the frequencies compared", never "no STS".
    """
    if sts.get("flag") or not sts.get("proxy"):
        return None
    if sts.get("avg_shift") is None:
        return ("The OSHA standard threshold shift cannot be assessed: 2000, 3000 "
                "and 4000 Hz were not compared.")
    missing = [f for f in OSHA_FREQS if f not in sts["freqs"]]
    need, need_freq = sts.get("missing_shift_needed_db"), sts.get("missing_freq")
    if short:
        return (f"({_hz(missing)} Hz not compared: "
                + (f"an OSHA standard threshold shift would need a {need_freq} Hz shift "
                   f"of {need:g} dB or more.)" if need is not None else
                   "an OSHA standard threshold shift cannot be ruled out.)"))
    return (f"{_hz(missing)} Hz {'were' if len(missing) > 1 else 'was'} not compared, "
            "so the OSHA standard threshold shift "
            f"rests on {_freq_label(sts['freqs'])} ({sts['avg_shift']:g} dB average "
            "shift), a proxy that can miss a shift"
            + (f": OSHA's 2k/3k/4k Hz average would reach 10 dB with a {need_freq} Hz "
               f"shift of {need:g} dB or more. Test {_hz(missing)} Hz before dismissing it."
               if need is not None else
               f". Test {_hz(missing)} Hz before dismissing it."))


def narrate(progression: dict) -> dict:
    """Say in words what the delta chart shows.

    A bar chart of threshold shifts requires the reader to already know
    which shifts matter. This states it: what changed, where, whether it
    meets a monitoring criterion, and what that implies.
    """
    lines: List[str] = []
    flagged = False
    asha_flagged = False
    proxy_sts_flagged = False
    any_proxy = False

    for side in ("right", "left"):
        p = progression[side]
        sts = p["osha_sts"]
        any_proxy = any_proxy or bool(sts.get("proxy"))
        deltas = {f: d for f, d in p["deltas"].items() if d is not None}
        if p.get("delta_3000") is not None:
            # A 3000 Hz shift can carry an STS on its own; leaving it out of
            # the narrative would call that ear "stable".
            deltas[3000] = p["delta_3000"]
        if not deltas:
            lines.append(f"{side.capitalize()} ear: no paired frequencies to compare.")
            continue

        worsened = {f: d for f, d in deltas.items() if d >= 10}
        improved = {f: d for f, d in deltas.items() if d <= -10}

        if not worsened and not improved:
            stable = (f"{side.capitalize()} ear: stable — every tested frequency is within "
                      "10 dB of the baseline, which is ordinary test-retest variation.")
            miss = _proxy_miss_line(sts, short=True)
            lines.append(f"{stable} {miss}" if miss else stable)
            continue

        if worsened:
            worst_freq = max(worsened, key=lambda f: worsened[f])
            freq_list = ", ".join(f"{f} Hz" for f in sorted(worsened))
            lines.append(
                f"{side.capitalize()} ear: hearing has worsened at {freq_list}, most at "
                f"{worst_freq} Hz ({worsened[worst_freq]:+g} dB)."
            )
            if all(f >= 2000 for f in worsened):
                lines.append(
                    f"The change is confined to the high frequencies — the pattern "
                    "noise exposure and ageing both produce."
                )
        if improved:
            lines.append(
                f"{side.capitalize()} ear: thresholds improved at "
                f"{', '.join(f'{f} Hz' for f in sorted(improved))}, which usually means "
                "a resolved middle-ear problem or a difference in test conditions."
            )

        if sts["flag"]:
            flagged = True
            proxy_sts_flagged = proxy_sts_flagged or bool(sts.get("proxy"))
            lines.append(_sts_line(sts, p.get("osha_recordable") or {}))
        else:
            miss = _proxy_miss_line(sts) or (_no_sts_line(sts) if worsened else None)
            if miss:
                lines.append(miss)
        if p["asha_ototoxicity"]["flag"]:
            flagged = True
            asha_flagged = True
            # "also" only when the sentence before it reports the OSHA shift
            # as met; otherwise this is the criterion the change meets.
            lines.append(
                ("It also meets" if sts["flag"] else
                 f"{side.capitalize()} ear: the change meets")
                + " ASHA ototoxicity-monitoring criteria: "
                + "; ".join(p["asha_ototoxicity"]["triggers"]) + "."
            )

    if flagged and proxy_sts_flagged and not asha_flagged:
        headline = ("Significant change since the baseline — this shift meets a formal "
                    "monitoring criterion on the frequencies compared, but the OSHA "
                    "shift rests on a proxy without 3000 Hz; confirm it.")
    elif flagged:
        headline = ("Significant change since the baseline — this shift meets a formal "
                    "monitoring criterion.")
    elif any_proxy:
        headline = ("No shift meets a formal monitoring criterion at the frequencies "
                    "compared; without 3000 Hz an OSHA standard threshold shift is not "
                    "fully ruled out.")
    else:
        headline = "No shift meets a formal monitoring criterion."

    return {
        "lines": lines,
        "flagged": flagged,
        "osha_proxy": any_proxy,
        "headline": headline,
    }
