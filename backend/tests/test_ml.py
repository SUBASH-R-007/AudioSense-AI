"""Smoke tests for the trained ML classifier (require trained artifacts)."""
import pytest

from app.ml.classifier import MODEL_PATH, classify_ear
from app.ml.features import build_features

pytestmark = pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason="model not trained — run generate_dataset + train first",
)


def bc_from_ac(ac):
    return {f: max(-10, v - 5) for f, v in ac.items() if f <= 4000}


def test_noise_notch_recognized():
    ac = {250: 10, 500: 10, 1000: 15, 2000: 15, 4000: 55, 8000: 20}
    result = classify_ear(ac, bc_from_ac(ac))
    assert result["pattern"] == "noise_notch_4k"
    assert result["confidence"] > 0.5
    # 4 kHz must be the glowing region for a 4k notch.
    assert result["freq_importance"][4000] == max(result["freq_importance"].values())


def test_ski_slope_recognized():
    ac = {250: 10, 500: 10, 1000: 15, 2000: 50, 4000: 85, 8000: 90}
    result = classify_ear(ac, bc_from_ac(ac))
    assert result["pattern"] in ("ski_slope", "sloping_high_frequency")


def test_probabilities_sum_to_one():
    ac = {250: 40, 500: 40, 1000: 45, 2000: 40, 4000: 45, 8000: 40}
    result = classify_ear(ac, bc_from_ac(ac))
    assert sum(result["probabilities"].values()) == pytest.approx(1.0, abs=0.01)


def test_absurd_zigzag_flags_ood():
    ac = {250: 120, 500: -10, 1000: 120, 2000: -10, 4000: 120, 8000: -10}
    result = classify_ear(ac, bc_from_ac({f: 0 for f in ac}))
    assert result["ood"] is True
    assert result["ood_message"] == "Atypical audiogram — priority human review"


def test_nr_handled():
    ac = {250: 90, 500: 100, 1000: 110, 2000: "NR", 4000: "NR", 8000: "NR"}
    result = classify_ear(ac, {})
    assert result["pattern"] == "corner_audiogram"


def test_feature_vector_shape():
    ac = {f: 20.0 for f in (250, 500, 1000, 2000, 4000, 8000)}
    bc = {f: 15.0 for f in (250, 500, 1000, 2000, 4000)}
    assert build_features(ac, bc).shape == (19,)
