"""Tests for triage priority, review routing, and throughput reporting."""
import io

from fastapi.testclient import TestClient

from app.clinical.triage import triage_case, worklist_summary
from app.main import app
from app.services.demo_cases import DEMO_CASES

client = TestClient(app)


def base(**over):
    a = {"safety": {"alerts": []}, "rules": {"right": {}, "left": {}, "disability": {}},
         "ml": {"right": None, "left": None}, "battery": {}}
    a.update(over)
    return a


def test_clean_case_is_routine_and_auto_releasable():
    t = triage_case(base(ml={"right": {"confidence": 0.98, "ood": False}, "left": None}))
    assert t["priority"] == 4
    assert t["level"] == "routine"
    assert t["auto_releasable"] is True
    assert t["review_required"] is False


def test_emergency_takes_top_priority():
    t = triage_case(base(safety={"alerts": [
        {"level": "emergency", "title": "Possible sudden sensorineural hearing loss"}]}))
    assert t["priority"] == 1
    assert t["level"] == "critical"
    assert t["sla"] == "same day"
    assert t["review_required"] is True


def test_urgent_ranks_below_emergency_above_review():
    urgent = triage_case(base(safety={"alerts": [{"level": "urgent", "title": "Asymmetry"}]}))
    review = triage_case(base(safety={"alerts": [{"level": "validity", "title": "Masking"}]}))
    assert urgent["priority"] == 2 < review["priority"] == 3


def test_low_confidence_forces_human_review():
    t = triage_case(base(ml={"right": {"confidence": 0.42, "ood": False}, "left": None}))
    assert t["review_required"] is True
    assert any(r["code"] == "low_confidence" for r in t["reasons"])


def test_out_of_distribution_forces_human_review():
    t = triage_case(base(ml={"right": {"confidence": 0.95, "ood": True}, "left": None}))
    assert t["review_required"] is True
    assert any(r["code"] == "atypical_pattern" for r in t["reasons"])


def test_provisional_type_forces_review():
    t = triage_case(base(rules={"right": {"provisional": True}, "left": {},
                                "disability": {}}))
    assert t["review_required"] is True
    assert any(r["code"] == "provisional_type" for r in t["reasons"])


def test_benchmark_disability_requires_signoff():
    t = triage_case(base(rules={"right": {}, "left": {},
                                "disability": {"benchmark_disability": True,
                                               "binaural_pct": 47.5}}))
    assert t["review_required"] is True
    assert any(r["code"] == "benchmark_disability" for r in t["reasons"])


def test_battery_conflict_forces_review():
    t = triage_case(base(battery={"has_contradictions": True, "contradiction_count": 2}))
    assert t["review_required"] is True


def test_no_response_is_noted_without_blocking_release():
    t = triage_case(base(rules={
        "right": {"ac_pta": {"nr_freqs": [8000]}}, "left": {}, "disability": {}}))
    assert any(r["code"] == "no_response" for r in t["reasons"])
    assert t["priority"] == 4  # noted, but not itself a reason to hold the report


def test_worklist_summary_counts_and_headline():
    cases = [
        {"triage": triage_case(base(safety={"alerts": [{"level": "emergency", "title": "x"}]}))},
        {"triage": triage_case(base(ml={"right": {"confidence": 0.4, "ood": False}, "left": None}))},
        {"triage": triage_case(base())},
        {"triage": triage_case(base())},
    ]
    s = worklist_summary(cases)
    assert s["total"] == 4
    assert s["by_priority"]["critical"] == 1
    assert s["review_required"] == 2
    assert s["auto_releasable"] == 2
    assert s["auto_release_pct"] == 50.0
    assert "need a clinician now" in s["headline"]


def test_empty_worklist_is_safe():
    assert worklist_summary([])["total"] == 0


# ------------------------------------------------------------- API level ---

def test_analyze_returns_triage_and_timing():
    case = next(c for c in DEMO_CASES if c["id"] == "normal")
    body = client.post("/api/analyze", json=case["record"]).json()
    assert body["triage"]["level"] in ("routine", "review", "urgent", "critical")
    assert body["timing"]["interpretation_ms"] > 0


def test_sudden_asymmetric_case_is_triaged_critical():
    case = next(c for c in DEMO_CASES if c["id"] == "sudden_asymmetric")
    body = client.post("/api/analyze", json=case["record"]).json()
    assert body["triage"]["priority"] == 1
    assert body["triage"]["review_required"] is True


def test_normal_case_is_auto_releasable():
    case = next(c for c in DEMO_CASES if c["id"] == "normal")
    body = client.post("/api/analyze", json=case["record"]).json()
    assert body["triage"]["auto_releasable"] is True


CSV_HEAD = (
    "name,age,sex,occupation,test_date,"
    "r_ac_250,r_ac_500,r_ac_1000,r_ac_2000,r_ac_4000,r_ac_8000,"
    "r_bc_250,r_bc_500,r_bc_1000,r_bc_2000,r_bc_4000,"
    "l_ac_250,l_ac_500,l_ac_1000,l_ac_2000,l_ac_4000,l_ac_8000,"
    "l_bc_250,l_bc_500,l_bc_1000,l_bc_2000,l_bc_4000\n"
)


def test_batch_returns_worklist_and_performance():
    csv = CSV_HEAD + (
        "Normal,30,male,clerk,2026-01-01,10,10,10,10,10,15,5,5,5,5,5,"
        "10,10,10,10,10,15,5,5,5,5,5\n"
        "Loss,60,male,farmer,2026-01-02,40,45,50,55,60,65,35,40,45,50,55,"
        "45,50,55,60,65,70,40,45,50,55,60\n"
    )
    body = client.post("/api/batch",
                       files={"file": ("b.csv", io.BytesIO(csv.encode()), "text/csv")}).json()
    assert body["worklist"]["total"] == 2
    assert body["performance"]["cases"] == 2
    assert body["performance"]["mean_ms"] > 0
    assert body["performance"]["cases_per_minute"] > 0
    # Worklist must be ordered by priority, not by CSV row order.
    priorities = [r["triage"]["priority"] for r in body["results"]]
    assert priorities == sorted(priorities)
    assert all("interpretation_ms" in r for r in body["results"])
