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
    assert {t["type"] for t in tymp["types"]} == {"A", "As", "Ad", "B", "C"}
    oae = client.get("/api/oae/reference").json()
    assert {p["key"] for p in oae["protocols"]} == set(dpoae.PROTOCOLS)
    assert set(oae["cochlear_regions"]) >= set(str(f) for f in dpoae.DP_FREQS) or \
        set(int(k) for k in oae["cochlear_regions"]) >= set(dpoae.DP_FREQS)
