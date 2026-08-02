"""ABR, MLR, LLR and BOA — evoked potentials and behavioural observation."""
import pytest
from fastapi.testclient import TestClient

from app.clinical import aep, boa
from app.main import app

client = TestClient(app)


# =========================================================== ABR normative

@pytest.mark.parametrize("level,wave,sd2,sd3", [
    (70, "I", [1.48, 2.16], [1.31, 2.33]),
    (70, "III", [3.59, 4.11], [3.46, 4.24]),
    (70, "V", [5.32, 5.96], [5.16, 6.12]),
    (80, "I", [1.38, 1.86], [1.26, 1.98]),
    (80, "III", [3.52, 3.84], [3.44, 3.92]),
    (80, "V", [5.23, 5.71], [5.11, 5.83]),
])
def test_the_encoded_norms_reproduce_the_published_limits(level, wave, sd2, sd3):
    """Table 2-4 is derived from Table 2-3, so it checks the transcription."""
    mean, sd, _ = aep.ABR_NORMS[level]["waves"][wave]
    limits = aep._limits(mean, sd)
    assert limits["sd2"] == sd2
    assert limits["sd3"] == sd3


def test_wave_v_latency_lengthens_as_intensity_falls():
    """The reason an absolute latency without its intensity is meaningless."""
    levels = sorted(aep.ABR_NORMS)
    v = [aep.ABR_NORMS[l]["waves"]["V"][0] for l in levels]
    assert v == sorted(v, reverse=True)
    assert aep.ABR_NORMS[90]["waves"]["V"][0] < aep.ABR_NORMS[20]["waves"]["V"][0]


def test_early_waves_drop_out_of_the_norms_at_low_intensity():
    """Wave V survives to the lowest levels; Wave I does not."""
    assert "I" not in aep.ABR_NORMS[20]["waves"]
    assert "V" in aep.ABR_NORMS[20]["waves"]


# ================================================================ ABR runs

def normal_abr(level=80):
    row = aep.ABR_NORMS[level]["waves"]
    return {w: row[w][0] for w in ("I", "III", "V")}


def test_a_normal_run_sits_at_zero_standard_deviations():
    result = aep.analyze_abr(normal_abr(80), intensity=80,
                             latencies_include_delay=False)
    for entry in result["absolute"]:
        if entry["present"]:
            assert entry["z"] == pytest.approx(0, abs=0.01)
            assert entry["within_2sd"] is True
    assert result["flags"] == []


def test_the_insert_delay_is_removed_before_comparison():
    """Forgetting 0.9 ms turns every normal trace into a delayed one."""
    raw = {w: v + aep.INSERT_DELAY_MS for w, v in normal_abr(80).items()}
    corrected = aep.analyze_abr(raw, intensity=80, latencies_include_delay=True)
    uncorrected = aep.analyze_abr(raw, intensity=80, latencies_include_delay=False)
    assert corrected["insert_delay_removed"] is True
    assert all(e["within_2sd"] for e in corrected["absolute"] if e["present"])
    assert any(e["delayed"] for e in uncorrected["absolute"] if e["present"])


def test_the_comparison_row_follows_the_intensity_used():
    late = {"I": 2.43, "III": 4.60, "V": 6.19}     # normal at 50 dB nHL
    at_50 = aep.analyze_abr(late, intensity=50, latencies_include_delay=False)
    at_90 = aep.analyze_abr(late, intensity=90, latencies_include_delay=False)
    assert at_50["norm_row_db_nhl"] == 50
    assert all(e["within_2sd"] for e in at_50["absolute"] if e["present"])
    assert any(e["delayed"] for e in at_90["absolute"] if e["present"])


def test_interpeak_intervals_are_computed_from_corrected_latencies():
    result = aep.analyze_abr(normal_abr(80), intensity=80,
                             latencies_include_delay=False)
    intervals = {e["pair"]: e["value"] for e in result["interwave"] if e["present"]}
    assert intervals["I-III"] == pytest.approx(2.06, abs=0.01)
    assert intervals["III-V"] == pytest.approx(1.79, abs=0.01)
    assert intervals["I-V"] == pytest.approx(3.85, abs=0.01)


def test_a_prolonged_interval_reads_as_retrocochlear_not_conductive():
    """A conductive loss shifts everything; a neural lesion stretches it."""
    result = aep.analyze_abr({"I": 1.62, "III": 3.68, "V": 6.60}, intensity=80,
                             latencies_include_delay=False)
    assert "interpeak_prolonged" in result["flags"]
    assert any("retrocochlear" in f for f in result["findings"])


def test_a_uniform_shift_is_called_conductive_rather_than_neural():
    shift = 0.8
    shifted = {w: v + shift for w, v in normal_abr(80).items()}
    result = aep.analyze_abr(shifted, intensity=80, latencies_include_delay=False)
    assert "interpeak_prolonged" not in result["flags"]
    assert any("not of a neural lesion" in f for f in result["findings"])


def test_an_absent_wave_v_is_the_significant_absence():
    result = aep.analyze_abr({"I": 1.62, "III": 3.68}, intensity=80,
                             latencies_include_delay=False)
    assert "wave_v_absent" in result["flags"]


def test_a_missing_wave_i_at_low_intensity_is_unremarkable():
    """Wave I is not expected at 20 dB nHL, so its absence is not a finding."""
    result = aep.analyze_abr({"V": 7.52}, intensity=20,
                             latencies_include_delay=False)
    wave_i = next(e for e in result["absolute"] if e["wave"] == "I")
    assert wave_i["expected_at_this_level"] is False
    assert result["flags"] == []


def test_a_cochlear_microphonic_with_a_poor_abr_is_auditory_neuropathy():
    result = aep.analyze_abr({}, intensity=80, cm_present=True)
    assert "cochlear_microphonic_present" in result["flags"]
    assert any("auditory neuropathy" in f for f in result["findings"])


# ================================================== ABR asymmetry and threshold

def test_an_interaural_wave_v_difference_beyond_the_criterion_is_flagged():
    right = aep.analyze_abr({"V": 5.47}, 80, latencies_include_delay=False)
    left = aep.analyze_abr({"V": 6.10}, 80, latencies_include_delay=False)
    result = aep.abr_asymmetry(right, left)
    assert result["difference"] == pytest.approx(0.63, abs=0.01)
    assert result["significant"] is True
    assert result["poorer_ear"] == "left"


def test_a_small_interaural_difference_is_not_an_asymmetry():
    right = aep.analyze_abr({"V": 5.47}, 80, latencies_include_delay=False)
    left = aep.analyze_abr({"V": 5.67}, 80, latencies_include_delay=False)
    assert aep.abr_asymmetry(right, left)["significant"] is False


def test_asymmetry_needs_a_wave_v_in_both_ears():
    right = aep.analyze_abr({"V": 5.47}, 80, latencies_include_delay=False)
    absent = aep.analyze_abr({"I": 1.62}, 80, latencies_include_delay=False)
    assert aep.abr_asymmetry(right, absent) is None


def test_the_threshold_is_the_lowest_level_with_a_wave_v():
    series = [{"intensity": 80, "wave_v": 5.47}, {"intensity": 60, "wave_v": 5.88},
              {"intensity": 40, "wave_v": 6.65}, {"intensity": 20, "wave_v": None}]
    result = aep.abr_threshold(series)
    assert result["estimated_threshold"] == 40
    assert result["no_response"] is False
    assert "not a substitute" in result["message"]


def test_no_wave_v_at_any_level_is_reported_as_no_response():
    series = [{"intensity": 90, "wave_v": None}, {"intensity": 80, "wave_v": None}]
    result = aep.abr_threshold(series)
    assert result["no_response"] is True
    assert result["estimated_threshold"] is None
    assert "maximum output" in result["message"]


def test_an_empty_ladder_yields_nothing():
    assert aep.abr_threshold([]) is None


# ==================================================================== MLR

def test_a_normal_mlr_matches_no_abnormal_pattern():
    result = aep.analyze_mlr({"Na": 18, "Pa": 28, "Nb": 38, "Pb": 52},
                             amplitudes={"Na-Pa": 1.2})
    assert result["abnormal"] is False
    assert result["na_pa_interval"] == 10.0
    assert all(p["within_range"] for p in result["peaks"] if p["present"])


def test_every_peak_carries_its_generator():
    result = aep.analyze_mlr({"Na": 18, "Pa": 28, "Nb": 38, "Pb": 52})
    generators = {p["peak"]: p["generator"] for p in result["peaks"]}
    assert "Heschl" in generators["Pa"]
    assert "halam" in generators["Na"]


def test_all_peaks_delayed_is_a_diffuse_pattern_not_a_focal_one():
    result = aep.analyze_mlr({"Na": 22, "Pa": 38, "Nb": 48, "Pb": 62})
    keys = [p["key"] for p in result["patterns"]]
    assert "delayed_all" in keys and "delayed_pa" not in keys


def test_pa_delayed_alone_is_localised():
    result = aep.analyze_mlr({"Na": 18, "Pa": 38, "Nb": 38, "Pb": 52})
    keys = [p["key"] for p in result["patterns"]]
    assert "delayed_pa" in keys and "delayed_all" not in keys


def test_absent_na_is_reported_with_its_technical_causes():
    result = aep.analyze_mlr({"Pa": 28, "Nb": 38})
    pattern = next(p for p in result["patterns"] if p["key"] == "absent_na")
    assert any("impedance" in c or "variability" in c for c in pattern["causes"])


def test_a_small_na_pa_amplitude_is_flagged():
    result = aep.analyze_mlr({"Na": 18, "Pa": 28}, amplitudes={"Na-Pa": 0.2})
    assert "reduced_amplitude" in [p["key"] for p in result["patterns"]]


def test_an_interhemispheric_amplitude_ratio_is_an_asymmetry():
    result = aep.analyze_mlr({"Na": 18, "Pa": 28}, amplitudes={"Na-Pa": 1.2},
                             opposite_amplitudes={"Na-Pa": 0.4})
    assert "asymmetric" in [p["key"] for p in result["patterns"]]


def test_sedation_is_offered_as_an_explanation_for_delay():
    result = aep.analyze_mlr({"Na": 22, "Pa": 38, "Nb": 48, "Pb": 62}, sedated=True)
    assert any("Sedation" in f for f in result["findings"])


def test_a_missing_pa_is_a_technical_question_first():
    result = aep.analyze_mlr({"Na": 18, "Nb": 38})
    assert any("technical" in f for f in result["findings"])


# ==================================================================== LLR

def test_a_normal_adult_llr_raises_nothing():
    result = aep.analyze_llr({"P1": 52, "N1": 105, "P2": 180, "N2": 320},
                             amplitudes={"N1-P2": 9}, age_months=300)
    assert result["flags"] == []
    assert result["n1_p2_interval"] == 75.0


def test_the_p1_maturation_check_accepts_an_age_appropriate_toddler():
    """A prominent P1 near 120 ms at 18 months is normal, not delayed."""
    result = aep.analyze_llr({"P1": 118, "N1": 140, "P2": 195}, age_months=18)
    assert result["maturation"]["delayed"] is False
    assert result["maturation"]["expected"] == 120


def test_a_p1_that_stays_infantile_is_the_implant_biomarker():
    result = aep.analyze_llr({"P1": 160, "N1": 150, "P2": 200}, age_months=60)
    assert "cortical_maturation_delayed" in result["flags"]
    assert any("cochlear-implant" in f for f in result["findings"])


def test_p1_shortens_with_age_across_the_maturation_bands():
    typical = [aep.expected_p1_latency(m)["typical_ms"]
               for m in (6, 18, 48, 100, 200)]
    assert typical == sorted(typical, reverse=True)


def test_maturation_is_skipped_without_an_age():
    result = aep.analyze_llr({"P1": 160, "N1": 150}, age_months=None)
    assert result["maturation"] is None


def test_an_absent_n1_is_a_technical_question_first():
    result = aep.analyze_llr({"P1": 52, "P2": 180}, age_months=300)
    assert "n1_absent" in result["flags"]


def test_two_prolonged_cortical_peaks_read_as_slowed_processing():
    result = aep.analyze_llr({"P1": 52, "N1": 200, "P2": 260}, age_months=300)
    assert "cortical_delay" in result["flags"]


# ================================================================ battery

def test_a_normal_abr_under_an_abnormal_mlr_localises_the_problem():
    """Neither recording gives this conclusion alone."""
    result = aep.aep_battery(
        abr=aep.analyze_abr(normal_abr(80), 80, latencies_include_delay=False),
        mlr=aep.analyze_mlr({"Na": 22, "Pa": 40, "Nb": 50, "Pb": 64}),
        llr=aep.analyze_llr({"P1": 52, "N1": 105, "P2": 180}, age_months=300))
    assert result["abnormal_levels"] == ["MLR"]
    assert "normal ABR below it" in result["headline"]


def test_all_normal_says_the_pathway_is_intact_as_far_as_it_reaches():
    result = aep.aep_battery(
        abr=aep.analyze_abr(normal_abr(80), 80, latencies_include_delay=False),
        mlr=aep.analyze_mlr({"Na": 18, "Pa": 28, "Nb": 38, "Pb": 52}))
    assert result["abnormal_levels"] == []
    assert "as far as they reach" in result["headline"]


def test_one_recording_alone_says_to_run_the_others():
    result = aep.aep_battery(
        abr=aep.analyze_abr({"I": 1.62, "III": 3.68, "V": 6.60}, 80,
                            latencies_include_delay=False))
    assert "bracket" in result["headline"]


def test_no_recordings_is_reported_as_unavailable():
    assert aep.aep_battery()["available"] is False


# ==================================================================== BOA

def test_minimum_response_levels_fall_steeply_over_the_first_two_years():
    """The behaviour matures, not the hearing — the core misreading of BOA.

    The published series falls monotonically until it plateaus near adult
    values, where the last two bands sit at 25 and 26 dB SPL. That final
    uptick is in the source and is within its own measurement noise, so the
    trend is asserted rather than strict monotonicity.
    """
    levels = [b["warble_db_spl"] for b in boa.BOA_NORMS]
    assert levels[:6] == sorted(levels[:6], reverse=True)
    assert abs(levels[-1] - levels[-2]) <= 2, "the plateau should stay flat"
    assert levels[0] - levels[-1] > 45


def test_a_newborn_response_level_is_far_above_a_normal_threshold():
    """78 dB SPL in an ear that hears normally — why MRLs are not thresholds."""
    newborn = boa.BOA_NORMS[0]["warble_db_spl"]
    assert newborn > 70
    result = boa.analyze_boa(0.5, observed_level_db_spl=newborn)
    assert result["concern"] is False
    assert result["is_threshold"] is False


def test_a_boa_result_is_never_a_threshold():
    result = boa.analyze_boa(3, observed_level_db_spl=70)
    assert result["is_threshold"] is False
    assert "not thresholds" in result["caveat"]


def test_a_response_level_matching_the_age_band_is_accepted():
    result = boa.analyze_boa(5, observed_level_db_spl=55)
    assert result["concern"] is False
    assert result["expected_mrl_db_spl"] == 51


def test_a_response_level_far_above_the_band_refers_for_objective_testing():
    result = boa.analyze_boa(3, observed_level_db_spl=95)
    assert result["concern"] is True
    assert "mrl_above_age_expectation" in result["flags"]
    assert any("ABR or ASSR" in f for f in result["findings"])
    assert any("do not repeat BOA" in f for f in result["findings"])


def test_localisation_below_four_months_is_questioned():
    result = boa.analyze_boa(2, observed_level_db_spl=70, responses=["head_turn"])
    assert "response_beyond_age" in result["flags"]
    assert result["age_appropriate_responses"] is False


def test_only_reflexive_responses_at_nine_months_is_a_reason_to_test_objectively():
    result = boa.analyze_boa(9, observed_level_db_spl=40,
                             responses=["eye_blink", "startle"])
    assert "only_reflexive_responses" in result["flags"]
    assert any("not to conclude" in f for f in result["findings"])


def test_a_single_observer_is_always_flagged():
    assert "single_observer" in boa.analyze_boa(3, 70, observers=1)["flags"]
    assert "single_observer" not in boa.analyze_boa(3, 70, observers=2)["flags"]


def test_repeated_presentations_raise_habituation():
    assert "habituation_risk" in boa.analyze_boa(3, 70, presentations=6)["flags"]
    assert "habituation_risk" not in boa.analyze_boa(3, 70, presentations=2)["flags"]


def test_past_six_months_the_better_test_is_named():
    assert "vra_indicated" in boa.analyze_boa(8, 45)["flags"]
    assert "vra_indicated" not in boa.analyze_boa(3, 70)["flags"]


def test_the_reference_states_what_boa_cannot_do():
    reference = boa.boa_reference()
    assert any("never thresholds" in l for l in reference["limits"])
    assert any("not ear-specific" in l for l in reference["limits"])
    assert reference["vra_from_months"] == 6


# ============================================================== endpoints

def test_the_abr_endpoint_corrects_the_insert_delay():
    body = client.post("/api/aep/abr", json={
        "intensity_db_nhl": 80,
        "waves": {"I": 2.52, "III": 4.58, "V": 6.37},
    }).json()
    latencies = {e["wave"]: e["latency"] for e in body["absolute"] if e["present"]}
    assert latencies["V"] == pytest.approx(5.47, abs=0.01)


def test_the_threshold_endpoint_returns_the_ladder():
    body = client.post("/api/aep/abr/threshold", json={"series": [
        {"intensity": 80, "wave_v": 5.47}, {"intensity": 30, "wave_v": 7.24},
    ]}).json()
    assert body["estimated_threshold"] == 30


def test_the_battery_endpoint_localises_across_levels():
    body = client.post("/api/aep/battery", json={
        "abr": {"waves": {"I": 1.62, "III": 3.68, "V": 5.47},
                "latencies_include_delay": False},
        "mlr": {"peaks": {"Na": 22, "Pa": 40, "Nb": 50, "Pb": 64}},
    }).json()
    assert body["abnormal_levels"] == ["MLR"]


def test_the_boa_endpoint_refuses_an_out_of_range_age():
    assert client.post("/api/boa/analyze",
                       json={"age_months": 200}).status_code == 422


def test_the_reference_endpoints_describe_all_four_tests():
    aep_ref = client.get("/api/aep/reference").json()
    assert {p["test"] for p in aep_ref["pathway"]} == {"ABR", "MLR", "LLR"}
    assert len(aep_ref["abr"]["norms"]) == len(aep.ABR_NORMS)
    assert {p["peak"] for p in aep_ref["mlr"]["peaks"]} == set(aep.MLR_NORMS)
    assert {p["peak"] for p in aep_ref["llr"]["peaks"]} == set(aep.LLR_NORMS)

    boa_ref = client.get("/api/boa/reference").json()
    assert len(boa_ref["bands"]) == len(boa.BOA_NORMS)
