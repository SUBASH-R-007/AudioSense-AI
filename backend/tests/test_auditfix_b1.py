"""Tympanometry and BOA: probe tone, compensated peak height, and age bands.

Every expected value here is worked out from the published rule, not read
back from the module:

  Jerger (1970) / BSA (2024) §11.1.4   a flat trace is Type B, split by the
                                       canal volume; a perforation adds the
                                       middle-ear space, so 4-5 ml is a volume
  ASHA (1997); BSA (2024) §11.1.3      peak height is compensated (peak - tail)
  Baldwin (2006); BSA (2024) §11.2     1000 Hz infant trace: positive peak
                                       above the tail-to-tail baseline = normal,
                                       flat / trough-shaped = abnormal
  Margolis et al. (2003), AAA (2020)   1 kHz newborn 5th percentile 0.6 mmho,
                                       -400 daPa tail to the main peak, a
                                       pass-fail criterion; AAA (2020) I.ii.b
                                       admittance below the age norm is
                                       abnormal
  Northern & Downs ABI                 rudimentary head turn in 6 wk - 4 mo
"""
import math

import pytest
from fastapi.testclient import TestClient

from app.clinical import boa, tympanometry
from app.clinical.immittance import classify_tympanogram
from app.main import app

client = TestClient(app)
TYMP = "/api/tympanometry/analyze"


def gaussian(peak_pressure, height, tail, fwhm=90, lo=-400, hi=200, step=10):
    sigma = fwhm / (2 * math.sqrt(2 * math.log(2)))
    return [{"pressure": p,
             "admittance": round(tail + height * math.exp(
                 -((p - peak_pressure) ** 2) / (2 * sigma ** 2)), 4)}
            for p in range(lo, hi + 1, step)]


def flat(ml, lo=-400, hi=200):
    return [{"pressure": p, "admittance": ml} for p in range(lo, hi + 1, 10)]


# ======================================= B1-1  perforation is not Type Add ===

@pytest.mark.parametrize("ml", [4.2, 5.0])
def test_a_perforations_flat_trace_is_type_b_large_volume(ml):
    """Compensated admittance 0 -> flat -> Type B; 4.2/5.0 ml > 2.0 -> large."""
    body = {"ear": "right", "age_years": 30, "trace": flat(ml)}
    result = client.post(TYMP, json=body).json()
    typed = result["tympanogram"]
    assert typed["type"] == "B"
    assert typed["ecv_flag"] == "large"
    assert "perforation" in typed["interpretation"].lower()
    assert "Ossicular discontinuity" not in typed["disorders"]
    assert result["curve"]["off_scale"] is False
    # The flags and the type now say the same thing.
    assert any("perforation" in f for f in result["flags"])
    assert not any("instrument ceiling" in f for f in result["flags"])


def test_a_flat_trace_has_no_peak_at_the_end_of_the_sweep():
    """The highest sample of a flat line is not a peak at -400 daPa."""
    result = tympanometry.analyze(trace=flat(4.2), age_years=30)
    assert not any("negative end of the sweep" in f for f in result["flags"])


@pytest.mark.parametrize("height,ecv,expected", [
    (2.6, 1.5, "Ad"),   # 1.66 < 2.6 < 3.0; raw 4.1 is canal + peak
    (3.5, 1.5, "Add"),  # 3.5 >= 3.0, a closed curve
    (0.8, 3.5, "A"),    # normal peak over a large canal
])
def test_trace_and_summary_values_give_the_same_type(height, ecv, expected):
    trace = tympanometry.analyze(trace=gaussian(0, height, ecv), age_years=30)
    summary = tympanometry.analyze(peak_pressure=0, compliance=height, ecv=ecv,
                                   age_years=30)
    assert trace["tympanogram"]["type"] == expected
    assert summary["tympanogram"]["type"] == expected


def test_trace_and_summary_agree_across_heights_and_volumes():
    for height in (0.05, 0.3, 0.8, 2.0, 2.6, 3.2):
        for ecv in (0.4, 1.0, 1.5, 2.5, 3.5):
            t = tympanometry.analyze(trace=gaussian(0, height, ecv), age_years=30)
            s = tympanometry.analyze(peak_pressure=0, compliance=height, ecv=ecv,
                                     age_years=30)
            assert t["tympanogram"]["type"] == s["tympanogram"]["type"], (height, ecv)
            if t["tympanogram"]["type"] == "B":
                assert t["tympanogram"]["ecv_flag"] == s["tympanogram"]["ecv_flag"]


def test_a_closed_deep_peak_over_a_large_canal_keeps_its_measurements():
    """Raw 5.0 mmho is canal 1.5 + peak 3.5: the apex was recorded."""
    result = tympanometry.analyze(trace=gaussian(-20, 3.5, 1.5), age_years=30)
    assert result["curve"]["off_scale"] is False
    assert result["measurements"]["static_compliance"] == pytest.approx(3.5, abs=0.05)
    assert result["measurements"]["peak_pressure"] == pytest.approx(-20, abs=10)


def test_a_compensated_peak_past_the_ceiling_is_off_scale():
    result = tympanometry.analyze(trace=gaussian(0, 4.5, 0.9), age_years=30)
    assert result["curve"]["off_scale"] is True
    assert result["tympanogram"]["type"] == "Add"


def test_a_gap_in_a_trace_that_never_rises_is_not_off_scale_or_flat():
    """A dropout: no peak exists to have left the scale, but one could hide in it."""
    trace = [{"pressure": p, "admittance": None if -60 <= p <= 40 else 4.2}
             for p in range(-400, 201, 10)]
    result = tympanometry.analyze(trace=trace, age_years=30)
    assert result["curve"]["off_scale"] is False
    assert result["curve"]["gap_without_peak"] is True
    assert result["tympanogram"] is None
    assert "gap" in result["not_typed"].lower()
    assert not any(line.startswith(("Type Add", "Type B"))
                   for line in result["interpretation"])


def test_a_known_flat_admittance_outranks_an_off_scale_claim():
    typed = tympanometry.classify(-10, 0.05, 4.2, age_years=30, off_scale=True)
    assert typed["type"] == "B" and typed["ecv_flag"] == "large"


# ================================ B1-2  1000 Hz infant interpretation =======

def test_the_reported_1000_hz_infant_entry_gets_no_226_hz_verdict():
    """0.3 mmho < 0.60, the Margolis (2003) newborn pass-fail criterion."""
    body = {"ear": "right", "age_years": 0.25, "probe_hz": 1000,
            "peak_pressure": 0, "compliance": 0.3, "ecv": 0.25}
    result = client.post(TYMP, json=body).json()
    typed = result["tympanogram"]
    assert typed["type"] == "1k-low-peak"
    assert typed["refer"] is True
    assert typed["type"] not in tympanometry.TYMPANOGRAM_TYPES
    assert typed["ecv_flag"] == "not_interpreted"
    # From summary values the baseline cannot be seen: never more than provisional.
    assert typed["provisional"] is True
    text = " ".join(result["interpretation"] + typed["disorders"]).lower()
    for word in ("otosclerosis", "cerumen", "tympanosclerosis", "perforation."):
        assert word not in text
    assert all(v is None for v in result["within_normal"].values())


def test_a_clear_positive_peak_at_1000_hz_is_normal():
    """Peak 0.9 above a level baseline; 0.9 >= 0.6 re the -400 tail."""
    result = tympanometry.analyze(trace=gaussian(-80, 0.9, 1.2), age_years=0.2,
                                  probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["type"] == "1k-peak"
    assert "provisional" not in typed
    assert "normal middle-ear function" in typed["interpretation"]
    assert typed["refer"] is False


def test_a_flat_1000_hz_trace_refers_and_never_says_cerumen():
    """Small 'volume' at 1000 Hz is not interpreted (BSA 2024 §11.2)."""
    result = tympanometry.analyze(trace=flat(0.2), age_years=0.2, probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["type"] == "1k-no-peak"
    assert typed["refer"] is True
    assert "Middle-ear effusion" in typed["disorders"]
    text = " ".join(result["interpretation"] + result["flags"]).lower()
    assert "cerumen" not in text and "wax" not in text


def test_a_trough_shaped_1000_hz_trace_is_abnormal():
    """The main deflection is below the baseline: a negative peak."""
    result = tympanometry.analyze(trace=gaussian(-50, -0.5, 1.5, fwhm=120),
                                  age_years=0.2, probe_hz=1000)
    assert result["tympanogram"]["type"] == "1k-no-peak"


def test_a_positive_and_a_negative_peak_together_count_as_positive():
    """BSA (2024) §11.2: both present -> classified as normal."""
    trace = [{"pressure": p,
              "admittance": round(1.0
                                  + 0.9 * math.exp(-((p + 60) ** 2) / (2 * 30 ** 2))
                                  - 0.4 * math.exp(-((p - 100) ** 2) / (2 * 25 ** 2)), 4)}
             for p in range(-400, 201, 10)]
    result = tympanometry.analyze(trace=trace, age_years=0.2, probe_hz=1000)
    assert result["tympanogram"]["type"] == "1k-peak"


def test_the_baseline_joins_the_tails_not_just_the_positive_one():
    """A sloping trace with no bump: +200-compensated it 'peaks' 0.6 at -400,
    but against the line joining -400 and +200 there is no peak at all."""
    trace = [{"pressure": p, "admittance": round(1.6 - (p + 400) / 600.0, 4)}
             for p in range(-400, 201, 10)]
    result = tympanometry.analyze(trace=trace, age_years=0.2, probe_hz=1000)
    assert result["tympanogram"]["type"] == "1k-no-peak"


def test_a_small_positive_peak_below_the_newborn_norm_is_not_called_normal():
    """0.3 mmho re the -400 tail < 0.6, the Margolis 5th percentile, which
    Margolis et al. (2003) give as a pass-fail criterion: it does not pass."""
    result = tympanometry.analyze(trace=gaussian(0, 0.3, 1.0), age_years=0.1,
                                  probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["type"] == "1k-low-peak"
    assert typed["refer"] is True
    assert typed["static_admittance"] == pytest.approx(0.3, abs=0.01)
    assert "Margolis" in typed["interpretation"]
    assert "consistent with normal" not in typed["interpretation"]


def test_a_1000_hz_sweep_short_of_minus_400_cannot_be_read_as_normal():
    result = tympanometry.analyze(trace=gaussian(0, 0.9, 1.0, lo=-200),
                                  age_years=0.2, probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["provisional"] is True
    assert any("-400" in c for c in typed["caveats"])
    assert any("-400" in f for f in result["flags"])


def test_1000_hz_beyond_nine_months_is_provisional():
    result = tympanometry.analyze(trace=gaussian(0, 0.9, 1.0), age_years=1.0,
                                  probe_hz=1000)
    assert result["tympanogram"]["provisional"] is True
    assert any("226 Hz" in c for c in result["tympanogram"]["caveats"])


def test_classify_reads_a_1000_hz_entry_by_the_infant_method():
    assert tympanometry.classify(0, 0.8, 0.5, age_years=0.25,
                                 probe_hz=1000)["type"] == "1k-peak"
    assert tympanometry.classify(0, 0.3, 0.5, age_years=0.25,
                                 probe_hz=1000)["type"] == "1k-low-peak"
    assert tympanometry.classify(None, 0.02, 0.5, age_years=0.25,
                                 probe_hz=1000)["type"] == "1k-no-peak"


def ramp_with_bump(bump):
    """A 1 kHz trace on a rising baseline: 0.5 mmho at -400 to 1.2 at +200,
    with a peak of ``bump`` at -300 daPa. The +200 tail is the highest point."""
    return [{"pressure": p,
             "admittance": round(0.5 + 0.7 * (p + 400) / 600
                                 + bump * math.exp(-((p + 300) ** 2) / (2 * 30 ** 2)), 4)}
            for p in range(-400, 201, 10)]


def test_the_newborn_criterion_is_measured_to_the_main_peak_not_the_highest_sample():
    """Main peak at -300: 0.5 + 0.7*100/600 + 0.333 = 0.9497 mmho.
    -400 tail: 0.5 + 0.333*exp(-100^2/1800) = 0.5013 mmho.
    Margolis measure 0.448 < 0.60 -> does not pass. The highest sample (the
    +200 tail, 1.2 mmho) would read 0.699 and pass; it is not a peak."""
    result = tympanometry.analyze(trace=ramp_with_bump(0.333), age_years=0.1,
                                  probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["type"] == "1k-low-peak"
    assert typed["refer"] is True and typed["suggests_conductive"] is True
    assert "consistent with normal" not in typed["interpretation"]
    assert typed["static_admittance"] == pytest.approx(0.448, abs=0.005)
    hf = result["curve"]["high_frequency"]
    assert hf["peak_pressure"] == -300
    # What is shown beside the verdict is the peak the verdict was reached on.
    assert result["measurements"]["peak_pressure"] == -300
    assert result["measurements"]["static_compliance"] == pytest.approx(0.448, abs=0.005)
    assert "-400" in result["measurements"]["static_compliance_reference"]


def test_a_trace_that_rises_into_the_sweep_end_has_no_main_peak():
    """1.0 + 0.8(1 - exp(-(p+400)/80)) rises the whole sweep: it bulges above
    the tail-to-tail baseline but never turns down, so BSA (2024) §11.2 has
    no main peak to call positive. Not normal; a peak past +200 is possible."""
    trace = [{"pressure": p,
              "admittance": round(1.0 + 0.8 * (1 - math.exp(-(p + 400) / 80.0)), 4)}
             for p in range(-400, 201, 10)]
    result = tympanometry.analyze(trace=trace, age_years=0.1, probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["type"] == "1k-no-peak"
    assert typed["refer"] is True
    assert typed["provisional"] is True
    assert any("+200" in c for c in typed["caveats"])
    assert result["curve"]["high_frequency"]["main_peak_found"] is False
    assert "consistent with normal" not in typed["interpretation"]


def test_a_straight_sloping_trace_is_simply_flat():
    """No bulge above the baseline: a plain negative trace, no sweep caveat."""
    trace = [{"pressure": p, "admittance": round(1.0 + 0.15 * (p + 400) / 600, 4)}
             for p in range(-400, 201, 10)]
    typed = tympanometry.analyze(trace=trace, age_years=0.1,
                                 probe_hz=1000)["tympanogram"]
    assert typed["type"] == "1k-no-peak" and "provisional" not in typed


def test_a_one_sample_ripple_in_a_trough_does_not_pass():
    """A positive and a negative peak count as positive (BSA 2024 §11.2), but
    a 0.08 mmho ripple is far below the 0.60 mmho admittance criterion."""
    trace = gaussian(-50, -0.5, 1.5, fwhm=120)
    for point in trace:
        if point["pressure"] == 150:
            point["admittance"] = round(point["admittance"] + 0.08, 4)
    typed = tympanometry.analyze(trace=trace, age_years=0.1,
                                 probe_hz=1000)["tympanogram"]
    assert typed["refer"] is True
    assert typed["type"] != "1k-peak"


@pytest.mark.parametrize("admittance,expected", [
    (0.03, "1k-no-peak"),   # within the 0.05 measurability floor
    (0.06, "1k-low-peak"),
    (0.1, "1k-low-peak"),
    (0.2, "1k-low-peak"),
    (0.39, "1k-low-peak"),  # Kei 2003 +200-tail P5: still below Margolis
    (0.59, "1k-low-peak"),
    (0.6, "1k-peak"),       # Margolis 2003 P5: passes
    (0.8, "1k-peak"),
])
def test_a_1000_hz_summary_value_is_judged_against_the_newborn_criterion(
        admittance, expected):
    typed = tympanometry.analyze(peak_pressure=0, compliance=admittance, ecv=0.5,
                                 age_years=0.25, probe_hz=1000)["tympanogram"]
    assert typed["type"] == expected
    assert typed["refer"] is (expected != "1k-peak")
    assert typed["suggests_conductive"] is (expected != "1k-peak")
    if expected != "1k-no-peak":
        # A summary value never shows the shape, nor the instrument's tail.
        assert typed["provisional"] is True
    if expected == "1k-low-peak":
        assert any("+200" in c and "Kei" in c for c in typed["caveats"])


@pytest.mark.parametrize("height,expected", [
    (0.03, "1k-no-peak"), (0.3, "1k-low-peak"), (0.9, "1k-peak")])
def test_1000_hz_trace_and_summary_values_agree(height, expected):
    """On a level baseline the -400 and +200 tails are equal, so a peak of
    ``height`` reads the same from either path."""
    trace = tympanometry.analyze(trace=gaussian(0, height, 1.0), age_years=0.1,
                                 probe_hz=1000)["tympanogram"]
    summary = tympanometry.analyze(peak_pressure=0, compliance=height, ecv=1.0,
                                   age_years=0.1, probe_hz=1000)["tympanogram"]
    assert trace["type"] == summary["type"] == expected


# ================================= B1-3  226 Hz under 6 months is refused ===

def test_a_226_hz_infant_trace_gets_no_type_no_norms_and_no_volume_verdict():
    """Tail 0.2 ml would read 'cerumen' on child norms; no norm applies here."""
    result = tympanometry.analyze(trace=gaussian(0, 0.8, 0.2), age_years=0.25,
                                  probe_hz=226)
    assert result["tympanogram"] is None
    assert result["probe_mode"] == "infant_low_probe"
    assert all(v is None for v in result["within_normal"].values())
    assert not any("cerumen" in f.lower() for f in result["flags"])
    assert not any(line.startswith("Type ") for line in result["interpretation"])
    assert result["curve"]["normative"]["applicable"] is False


def test_a_226_hz_infant_summary_entry_is_refused_too():
    result = tympanometry.analyze(peak_pressure=0, compliance=0.6, ecv=0.5,
                                  age_years=0.3, probe_hz=226)
    assert result["tympanogram"] is None and result["infant_warning"]


def test_the_battery_refuses_an_infant_tympanogram_with_no_probe_recorded():
    """The battery does not record the probe; it cannot assume 1000 Hz."""
    assert classify_tympanogram(0, 0.8, 0.5, age_years=0.25) is None
    assert classify_tympanogram(0, 0.8, 0.5, age_years=0.5)["type"] == "A"


def test_six_to_nine_months_at_226_hz_is_typed_with_a_probe_caution():
    result = tympanometry.analyze(trace=gaussian(0, 0.8, 0.6), age_years=0.6,
                                  probe_hz=226)
    assert result["tympanogram"]["type"] == "A"
    assert result["infant_warning"] is None
    assert any("1000 Hz" in f for f in result["flags"])


def test_an_unsupported_probe_is_not_typed_against_226_hz_norms():
    result = tympanometry.analyze(trace=gaussian(0, 0.8, 1.0), age_years=30,
                                  probe_hz=678)
    assert result["tympanogram"] is None
    assert result["not_typed"]


# ================================== B1-4  missing pressure is not "flat" ====

def test_a_peak_without_its_pressure_is_indeterminate_not_type_b():
    assert tympanometry.classify(None, 0.8, 1.2, age_years=30) is None
    result = tympanometry.analyze(peak_pressure=None, compliance=0.8, ecv=1.2,
                                  age_years=30)
    assert result["tympanogram"] is None
    assert "peak pressure was not recorded" in result["not_typed"].lower()
    assert not any(line.startswith("Type B") for line in result["interpretation"])
    assert "not flat (not Type B)" in result["not_typed"]


def test_what_needs_no_pressure_is_still_typed():
    # Flat has no peak pressure by definition; Add is decided on height alone.
    assert tympanometry.classify(None, 0.1, 1.2, age_years=30)["type"] == "B"
    assert tympanometry.classify(None, 3.5, 1.2, age_years=30)["type"] == "Add"


def test_a_pressure_without_an_admittance_is_indeterminate_not_type_a():
    assert tympanometry.classify(-50, None, 1.2, age_years=30) is None


def test_the_battery_does_not_report_type_b_for_a_missing_pressure():
    body = {"patient": {"name": "T", "age": 30, "sex": "female"},
            "right": {"ac": {str(f): 20 for f in (250, 500, 1000, 2000, 4000, 8000)},
                      "tymp_pressure": None, "tymp_compliance": 0.8, "tymp_ecv": 1.2},
            "left": {"ac": {str(f): 20 for f in (250, 500, 1000, 2000, 4000, 8000)}}}
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 200, r.text
    imm = r.json()["immittance"]["right"]
    assert imm is None or imm["tympanogram"] is None


# ============================== B1-5  the gradient cut-off is labelled ======

def test_the_gradient_cut_off_is_labelled_a_heuristic_where_it_is_applied():
    result = tympanometry.analyze(trace=gaussian(-40, 0.5, 1.0, fwhm=230),
                                  age_years=30)
    assert result["curve"]["gradient"] < tympanometry.GRADIENT_NORMAL_MIN
    assert any("heuristic" in f for f in result["flags"] if "gradient" in f.lower())
    assert any("heuristic" in line for line in result["interpretation"]
               if "gradient" in line.lower())
    assert "heuristic" in result["curve"]["normative"]["gradient_basis"]
    # A heuristic never changes the type.
    assert result["tympanogram"]["type"] == "A"


# ========================================= B1-6  BOA head-turn by age =======

def test_a_rudimentary_head_turn_before_four_months_is_age_appropriate():
    result = boa.analyze_boa(3.5, responses=["head_turn"], observers=2)
    assert "response_beyond_age" not in result["flags"]
    assert result["age_appropriate_responses"] is True
    assert any("rudimentary" in f for f in result["findings"])


def test_a_head_turn_before_six_weeks_is_questioned():
    result = boa.analyze_boa(1, responses=["head_turn"], observers=2)
    assert "response_beyond_age" in result["flags"]


@pytest.mark.parametrize("age,flagged", [(2, True), (3.9, True), (4, False), (5, False)])
def test_localisation_is_questioned_only_before_four_months(age, flagged):
    result = boa.analyze_boa(age, responses=["localisation"], observers=2)
    assert ("response_beyond_age" in result["flags"]) is flagged


def test_the_head_turn_flag_follows_the_bands_it_is_judged_against():
    """The behaviour list a clinician reads and the flag cannot disagree."""
    start = boa.LOCALISING_FROM_MONTHS["head_turn"]
    first = boa.age_band(start)
    before = boa.age_band(start - 0.1)
    assert any("head turn" in b.lower() for b in first["expected"])
    assert not any("head turn" in b.lower() for b in before["expected"])
    lateral = boa.age_band(boa.LOCALISING_FROM_MONTHS["localisation"])
    assert any("laterally" in b.lower() for b in lateral["expected"])


# ======================================= B1-7  BOA level reference ==========

def test_every_boa_result_states_that_its_reference_level_is_unverified():
    result = boa.analyze_boa(3, observed_level_db_spl=70, observers=2)
    assert "dB HL" in result["unit_note"] and "dB SPL" in result["unit_note"]
    assert boa.boa_reference()["unit_note"] == result["unit_note"]
    assert client.get("/api/boa/reference").json()["unit_note"] == result["unit_note"]


def test_the_on_screen_caveat_does_not_assert_an_unverified_reference():
    """The caveat is the text the BOA panel always renders. It may not state
    '78 dB SPL' (or a dB distance derived from it) as fact."""
    caveat = boa.analyze_boa(1, observers=2)["caveat"]
    assert "78 dB SPL" not in caveat and "75 dB" not in caveat
    assert "unverified" in caveat
    assert "not thresholds" in caveat


def test_a_one_month_old_is_one_month_not_one_months():
    findings = boa.analyze_boa(1, responses=["head_turn"], observers=2)["findings"]
    assert any("Recorded at 1 month," in f for f in findings)
    assert not any("1 months" in f for f in findings)


# ================= unrecorded points: off the scale, a lost apex, a dropout ==

def falling_line():
    """1.5 mmho at -400 falling straight to 1.0 at +200: every point lies on
    the line joining the tails, so BSA (2024) §11.2 finds no positive peak."""
    return [{"pressure": p, "admittance": round(1.5 - 0.5 * (p + 400) / 600, 4)}
            for p in range(-400, 201, 10)]


@pytest.mark.parametrize("missing_at", [0, -200, 100])
def test_a_dropped_sample_never_turns_a_1000_hz_trace_without_a_peak_into_a_pass(
        missing_at):
    trace = falling_line()
    for point in trace:
        if point["pressure"] == missing_at:
            point["admittance"] = None
    result = client.post(TYMP, json={"age_years": 0.1, "probe_hz": 1000,
                                     "trace": trace}).json()
    typed = result["tympanogram"]
    assert typed["type"] == "1k-no-peak"
    assert typed["refer"] is True and typed["provisional"] is True
    assert "consistent with normal" not in typed["interpretation"]
    assert result["curve"]["off_scale"] is False
    assert result["curve"]["gap"] == "dropout"
    # Its highest value is 1.5 mmho: nothing exceeded a 4 mmho ceiling.
    assert not any("instrument ceiling" in f for f in result["flags"])


def test_a_point_marked_off_scale_is_read_as_unrecorded_not_as_a_peak():
    trace = falling_line()
    trace[20]["off_scale"] = True          # -200 daPa, value 1.333 kept
    typed = client.post(TYMP, json={"age_years": 0.1, "probe_hz": 1000,
                                    "trace": trace}).json()["tympanogram"]
    assert typed["type"] == "1k-no-peak" and typed["refer"] is True
    assert typed["provisional"] is True


def test_a_trough_with_a_dropout_still_refers():
    trace = gaussian(-50, -0.5, 1.5, fwhm=120)
    trace[30]["admittance"] = None
    typed = tympanometry.analyze(trace=trace, age_years=0.1,
                                 probe_hz=1000)["tympanogram"]
    assert typed["type"] == "1k-no-peak" and typed["refer"] is True


def normal_226(missing_at):
    """Type A: 0.8 mmho at -10 daPa over a 1.0 ml canal, one sample unrecorded."""
    trace = gaussian(-10, 0.8, 1.0)
    for point in trace:
        if point["pressure"] == missing_at:
            point["admittance"] = None
    return trace


def test_a_dropout_far_from_a_normal_peak_is_not_type_add():
    """-350 daPa sits on the flat tail: the trace does not climb toward it."""
    result = tympanometry.analyze(trace=normal_226(-350), age_years=30)
    assert result["tympanogram"] is None
    assert result["curve"]["off_scale"] is False
    assert result["curve"]["gap"] == "dropout"
    assert "gap" in result["not_typed"].lower()
    assert not any(line.startswith("Type Add") for line in result["interpretation"])


def test_a_dropped_apex_sample_on_a_normal_peak_is_not_type_add():
    """Beside the missing -10 daPa sample the peak stands 0.8 *
    exp(-10^2 / 2(90/2.355)^2) = 0.77 mmho above the tail and is rounding
    over: nowhere near the 3.0 mmho that makes a peak Add. The apex was lost,
    not driven off the scale."""
    result = tympanometry.analyze(trace=normal_226(-10), age_years=30)
    assert result["tympanogram"] is None
    assert result["curve"]["off_scale"] is False
    assert result["curve"]["gap"] == "apex"
    assert "not recorded" in result["not_typed"]
    assert result["measurements"]["static_compliance"] is None


def test_a_lost_apex_on_a_deep_closed_peak_is_not_typed_add():
    """Ad: 2.4 mmho over 0.9 ml. Beside the missing apex sample the limbs
    stand 2.4 * exp(-10^2 / 2(90/2.355)^2) = 2.32 mmho and are rounding over,
    so they cannot be shown to reach 3.0."""
    trace = gaussian(-10, 2.4, 0.9)
    for point in trace:
        if point["pressure"] == -10:
            point["admittance"] = None
    result = tympanometry.analyze(trace=trace, age_years=30)
    assert result["tympanogram"] is None
    assert result["curve"]["gap"] == "apex"


def test_the_off_scale_example_trace_is_still_type_add():
    """The Immittance page's 'Off-scale (Add)' preset: 7.2 mmho over 0.9 ml,
    fwhm 95, cut at a 4 mmho ceiling. The limbs are recorded up to 60 daPa
    from the centre, where they stand 7.2 * exp(-60^2 / 2(95/2.355)^2) = 2.38
    mmho above the tail and still steepening (0.078 mmho/daPa over the last
    step against 0.059 over the one before). 2.38 + 1.5 * 0.078 * 10 = 3.56
    >= 3.0 by the first unrecorded point."""
    sigma = 95 / 2.355
    trace = []
    for p in range(-400, 201, 10):
        value = 0.9 + 7.2 * math.exp(-((p + 10) ** 2) / (2 * sigma ** 2))
        trace.append({"pressure": p, "admittance": None, "off_scale": True}
                     if value > 4 else {"pressure": p, "admittance": round(value, 4)})
    result = client.post(TYMP, json={"age_years": 30, "trace": trace}).json()
    assert result["tympanogram"]["type"] == "Add"
    assert result["curve"]["gap"] == "off_scale"


# ========================= 1000 Hz: sweep range, artefact, admittance range ==

@pytest.mark.parametrize("hi", [0, 100])
def test_a_1000_hz_sweep_that_stops_short_of_plus_200_is_not_a_clean_pass(hi):
    """BSA (2024) §10.2: the range should be at least +200 to -400 daPa."""
    result = tympanometry.analyze(trace=gaussian(-20, 1.0, 0.8, hi=hi),
                                  age_years=0.1, probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["provisional"] is True
    assert any("+200" in c and "§10.2" in c for c in typed["caveats"])
    assert any("+200" in f for f in result["flags"])
    assert "consistent with normal" not in typed["interpretation"]


def test_a_one_sample_spike_on_a_rising_trace_is_not_a_main_peak():
    """A straight 0.5 -> 1.5 mmho ramp with one sample at +150 raised 0.06
    and its neighbours lowered 0.04 — a movement artefact (BSA 2024 §10.2).
    Read sample by sample it is a local maximum 0.06 above the baseline and
    0.98 above the -400 tail, which would pass; it spans one 10 daPa sample
    and is not a tympanometric peak."""
    trace = [{"pressure": p, "admittance": round(0.5 + (p + 400) / 600, 4)}
             for p in range(-400, 201, 10)]
    for point in trace:
        if point["pressure"] == 150:
            point["admittance"] = round(point["admittance"] + 0.06, 4)
        elif point["pressure"] in (140, 160):
            point["admittance"] = round(point["admittance"] - 0.04, 4)
    typed = tympanometry.analyze(trace=trace, age_years=0.1,
                                 probe_hz=1000)["tympanogram"]
    assert typed["type"] == "1k-no-peak" and typed["refer"] is True


def test_a_narrow_real_1000_hz_peak_still_passes():
    """fwhm 50 daPa, 0.9 mmho: averaging three samples lowers it by a few
    percent; it remains far above the baseline and 0.9 >= 0.6 re -400."""
    result = tympanometry.analyze(trace=gaussian(-40, 0.9, 1.0, fwhm=50),
                                  age_years=0.1, probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["type"] == "1k-peak" and "provisional" not in typed
    assert typed["static_admittance"] == pytest.approx(0.9, abs=0.01)


def test_a_1000_hz_peak_above_the_newborn_95th_percentile_is_not_called_normal():
    """4.6 mmho re the -400 tail > 4.3, the Margolis (2003) 95th percentile;
    AAA (2020) I.ii.b counts hyper-mobility as abnormal."""
    typed = tympanometry.analyze(trace=gaussian(-20, 4.6, 0.8), age_years=0.1,
                                 probe_hz=1000)["tympanogram"]
    assert typed["type"] == "1k-peak"
    assert typed["provisional"] is True
    assert "within the newborn norms" not in typed["interpretation"]
    assert any("95th percentile" in c for c in typed["caveats"])


def test_an_unrecorded_1000_hz_apex_is_read_as_a_lower_bound():
    """1.0 mmho at -20 daPa over a level 0.8 tail, -30 to -10 unrecorded.
    The recorded points beside the gap (-40 and 0) stand 1.0 * exp(-20^2 /
    2(90/2.355)^2) = 0.872 above the -400 tail, which already meets 0.6; the
    apex can only be higher. Still provisional: the peak was not recorded."""
    trace = gaussian(-20, 1.0, 0.8)
    for point in trace:
        if -30 <= point["pressure"] <= -10:
            point["admittance"] = None
    result = tympanometry.analyze(trace=trace, age_years=0.1, probe_hz=1000)
    typed = result["tympanogram"]
    assert typed["type"] == "1k-peak" and typed["refer"] is False
    assert typed["provisional"] is True
    assert typed["static_admittance"] == pytest.approx(0.872, abs=0.005)
    assert typed["static_admittance_is_lower_bound"] is True
    assert result["curve"]["off_scale"] is False and result["curve"]["gap"] == "apex"
    assert "lower bound" in result["measurements"]["static_compliance_reference"]


def test_an_unrecorded_apex_below_the_criterion_is_not_called_low_as_fact():
    """0.5 mmho peak, apex unrecorded: beside the gap 0.5 * 0.872 = 0.436 <
    0.6, so it cannot pass as recorded, but the apex itself is unknown."""
    trace = gaussian(-20, 0.5, 0.8)
    for point in trace:
        if -30 <= point["pressure"] <= -10:
            point["admittance"] = None
    typed = tympanometry.analyze(trace=trace, age_years=0.1,
                                 probe_hz=1000)["tympanogram"]
    assert typed["type"] == "1k-low-peak" and typed["refer"] is True
    assert typed["provisional"] is True
    assert "apex itself was not recorded" in typed["interpretation"]


def test_a_1000_hz_trace_reports_no_226_hz_volume_or_shape_numbers():
    """BSA (2024) §11.2: ear-canal volume is disregarded at 1000 Hz, and the
    +200 daPa admittance in mmho is not a volume at that probe tone."""
    measurements = tympanometry.analyze(trace=ramp_with_bump(0.333), age_years=0.1,
                                        probe_hz=1000)["measurements"]
    assert measurements["ecv"] is None
    assert measurements["gradient"] is None and measurements["width"] is None
