"""Tests for ISO 7029 age-matched norms, the verdict, and the narrative."""
import pytest
from fastapi.testclient import TestClient

from app.clinical.norms import (
    analyze_norms,
    ear_norms,
    hearing_age,
    median_threshold,
    percentile,
)
from app.clinical.progression import compare_tests, narrate
from app.main import app
from app.services.demo_cases import DEMO_CASES
from app.services.verdict import build_verdict

client = TestClient(app)


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


# ------------------------------------------------------------ ISO 7029 ----

def test_reference_age_has_no_age_related_shift():
    for f in (250, 1000, 4000, 8000):
        assert median_threshold(18, f) == 0.0


def test_median_shift_grows_with_age():
    values = [median_threshold(age, 4000, "male") for age in (20, 40, 60, 80)]
    assert values == sorted(values)
    assert values[-1] > values[0]


def test_high_frequencies_deteriorate_faster_than_low():
    at_60 = {f: median_threshold(60, f, "male") for f in (250, 1000, 4000, 8000)}
    assert at_60[8000] > at_60[4000] > at_60[1000] > at_60[250]


def test_men_lose_high_frequency_hearing_faster_than_women():
    assert median_threshold(60, 4000, "male") > median_threshold(60, 4000, "female")
    # Below 2 kHz the standard uses the same coefficients for both sexes.
    assert median_threshold(60, 500, "male") == median_threshold(60, 500, "female")


def test_median_is_clamped_to_the_modelled_range():
    assert median_threshold(95, 4000) == median_threshold(80, 4000)
    assert median_threshold(5, 4000) == median_threshold(18, 4000)


def test_hearing_age_inverts_the_median_curve():
    """The age recovered from a median threshold must be that age."""
    for age in (30, 45, 60, 75):
        threshold = median_threshold(age, 4000, "male")
        assert hearing_age(threshold, 4000, "male") == pytest.approx(age, abs=1.0)


def test_hearing_age_none_for_perfect_hearing():
    assert hearing_age(0, 4000) is None


def test_percentile_at_the_median_is_about_fifty():
    median = median_threshold(60, 4000, "male")
    p = percentile(median, 60, 4000, "male")
    assert p["better_than_pct"] == pytest.approx(50.0, abs=1.0)
    assert p["within_normal_variation"] is True


def test_worse_threshold_gives_lower_percentile():
    median = median_threshold(50, 4000, "male")
    better = percentile(median - 15, 50, 4000, "male")["better_than_pct"]
    worse = percentile(median + 25, 50, 4000, "male")["better_than_pct"]
    assert better > 50 > worse
    assert worse < 20


def test_young_welder_has_older_ears_than_his_age():
    """The pre-clinical NIHL story, expressed as hearing age."""
    ac = {250: 10, 500: 10, 1000: 10, 2000: 15, 4000: 45, 8000: 45}
    result = ear_norms(ac, age=26, sex="male")
    assert result["hearing_age"] > 26 + 15
    assert "older than the patient" in result["summary"]


def test_normal_thresholds_are_not_called_hearing_loss():
    """A raised hearing age with normal thresholds is early change, not loss."""
    ac = {250: 10, 500: 10, 1000: 10, 2000: 15, 4000: 15, 8000: 15}
    result = ear_norms(ac, age=26, sex="male")
    assert result["clinically_normal"] is True
    assert "still within normal limits" in result["summary"]
    assert "rather than hearing loss" in result["summary"]


def test_percentiles_are_not_alarmist_for_normal_thresholds():
    """15 dB at 2 kHz is normal hearing — it must not read as bottom 1%."""
    p = percentile(15, 26, 2000, "male")
    assert p["better_than_pct"] > 3, (
        "spread too tight: normal thresholds produce alarming percentiles")


def test_age_appropriate_hearing_is_reported_as_such():
    ac = {f: median_threshold(60, f, "male") for f in
          (250, 500, 1000, 2000, 4000, 8000)}
    result = ear_norms(ac, age=60, sex="male")
    assert result["age_gap"] <= 3
    assert "expected at this age" in result["summary"]


def test_norms_none_without_thresholds():
    assert ear_norms({}, 40) is None
    assert analyze_norms({}, {}, 40) is None


def test_analyze_norms_uses_the_worse_ear():
    good = {250: 10, 500: 10, 1000: 10, 2000: 10, 4000: 10, 8000: 10}
    bad = {250: 20, 500: 25, 1000: 30, 2000: 45, 4000: 60, 8000: 70}
    result = analyze_norms(good, bad, age=40, sex="male")
    assert result["hearing_age"] == result["left"]["hearing_age"]
    assert result["age_gap"] > 0


# -------------------------------------------------------------- verdict ---

def test_verdict_for_normal_hearing():
    case = next(c for c in DEMO_CASES if c["id"] == "normal")
    body = client.post("/api/analyze", json=case["record"]).json()
    v = body["verdict"]
    assert v["tone"] == "normal"
    assert "normal limits" in v["headline"]
    assert v["review_required"] is False
    assert any(n["label"].endswith("PTA") for n in v["numbers"])


def test_verdict_leads_with_the_emergency():
    case = next(c for c in DEMO_CASES if c["id"] == "sudden_asymmetric")
    v = client.post("/api/analyze", json=case["record"]).json()["verdict"]
    assert v["tone"] == "emergency"
    assert "emergency" in v["headline"].lower()
    assert v["action_level"] == "emergency"


def test_verdict_for_preclinical_damage_says_it_is_preventable():
    case = next(c for c in DEMO_CASES if c["id"] == "preclinical_nihl")
    v = client.post("/api/analyze", json=case["record"]).json()["verdict"]
    assert v["tone"] == "warning"
    assert "preventable" in v["headline"]


def test_verdict_describes_the_loss_in_plain_words():
    case = next(c for c in DEMO_CASES if c["id"] == "noise_notch")
    v = client.post("/api/analyze", json=case["record"]).json()["verdict"]
    assert v["headline"][0].isupper() and v["headline"].endswith(".")
    assert "mild" in v["headline"].lower()
    assert "noise notch" in v["headline"].lower()
    # Unit casing must survive the sentence-casing of the pattern label.
    assert "kHz" in v["headline"] and "khz" not in v["headline"]


def test_verdict_recommends_aids_for_moderate_loss():
    case = next(c for c in DEMO_CASES if c["id"] == "presbycusis")
    v = client.post("/api/analyze", json=case["record"]).json()["verdict"]
    assert "hearing-aid" in v["action"] or "hearing aid" in v["action"]


def test_verdict_includes_hearing_age_number():
    case = next(c for c in DEMO_CASES if c["id"] == "presbycusis")
    v = client.post("/api/analyze", json=case["record"]).json()["verdict"]
    assert any(n["label"] == "Hearing age" for n in v["numbers"])


def test_verdict_caps_the_number_of_figures():
    for case in DEMO_CASES:
        v = client.post("/api/analyze", json=case["record"]).json()["verdict"]
        assert len(v["numbers"]) <= 4, case["id"]


def test_verdict_handles_missing_data_without_crashing():
    v = build_verdict({"rules": {}, "ml": {}, "safety": {}, "triage": {}})
    assert v["tone"] == "unknown"
    assert v["numbers"] == []


# ------------------------------------------------------------ narrative ---

def test_narrative_reports_stability():
    result = compare_tests(
        {"right": {"ac": flat(20)}, "left": {"ac": flat(20)}},
        {"right": {"ac": flat(22)}, "left": {"ac": flat(20)}},
    )
    assert result["narrative"]["flagged"] is False
    assert any("stable" in line for line in result["narrative"]["lines"])


def test_narrative_names_the_frequencies_that_changed():
    baseline = flat(20)
    current = {**baseline, 4000: 45, 8000: 40}
    result = compare_tests(
        {"right": {"ac": baseline}, "left": {"ac": baseline}},
        {"right": {"ac": current}, "left": {"ac": baseline}},
    )
    text = " ".join(result["narrative"]["lines"])
    assert "4000 Hz" in text and "8000 Hz" in text
    assert "high frequencies" in text


def test_narrative_calls_out_a_recordable_osha_shift():
    baseline = flat(20)
    current = {**baseline, 2000: 35, 4000: 40}
    result = compare_tests(
        {"right": {"ac": baseline}, "left": {"ac": baseline}},
        {"right": {"ac": current}, "left": {"ac": baseline}},
    )
    assert result["narrative"]["flagged"] is True
    assert "recordable" in " ".join(result["narrative"]["lines"])


def test_narrative_explains_improvement():
    baseline = flat(45)
    current = {**baseline, 250: 15, 500: 15}
    n = narrate(compare_tests(
        {"right": {"ac": baseline}, "left": {"ac": baseline}},
        {"right": {"ac": current}, "left": {"ac": baseline}},
    ))
    assert any("improved" in line for line in n["lines"])


def test_progression_endpoint_returns_the_narrative():
    pair = client.get("/api/demo-cases").json()["progression_pair"]
    body = client.post("/api/progression",
                       json={"baseline": pair["baseline"], "current": pair["current"]}).json()
    assert body["progression"]["narrative"]["flagged"] is True
    assert body["progression"]["narrative"]["lines"]


# ------------------------------------------------ the headline grade ----
#
# `_worse_grade` picks which ear the single headline sentence describes. Every
# other verdict test drives DEMO_CASES, and the only demo case whose ears grade
# differently takes the emergency branch and returns before the grade is read —
# so `min` (worse ear) and `max` (better ear) were indistinguishable to the
# whole suite while the difference is "deaf in one ear" versus "normal".

def test_verdict_headlines_the_worse_ear_when_the_ears_differ():
    record = {
        "patient": {"name": "Asym", "age": 55, "sex": "male",
                    "occupation": "Farmer", "test_date": "2026-08-01",
                    "onset": "gradual", "symptoms": []},
        "right": {"ac": flat(95), "bc": flat(95, (250, 500, 1000, 2000, 4000)),
                  "masked": True},
        "left": {"ac": flat(10), "bc": flat(10, (250, 500, 1000, 2000, 4000)),
                 "masked": True},
    }
    body = client.post("/api/analyze", json=record).json()
    # Without this the case could be routed back through the emergency branch
    # by a future safety rule and quietly stop testing the grade at all.
    assert body["safety"]["has_emergency"] is False
    headline = body["verdict"]["headline"].lower()
    assert "profound" in headline
    assert "normal limits" not in headline
    assert body["verdict"]["tone"] == "loss"


def test_worse_grade_is_side_independent():
    from app.services.verdict import _worse_grade
    worse = {"who_grade": {"grade": "Profound hearing loss"}}
    better = {"who_grade": {"grade": "Normal hearing"}}
    assert _worse_grade({"right": worse, "left": better}) == "Profound hearing loss"
    assert _worse_grade({"right": better, "left": worse}) == "Profound hearing loss"


# --------------------------------------------------- single-ear tests ----
#
# An ear with no PTA-frequency thresholds is emitted as "ac_pta": None and
# "who_grade": None, not as a missing key. Readers that used `.get(k, {})`
# crashed on it, so a genuinely one-sided test 500'd.

@pytest.mark.parametrize("tested,blank", [("right", "left"), ("left", "right")])
def test_a_single_ear_test_analyses_without_crashing(tested, blank):
    record = {
        "patient": {"name": "One Ear", "age": 40},
        tested: {"ac": flat(45), "bc": flat(20, (250, 500, 1000, 2000, 4000))},
        blank: {"ac": {}, "bc": {}},
    }
    r = client.post("/api/analyze", json=record)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"]["headline"]
    assert body["rules"][blank]["ac_pta"] is None
    assert body["rules"][blank]["who_grade"] is None


def test_an_empty_record_analyses_without_crashing():
    r = client.post("/api/analyze", json={})
    assert r.status_code == 200, r.text
    assert r.json()["verdict"]["headline"]


def test_an_ear_tested_off_the_pta_frequencies_analyses():
    """250 and 8000 Hz only: measured, but no PTA — the same None shape."""
    r = client.post("/api/analyze", json={
        "patient": {"name": "Edges", "age": 40},
        "right": {"ac": {250: 30, 8000: 60}, "bc": {}},
        "left": {"ac": {}, "bc": {}},
    })
    assert r.status_code == 200, r.text
