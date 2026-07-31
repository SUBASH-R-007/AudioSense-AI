"""Tests for counterfactual explanations, case retrieval, and the
clinician feedback loop."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.classifier import MODEL_PATH, classify_ear

client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not MODEL_PATH.exists(), reason="model not trained")


def bc_from_ac(ac):
    return {f: max(-10, v - 5) for f, v in ac.items() if f <= 4000}


NOTCH = {250: 10, 500: 10, 1000: 15, 2000: 15, 4000: 55, 8000: 20}


def test_counterfactuals_name_frequency_and_amount():
    result = classify_ear(NOTCH, bc_from_ac(NOTCH))
    cfs = result["counterfactuals"]
    assert cfs, "expected at least one counterfactual"
    for cf in cfs:
        assert cf["freq"] in (250, 500, 1000, 2000, 4000, 8000)
        assert cf["delta_db"] != 0
        assert cf["new_pattern"] != result["pattern"]
        assert "would" in cf["text"]


def test_counterfactual_for_notch_targets_4k():
    """Flattening the 4 kHz notch should be the cheapest way to change class."""
    result = classify_ear(NOTCH, bc_from_ac(NOTCH))
    assert result["counterfactuals"][0]["freq"] == 4000


def test_counterfactuals_sorted_by_smallest_change():
    result = classify_ear(NOTCH, bc_from_ac(NOTCH))
    deltas = [abs(c["delta_db"]) for c in result["counterfactuals"]]
    assert deltas == sorted(deltas)


def test_similar_cases_support_the_prediction():
    result = classify_ear(NOTCH, bc_from_ac(NOTCH))
    sim = result["similar_cases"]
    assert sim is not None
    assert sim["k"] == len(sim["neighbour_labels"])
    assert sim["agree"] >= sim["k"] // 2  # a clean notch should have consensus
    assert 0 <= sim["agreement_pct"] <= 100
    assert len(sim["example_thresholds"]) == 3


def test_similar_cases_examples_are_real_audiograms():
    result = classify_ear(NOTCH, bc_from_ac(NOTCH))
    for example in result["similar_cases"]["example_thresholds"]:
        assert set(example) == {"250", "500", "1000", "2000", "4000", "8000"}
        assert all(-10 <= v <= 120 for v in example.values())


# ------------------------------------------------------------- feedback ---

def test_feedback_roundtrip(tmp_path, monkeypatch):
    import app.routers.feedback as fb
    monkeypatch.setattr(fb, "FEEDBACK_PATH", tmp_path / "feedback.jsonl")

    assert client.get("/api/feedback").json()["total"] == 0

    r = client.post("/api/feedback", json={
        "ear": "right", "predicted": "flat", "confidence": 0.71,
        "corrected": "cookie_bite", "note": "clearly mid-frequency",
        "clinician": "Dr. R",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["stored"] is True
    assert body["total"] == 1
    assert body["disagreements"] == 1
    assert body["agreement_pct"] == 0.0

    client.post("/api/feedback", json={
        "ear": "left", "predicted": "flat", "corrected": "flat",
    })
    stats = client.get("/api/feedback").json()
    assert stats["total"] == 2
    assert stats["disagreements"] == 1
    assert stats["agreement_pct"] == 50.0
    assert stats["retrain_ready"] is False
    assert "Cookie-bite (mid-frequency)" in stats["by_corrected_pattern"]
