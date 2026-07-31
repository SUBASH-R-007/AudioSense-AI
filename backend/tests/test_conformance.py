"""Guideline conformance and reproducibility.

The problem statement asks for *consistent* diagnostic decision-making.
Boundary tests prove the rules are right at the edges; these tests prove
they are right EVERYWHERE, by sweeping the whole clinically reachable
input space and checking every result against the published guideline
independently re-derived in the test itself.

They also prove reproducibility: identical input produces byte-identical
output, every time, on every machine — which is the property a human
interpreter cannot offer.
"""
import json

import pytest

from app.clinical.rules import analyze_test, hearing_type, pta, rpwd_disability, who_grade
from app.clinical.triage import triage_case

FREQS = (250, 500, 1000, 2000, 4000, 8000)
PTA_FREQS = (500, 1000, 2000, 4000)


def flat(level, freqs=FREQS):
    return {f: level for f in freqs}


def bc_flat(level):
    return {f: level for f in (250, 500, 1000, 2000, 4000)}


# ---------------------------------------------------------------------------
# WHO 2021 degree — swept across the entire scale
# ---------------------------------------------------------------------------

def who_grade_reference(value: float) -> str:
    """The WHO 2021 table, re-derived independently of the implementation."""
    if value < 20:
        return "Normal hearing"
    if value < 35:
        return "Mild hearing loss"
    if value < 50:
        return "Moderate hearing loss"
    if value < 65:
        return "Moderately severe hearing loss"
    if value < 80:
        return "Severe hearing loss"
    return "Profound hearing loss"


def test_who_grade_matches_guideline_across_entire_scale():
    """Sweep -10.0 to 120.0 dB HL in 0.5 dB steps — 261 checks."""
    value = -10.0
    checked = 0
    while value <= 120.0:
        assert who_grade(value)["grade"] == who_grade_reference(value), (
            f"WHO grade mismatch at PTA {value}")
        checked += 1
        value = round(value + 0.5, 1)
    assert checked == 261


def test_who_grade_is_monotonic():
    """Hearing can never be graded better as thresholds get worse."""
    order = ["Normal hearing", "Mild hearing loss", "Moderate hearing loss",
             "Moderately severe hearing loss", "Severe hearing loss",
             "Profound hearing loss"]
    last = -1
    v = -10.0
    while v <= 120.0:
        idx = order.index(who_grade(v)["grade"])
        assert idx >= last, f"grade went backwards at {v}"
        last = idx
        v = round(v + 0.5, 1)


def test_pta_equals_arithmetic_mean_across_the_scale():
    for level in range(-10, 121, 5):
        assert pta(flat(level))["value"] == float(level)


# ---------------------------------------------------------------------------
# Type — swept across the AC/BC plane
# ---------------------------------------------------------------------------

def type_reference(ac_level: float, bc_level: float) -> str:
    """Standard criteria, re-derived: gap must EXCEED 10 dB to count."""
    abg = ac_level - bc_level
    if abg > 10 and bc_level <= 20:
        return "Conductive"
    if abg > 10 and bc_level > 20:
        return "Mixed"
    if abg <= 10 and ac_level > 20:
        return "Sensorineural"
    return "Normal"


def test_type_matches_criteria_across_ac_bc_plane():
    """Every AC/BC combination in 5 dB steps where BC <= AC (physically real)."""
    checked = 0
    for ac_level in range(-10, 121, 5):
        for bc_level in range(-10, min(ac_level, 70) + 1, 5):
            result = hearing_type(flat(ac_level), bc_flat(bc_level))
            assert result["type"] == type_reference(ac_level, bc_level), (
                f"type mismatch at AC {ac_level} / BC {bc_level}: "
                f"got {result['type']}")
            assert result["provisional"] is False
            checked += 1
    assert checked == 323  # every physically real AC/BC pair in 5 dB steps


def test_conductive_requires_gap_strictly_greater_than_ten():
    """The 10 dB boundary, swept at every BC level."""
    for bc_level in range(-10, 21, 5):
        exactly_ten = hearing_type(flat(bc_level + 10), bc_flat(bc_level))
        assert exactly_ten["type"] != "Conductive", f"BC {bc_level}: 10 dB gap"
        just_over = hearing_type(flat(bc_level + 15), bc_flat(bc_level))
        assert just_over["type"] == "Conductive", f"BC {bc_level}: 15 dB gap"


# ---------------------------------------------------------------------------
# RPwD Act 2016 disability — swept, with the formula re-derived
# ---------------------------------------------------------------------------

def monaural_reference(pta_value: float) -> float:
    return min(100.0, max(0.0, 1.5 * (pta_value - 25)))


def test_rpwd_monaural_formula_across_the_scale():
    for value in range(-10, 121, 1):
        result = rpwd_disability(float(value), float(value))
        assert result["right"]["pct"] == pytest.approx(
            monaural_reference(value), abs=0.01), f"monaural mismatch at {value}"


def test_rpwd_binaural_weighting_across_ear_combinations():
    """(5 x better + worse) / 6, checked over the whole plane in 5 dB steps."""
    checked = 0
    for right in range(0, 121, 5):
        for left in range(0, 121, 5):
            result = rpwd_disability(float(right), float(left))
            r_pct = monaural_reference(right)
            l_pct = monaural_reference(left)
            better, worse = min(r_pct, l_pct), max(r_pct, l_pct)
            expected = (5 * better + worse) / 6
            assert result["binaural_pct"] == pytest.approx(expected, abs=0.01)
            assert result["benchmark_disability"] is (expected >= 40.0)
            checked += 1
    assert checked == 25 * 25


def test_rpwd_never_exceeds_bounds():
    for right in range(-10, 121, 5):
        for left in range(-10, 121, 5):
            result = rpwd_disability(float(right), float(left))
            assert 0.0 <= result["binaural_pct"] <= 100.0
            assert 0.0 <= result["right"]["pct"] <= 100.0


def test_better_ear_dominates_the_binaural_result():
    """One good ear must carry the score — that is the point of the weighting."""
    one_good = rpwd_disability(20.0, 120.0)["binaural_pct"]
    both_bad = rpwd_disability(120.0, 120.0)["binaural_pct"]
    assert one_good < both_bad / 3


# ---------------------------------------------------------------------------
# Reproducibility — the consistency claim
# ---------------------------------------------------------------------------

CASES = [
    (flat(10), bc_flat(8), flat(15), bc_flat(12)),
    ({250: 15, 500: 15, 1000: 20, 2000: 25, 4000: 60, 8000: 30}, bc_flat(20),
     {250: 10, 500: 15, 1000: 20, 2000: 30, 4000: 55, 8000: 25}, bc_flat(18)),
    (flat(45), bc_flat(10), flat(50), bc_flat(12)),
    ({250: 85, 500: 95, 1000: 110, 2000: "NR", 4000: "NR", 8000: "NR"}, {},
     {250: 90, 500: 100, 1000: "NR", 2000: "NR", 4000: "NR", 8000: "NR"}, {}),
]


@pytest.mark.parametrize("case", CASES, ids=["normal", "notch", "conductive", "profound"])
def test_identical_input_gives_identical_output(case):
    """Run the rules engine 50 times; every result must be byte-identical."""
    first = json.dumps(analyze_test(*case), sort_keys=True, default=str)
    for _ in range(49):
        again = json.dumps(analyze_test(*case), sort_keys=True, default=str)
        assert again == first, "rules engine is not deterministic"


def test_result_does_not_depend_on_dict_insertion_order():
    """Entering thresholds in a different order must not change the answer."""
    ac = {250: 15, 500: 15, 1000: 20, 2000: 25, 4000: 60, 8000: 30}
    shuffled = {k: ac[k] for k in reversed(list(ac))}
    bc = bc_flat(20)
    assert (json.dumps(analyze_test(ac, bc, ac, bc), sort_keys=True, default=str)
            == json.dumps(analyze_test(shuffled, bc, shuffled, bc), sort_keys=True, default=str))


def test_triage_is_deterministic():
    analysis = {
        "safety": {"alerts": [{"level": "urgent", "title": "Asymmetric hearing loss"}]},
        "rules": {"right": {}, "left": {}, "disability": {}},
        "ml": {"right": {"confidence": 0.99, "ood": False}, "left": None},
        "battery": {},
    }
    first = json.dumps(triage_case(analysis), sort_keys=True)
    for _ in range(20):
        assert json.dumps(triage_case(analysis), sort_keys=True) == first
