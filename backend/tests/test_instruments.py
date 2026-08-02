"""Tympanometry curves and DP-grams as standalone instruments."""
import math

import pytest
from fastapi.testclient import TestClient

from app.clinical import dpoae, tympanometry
from app.main import app

client = TestClient(app)


def gaussian_trace(peak_pressure, height, tail=0.7, width=90, step=10):
    """A realistic tympanogram: Gaussian peak on a flat canal-volume tail."""
    sigma = width / 2.355
    return [{"pressure": p,
             "admittance": round(tail + height * math.exp(
                 -((p - peak_pressure) ** 2) / (2 * sigma ** 2)), 4)}
            for p in range(-400, 201, step)]


# ------------------------------------------------------ curve analysis ----

def test_peak_pressure_is_recovered_from_the_trace():
    result = tympanometry.analyze_trace(gaussian_trace(-150, 0.8))
    assert result["peak"]["pressure"] == pytest.approx(-150, abs=10)


def test_compliance_is_measured_above_the_tail_not_absolutely():
    """Static compliance is peak height minus canal volume, not raw height."""
    result = tympanometry.analyze_trace(gaussian_trace(0, 0.8, tail=1.4))
    assert result["ecv"] == pytest.approx(1.4, abs=0.05)
    assert result["peak"]["admittance"] == pytest.approx(0.8, abs=0.05)
    assert result["peak"]["raw_admittance"] == pytest.approx(2.2, abs=0.05)


def test_tympanometric_width_matches_the_curve_it_was_drawn_from():
    result = tympanometry.analyze_trace(gaussian_trace(0, 0.9, width=100))
    assert result["width"] == pytest.approx(100, abs=8)


def test_width_is_none_when_there_is_no_peak_to_measure():
    flat = [{"pressure": p, "admittance": 0.75} for p in range(-400, 201, 10)]
    assert tympanometry.analyze_trace(flat)["width"] is None


def test_a_broad_peak_is_flagged_even_when_its_height_is_normal():
    """The gradient catches early effusion that peak height alone misses."""
    result = tympanometry.analyze(trace=gaussian_trace(-40, 0.5, width=210),
                                  age_years=30)
    assert result["tympanogram"]["type"] == "A"
    assert result["within_normal"]["compliance"] is True
    assert result["within_normal"]["width"] is False
    assert any("width" in f.lower() for f in result["flags"])


def test_large_canal_volume_is_flagged_as_a_probable_perforation():
    result = tympanometry.analyze(trace=gaussian_trace(0, 0.02, tail=2.6),
                                  age_years=30)
    assert result["tympanogram"]["type"] == "B"
    assert result["tympanogram"]["ecv_flag"] == "large"
    assert any("volume" in f.lower() for f in result["flags"])


def test_flat_trace_at_normal_volume_reads_as_effusion():
    result = tympanometry.analyze(trace=gaussian_trace(0, 0.02, tail=1.0),
                                  age_years=30)
    assert result["tympanogram"]["type"] == "B"
    assert result["tympanogram"]["ecv_flag"] == "normal"
    assert "effusion" in result["tympanogram"]["interpretation"].lower()


def test_peak_at_the_edge_of_the_sweep_is_flagged_not_typed_silently():
    result = tympanometry.analyze(trace=gaussian_trace(-400, 0.6), age_years=30)
    assert any("sweep" in f.lower() for f in result["flags"])


def test_too_few_points_is_not_a_trace():
    assert tympanometry.analyze_trace([{"pressure": 0, "admittance": 1.0}]) is None


# --------------------------------------------------------- age norms ------

def test_children_have_a_wider_normal_gradient_and_smaller_canal():
    child, adult = tympanometry.normative(5), tympanometry.normative(30)
    assert child["width"][1] > adult["width"][1]
    assert child["ecv"][1] < adult["ecv"][1]


def test_same_volume_is_normal_for_an_adult_and_large_for_a_child():
    trace = gaussian_trace(0, 0.6, tail=1.6)
    assert not tympanometry.analyze(trace=trace, age_years=30)["flags"]
    assert tympanometry.analyze(trace=trace, age_years=4)["flags"]


# ------------------------------------------------------- probe tone -------

def test_226_hz_probe_is_refused_for_a_young_infant():
    result = tympanometry.analyze(trace=gaussian_trace(0, 0.8),
                                  age_years=0.25, probe_hz=226)
    assert result["infant_warning"]
    assert "1000 Hz" in result["infant_warning"]
    assert result["tympanogram"]["provisional"] is True


def test_1000_hz_probe_is_accepted_for_the_same_infant():
    result = tympanometry.analyze(trace=gaussian_trace(0, 0.8),
                                  age_years=0.25, probe_hz=1000)
    assert result["infant_warning"] is None
    assert "provisional" not in result["tympanogram"]


# ------------------------------------------------------ synthesis ---------

def test_summary_only_entry_still_produces_a_drawable_curve():
    result = tympanometry.analyze(peak_pressure=-220, compliance=0.5, ecv=1.0)
    assert result["curve"]["source"] == "modelled"
    assert len(result["curve"]["points"]) > 20
    assert result["tympanogram"]["type"] == "C"


def test_modelled_curves_are_labelled_as_modelled_in_the_interpretation():
    result = tympanometry.analyze(peak_pressure=0, compliance=0.7, ecv=1.0)
    assert any("modelled" in line for line in result["interpretation"])


def test_a_synthesized_curve_reads_back_as_the_numbers_that_made_it():
    """Round-trip: the drawing must not misrepresent the values it came from."""
    points = tympanometry.synthesize_trace(-120, 0.6, ecv=1.1, width=95)
    back = tympanometry.analyze_trace(points)
    assert back["peak"]["pressure"] == pytest.approx(-120, abs=10)
    assert back["peak"]["admittance"] == pytest.approx(0.6, abs=0.05)
    assert back["ecv"] == pytest.approx(1.1, abs=0.05)


# ----------------------------------------------------------- reflexes -----

def test_reflexes_present_with_a_flat_trace_are_called_out():
    result = tympanometry.analyze(
        trace=gaussian_trace(0, 0.02, tail=1.0),
        reflexes={"ipsi": 85, "contra": 90}, pta=30, age_years=30)
    assert any("reflexes are present despite" in line.lower()
               for line in result["interpretation"])


# ============================== OAE / DP-gram =============================

def dp(freqs, amplitude, noise=-12.0):
    return [{"freq": f, "amplitude": amplitude, "noise_floor": noise}
            for f in freqs]


def test_snr_criterion_is_inclusive_at_the_boundary():
    at = dpoae.dp_gram([{"freq": 2000, "amplitude": -6.0, "noise_floor": -12.0}])
    below = dpoae.dp_gram([{"freq": 2000, "amplitude": -6.1, "noise_floor": -12.0}])
    assert at["points"][0]["present"] is True     # exactly 6.0 dB
    assert below["points"][0]["present"] is False


def test_newborn_protocol_requires_all_three_frequencies():
    two_of_three = dp([2000, 3000], 10) + dp([4000], -20)
    assert dpoae.dp_gram(two_of_three, "newborn")["outcome"] == "refer"
    assert dpoae.dp_gram(dp([2000, 3000, 4000], 10), "newborn")["outcome"] == "pass"


def test_general_screening_tolerates_one_failure():
    mixed = dp([2000, 3000], 10) + dp([4000], -20)
    assert dpoae.dp_gram(mixed, "screening")["outcome"] == "pass"


def test_missing_protocol_frequency_is_incomplete_not_a_pass():
    result = dpoae.dp_gram(dp([2000, 3000], 10), "newborn")
    assert result["outcome"] == "incomplete"
    assert result["missing_freqs"] == [4000]


def test_high_noise_floor_invalidates_rather_than_fails():
    noisy = dp([2000, 3000, 4000], 2.0, noise=18.0)
    result = dpoae.dp_gram(noisy, "newborn")
    assert result["invalid_freqs"] == [2000, 3000, 4000]
    assert result["referred_freqs"] == []
    assert result["outcome"] == "incomplete"


def test_absent_emissions_above_the_ceiling_carry_no_information():
    """A dead emission at a 70 dB threshold is expected, not new evidence."""
    absent = dp([2000, 3000, 4000], -20)
    thresholds = {2000: 70, 3000: 75, 4000: 80}
    result = dpoae.dp_gram(absent, "screening", thresholds)
    assert result["uninformative_freqs"] == [2000, 3000, 4000]
    assert result["referred_freqs"] == []


def test_the_same_absence_at_normal_thresholds_is_preclinical_damage():
    result = dpoae.analyze(points=dp([2000, 3000, 4000], -20),
                           protocol="screening",
                           ac_numeric={2000: 10, 3000: 10, 4000: 10})
    assert result["referred_freqs"] == [2000, 3000, 4000]
    assert len(result["preclinical_damage"]) == 3


# ------------------------------------------------- cochlear profile -------

def test_high_frequency_loss_maps_to_the_basal_turn():
    result = dpoae.analyze(points=dp([1000, 2000], 10) + dp([4000, 6000], -20),
                           protocol="diagnostic")
    assert result["cochlear_profile"]["pattern"] == "basal"
    assert any("basal" in r for r in result["cochlear_profile"]["regions"])


def test_intact_emissions_report_an_intact_cochlea():
    result = dpoae.analyze(points=dp(dpoae.DP_FREQS, 12), protocol="diagnostic")
    assert result["cochlear_profile"]["pattern"] == "intact"


def test_a_notch_with_recovery_above_is_named_as_a_notch():
    points = dp([1000, 2000], 10) + dp([4000], -20) + dp([8000], 10)
    result = dpoae.analyze(points=points, protocol="diagnostic")
    assert result["cochlear_profile"]["pattern"] == "notch"


def test_no_points_reports_unavailable_rather_than_failing():
    assert dpoae.analyze(points=[])["available"] is False


# --------------------------------------------------------- endpoints ------

def test_tympanometry_endpoint_round_trips_a_trace():
    body = {"ear": "right", "age_years": 30, "trace": gaussian_trace(-30, 0.8)}
    result = client.post("/api/tympanometry/analyze", json=body).json()
    assert result["tympanogram"]["type"] == "A"
    assert result["curve"]["source"] == "measured"


def test_oae_endpoint_reports_the_protocol_it_judged_against():
    body = {"protocol": "occupational", "points": dp([3000, 4000, 6000], -20),
            "ac": {"3000": 10, "4000": 15, "6000": 15}}
    result = client.post("/api/oae/analyze", json=body).json()
    assert result["outcome"] == "refer"
    assert result["protocol"]["key"] == "occupational"
    assert result["preclinical_damage"]


def test_reference_endpoints_describe_every_type_and_protocol():
    tymp = client.get("/api/tympanometry/reference").json()
    assert {t["type"] for t in tymp["types"]} == {"A", "As", "Ad", "Add", "B", "C", "D", "E"}
    # Every type ships a generated curve, and each curve re-classifies as
    # itself — the picture and the label cannot drift apart.
    assert {c["type"] for c in tymp["curves"]} == {t["type"] for t in tymp["types"]}
    oae = client.get("/api/oae/reference").json()
    assert {p["key"] for p in oae["protocols"]} == set(dpoae.PROTOCOLS)
    assert set(oae["cochlear_regions"]) >= set(str(f) for f in dpoae.DP_FREQS) or \
        set(int(k) for k in oae["cochlear_regions"]) >= set(dpoae.DP_FREQS)


# ================= the eight-type classification (immittance reference) ====

@pytest.mark.parametrize("type_key,compliance", [
    ("As", 0.30), ("A", 0.80), ("Ad", 2.40), ("Add", 3.60),
])
def test_peak_height_selects_the_right_type_for_an_adult(type_key, compliance):
    result = tympanometry.analyze(trace=gaussian_trace(-10, compliance, tail=0.9),
                                  age_years=30)
    assert result["tympanogram"]["type"] == type_key


def test_add_is_separated_from_ad_by_running_off_the_scale():
    """Ad is a deep peak; Add is a disconnected ossicular chain."""
    deep = tympanometry.analyze(trace=gaussian_trace(-10, 2.4, tail=0.9),
                                age_years=30)["tympanogram"]
    off_scale = tympanometry.analyze(
        trace=gaussian_trace(-10, tympanometry.OFF_SCALE_ADMITTANCE + 0.5, tail=0.9),
        age_years=30)["tympanogram"]
    assert deep["type"] == "Ad" and off_scale["type"] == "Add"
    assert "Ossicular discontinuity" in off_scale["disorders"]


@pytest.mark.parametrize("notch_width,expected", [(45, "D"), (110, "E")])
def test_a_notched_peak_is_type_d_or_e_by_its_width(notch_width, expected):
    trace = tympanometry.synthesize_trace(
        -10, 0.9 if expected == "D" else 2.3, ecv=0.9,
        width=70 if expected == "D" else 120,
        notched=True, notch_width=notch_width)
    result = tympanometry.analyze(trace=trace, age_years=30)
    assert result["tympanogram"]["type"] == expected
    assert result["curve"]["notch"]["notched"] is True


def test_a_notch_outranks_peak_depth():
    """Type D and E are notched by definition; Ad and Add are not."""
    trace = tympanometry.synthesize_trace(-10, 2.3, ecv=0.9, width=120,
                                          notched=True, notch_width=110)
    assert tympanometry.analyze(trace=trace, age_years=30)["tympanogram"]["type"] == "E"


def test_shallow_ripples_are_not_read_as_a_notch():
    result = tympanometry.analyze(trace=gaussian_trace(-10, 0.9), age_years=30)
    assert result["curve"]["notch"]["notched"] is False
    assert result["tympanogram"]["type"] == "A"


@pytest.mark.parametrize("ecv,band,expect_word", [
    (0.35, "small", "cerumen"), (1.0, "normal", "effusion"), (2.6, "large", "perforation"),
])
def test_type_b_splits_three_ways_on_canal_volume(ecv, band, expect_word):
    """Small volume is an artefact, not middle-ear disease — the case a
    two-way split silently reports as fluid."""
    result = tympanometry.analyze(trace=gaussian_trace(0, 0.02, tail=ecv),
                                  age_years=30)
    typed = result["tympanogram"]
    assert typed["type"] == "B" and typed["ecv_flag"] == band
    assert expect_word in typed["interpretation"].lower()


def test_the_flat_to_shallow_boundary_is_flagged_rather_than_hidden():
    """The reference's Type B and Type As bands touch at 0.2 mmho."""
    flat = tympanometry.classify(-10, 0.19, 1.0, age_years=30)
    shallow = tympanometry.classify(-10, 0.20, 1.0, age_years=30)
    assert flat["type"] == "B" and shallow["type"] == "As"
    assert flat["borderline"] and shallow["borderline"]


def test_children_have_their_own_compliance_band():
    """The bands differ at both ends, and the type follows the age.

    0.36 mmho is below the adult floor (0.37) but inside the child band; 1.40
    is inside the adult ceiling (1.66) but above the child one (1.25).
    """
    shallow = gaussian_trace(-10, 0.36, tail=0.7)
    assert tympanometry.analyze(trace=shallow, age_years=30)["tympanogram"]["type"] == "As"
    assert tympanometry.analyze(trace=shallow, age_years=5)["tympanogram"]["type"] == "A"

    deep = gaussian_trace(-10, 1.40, tail=0.7)
    assert tympanometry.analyze(trace=deep, age_years=30)["tympanogram"]["type"] == "A"
    assert tympanometry.analyze(trace=deep, age_years=5)["tympanogram"]["type"] == "Ad"


def test_gradient_falls_as_the_peak_broadens():
    sharp = tympanometry.analyze_trace(gaussian_trace(0, 0.9, width=80))
    broad = tympanometry.analyze_trace(gaussian_trace(0, 0.9, width=220))
    assert sharp["gradient"] > tympanometry.GRADIENT_NORMAL_MIN
    assert broad["gradient"] < tympanometry.GRADIENT_NORMAL_MIN


def test_every_reference_curve_reclassifies_as_its_own_type():
    """The generated pictures and their labels cannot drift apart."""
    reference = tympanometry.reference_curves(30)
    assert len(reference["curves"]) == 8
    for entry in reference["curves"]:
        back = tympanometry.analyze(trace=entry["points"], age_years=30)
        assert back["tympanogram"]["type"] == entry["type"], entry["type"]


def test_a_small_canal_volume_is_flagged_as_an_artefact():
    result = tympanometry.analyze(trace=gaussian_trace(0, 0.02, tail=0.3),
                                  age_years=30)
    assert any("cerumen" in f.lower() or "blocked" in f.lower()
               for f in result["flags"])


def test_an_off_scale_trace_has_no_apex_and_is_type_add():
    """The limbs ascend and never meet — there is nothing to join at the top."""
    trace = tympanometry.synthesize_trace(
        -10, tympanometry.INSTRUMENT_CEILING_MMHO * 1.8, ecv=1.3, width=95,
        ceiling=tympanometry.INSTRUMENT_CEILING_MMHO)
    gaps = [p for p in trace if p["admittance"] is None]
    assert gaps, "the trace must leave the recordable range"
    assert all(p.get("off_scale") for p in gaps)

    result = tympanometry.analyze(trace=trace, age_years=30)
    assert result["tympanogram"]["type"] == "Add"
    assert result["tympanogram"]["off_scale"] is True
    # No apex means no apex-derived measurement.
    assert result["curve"]["off_scale"] is True
    assert result["curve"]["peak"]["admittance"] is None
    assert result["curve"]["gradient"] is None
    assert result["curve"]["width"] is None
    assert result["measurements"]["static_compliance"] is None


def test_the_off_scale_gap_survives_into_the_plotted_points():
    """Dropping the gap would let a chart draw a peak that was never recorded."""
    trace = tympanometry.synthesize_trace(
        -10, tympanometry.INSTRUMENT_CEILING_MMHO * 1.8, ecv=1.3, width=95,
        ceiling=tympanometry.INSTRUMENT_CEILING_MMHO)
    points = tympanometry.analyze_trace(trace, age_years=30)["points"]
    assert any(p["admittance"] is None for p in points)
    # Both limbs are still present, one either side of the gap.
    pressures = [p["pressure"] for p in points if p["admittance"] is None]
    below = [p for p in points if p["admittance"] is not None
             and p["pressure"] < min(pressures)]
    above = [p for p in points if p["admittance"] is not None
             and p["pressure"] > max(pressures)]
    assert below and above


def test_a_deep_but_closed_peak_stays_type_ad():
    """Ad closes below the ceiling; that contrast is the whole distinction."""
    trace = tympanometry.synthesize_trace(-10, 2.4, ecv=1.3, width=95,
                                          ceiling=tympanometry.INSTRUMENT_CEILING_MMHO)
    assert all(p["admittance"] is not None for p in trace)
    result = tympanometry.analyze(trace=trace, age_years=30)
    assert result["tympanogram"]["type"] == "Ad"
    assert result["curve"]["off_scale"] is False


def test_a_trace_recorded_with_an_explicit_gap_is_read_as_off_scale():
    """Real instruments mark the unmeasured region rather than omitting it."""
    trace = [{"pressure": p, "admittance": None if -60 <= p <= 40 else 1.0}
             for p in range(-400, 201, 10)]
    result = tympanometry.analyze(trace=trace, age_years=30)
    assert result["curve"]["off_scale"] is True
    assert result["tympanogram"]["type"] == "Add"


def test_the_off_scale_reference_curve_reports_no_compliance():
    reference = tympanometry.reference_curves(30)
    add = next(c for c in reference["curves"] if c["type"] == "Add")
    assert add["off_scale"] is True
    assert add["compliance"] is None
    assert any(p["admittance"] is None for p in add["points"])
    # Every other type still closes.
    assert not any(c["off_scale"] for c in reference["curves"] if c["type"] != "Add")


def test_the_endpoint_accepts_a_trace_with_an_off_scale_gap():
    """The one type defined by a gap must be submittable through the API."""
    trace = tympanometry.synthesize_trace(
        -10, tympanometry.INSTRUMENT_CEILING_MMHO * 1.8, ecv=1.3, width=95,
        ceiling=tympanometry.INSTRUMENT_CEILING_MMHO)
    response = client.post("/api/tympanometry/analyze",
                           json={"ear": "right", "age_years": 30, "trace": trace})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tympanogram"]["type"] == "Add"
    assert body["curve"]["off_scale"] is True
    assert any(p["admittance"] is None for p in body["curve"]["points"])


def test_no_apex_means_no_peak_pressure_either():
    """The pressure of a peak that was never reached is not a peak pressure."""
    trace = tympanometry.synthesize_trace(
        -10, tympanometry.INSTRUMENT_CEILING_MMHO * 1.8, ecv=1.3, width=95,
        ceiling=tympanometry.INSTRUMENT_CEILING_MMHO)
    result = tympanometry.analyze(trace=trace, age_years=30)
    assert result["curve"]["peak"]["pressure"] is None
    assert result["measurements"]["peak_pressure"] is None
    assert result["measurements"]["width"] is None
    assert result["measurements"]["gradient"] is None
    # And no shape flag pretends otherwise.
    assert not any("width" in f.lower() or "gradient" in f.lower()
                   for f in result["flags"] if "cannot be measured" not in f)
    assert result["tympanogram"]["type"] == "Add"


# ============ manual entry of the four printed values (ECV/PP/SC/GRAD) =====

@pytest.mark.parametrize("gradient", [0.15, 0.30, 0.575, 0.80])
def test_an_entered_gradient_shapes_the_curve_it_draws(gradient):
    """A curve drawn from GRAD 0.30 must measure back as 0.30.

    Otherwise the drawing would be a plausible shape rather than a picture of
    the number the clinician typed.
    """
    points = tympanometry.synthesize_trace(-20, 0.8, ecv=1.0, gradient=gradient)
    back = tympanometry.analyze_trace(points)
    assert back["gradient"] == pytest.approx(gradient, abs=0.01)


def test_width_and_gradient_are_inverses_where_the_sweep_allows_it():
    """Exact from 0.2 up, which is the whole clinically relevant range."""
    for gradient in (0.2, 0.25, 0.5, 0.9):
        width = tympanometry.width_from_gradient(gradient)
        points = tympanometry.synthesize_trace(0, 0.9, ecv=1.0, width=width)
        assert tympanometry.analyze_trace(points)["gradient"] == \
            pytest.approx(gradient, abs=0.01)


def test_a_very_low_gradient_drifts_upward_and_says_so():
    """A peak that broad has not returned to baseline by +200 daPa.

    The drift is one-directional and small enough that a gradient entered as
    abnormal still reads abnormal — which is the property that matters.
    """
    for gradient in (0.05, 0.10, 0.15):
        points = tympanometry.synthesize_trace(0, 0.9, ecv=1.0, gradient=gradient)
        read_back = tympanometry.analyze_trace(points)["gradient"]
        assert read_back >= gradient
        assert read_back < tympanometry.GRADIENT_NORMAL_MIN

    result = tympanometry.analyze(peak_pressure=-20, compliance=0.5, ecv=1.0,
                                  gradient=0.1, age_years=30)
    assert result["curve"]["gradient_note"]
    assert result["within_normal"]["gradient"] is False


def test_a_drawable_gradient_carries_no_such_caveat():
    result = tympanometry.analyze(peak_pressure=-20, compliance=0.85, ecv=1.0,
                                  gradient=0.55, age_years=30)
    assert result["curve"]["gradient_note"] is None


def test_an_invalid_gradient_falls_back_rather_than_failing():
    assert tympanometry.width_from_gradient(None) is None
    assert tympanometry.width_from_gradient(0) is None
    assert tympanometry.width_from_gradient(1) is None
    assert tympanometry.width_from_gradient(1.5) is None


def test_the_four_printed_values_produce_a_typed_result():
    result = tympanometry.analyze(peak_pressure=-25, compliance=0.45, ecv=1.1,
                                  gradient=0.14, age_years=30)
    assert result["tympanogram"]["type"] == "A"
    assert result["curve"]["source"] == "modelled"
    measured = result["measurements"]
    assert measured["ecv"] == 1.1
    assert measured["peak_pressure"] == -25
    assert measured["static_compliance"] == 0.45
    assert measured["gradient"] == 0.14


def test_a_manually_entered_low_gradient_is_judged_abnormal():
    """The rounded peak that peak height alone misses, entered by hand."""
    result = tympanometry.analyze(peak_pressure=-25, compliance=0.45, ecv=1.1,
                                  gradient=0.14, age_years=30)
    assert result["within_normal"]["gradient"] is False
    assert result["within_normal"]["compliance"] is True
    assert any("gradient" in line.lower() for line in result["interpretation"])


def test_a_manually_entered_normal_gradient_passes():
    result = tympanometry.analyze(peak_pressure=-20, compliance=0.85, ecv=1.0,
                                  gradient=0.55, age_years=30)
    assert result["within_normal"]["gradient"] is True
    assert result["tympanogram"]["type"] == "A"


def test_manual_entry_still_types_the_abnormal_cases():
    negative = tympanometry.analyze(peak_pressure=-220, compliance=0.6, ecv=1.0,
                                    gradient=0.5, age_years=30)
    shallow = tympanometry.analyze(peak_pressure=-10, compliance=0.25, ecv=1.0,
                                   gradient=0.5, age_years=30)
    assert negative["tympanogram"]["type"] == "C"
    assert shallow["tympanogram"]["type"] == "As"


def test_the_endpoint_accepts_the_four_values_without_a_trace():
    body = client.post("/api/tympanometry/analyze", json={
        "ear": "right", "age_years": 30,
        "ecv": 1.1, "peak_pressure": -25, "compliance": 0.45, "gradient": 0.14,
    })
    assert body.status_code == 200, body.text
    result = body.json()
    assert result["curve"]["source"] == "modelled"
    assert result["measurements"]["gradient"] == 0.14
    assert len(result["curve"]["points"]) > 20


def test_the_endpoint_rejects_a_gradient_outside_zero_to_one():
    assert client.post("/api/tympanometry/analyze",
                       json={"gradient": 1.4, "compliance": 0.5}).status_code == 422
