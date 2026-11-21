"""Evoked potentials — regressions for the clinical audit of the ABR and LLR.

Every expected value here is computed from the published source it rests on,
not read back from the module: the reference table's mean and SD, the adult
interpeak limits, the Sharma, Dorman & Spahr (2002) P1 fit, the Selters &
Brackmann (1977) correction and de Jager's nHL-to-eHL corrections.
"""
import math

import pytest
from fastapi.testclient import TestClient

from app.clinical import aep
from app.clinical import diagnosis as D
from app.main import app

client = TestClient(app)


def abr_body(waves, intensity=80, **extra):
    body = {"intensity_db_nhl": intensity, "waves": waves,
            "latencies_include_delay": False}
    body.update(extra)
    return body


def sharma_p1(age_months):
    """Normal-hearing P1, ms: 155.6 - 32.746 ln(age in years) (Sharma 2002)."""
    return 155.6 - 32.746 * math.log(age_months / 12.0)


# ======================================= a delayed ABR is an abnormal ABR

def test_an_isolated_late_wave_v_is_flagged_and_retrocochlear_is_not_excluded():
    """Wave V 7.5 ms at 80 dB nHL is ~17 SD late against 5.47 +/- 0.12."""
    body = client.post("/api/aep/abr", json=abr_body({"V": 7.5})).json()
    v = next(e for e in body["absolute"] if e["wave"] == "V")
    assert v["z"] == pytest.approx((7.5 - 5.47) / 0.12, abs=0.01)
    assert v["delayed"] is True
    assert "absolute_latency_delayed" in body["flags"]
    assert "interpeak_unmeasurable" in body["flags"]
    assert body["status"] == "abnormal"
    text = " ".join(body["findings"])
    # The "not a neural lesion" reading needs measured, normal intervals.
    assert "not of a neural lesion" not in text
    assert "cannot be excluded" in text


def test_the_battery_never_calls_a_delayed_abr_normal():
    body = client.post("/api/aep/battery",
                       json={"abr": abr_body({"V": 7.5})}).json()
    assert body["abnormal_levels"] == ["ABR"]
    assert body["abnormal"] is True
    assert "within normal limits" not in body["headline"]
    assert "intact" not in body["headline"]


def test_the_conductive_pattern_is_abnormal_and_named_peripheral():
    """All waves +1 ms at 80 dB: intervals 2.06 / 1.79 / 3.85 ms, all normal."""
    result = aep.analyze_abr({"I": 2.62, "III": 4.68, "V": 6.47}, 80,
                             latencies_include_delay=False)
    intervals = {e["pair"]: e["value"] for e in result["interwave"]}
    assert intervals == {"I-III": 2.06, "III-V": 1.79, "I-V": 3.85}
    assert "interpeak_prolonged" not in result["flags"]
    assert "absolute_latency_delayed" in result["flags"]
    assert result["interpretation"] == "peripheral"
    assert any("conductive" in f for f in result["findings"])

    battery = aep.aep_battery(abr=result)
    assert battery["abnormal_levels"] == ["ABR"]
    assert "within normal limits" not in battery["headline"]
    assert "conductive or cochlear" in battery["headline"]


def test_the_peripheral_reading_still_requires_the_intervals_to_be_measured():
    """With Wave I absent, III-V alone cannot clear the eighth nerve."""
    result = aep.analyze_abr({"III": 5.18, "V": 6.97}, 80,
                             latencies_include_delay=False)
    assert "interpeak_unmeasurable" in result["flags"]
    assert result["interpretation"] == "indeterminate_delay"
    assert any("says nothing about the eighth nerve" in f for f in result["findings"])


def test_absolute_delay_is_three_sd_with_two_to_three_reported_borderline():
    """ACNS 9C: 2.5 or 3 SD; the wider is used, 2-3 SD is borderline."""
    mean, sd, _ = aep.ABR_NORMS[80]["waves"]["I"]   # Wave I: no sex allowance
    at_2_5 = round(mean + 2.5 * sd, 2)
    at_3_5 = round(mean + 3.5 * sd, 2)
    border = aep.analyze_abr({"I": at_2_5, "III": 3.68, "V": 5.47}, 80,
                             latencies_include_delay=False, sex="female")
    late = aep.analyze_abr({"I": at_3_5, "III": 3.68, "V": 5.47}, 80,
                           latencies_include_delay=False, sex="female")
    assert border["flags"] == [] and border["status"] == "borderline"
    assert "absolute_latency_delayed" in late["flags"]

    battery = aep.aep_battery(abr=border)
    assert battery["uncertain_levels"] == ["ABR"]
    assert "within normal limits" not in battery["headline"]


def test_adult_limits_are_not_applied_to_an_infant():
    """ACNS 9C: age-specific norms under 3 years. Beyond adult = indeterminate."""
    late_for_adult = {"I": 1.9, "III": 4.4, "V": 6.4}     # I-V 4.5, V z +7.75
    infant = aep.analyze_abr(late_for_adult, 80, latencies_include_delay=False,
                             age_months=6)
    adult = aep.analyze_abr(late_for_adult, 80, latencies_include_delay=False,
                            age_months=360)
    assert infant["flags"] == [] and infant["status"] == "indeterminate"
    assert adult["status"] == "abnormal"
    assert aep.aep_battery(abr=infant)["uncertain_levels"] == ["ABR"]


# ================================================ interpeak limits (C-5)

def test_a_normal_mans_interpeak_intervals_are_not_called_retrocochlear():
    """I-V 4.25, I-III 2.20, III-V 2.05 ms are inside 4.5 / 2.5 / 2.4 ms."""
    body = client.post("/api/aep/abr", json=abr_body(
        {"I": 1.62, "III": 3.82, "V": 5.87}, sex="male")).json()
    assert "interpeak_prolonged" not in body["flags"]
    assert body["interpretation"] != "retrocochlear"
    assert not any("retrocochlear until excluded" in f for f in body["findings"])
    limits = {e["pair"]: e["upper_limit"] for e in body["interwave"]}
    assert limits == {"I-III": 2.5, "III-V": 2.4, "I-V": 4.5}


@pytest.mark.parametrize("v,prolonged", [(6.12, False), (6.13, True)])
def test_the_i_v_limit_is_four_and_a_half_milliseconds(v, prolonged):
    """I 1.62 + 4.50 = 6.12 sits on the limit; 0.01 ms more is past it.

    III at 3.82 keeps I-III (2.20) and III-V (2.30-2.31) inside their limits,
    so only I-V decides.
    """
    result = aep.analyze_abr({"I": 1.62, "III": 3.82, "V": v}, 80,
                             latencies_include_delay=False, sex="male")
    i_v = next(e for e in result["interwave"] if e["pair"] == "I-V")
    assert i_v["prolonged"] is prolonged
    assert ("interpeak_prolonged" in result["flags"]) is prolonged


def test_a_male_allowance_applies_to_the_later_waves_only():
    """Stone et al. 2009: women's later waves run ~0.15 ms earlier."""
    mean, sd, _ = aep.ABR_NORMS[80]["waves"]["V"]
    v = round(mean + 3 * sd + 0.10, 2)          # past 3 SD, inside 3 SD + 0.15
    female = aep.analyze_abr({"V": v}, 80, latencies_include_delay=False,
                             sex="female")
    male = aep.analyze_abr({"V": v}, 80, latencies_include_delay=False, sex="male")
    unknown = aep.analyze_abr({"V": v}, 80, latencies_include_delay=False)
    assert "absolute_latency_delayed" in female["flags"]
    assert "absolute_latency_delayed" not in male["flags"]
    # Sex unknown: not called delayed, but not called normal either.
    assert unknown["flags"] == [] and unknown["status"] == "borderline"
    wave_i = next(e for e in male["absolute"] if e["wave"] == "I")
    assert wave_i.get("sex_allowance_ms") is None   # absent wave, no entry


# ===================================================== cochlear microphonic

def test_a_cochlear_microphonic_beside_a_normal_abr_is_not_abnormal():
    body = client.post("/api/aep/battery", json={"abr": abr_body(
        {"I": 1.62, "III": 3.68, "V": 5.47}, cm_present=True)}).json()
    assert body["abnormal_levels"] == []
    run = aep.analyze_abr({"I": 1.62, "III": 3.68, "V": 5.47}, 80,
                          latencies_include_delay=False, cm_present=True)
    assert "cochlear_microphonic_present" not in run["flags"]
    assert any("not the auditory neuropathy pattern" in f for f in run["findings"])


def test_a_cochlear_microphonic_with_no_wave_v_is_still_the_ansd_pattern():
    run = aep.analyze_abr({}, 90, cm_present=True)
    assert "cochlear_microphonic_present" in run["flags"]
    assert run["interpretation"] == "ansd"


# ================================================= interaural comparison

def test_wave_v_from_runs_at_different_levels_is_not_compared():
    """Both at their own row's mean: 5.37 at 90 and 5.88 at 60 dB nHL."""
    body = client.post("/api/aep/abr/asymmetry", json={
        "right": abr_body({"V": 5.37}, 90),
        "left": abr_body({"V": 5.88}, 60)}).json()
    assert body["available"] is False
    assert body["significant"] is None
    assert "same level" in body["note"]


def test_equal_level_runs_are_still_compared():
    body = client.post("/api/aep/abr/asymmetry", json={
        "right": abr_body({"V": 5.47}), "left": abr_body({"V": 6.10})}).json()
    assert body["available"] is True
    assert body["difference"] == pytest.approx(0.63, abs=0.005)
    assert body["significant"] is True and body["poorer_ear"] == "left"
    assert body["hearing_loss_correction"]["applied"] is False
    assert any("Selters & Brackmann" in l for l in body["limitations"])


@pytest.mark.parametrize("left_4k,correction", [
    (40, 0.0), (55, 0.0), (60, 0.1), (65, 0.1), (80, 0.3), (90, 0.4)])
def test_the_selters_brackmann_correction_is_point_one_ms_per_ten_db(left_4k,
                                                                      correction):
    """0.1 ms per complete 10 dB of 4 kHz loss above 50 dB HL.

    Clicks at 100 dB nHL keep every ear at least 10 dB above its 4 kHz
    threshold, where BSA 2019 (s7.6) allows absolute latencies to be used. A
    corrected difference is judged against 0.37 ms (Lightfoot 1992, BSA 2019
    Table 1), borderline above Selters & Brackmann's own 0.2 ms.
    """
    body = client.post("/api/aep/abr/asymmetry", json={
        "right": abr_body({"V": 5.47}, 100, threshold_4k_db_hl=10),
        "left": abr_body({"V": 6.10}, 100, threshold_4k_db_hl=left_4k)}).json()
    assert body["hearing_loss_correction"]["left_ms"] == pytest.approx(correction)
    expected = round(abs(5.47 - (6.10 - correction)), 2)
    assert body["difference"] == pytest.approx(expected, abs=0.005)
    assert body["criterion"] == 0.37
    assert body["significant"] is (expected > 0.37)
    assert body["borderline"] is (0.2 < expected <= 0.37)


# ============================================================= nHL and eHL

def test_a_click_threshold_is_reported_in_nhl_with_its_ehl_range():
    """de Jager: typical click correction 0-5 dB."""
    body = client.post("/api/aep/abr/threshold", json={"series": [
        {"intensity": 70, "wave_v": 5.7}, {"intensity": 30, "wave_v": 7.3},
        {"intensity": 20, "wave_v": None}]}).json()
    assert body["unit"] == "dB nHL"
    assert body["estimated_threshold_db_nhl"] == 30
    assert body["ehl"]["range_db_ehl"] == [25, 30]
    assert "dB nHL" in body["message"] and "not a substitute" in body["message"]


@pytest.mark.parametrize("freq,correction", [
    (500, 20), (1000, 15), (2000, 10), (4000, 10)])
def test_a_tone_burst_threshold_gets_the_typical_correction(freq, correction):
    """de Jager: typical tone-burst corrections 20 / 15 / 10 / 10 dB."""
    body = client.post("/api/aep/abr/threshold", json={
        "stimulus": "tone_burst", "frequency_hz": freq,
        "series": [{"intensity": 50, "wave_v": 7.6}]}).json()
    assert body["ehl"]["estimate_db_ehl"] == 50 - correction


def test_an_unlisted_tone_burst_frequency_stays_in_nhl():
    body = client.post("/api/aep/abr/threshold", json={
        "stimulus": "tone_burst", "frequency_hz": 3000,
        "series": [{"intensity": 50, "wave_v": 7.6}]}).json()
    assert body["ehl"]["estimate_db_ehl"] is None
    assert body["estimated_threshold_db_nhl"] == 50


# =========================================================== interpolation

def test_an_intermediate_level_is_judged_against_interpolated_norms():
    """75 dB nHL: V mean (5.64 + 5.47) / 2 = 5.555, SD (0.16 + 0.12) / 2 = 0.14."""
    result = aep.analyze_abr({"V": 5.555}, 75, latencies_include_delay=False)
    v = next(e for e in result["absolute"] if e["wave"] == "V")
    assert result["norm_interpolated"] is True
    assert result["norm_rows_db_nhl"] == [70, 80]
    assert v["norm"]["mean"] == pytest.approx(5.555, abs=1e-6)
    assert v["norm"]["sd"] == pytest.approx(0.14, abs=1e-6)
    assert abs(v["z"]) < 0.1


def test_a_table_level_still_uses_its_own_row():
    result = aep.analyze_abr({"V": 5.47}, 80, latencies_include_delay=False)
    assert result["norm_interpolated"] is False
    assert result["norm_row_db_nhl"] == 80


# ===================================================== P1 cortical maturation

@pytest.mark.parametrize("months", [3, 6, 12, 18, 36, 48, 120, 240])
def test_a_p1_at_the_published_normal_mean_is_never_delayed(months):
    p1 = round(sharma_p1(months), 1)
    result = aep.analyze_llr({"P1": p1, "N1": 100, "P2": 180, "N2": 325},
                             age_months=months)
    assert result["maturation"]["delayed"] is False
    assert "cortical_maturation_delayed" not in result["flags"]
    assert not any("cochlear-implant" in f for f in result["findings"])


@pytest.mark.parametrize("months", [18, 36, 60, 120])
def test_delay_is_called_only_outside_the_95_percent_limit(months):
    """Sharma 2002 Fig. 2: the 95% limits sit ~32 ms either side of the fit.

    Ages where the published curves are flat enough to read to a millisecond.
    """
    mean = sharma_p1(months)
    inside = aep.analyze_llr({"P1": round(mean + 31, 1)}, age_months=months)
    outside = aep.analyze_llr({"P1": round(mean + 33, 1)}, age_months=months)
    assert inside["maturation"]["delayed"] is False
    assert outside["maturation"]["delayed"] is True
    assert "cortical_maturation_delayed" in outside["flags"]
    assert any("cochlear-implant" in f for f in outside["findings"])


def test_an_infant_outside_the_normative_ages_is_not_judged():
    """The curve starts at 0.1 years; earlier is not extrapolated."""
    result = aep.analyze_llr({"P1": 300}, age_months=0.5)
    assert result["maturation"]["assessable"] is False
    assert result["flags"] == []
    assert result["status"] == "indeterminate"


def test_an_absent_n1_in_a_young_child_is_not_a_finding():
    """Ponton 2000: N1 only emerges reliably between about 7 and 11 years."""
    child = aep.analyze_llr({"P1": round(sharma_p1(48), 1), "N2": 250},
                            age_months=48)
    adult = aep.analyze_llr({"P1": 52, "P2": 180}, age_months=300)
    assert "n1_absent" not in child["flags"]
    assert "n1_absent" in adult["flags"]


def test_adult_windows_do_not_make_a_normal_child_cortically_delayed():
    """A normal 4-year-old: P1 ~110 ms and P2 ~210 ms, both beyond adult windows."""
    child = aep.analyze_llr({"P1": 110, "P2": 210}, age_months=48)
    assert "cortical_delay" not in child["flags"]
    p1 = next(r for r in child["peaks"] if r["peak"] == "P1")
    assert p1["within_range"] is True


# ================================================================ battery

def test_the_abr_level_is_only_as_normal_as_its_worse_ear():
    right = aep.analyze_abr({"I": 1.62, "III": 3.68, "V": 5.47}, 80,
                            latencies_include_delay=False, ear="right")
    left = aep.analyze_abr({"I": 1.62, "III": 4.30, "V": 6.60}, 80,
                           latencies_include_delay=False, ear="left")
    battery = aep.aep_battery(abr=right, abr_other_ear=left)
    assert battery["abnormal_levels"] == ["ABR"]
    assert {e["ear"]: e["status"] for e in battery["levels"][0]["ears"]} == {
        "right": "normal", "left": "abnormal"}

    body = client.post("/api/aep/battery", json={
        "abr": abr_body({"I": 1.62, "III": 3.68, "V": 5.47}, ear="right"),
        "abr_other_ear": abr_body({"I": 1.62, "III": 4.30, "V": 6.60}, ear="left"),
    }).json()
    assert body["abnormal_levels"] == ["ABR"]


def test_the_diagnostic_picture_raises_the_alarm_for_an_abnormal_battery():
    """diagnosis.py reads the battery's own ``abnormal`` field."""
    battery = aep.aep_battery(
        abr=aep.analyze_abr({"V": 7.5}, 80, latencies_include_delay=False))
    picture = D.diagnostic_picture(analysis=None, aep={"battery": battery})
    finding = next(f for f in picture["findings"] if f["key"] == "aep")
    assert finding["alarm"] is True


def test_the_reference_publishes_the_criteria_actually_used():
    ref = client.get("/api/aep/reference").json()
    assert ref["abr"]["interpeak_upper_limits_ms"] == {"I-III": 2.5, "III-V": 2.4,
                                                       "I-V": 4.5}
    # Lightfoot 1992 via BSA 2019 Table 1.
    assert ref["abr"]["i_v_upper_95_cl_ms"] == {"female": 4.34, "male": 4.46}
    assert ref["abr"]["interaural_v_corrected_criterion_ms"] == 0.37
    assert ref["abr"]["interaural_v_selters_brackmann_ms"] == 0.2
    assert ref["abr"]["min_sensation_level_db"] == 10
    assert ref["llr"]["p1_model"]["intercept_ms"] == 155.6
    first = ref["llr"]["p1_maturation"][0]
    assert first["typical_ms"] == pytest.approx(sharma_p1(3), abs=0.05)


# ============== a delay is peripheral only when it starts at Wave I (C-2)

NOT_NEURAL = "not of a neural lesion"


@pytest.mark.parametrize("sex", ["female", "male", None])
def test_a_late_wave_v_with_wave_i_on_time_is_not_called_peripheral(sex):
    """I 1.62 / III 3.68 / V 6.05 at 80 dB nHL.

    Wave I sits on the 80 dB mean (z 0); Wave V is (6.05 - 5.47) / 0.12 = 4.83
    SD late, past even the male 3 SD + 0.15 ms limit of 5.98 ms. The whole
    delay lies between I and V (III-V 2.37 ms), so nothing was shifted before
    the nerve and retrocochlear pathology cannot be excluded.
    """
    body = client.post("/api/aep/abr", json=abr_body(
        {"I": 1.62, "III": 3.68, "V": 6.05}, sex=sex)).json()
    wave_i = next(e for e in body["absolute"] if e["wave"] == "I")
    wave_v = next(e for e in body["absolute"] if e["wave"] == "V")
    assert wave_i["z"] == pytest.approx(0, abs=0.01)
    assert wave_v["z"] == pytest.approx((6.05 - 5.47) / 0.12, abs=0.01)
    assert body["status"] == "abnormal"
    assert body["interpretation"] == "retrocochlear_not_excluded"
    assert "delay_within_i_v" in body["flags"]
    text = " ".join(body["findings"])
    assert NOT_NEURAL not in text
    assert "retrocochlear pathology cannot be excluded" in text

    battery = client.post("/api/aep/battery", json={"abr": abr_body(
        {"I": 1.62, "III": 3.68, "V": 6.05}, sex=sex)}).json()
    assert "before the brainstem" not in battery["headline"]
    assert "cannot be excluded" in battery["headline"]


@pytest.mark.parametrize("waves,level,sex", [
    ({"I": 1.62, "III": 4.12, "V": 5.47}, 80, None),      # only III late, z +5.5
    ({"I": 1.53, "III": 3.58, "V": 5.95}, 90, "male"),    # I at the 90 dB mean
    ({"I": 1.62, "III": 3.68, "V": 6.08}, 80, "male"),
    ({"I": 1.62, "III": 3.82, "V": 5.87}, 80, "female"),  # C-5 case, V z +3.33
])
def test_other_on_time_wave_i_delays_are_not_peripheral(waves, level, sex):
    result = aep.analyze_abr(waves, level, latencies_include_delay=False, sex=sex)
    mean_i, sd_i, _ = aep.ABR_NORMS[level]["waves"]["I"]
    assert abs(waves["I"] - mean_i) / sd_i <= 2          # Wave I on time
    assert result["status"] == "abnormal"
    assert result["interpretation"] == "retrocochlear_not_excluded"
    assert not any(NOT_NEURAL in f for f in result["findings"])


def test_a_late_wave_i_with_an_intact_i_v_is_still_peripheral():
    """Wave I 2.5 SD late (1.62 + 2.5 x 0.12 = 1.92), V 5.90 (z +3.58, female),
    I-V 3.98 ms — the women's Lightfoot mean, well inside 4.34 ms."""
    result = aep.analyze_abr({"I": 1.92, "III": 4.00, "V": 5.90}, 80,
                             latencies_include_delay=False, sex="female")
    assert result["interpretation"] == "peripheral"
    assert any(NOT_NEURAL in f for f in result["findings"])


def test_a_late_wave_i_does_not_excuse_an_i_v_near_the_limit():
    """I 2.00 (z +3.17), V 6.47: I-V 4.47 ms is inside the 4.5 ms clinical
    limit but beyond the men's 95% limit of 4.46 ms (Lightfoot 1992), so the
    periphery does not account for all of the delay."""
    result = aep.analyze_abr({"I": 2.00, "III": 4.10, "V": 6.47}, 80,
                             latencies_include_delay=False, sex="male")
    i_v = next(e for e in result["interwave"] if e["pair"] == "I-V")
    assert i_v["value"] == pytest.approx(4.47) and i_v["prolonged"] is False
    assert i_v["borderline"] is True
    assert result["interpretation"] == "retrocochlear_not_excluded"
    assert not any(NOT_NEURAL in f for f in result["findings"])


@pytest.mark.parametrize("v,borderline", [(5.69, False), (5.70, True)])
def test_an_i_v_beyond_the_adult_95_percent_limit_is_borderline(v, borderline):
    """Women's I-V upper 95% CL 4.34 ms (BSA 2019 Table 1): I 1.35 + 4.34 = 5.69.

    Wave V stays inside 2 SD (5.47 + 2 x 0.12 = 5.71), so only I-V decides.
    """
    result = aep.analyze_abr({"I": 1.35, "III": 3.50, "V": v}, 80,
                             latencies_include_delay=False, sex="female")
    i_v = next(e for e in result["interwave"] if e["pair"] == "I-V")
    assert i_v["upper_95_cl"] == 4.34
    assert i_v["borderline"] is borderline
    assert result["flags"] == []
    assert result["status"] == ("borderline" if borderline else "normal")
    if borderline:
        assert aep.aep_battery(abr=result)["uncertain_levels"] == ["ABR"]


def test_the_mens_i_v_limit_is_four_point_four_six():
    """The same 4.35 ms I-V is inside the men's 4.46 ms limit."""
    result = aep.analyze_abr({"I": 1.35, "III": 3.50, "V": 5.70}, 80,
                             latencies_include_delay=False, sex="male")
    i_v = next(e for e in result["interwave"] if e["pair"] == "I-V")
    assert i_v["upper_95_cl"] == 4.46 and i_v["borderline"] is False
    assert result["status"] == "normal"


def test_an_infants_gross_delay_is_not_reassured_away():
    """V 9.5 ms at 80 dB nHL, 24 months: beyond the adult 5.98 ms limit
    (5.47 + 0.15 + 3 x 0.12, sex unknown) by 3.52 ms."""
    result = aep.analyze_abr({"V": 9.5}, 80, latencies_include_delay=False,
                             age_months=24)
    assert result["status"] == "indeterminate"
    text = " ".join(result["findings"])
    assert "not evidence of delay" not in text
    assert "+3.52 ms" in text
    assert "age-specific" in text


# ============================= CM beside an abnormal ABR (C-6 consistency)

def test_a_cochlear_microphonic_beside_a_grossly_late_wave_v_leaves_ansd_open():
    """V 8.5 ms at 80 dB nHL is (8.5 - 5.47) / 0.12 = 25 SD late."""
    result = aep.analyze_abr({"V": 8.5}, 80, latencies_include_delay=False,
                             cm_present=True)
    assert "cochlear_microphonic_abnormal_abr" in result["flags"]
    text = " ".join(result["findings"])
    assert "not the auditory neuropathy pattern" not in text
    assert "auditory neuropathy spectrum disorder is not excluded" in text
    assert "polarity" in text
    battery = aep.aep_battery(abr=result)
    assert "auditory neuropathy not excluded" in battery["headline"]


def test_a_cochlear_microphonic_beside_a_normal_abr_states_its_condition():
    result = aep.analyze_abr({"I": 1.62, "III": 3.68, "V": 5.47}, 80,
                             latencies_include_delay=False, cm_present=True)
    assert result["flags"] == [] and result["status"] == "normal"
    assert any("provided Wave V repeated" in f for f in result["findings"])


# ============================ the corrected interaural criterion (C-8)

def asym(right, left, level=80):
    return client.post("/api/aep/abr/asymmetry", json={
        "right": abr_body({"V": right[0]}, level, threshold_4k_db_hl=right[1]),
        "left": abr_body({"V": left[0]}, level, threshold_4k_db_hl=left[1]),
    }).json()


def test_a_corrected_difference_is_judged_against_the_corrected_limit():
    """Raw 0.7 ms; right 4 kHz 80 dB HL corrects by 0.3 ms; corrected 0.4 ms.

    At 90 dB nHL the click is 10 dB above the 80 dB HL threshold. 0.4 ms is
    beyond Selters & Brackmann's 0.2 ms and Lightfoot's 0.37 ms alike.
    """
    body = asym((6.0, 80), (5.3, 20), level=90)
    assert body["uncorrected_difference"] == pytest.approx(0.7)
    assert body["difference"] == pytest.approx(6.0 - 0.3 - 5.3, abs=0.005)
    assert body["significant"] is True and body["status"] == "asymmetric"
    assert body["poorer_ear"] == "right"


@pytest.mark.parametrize("right_v,status", [
    (5.50, "symmetric"),     # 0.20: not beyond Selters & Brackmann's 0.2
    (5.51, "borderline"),    # 0.21
    (5.67, "borderline"),    # 0.37: on Lightfoot's limit
    (5.68, "asymmetric"),    # 0.38
])
def test_the_corrected_criterion_boundaries(right_v, status):
    body = asym((right_v, 20), (5.30, 20))
    assert body["hearing_loss_correction"]["applied"] is True
    assert body["status"] == status
    assert body["significant"] is (status == "asymmetric")
    assert body["borderline"] is (status == "borderline")
    if status != "symmetric":
        assert body["poorer_ear"] == "right"
    if status == "borderline":
        assert "within" not in body["message"]


def test_without_both_thresholds_the_uncorrected_criterion_stays_0_4():
    body = asym((5.67, None), (5.30, 20))
    assert body["hearing_loss_correction"]["applied"] is False
    assert body["criterion"] == 0.4
    assert body["status"] == "symmetric"


@pytest.mark.parametrize("thr,interpretable", [(70, True), (71, False), (80, False)])
def test_a_click_under_10_db_sensation_level_is_not_compared(thr, interpretable):
    """BSA 2019 s7.6: absolute latencies are not relied on below 10 dB SL."""
    body = asym((6.2, thr), (5.5, 20), level=80)
    assert body["available"] is interpretable
    if not interpretable:
        assert body["status"] == "not_interpretable"
        assert body["significant"] is None
        assert "10 dB" in body["note"]


def test_a_correction_that_reverses_the_ears_is_called_out():
    """Equal raw Wave V; the right ear's 90 dB HL loss corrects it by 0.4 ms."""
    body = asym((5.5, 90), (5.5, 20), level=100)
    assert body["uncorrected_difference"] == 0
    assert body["difference"] == pytest.approx(0.4)
    assert any("reverses which ear is later" in l for l in body["limitations"])


# ======================================= battery wording (verifier notes)

def test_wave_v_without_wave_i_is_not_called_an_intact_pathway():
    run = aep.analyze_abr({"V": 5.5}, 80, latencies_include_delay=False)
    assert run["status"] == "normal" and run["i_v_measured"] is False
    battery = aep.aep_battery(abr=run)
    assert "pathway is intact" not in battery["headline"]
    assert "eighth-nerve" in battery["headline"]
    assert battery["limitations"]


def test_every_abnormal_level_is_named_in_the_headline():
    periph = aep.analyze_abr({"I": 2.62, "III": 4.68, "V": 6.47}, 80,
                             latencies_include_delay=False)
    llr = aep.analyze_llr({"P1": 160, "N1": 150, "P2": 200}, age_months=60)
    battery = aep.aep_battery(abr=periph, llr=llr)
    assert battery["abnormal_levels"] == ["ABR", "LLR"]
    assert "LLR" in battery["headline"]
    assert "cortical maturation delayed" in battery["headline"]


# ===================================== adult P1 consistency (C-3 minor)

@pytest.mark.parametrize("months", [240, 241, 300])
def test_an_adult_p1_row_and_its_maturation_verdict_agree(months):
    """Past 20 years P1 is read against the curve's 20-year end, 57.5 +/- 32."""
    end = sharma_p1(240)
    result = aep.analyze_llr({"P1": 70, "N1": 105, "P2": 180, "N2": 320},
                             age_months=months)
    p1 = next(r for r in result["peaks"] if r["peak"] == "P1")
    assert p1["range"] == [pytest.approx(end - 32, abs=0.05),
                           pytest.approx(end + 32, abs=0.05)]
    assert p1["within_range"] is True
    assert result["maturation"]["delayed"] is False
    assert result["status"] == "normal"


def test_a_late_adult_p1_is_borderline_not_an_implant_marker():
    result = aep.analyze_llr({"P1": 95, "N1": 105, "P2": 180, "N2": 320},
                             age_months=300)
    assert result["maturation"]["adult"] is True
    assert "cortical_maturation_delayed" not in result["flags"]
    assert not any("cochlear-implant" in f for f in result["findings"])
    assert result["status"] == "borderline"


@pytest.mark.parametrize("months", [24, 300])
def test_nothing_read_is_not_a_normal_cortical_result(months):
    """A section emptied of its example has no peaks; that is not normal."""
    assert aep.analyze_mlr({})["status"] == "indeterminate"
    llr = aep.analyze_llr({}, age_months=months)
    assert llr["status"] == "indeterminate" and "n1_absent" not in llr["flags"]
    battery = aep.aep_battery(mlr=aep.analyze_mlr({}), llr=llr)
    assert battery["uncertain_levels"] == ["MLR", "LLR"]
    assert "within normal limits" not in battery["headline"]


def test_a_single_late_component_is_borderline_not_normal():
    result = aep.analyze_llr({"P1": 52, "N1": 170, "P2": 180, "N2": 320},
                             age_months=300)
    n1 = next(r for r in result["peaks"] if r["peak"] == "N1")
    assert n1["delayed"] is True
    assert result["flags"] == [] and result["status"] == "borderline"
