"""Regression tests: listening lab, amplification, noise dose, progression, norms.

Every expected value is computed here from the published rule, never read
back from the module under test.
"""
import math

import pytest
from fastapi.testclient import TestClient

from app.clinical.listening_lab import (
    compare_srtn_with_audiogram,
    score_digits_in_noise,
    score_speech_babble,
)
from app.clinical.noise_dose import compute_dose
from app.clinical.norms import (
    analyze_norms,
    ear_norms,
    median_threshold,
    percentile,
    sex_basis,
)
from app.clinical.prescription import (
    aided_thresholds,
    nal_r_gains,
    prescribe,
    verify_fitting,
)
from app.clinical.progression import compare_ears, compare_tests, ear_deltas, osha_sts
from app.main import app
from app.services.sii import sii_bundle

client = TestClient(app)

FREQS = (250, 500, 1000, 2000, 4000, 8000)


def flat(level, freqs=FREQS):
    return {f: level for f in freqs}


def _record(right, left, date):
    return {"patient": {"age": 40, "test_date": date},
            "right": {"ac": {str(k): v for k, v in right.items()}},
            "left": {"ac": {str(k): v for k, v in left.items()}}}


# ===================================================== progression (D-1) ===
#
# 29 CFR 1904.10(a): recordable = work-related STS AND the same ear's hearing
# level averaging >= 25 dB HL at 2/3/4 kHz.

def test_sts_below_25_db_hearing_level_is_not_called_recordable():
    """The finding's repro (no 3000 Hz): never called recordable. The 2/4 kHz
    hearing level of 10 dB HL cannot settle 1904.10(a) on its own — the 2/3/4
    kHz average reaches 25 only if 3000 Hz is 3 x 25 - (10 + 10) = 55 dB HL."""
    base = flat(0)
    cur = {**base, 2000: 10, 4000: 10}
    body = client.post("/api/progression", json={
        "baseline": _record(base, base, "2025-01-01"),
        "current": _record(cur, base, "2026-01-01")}).json()
    right = body["progression"]["right"]
    assert right["osha_sts"]["flag"] is True          # (10 + 10) / 2 = 10
    rec = right["osha_recordable"]
    assert rec["hearing_level_avg"] == 10.0           # (10 + 10) / 2
    assert rec["hearing_level_criterion_met"] is None
    assert rec["hearing_level_needed_db"] == 55.0
    assert rec["recordable_if_work_related"] is None
    assert rec["status"] == "undetermined"
    lines = body["progression"]["narrative"]["lines"]
    assert not any("recordable" in ln for ln in lines)
    assert any("1904.10" in ln and "300 Log" in ln and "cannot be determined" in ln
               and "55 dB HL" in ln for ln in lines)


def test_sts_below_25_db_with_3000_hz_is_settled_not_recordable():
    """Same ear with 3000 Hz 0 -> 10: STS (10 + 10 + 10) / 3 = 10, hearing
    level 10 dB HL < 25 — settled: not on the OSHA 300 Log."""
    base, cur = flat(0), {**flat(0), 2000: 10, 4000: 10}
    r = compare_ears(base, cur, baseline_3k=0, current_3k=10)
    assert r["osha_sts"]["determined"] is True and r["osha_sts"]["flag"] is True
    rec = r["osha_recordable"]
    assert rec["hearing_level_criterion_met"] is False
    assert rec["recordable_if_work_related"] is False and rec["determined"] is True
    lines = compare_tests({"right": {"ac": base, "ac_3000": 0}, "left": {"ac": base}},
                          {"right": {"ac": cur, "ac_3000": 10}, "left": {"ac": base}}
                          )["narrative"]["lines"]
    assert any("does not go on the OSHA 300 Log" in ln for ln in lines)


def test_sts_with_25_db_hearing_level_is_recordable_if_work_related():
    base = {**flat(10)}
    cur = {**base, 2000: 25, 4000: 25}  # shifts 15/15/15; HL (25+25+25)/3 = 25
    r = compare_ears(base, cur, baseline_3k=10, current_3k=25)
    assert r["osha_sts"]["flag"] is True and r["osha_sts"]["determined"] is True
    assert r["osha_recordable"]["hearing_level_avg"] == 25.0
    assert r["osha_recordable"]["hearing_level_criterion_met"] is True  # ">= 25"
    assert r["osha_recordable"]["recordable_if_work_related"] is True
    text = " ".join(compare_tests(
        {"right": {"ac": base, "ac_3000": 10}, "left": {"ac": base}},
        {"right": {"ac": cur, "ac_3000": 25}, "left": {"ac": base}})["narrative"]["lines"])
    assert "recordable" in text and "work-related" in text


def test_both_conditions_met_on_the_proxy_await_3000_hz():
    """Without 3000 Hz the same case meets both conditions on 2/4 kHz only:
    a 3000 Hz threshold below 3 x 25 - 50 = 25 dB HL would undo the hearing
    level, so it is not settled as recordable."""
    base = flat(10)
    cur = {**base, 2000: 25, 4000: 25}
    rec = compare_ears(base, cur)["osha_recordable"]
    assert rec["status"] == "met_on_proxy"
    assert rec["recordable_if_work_related"] is None
    assert rec["hearing_level_needed_db"] == 25.0
    text = " ".join(compare_tests({"right": {"ac": base}, "left": {"ac": base}},
                                  {"right": {"ac": cur}, "left": {"ac": base}})
                    ["narrative"]["lines"])
    assert "once 3000 Hz has been tested" in text


def test_no_sts_is_never_recordable_whatever_the_hearing_level():
    r = compare_ears(flat(50), flat(55), baseline_3k=50, current_3k=55)  # +5: no STS
    assert r["osha_sts"]["flag"] is False and r["osha_sts"]["determined"] is True
    assert r["osha_recordable"]["hearing_level_criterion_met"] is True  # HL 55
    assert r["osha_recordable"]["recordable_if_work_related"] is False


def test_an_unflagged_proxy_does_not_settle_recordability():
    """+5 at 2/4 kHz without 3000 Hz is no STS on the proxy, not no STS."""
    r = compare_ears(flat(50), flat(55))
    assert r["osha_sts"]["flag"] is False
    # 3000 Hz would need a shift of 3 x 10 - (5 + 5) = 20 dB to make it an STS.
    assert r["osha_sts"]["missing_shift_needed_db"] == 20.0
    assert r["osha_recordable"]["recordable_if_work_related"] is None


def test_hearing_level_settled_when_3000_hz_cannot_change_it():
    """Current 2/4 kHz of 50/60: even 3000 Hz at the -10 dB HL floor gives a
    2/3/4 kHz average of (50 - 10 + 60) / 3 = 33.3 >= 25."""
    rec = compare_ears(flat(10), {**flat(10), 2000: 50, 4000: 60})["osha_recordable"]
    assert rec["hearing_level_needed_db"] == 75 - 110
    assert rec["hearing_level_criterion_met"] is True
    assert rec["status"] == "met_on_proxy"       # the STS still rests on 2/4 kHz


def test_current_3000_hz_alone_completes_the_hearing_level():
    """1904.10(b)(2)(ii): the hearing level comes from the current audiogram
    alone, so a current 3000 Hz of 40 counts without a baseline 3000 Hz:
    (20 + 40 + 20) / 3 = 26.7 >= 25. The STS (needs both 3000 Hz values)
    stays on the proxy, so the case is not yet settled — and never called
    off the 300 Log."""
    base = flat(10)
    cur = {**base, 2000: 20, 4000: 20}
    body = client.post("/api/progression", json={
        "baseline": _record(base, base, "2025-01-01"),
        "current": _record(cur, base, "2026-01-01"),
        "thresholds_3000": {"current": {"right": 40}}}).json()["progression"]
    rec = body["right"]["osha_recordable"]
    assert rec["hearing_level_freqs"] == [2000, 3000, 4000]
    assert rec["hearing_level_avg"] == pytest.approx(80 / 3, abs=0.05)
    assert rec["hearing_level_criterion_met"] is True
    assert rec["status"] == "met_on_proxy"
    assert rec["recordable_if_work_related"] is None
    text = " ".join(body["narrative"]["lines"])
    assert "does not go on the OSHA 300 Log" not in text
    assert "26.7 dB HL" in text


# ================================================== 3000 Hz proxy (D-2) ====

def test_proxy_misses_a_real_sts_and_says_so():
    """Shifts 0/15/15 at 2/3/4 kHz: OSHA average 10 (STS); proxy 7.5."""
    deltas = ear_deltas(flat(10), {**flat(10), 4000: 25})
    proxy = osha_sts(deltas)
    assert proxy["avg_shift"] == 7.5 and proxy["flag"] is False
    assert proxy["proxy"] is True
    assert "3000 Hz" in proxy["proxy_note"]
    real = osha_sts(deltas, delta_3k=15)
    assert real["avg_shift"] == pytest.approx((0 + 15 + 15) / 3, abs=0.01)
    assert real["flag"] is True
    assert real["proxy"] is False and real["freqs"] == [2000, 3000, 4000]


def test_proxy_over_calls_a_non_sts_and_says_so():
    """Shifts 10/0/10: OSHA average 6.7 (no STS); proxy 10 (flagged)."""
    deltas = ear_deltas(flat(10), {**flat(10), 2000: 20, 4000: 20})
    assert osha_sts(deltas)["flag"] is True
    real = osha_sts(deltas, delta_3k=0)
    assert real["avg_shift"] == pytest.approx(20 / 3, abs=0.01)
    assert real["flag"] is False


def test_progression_endpoint_uses_3000_hz_when_supplied():
    base = flat(10)
    cur = {**base, 4000: 25}
    payload = {"baseline": _record(base, base, "2025-01-01"),
               "current": _record(cur, base, "2026-01-01")}
    without = client.post("/api/progression", json=payload).json()
    assert without["progression"]["right"]["osha_sts"]["flag"] is False
    assert without["progression"]["right"]["osha_sts"]["proxy"] is True

    payload["thresholds_3000"] = {"baseline": {"right": 10, "left": 10},
                                  "current": {"right": 25, "left": 10}}
    body = client.post("/api/progression", json=payload).json()
    sts = body["progression"]["right"]["osha_sts"]
    assert sts["proxy"] is False and sts["flag"] is True
    assert sts["avg_shift"] == pytest.approx(10.0, abs=0.01)
    assert body["progression"]["left"]["osha_sts"]["flag"] is False


def test_progression_rejects_an_out_of_range_3000_hz_threshold():
    base = flat(10)
    r = client.post("/api/progression", json={
        "baseline": _record(base, base, "2025-01-01"),
        "current": _record(base, base, "2026-01-01"),
        "thresholds_3000": {"current": {"right": 130}}})
    assert r.status_code == 422


def test_recording_level_uses_3000_hz_when_supplied():
    """Current 20/40/20 dB HL: 2/3/4 kHz average 26.7 (>= 25); the 2/4 proxy
    would read 20 and miss the recording criterion."""
    base = flat(10)
    cur = {**base, 2000: 20, 4000: 20}
    r = compare_ears(base, cur, baseline_3k=10, current_3k=40)
    assert r["osha_sts"]["avg_shift"] == pytest.approx((10 + 30 + 10) / 3, abs=0.01)
    assert r["osha_recordable"]["hearing_level_avg"] == pytest.approx(80 / 3, abs=0.05)
    assert r["osha_recordable"]["recordable_if_work_related"] is True


def test_a_shift_carried_by_3000_hz_is_not_narrated_as_stable():
    base = flat(10)
    cur = {**base, 2000: 15, 4000: 15}     # +5 / (3k +20) / +5 -> average 10
    result = compare_tests(
        {"right": {"ac": base, "ac_3000": 10}, "left": {"ac": base}},
        {"right": {"ac": cur, "ac_3000": 30}, "left": {"ac": base}})
    assert result["right"]["osha_sts"]["flag"] is True
    right_lines = [ln for ln in result["narrative"]["lines"] if "Right ear" in ln]
    assert right_lines and "stable" not in right_lines[0]
    assert "3000 Hz" in right_lines[0]


def test_narrative_warns_when_the_proxy_may_have_missed_a_shift():
    """The finding's 0/15/15 example without 3000 Hz: the proxy (7.5 dB) does
    not flag, but a 3000 Hz shift of 3 x 10 - (0 + 15) = 15 dB would make it
    an STS — the narrative and headline must say so, not "no shift"."""
    base = flat(10)
    cur = {**base, 4000: 25}
    narrative = compare_tests({"right": {"ac": base}, "left": {"ac": base}},
                              {"right": {"ac": cur}, "left": {"ac": base}})["narrative"]
    assert narrative["flagged"] is False
    assert narrative["osha_proxy"] is True
    text = " ".join(narrative["lines"])
    assert "3000 Hz shift of 15 dB or more" in text
    assert "not fully ruled out" in narrative["headline"]
    # A stable ear states the (large) 3000 Hz shift it would take: 3 x 10 - 0.
    assert "3000 Hz shift of 30 dB or more" in text


def test_complete_comparison_keeps_the_plain_headline():
    base = flat(10)
    narrative = compare_tests(
        {"right": {"ac": base, "ac_3000": 10}, "left": {"ac": base, "ac_3000": 10}},
        {"right": {"ac": base, "ac_3000": 10}, "left": {"ac": base, "ac_3000": 10}},
    )["narrative"]
    assert narrative["osha_proxy"] is False
    assert narrative["headline"] == "No shift meets a formal monitoring criterion."


def test_a_single_frequency_proxy_is_named_as_such():
    """2000 Hz untested: the average rests on 4 kHz alone and must not be
    narrated as a 2k/4k average."""
    base = {f: 10 for f in FREQS if f != 2000}
    cur = {**base, 4000: 25}
    result = compare_tests({"right": {"ac": base}, "left": {"ac": flat(10)}},
                           {"right": {"ac": cur}, "left": {"ac": flat(10)}})
    sts = result["right"]["osha_sts"]
    assert sts["freqs"] == [4000] and sts["flag"] is True
    assert "2000/3000 Hz were not available" in sts["proxy_note"]
    sts_line = next(ln for ln in result["narrative"]["lines"] if "proxy for OSHA" in ln)
    assert "On the 4k Hz proxy" in sts_line and "2k/4k" not in sts_line
    # Hearing level from 4 kHz alone (25) cannot settle the 2/3/4 kHz average.
    assert result["right"]["osha_recordable"]["recordable_if_work_related"] is None


def test_a_flag_resting_only_on_the_proxy_is_headlined_as_such():
    """+15 at 2 kHz and +5 at 4 kHz: the proxy average of 10 flags, and no
    ASHA criterion fires (no shift >= 20, no adjacent pair >= 10), so the
    only flag is the proxy STS."""
    base = flat(10)
    cur = {**base, 2000: 25, 4000: 15}
    narrative = compare_tests({"right": {"ac": base}, "left": {"ac": base}},
                              {"right": {"ac": cur}, "left": {"ac": base}})["narrative"]
    assert narrative["flagged"] is True
    assert "proxy without 3000 Hz" in narrative["headline"]


# ============================================================ NAL-R (D-3) ===

SKI = {250: 10, 500: 15, 1000: 20, 2000: 55, 4000: 70, 8000: 75}
NAL_K = {250: -17, 500: -8, 1000: 1, 2000: -1, 4000: -2, 8000: -2}


def _nal_r(h):
    x = 0.05 * (h[500] + h[1000] + h[2000])
    return {f: min(45.0, max(0.0, x + 0.31 * h[f] + NAL_K[f])) for f in FREQS}


def test_nal_r_applies_the_formula_at_every_band_of_an_impaired_ear():
    body = client.post("/api/prescription",
                       json={"ac": {str(f): v for f, v in SKI.items()}}).json()
    expected = _nal_r(SKI)                       # 1 kHz: 4.5 + 6.2 + 1 = 11.7
    for f in FREQS:
        assert body["gains"][str(f)] == pytest.approx(expected[f], abs=0.06), f
    assert body["gains"]["1000"] == pytest.approx(11.7, abs=0.06)
    assert body["gains"]["500"] == pytest.approx(1.15, abs=0.06)
    assert body["gains"]["250"] == 0.0           # negative target -> zero
    assert body["candidate"] is True


def test_an_ear_with_no_loss_is_not_fitted():
    b = prescribe(flat(15))
    assert b["candidate"] is False
    assert all(g == 0.0 for g in b["gains"].values())
    assert "no amplification" in b["note"].lower()


def test_twenty_db_is_the_start_of_hearing_loss_for_candidacy():
    """WHO 2021: 20 dB HL is mild loss, so one band at 20 makes a candidate."""
    ac = {**flat(10), 4000: 20}
    gains = nal_r_gains(ac)
    x = 0.05 * 30
    assert gains[1000] == pytest.approx(x + 0.31 * 10 + 1, abs=0.06)    # 5.6
    assert gains[4000] == pytest.approx(x + 0.31 * 20 - 2, abs=0.06)    # 5.7


def test_aided_sii_and_fitting_follow_the_full_prescription():
    b = sii_bundle(SKI)
    assert b["prescription_gains"][1000] == pytest.approx(11.7, abs=0.06)
    assert b["aided_quiet"]["sii"] >= b["quiet"]["sii"]
    # An aid that matches the prescription verifies; one that gives nothing
    # at 1 kHz is now correctly called under target there.
    on_target = verify_fitting(SKI, aided_thresholds(SKI))
    assert on_target["on_target"] is True
    aided = dict(aided_thresholds(SKI))
    aided[1000] = SKI[1000]
    off = verify_fitting(SKI, aided)
    assert 1000 in off["off_target_freqs"]


def test_a_loss_without_the_nal_r_frequencies_is_not_given_zero_as_a_prescription():
    """NAL-R's X term needs 500/1000/2000 Hz; with none tested the formula
    cannot run, which is not the same as "no gain needed"."""
    ac = {250: 60, 8000: 70}
    b = prescribe(ac)
    assert b["candidate"] is True and b["prescribable"] is False
    assert b["x_term_freqs"] == []
    assert "no gain can be prescribed" in b["note"]
    assert "First-fit reference" not in b["note"]
    fit = verify_fitting(ac, {250: 40, 8000: 50})
    assert fit["on_target"] is None
    assert "cannot be verified" in fit["summary"]


def test_a_partial_x_term_is_disclosed():
    ac = {500: 40, 1000: 50, 4000: 60}           # 2000 Hz untested
    b = prescribe(ac)
    assert b["prescribable"] is True and b["x_term_freqs"] == [500, 1000]
    assert "2000 Hz" in b["note"] and "estimated" in b["note"]
    # X = 0.05 x (40 + 50) x 3/2 = 6.75; IG(1 kHz) = 6.75 + 15.5 + 1 = 23.25.
    assert b["gains"][1000] == pytest.approx(23.25, abs=0.06)


# ======================================================= noise dose (D-4) ===

def _t(level, criterion, exchange):
    return 8 / 2 ** ((level - criterion) / exchange)


def test_pel_and_action_level_integrate_different_sound():
    body = client.post("/api/noise-dose", json={"exposures": [
        {"level_dba": 89, "hours": 8}, {"level_dba": 95, "hours": 1}]}).json()
    pel = 100 * (1 / _t(95, 90, 5))                          # 89 dBA excluded
    action = 100 * (8 / _t(89, 90, 5) + 1 / _t(95, 90, 5))   # both counted
    assert body["osha_pel_dose_pct"] == pytest.approx(pel, abs=0.06)       # 25.0
    assert body["osha_action_dose_pct"] == pytest.approx(action, abs=0.06)  # 112.1
    assert body["osha_dose_pct"] == body["osha_action_dose_pct"]
    assert body["twa_dba"] == pytest.approx(16.61 * math.log10(action / 100) + 90,
                                            abs=0.06)
    assert body["risk"] == "action"
    assert "exceeds" not in body["verdict"].lower()
    assert "hearing conservation programme" in body["verdict"]


def test_sound_below_80_dba_contributes_nothing():
    d = compute_dose([{"level_dba": 70, "hours": 8}])
    assert d["osha_dose_pct"] == 0.0
    assert d["osha_pel_dose_pct"] == 0.0
    assert d["niosh_dose_pct"] == 0.0
    assert d["twa_dba"] is None
    assert d["risk"] == "low"


def test_80_dba_is_integrated_for_the_action_level_and_niosh():
    d = compute_dose([{"level_dba": 80, "hours": 8}])
    assert d["osha_action_dose_pct"] == pytest.approx(100 * 8 / _t(80, 90, 5), abs=0.06)
    assert d["osha_pel_dose_pct"] == 0.0
    assert d["niosh_dose_pct"] == pytest.approx(100 * 8 / _t(80, 85, 3), abs=0.06)
    d79 = compute_dose([{"level_dba": 79, "hours": 8}])
    assert d79["niosh_dose_pct"] == 0.0 and d79["osha_action_dose_pct"] == 0.0


def test_pel_is_exceeded_only_above_100_percent():
    over = compute_dose([{"level_dba": 90, "hours": 8.01}])   # 100.125%
    assert over["osha_pel_dose_pct"] > 100 and over["risk"] == "high"
    assert "exceeds" in over["verdict"].lower()
    at = compute_dose([{"level_dba": 90, "hours": 8}])        # exactly 100%
    assert at["osha_pel_dose_pct"] == 100.0
    assert at["risk"] == "action"
    assert "exceeds" not in at["verdict"].lower()


def test_a_dose_just_over_the_pel_is_never_shown_as_100():
    """8.0002 h at 90 dBA is 100.0025% — over unity (Table G-16 note 1). It
    is shown rounded UP (100.1) and judged on that, never as 100.0 'at the
    limit'."""
    d = compute_dose([{"level_dba": 90, "hours": 8.0002}])
    assert 100 * 8.0002 / 8 > 100
    assert d["osha_pel_dose_pct"] == 100.1
    assert d["risk"] == "high"
    assert "exceeds" in d["verdict"].lower()


def test_exact_doses_are_not_rounded_up_by_float_residue():
    """85 dBA x 8 h is exactly 50% and 95 dBA x 4 h exactly 100%."""
    assert compute_dose([{"level_dba": 85, "hours": 8}])["osha_action_dose_pct"] == 50.0
    d = compute_dose([{"level_dba": 95, "hours": 4}])
    assert d["osha_pel_dose_pct"] == 100.0 and d["risk"] == "action"
    # Three exposures summing to exactly 100%: 4 h at 90 (50%), 2 h at 95
    # (50%), and 2 h at 70 dBA (not integrated).
    d = compute_dose([{"level_dba": 90, "hours": 4}, {"level_dba": 95, "hours": 2},
                      {"level_dba": 70, "hours": 2}])
    assert d["osha_pel_dose_pct"] == 100.0 and d["risk"] == "action"


def test_niosh_rel_band_is_still_reported():
    d = compute_dose([{"level_dba": 100, "hours": 0.25}])
    assert d["osha_action_dose_pct"] == pytest.approx(100 * 0.25 / _t(100, 90, 5), abs=0.06)
    assert d["niosh_dose_pct"] == pytest.approx(100 * 0.25 / _t(100, 85, 3), abs=0.06)
    assert d["risk"] == "niosh"


def test_protection_can_bring_an_exposure_under_the_pel_threshold():
    d = compute_dose([{"level_dba": 100, "hours": 8}], nrr=29, protection_worn=True)
    assert d["protection_attenuation_db"] == 11.0              # (29 - 7) / 2
    assert d["osha_pel_dose_pct"] == 0.0                       # 89 dBA < 90
    assert d["osha_action_dose_pct"] == pytest.approx(100 * 8 / _t(89, 90, 5), abs=0.06)
    assert d["risk"] == "action"


# ===================================================== speech in noise ======

SCORERS = (score_digits_in_noise, score_speech_babble)


@pytest.mark.parametrize("score", SCORERS)
def test_displayed_srt_and_band_agree_at_the_cutoffs(score):
    """D-5: the band is decided on the value shown."""
    r = score([-6.96])
    assert r["srt_db_snr"] == -7.0 and r["band"] == "normal"
    r = score([-4.46])
    assert r["srt_db_snr"] == -4.5 and r["band"] == "insufficient"


@pytest.mark.parametrize("score", SCORERS)
def test_band_always_matches_the_displayed_value(score):
    def band_of(v):
        return "normal" if v <= -7.0 else "insufficient" if v <= -4.5 else "poor"
    for i in range(-1000, -300):
        r = score([i / 100])
        assert r["band"] == band_of(r["srt_db_snr"]), (i / 100, r)


@pytest.mark.parametrize("score", SCORERS)
def test_short_tracks_are_flagged_low_reliability(score):
    """D-7: four reversals averaged in full give -4.0 — flagged, not trusted."""
    r = score([0, -2, -8, -6])
    assert r["srt_db_snr"] == -4.0 and r["reversals_used"] == 4
    assert r["reliable"] is False
    assert "low-reliability" in r["interpretation"]
    full = score([0, -2, -8, -6, -8, -6])
    assert full["reliable"] is True and full["reliability_note"] is None
    assert full["srt_db_snr"] == -7.0   # (-8 - 6 - 8 - 6) / 4


def test_digits_in_noise_bands_are_declared_provisional():
    """D-8: the -7.0 / -4.5 cut-offs are not traceable to a validation."""
    body = client.post("/api/listening/digits-in-noise",
                       json={"reversals": [-5, -5, -5, -5, -5, -5]}).json()["result"]
    assert body["provisional_bands"] is True
    assert body["normative"].startswith("Provisional")


# ================================================ audiogram cross-check ====

def _poor():
    return score_digits_in_noise([-2, -4, -2, -4, -2, -4])


def test_one_normal_ear_is_not_called_a_normal_audiogram():
    """D-6: right 10 / left 90 — say which ear; not hidden hearing loss."""
    cmp = compare_srtn_with_audiogram(_poor(), flat(10), flat(90))
    assert cmp["hidden_hearing_loss"] is False
    assert "Pure-tone thresholds are normal" not in cmp["note"]
    assert "right ear" in cmp["note"] and "left ear" in cmp["note"]
    assert cmp["right_pta"] == 10.0 and cmp["left_pta"] == 90.0


def test_pta_of_20_is_mild_loss_not_normal():
    """WHO 2021: normal hearing is a PTA below 20 dB HL."""
    assert compare_srtn_with_audiogram(_poor(), flat(20), flat(20))["hidden_hearing_loss"] is False
    just_normal = flat(19)                                       # PTA 19, every band < 20
    cmp = compare_srtn_with_audiogram(_poor(), just_normal, just_normal)
    assert cmp["better_ear_pta"] == 19.0
    assert cmp["hidden_hearing_loss"] is True


def test_a_normal_pta_hiding_a_raised_threshold_is_not_hidden_loss():
    """5/5/10/55 dB HL is a PTA of (5 + 5 + 10 + 55) / 4 = 18.75, but 55 dB
    at 4 kHz is a visible notch: hidden hearing loss requires every threshold
    0.25-8 kHz below 20 dB HL (Liberman et al. 2016)."""
    notch = {250: 5, 500: 5, 1000: 5, 2000: 10, 4000: 55, 8000: 10}
    cmp = compare_srtn_with_audiogram(_poor(), notch, notch)
    assert cmp["right_pta"] == 18.8
    assert cmp["hidden_hearing_loss"] is False
    assert cmp["raised_thresholds"]["right"] == {4000: 55.0}
    assert "4000 Hz (55 dB HL)" in cmp["note"]
    assert "Pure-tone thresholds are normal" not in cmp["note"]
    assert "not hidden hearing loss" in cmp["note"]


def test_a_raised_8_khz_threshold_also_blocks_hidden_loss():
    hf = {500: 5, 1000: 5, 2000: 5, 4000: 15, 8000: 70}            # PTA 7.5
    body = client.post("/api/listening/digits-in-noise", json={
        "reversals": [-2, -4, -2, -4, -2, -4],
        "right_ac": hf, "left_ac": flat(10)}).json()["versus_audiogram"]
    assert body["hidden_hearing_loss"] is False
    assert body["raised_thresholds"]["right"] == {"8000": 70.0}
    assert body["raised_thresholds"]["left"] == {}
    assert "right ear at 8000 Hz (70 dB HL)" in body["note"]


def test_a_threshold_of_exactly_20_is_raised():
    ac = {**flat(10), 4000: 20}
    cmp = compare_srtn_with_audiogram(_poor(), ac, flat(10))
    assert cmp["hidden_hearing_loss"] is False
    assert cmp["raised_thresholds"]["right"] == {4000: 20.0}


def test_a_normal_srt_still_mentions_a_raised_threshold():
    notch = {500: 5, 1000: 5, 2000: 10, 4000: 55}
    good = score_digits_in_noise([-9, -9, -9, -9, -9, -9])
    cmp = compare_srtn_with_audiogram(good, notch, notch)
    assert cmp["hidden_hearing_loss"] is False
    assert "4000 Hz (55 dB HL)" in cmp["note"]
    assert "does not rule that loss out" in cmp["note"]


def test_babble_hidden_hearing_loss_states_the_bands_are_provisional():
    normal = {500: 10, 1000: 10, 2000: 10, 4000: 10}
    body = client.post("/api/listening/speech-babble", json={
        "reversals": [-2, -4, -2, -4, -2, -4],
        "right_ac": normal, "left_ac": normal}).json()["versus_audiogram"]
    assert body["hidden_hearing_loss"] is True
    assert body["provisional_bands"] is True
    assert "provisional" in body["note"]


def test_cross_check_carries_the_low_reliability_caveat():
    cmp = compare_srtn_with_audiogram(score_digits_in_noise([0, 1]), flat(10), flat(10))
    assert cmp["srt_reliable"] is False
    assert "repeat it" in cmp["note"]


# ==================================================== ISO 7029 norms (D-9) ==

A_M = {4000: 0.016}
A_F = {4000: 0.009}


def test_unspecified_sex_uses_the_mean_of_the_two_curves():
    expected = (A_M[4000] + A_F[4000]) / 2 * (60 - 18) ** 2   # 22.05
    assert median_threshold(60, 4000, "unspecified") == pytest.approx(expected, abs=0.06)
    assert median_threshold(60, 4000, "other") == median_threshold(60, 4000, "unspecified")
    assert median_threshold(60, 4000, "male") == pytest.approx(A_M[4000] * 42 ** 2, abs=0.06)
    assert median_threshold(60, 4000, "F") == pytest.approx(A_F[4000] * 42 ** 2, abs=0.06)
    assert sex_basis("Male") == "male" and sex_basis("female") == "female"
    assert sex_basis("") == "unspecified"


def test_unspecified_sex_is_declared_in_the_payload():
    body = client.post("/api/analyze", json={
        "patient": {"age": 60, "sex": "unspecified"},
        "right": {"ac": {"4000": 20}}, "left": {"ac": {"4000": 20}}}).json()
    right = body["norms"]["right"]
    assert right["sex_basis"] == "unspecified"
    assert right["per_frequency"][0]["expected_for_age"] == pytest.approx(22.05, abs=0.06)
    assert "mean" in right["sex_note"]
    assert "ISO 7029:2000" in right["method"]


@pytest.mark.parametrize("age,extrapolated", [(18, False), (70, False), (71, True),
                                              (80, True), (85, True), (17, True)])
def test_ages_outside_18_to_70_are_marked_extrapolated(age, extrapolated):
    r = ear_norms({4000: 30, 2000: 20}, age=age, sex="male")
    assert r["age_in_standard_range"] is (not extrapolated)
    assert r["extrapolated"] is extrapolated
    assert all(p["age_extrapolated"] is extrapolated for p in r["per_frequency"])
    if extrapolated:
        assert "extrapolated" in r["summary"] or "young-adult reference" in r["summary"]


def test_ages_above_80_are_clamped_and_say_so():
    assert median_threshold(85, 4000, "male") == median_threshold(80, 4000, "male")
    r = ear_norms({4000: 40}, age=85, sex="male")
    assert "80-year value" in r["extrapolation_note"]


def test_hearing_age_beyond_70_is_flagged():
    # 4 kHz male: hearing age 18 + sqrt(60 / 0.016) = 79.2, beyond 70.
    r = ear_norms({4000: 60}, age=40, sex="male")
    assert r["per_frequency"][0]["hearing_age"] == pytest.approx(18 + math.sqrt(60 / 0.016), abs=0.06)
    assert r["per_frequency"][0]["hearing_age_extrapolated"] is True
    assert r["hearing_age_extrapolated"] is True
    both = analyze_norms({4000: 60}, {4000: 60}, age=40, sex="male")
    assert both["extrapolated"] is True
    assert "Extrapolated" in both["headline"]
    assert both["standard"] == "ISO 7029:2000"


def test_percentile_marks_out_of_range_ages():
    assert percentile(30, 75, 4000, "male")["age_extrapolated"] is True
    assert percentile(30, 50, 4000, "male")["age_extrapolated"] is False


def test_20_db_hl_is_not_called_within_normal_limits_by_the_norms():
    """WHO 2021: 20 dB HL is mild loss. The norms summary must not call it
    'within normal limits' while the prescription in the same payload treats
    it as a loss to fit."""
    r = ear_norms(flat(20), age=30, sex="male")
    assert r["clinically_normal"] is False
    assert "within normal limits" not in r["summary"]
    assert ear_norms(flat(19), age=30, sex="male")["clinically_normal"] is True


def test_norms_and_prescription_agree_on_20_db_hl():
    body = client.post("/api/analyze", json={
        "patient": {"age": 30, "sex": "male"},
        "right": {"ac": {str(f): 20 for f in FREQS}},
        "left": {"ac": {str(f): 20 for f in FREQS}}}).json()
    assert body["prescription"]["right"]["candidate"] is True
    assert body["norms"]["right"]["clinically_normal"] is False
    assert "within normal limits" not in body["norms"]["right"]["summary"]
