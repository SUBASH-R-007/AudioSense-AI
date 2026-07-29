"""Boundary-pinned tests for the MODULE 1 clinical rules engine."""
import pytest

from app.clinical.rules import (
    air_bone_gap,
    analyze_test,
    hearing_type,
    pta,
    rpwd_disability,
    who_grade,
)

PTA_FREQS = [500, 1000, 2000, 4000]


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


# ---------------------------------------------------------------- PTA ------

def test_pta_is_mean_of_500_1k_2k_4k():
    ac = {250: 5, 500: 20, 1000: 30, 2000: 40, 4000: 50, 8000: 90}
    assert pta(ac)["value"] == 35.0  # 250/8000 excluded


def test_pta_nr_counts_as_120_and_is_flagged():
    ac = {500: 60, 1000: 60, 2000: 60, 4000: "NR"}
    result = pta(ac)
    assert result["value"] == pytest.approx((60 + 60 + 60 + 120) / 4)
    assert result["nr_freqs"] == [4000]


def test_pta_missing_freq_excluded_and_flagged():
    ac = {500: 40, 1000: 40, 2000: 40}
    result = pta(ac)
    assert result["value"] == 40.0
    assert result["missing_freqs"] == [4000]


def test_pta_none_when_no_data():
    assert pta({250: 10, 8000: 10}) is None


# ------------------------------------------------------- WHO 2021 grades ---

@pytest.mark.parametrize("value,grade", [
    (0, "Normal hearing"),
    (19.99, "Normal hearing"),
    (20.0, "Mild hearing loss"),          # boundary: exactly 20 -> Mild
    (34.99, "Mild hearing loss"),
    (35.0, "Moderate hearing loss"),      # boundary: exactly 35 -> Moderate
    (49.99, "Moderate hearing loss"),
    (50.0, "Moderately severe hearing loss"),  # boundary: exactly 50
    (64.99, "Moderately severe hearing loss"),
    (65.0, "Severe hearing loss"),
    (79.99, "Severe hearing loss"),
    (80.0, "Profound hearing loss"),
    (120.0, "Profound hearing loss"),
    (-10.0, "Normal hearing"),
])
def test_who_grade_boundaries(value, grade):
    assert who_grade(value)["grade"] == grade


# ------------------------------------------------------------- ABG/type ----

def test_abg_exactly_10_is_not_conductive():
    ac = flat(30)
    bc = {f: 20 for f in (250, 500, 1000, 2000, 4000)}
    assert air_bone_gap(ac, bc)["value"] == 10.0
    result = hearing_type(ac, bc)
    assert result["type"] == "Sensorineural"  # gap must EXCEED 10
    assert result["provisional"] is False


def test_conductive_when_gap_over_10_and_bc_normal():
    ac = flat(45)
    bc = {f: 10 for f in (250, 500, 1000, 2000, 4000)}
    result = hearing_type(ac, bc)
    assert result["type"] == "Conductive"
    assert result["abg"]["value"] == 35.0


def test_mixed_when_gap_over_10_and_bc_elevated():
    ac = flat(70)
    bc = {f: 35 for f in (250, 500, 1000, 2000, 4000)}
    assert hearing_type(ac, bc)["type"] == "Mixed"


def test_normal_when_ac_within_normal_and_no_gap():
    ac = flat(10)
    bc = {f: 10 for f in (250, 500, 1000, 2000, 4000)}
    assert hearing_type(ac, bc)["type"] == "Normal"


def test_missing_bc_flags_provisional():
    ac = flat(50)
    result = hearing_type(ac, {})
    assert result["provisional"] is True
    assert "type provisional — BC not tested" in result["caveats"]
    assert result["type"] == "Sensorineural (provisional)"


def test_partial_bc_flags_provisional_but_classifies():
    ac = flat(45)
    bc = {500: 10, 1000: 10}  # only 2 of 4 PTA freqs
    result = hearing_type(ac, bc)
    assert result["provisional"] is True
    assert result["type"] == "Conductive"


# ------------------------------------------------------ RPwD disability ----

def test_rpwd_monaural_formula_and_intermediates():
    result = rpwd_disability(55.0, 55.0)
    # 1.5 * (55 - 25) = 45%
    assert result["right"]["pct"] == 45.0
    assert result["binaural_pct"] == 45.0
    assert result["benchmark_disability"] is True
    assert "1.5 ×" in result["right"]["formula"]


def test_rpwd_clamps_low_at_zero():
    result = rpwd_disability(10.0, 10.0)  # 1.5*(10-25) = -22.5 -> 0
    assert result["right"]["pct"] == 0.0
    assert result["binaural_pct"] == 0.0
    assert result["benchmark_disability"] is False


def test_rpwd_clamps_high_at_100():
    result = rpwd_disability(120.0, 120.0)  # 1.5*95 = 142.5 -> 100
    assert result["right"]["pct"] == 100.0
    assert result["binaural_pct"] == 100.0


def test_rpwd_binaural_weighting_favors_better_ear():
    result = rpwd_disability(25.0, 105.0)  # right better: 0%, left worse: 100%
    assert result["better_ear"] == "right"
    assert result["binaural_pct"] == pytest.approx((5 * 0 + 100) / 6, abs=0.01)
    assert result["benchmark_disability"] is False  # 16.67% < 40%


def test_rpwd_benchmark_at_exactly_40():
    # binaural exactly 40: both ears monaural 40 -> PTA = 40/1.5+25 = 51.667
    result = rpwd_disability(51.6667, 51.6667)
    assert result["binaural_pct"] == pytest.approx(40.0, abs=0.01)
    assert result["benchmark_disability"] is True


# ------------------------------------------------------------ full test ----

def test_analyze_test_end_to_end():
    right_ac = flat(20)
    left_ac = {250: 15, 500: 20, 1000: 25, 2000: 40, 4000: 70, 8000: 65}
    bc_r = {f: 15 for f in (250, 500, 1000, 2000, 4000)}
    bc_l = {250: 15, 500: 20, 1000: 25, 2000: 40, 4000: 65}
    result = analyze_test(right_ac, bc_r, left_ac, bc_l)
    assert result["right"]["who_grade"]["grade"] == "Mild hearing loss"  # PTA 20
    assert result["left"]["ac_pta"]["value"] == 38.75
    assert result["left"]["who_grade"]["grade"] == "Moderate hearing loss"
    assert result["disability"]["better_ear"] == "right"
