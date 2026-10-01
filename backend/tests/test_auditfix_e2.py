"""Otoscopy model honesty: grouped validation, fold-local scaling, and a
result that says plainly it is not a validated diagnosis.

The reference atlas is 62 views cut from 22 source pictures. A validation
that holds out one view while its siblings stay in training is partly
testing the model on a picture it learned from; these tests pin the
source-picture protocol, the scaler being fit inside each fold, the card
leading with the held-out figure, and the API wording that follows from it.
"""
import inspect
import json
import math
import re
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.otoscopy import model as M

client = TestClient(app)

needs_model = pytest.mark.skipif(
    not M.model_available(),
    reason="otoscopy model not trained — run python -m scripts.train_otoscopy",
)


def _published_card() -> dict:
    return json.loads(M.CARD_PATH.read_text(encoding="utf-8"))


def _reference_image(label="otitis_media"):
    found, _ = M.scan_directory(M.REFERENCE_DIR)
    return cv2.imread(str(found[label][0]), cv2.IMREAD_COLOR)


# ------------------------------------------------------- source grouping ---

def test_a_reference_view_belongs_to_the_picture_it_was_cut_from():
    assert M.source_photograph(
        "otoscope_reference/tumor/tumor_cbfcad82_05.jpg") == "cbfcad82"
    assert M.source_photograph(
        r"otoscope_reference\normal\normal_0ae4c32e_01.jpg") == "0ae4c32e"
    # A file without the extraction script's naming is its own source.
    assert M.source_photograph("otoscope_kaggle/aom/img_0042.jpg") \
        == "otoscope_kaggle/aom/img_0042.jpg"


def test_the_reference_atlas_is_62_views_from_22_source_pictures():
    found, _ = M.scan_directory(M.REFERENCE_DIR)
    paths = [p for ps in found.values() for p in ps]
    assert len(paths) == 62
    assert len(np.unique(M.source_groups(paths))) == 22
    per_class = {lbl: len({M.source_photograph(p) for p in ps})
                 for lbl, ps in found.items()}
    # Seven of the eight patterns rest on two pictures each.
    assert per_class.pop("normal") == 8
    assert set(per_class.values()) == {2}


# --------------------------------------------- grouped cross-validation ---

def _sibling_leak_dataset(seed=0):
    """Labels carried only by a per-picture signature shared by its views.

    Nothing generalises from one picture to another, so an honest estimate
    is chance (25% for four classes). A protocol that leaves sibling views in
    training recognises the picture and looks near perfect.
    """
    rng = np.random.default_rng(seed)
    n_sources, crops_per_source, rows_per_crop, dim = 12, 3, 2, 40
    signatures = rng.normal(0, 3.0, size=(n_sources, dim))
    X, y, crops, sources = [], [], [], []
    for s in range(n_sources):
        for c in range(crops_per_source):
            crop_id = s * crops_per_source + c
            for _ in range(rows_per_crop):
                X.append(signatures[s] + rng.normal(0, 0.3, dim))
                y.append(f"class{s % 4}")
                crops.append(crop_id)
                sources.append(s)
    return (np.asarray(X), np.asarray(y), np.asarray(crops), np.asarray(sources))


def test_holding_out_whole_pictures_removes_the_sibling_leak():
    X, y, crops, sources = _sibling_leak_dataset()
    by_view = M._grouped_cv(X, y, crops, crops, "crop", sources)
    by_picture = M._grouped_cv(X, y, crops, sources, "source_photograph", sources)
    assert by_view["images_tested"] == by_picture["images_tested"] == 36
    assert by_view["accuracy"] >= 0.9          # memorised the picture
    assert by_picture["accuracy"] <= 0.5       # nothing to generalise from
    assert by_picture["held_out_groups"] == 12
    assert by_picture["optimistic"] is False and by_view["optimistic"] is True


def test_the_scaler_is_fit_on_the_training_fold_only(monkeypatch):
    """A scaler fit on every row has already seen the held-out picture."""
    from sklearn.preprocessing import StandardScaler

    X, y, crops, sources = _sibling_leak_dataset()
    fitted_on = []
    real_fit = StandardScaler.fit

    def spy(self, data, *args, **kwargs):
        fitted_on.append(np.asarray(data).shape[0])
        return real_fit(self, data, *args, **kwargs)

    monkeypatch.setattr(StandardScaler, "fit", spy)
    result = M._grouped_cv(X, y, crops, sources, "source_photograph", sources)
    rows_per_source = len(X) // 12
    assert fitted_on, "the fold never fit a scaler of its own"
    assert len(fitted_on) == 12
    assert all(n == len(X) - rows_per_source for n in fitted_on)
    assert result["scaler"] == "fit on the training fold only"


def test_wilson_interval_satisfies_its_defining_equation():
    """Each bound b solves |p - b| = z * sqrt(b(1-b)/n) (Wilson 1927)."""
    z = 1.959964
    for k, n in ((17, 62), (16, 62), (0, 8), (8, 8)):
        lo, hi = M.wilson_interval(k, n)
        p = k / n
        for b in (lo, hi):
            if b in (0.0, 1.0):
                continue
            assert abs(abs(p - b) - z * math.sqrt(b * (1 - b) / n)) < 2e-3
        assert lo <= p <= hi
    # The auditor's independent figure for 16/62.
    assert M.wilson_interval(16, 62) == [0.166, 0.379]


def test_resampling_whole_pictures_widens_the_interval_for_clustered_errors():
    # Ten pictures of six views; every view of a picture shares its fate.
    correct = np.repeat([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], 6)
    clusters = np.repeat(np.arange(10), 6)
    lo_w, hi_w = M.wilson_interval(int(correct.sum()), len(correct))
    lo_c, hi_c = M._cluster_bootstrap_interval(correct, clusters)
    assert (hi_c - lo_c) > (hi_w - lo_w) + 0.1
    assert M._cluster_bootstrap_interval(correct, clusters) == [lo_c, hi_c]


# ------------------------------------------------------------ model card ---

@needs_model
def test_the_published_card_leads_with_the_source_picture_figure():
    card = _published_card()
    keys = list(card)
    assert keys.index("validation") < keys.index("validation_optimistic")
    v, opt = card["validation"], card["validation_optimistic"]
    assert v["protocol"] == "source_photograph" and v["optimistic"] is False
    assert opt["protocol"] == "crop" and opt["optimistic"] is True
    assert "OPTIMISTIC" in opt["method"]
    assert v["held_out_groups"] == card["n_source_photographs"] == 22
    assert v["images_tested"] == card["n_images"] == 62
    assert v["scaler"] == "fit on the training fold only"
    assert card["reliable"] is False
    # Held out by picture, the model is markedly worse than held out by view.
    assert v["accuracy"] < opt["accuracy"]


@needs_model
def test_the_card_figures_are_internally_consistent():
    v = _published_card()["validation"]
    per = v["per_class_recall"]
    assert sum(r["n"] for r in per.values()) == v["images_tested"]
    assert sum(r["correct"] for r in per.values()) == v["correct"]
    assert v["accuracy"] == round(v["correct"] / v["images_tested"], 4)
    assert sum(sum(row.values()) for row in v["confusion"].values()) == v["images_tested"]
    assert v["accuracy_ci95"] == M.wilson_interval(v["correct"], v["images_tested"])
    lo, hi = v["accuracy_ci95_by_source_photograph"]
    assert lo <= v["accuracy"] <= hi
    assert v["top3_accuracy"] >= v["top2_accuracy"] >= v["accuracy"]
    assert sum(b["n"] for b in v["accuracy_by_certainty"].values()) == v["images_tested"]
    # Chance for eight balanced guesses, and the always-commonest baselines
    # recomputed here from the per-class counts.
    from app.otoscopy.taxonomy import CATEGORY, URGENCY
    assert v["chance_level"] == 0.125
    for level, mapping in (("category", CATEGORY), ("urgency", URGENCY)):
        totals = {}
        for cls, r in per.items():
            totals[mapping[cls]] = totals.get(mapping[cls], 0) + r["n"]
        assert v["no_information_rate"][level] == round(max(totals.values()) / 62, 4)


@needs_model
def test_the_card_records_what_the_reproduction_measured():
    """Leave-one-source-picture-out, scaler inside each fold.

    17/62 here; the audit measured 16/62 with the scaler fit on all rows.
    Either way: about a quarter right, against 12.5% chance, and the
    unsafe patterns essentially never named.
    """
    v = _published_card()["validation"]
    assert v["correct"] == 17 and v["images_tested"] == 62
    assert v["accuracy_ci95"] == [0.179, 0.396]
    got = {c: (r["correct"], r["n"]) for c, r in v["per_class_recall"].items()}
    assert got == {
        "cerumen_impaction": (4, 10), "normal": (6, 9), "otitis_media": (5, 10),
        "perforation_attic": (1, 8), "perforation_central": (1, 6),
        "perforation_marginal": (0, 7), "retraction": (0, 4), "tumor": (0, 8),
    }
    # Confident when wrong.
    assert v["mean_top_probability"]["when_wrong"] >= 0.7


@needs_model
def test_the_published_card_belongs_to_the_shipped_artifact():
    import joblib

    bundle = joblib.load(M.ARTIFACT)
    assert _published_card()["training_fingerprint"] == M.training_fingerprint(
        bundle["ref_paths"], bundle["ref_y"])


@needs_model
def test_the_model_endpoint_serves_the_source_picture_figure():
    body = client.get("/api/otoscopy/model").json()
    card = _published_card()
    assert body["validation"]["protocol"] == "source_photograph"
    assert body["validation"]["accuracy"] == card["validation"]["accuracy"]
    assert body["validation_optimistic"]["optimistic"] is True
    assert body["reliable"] is False
    assert "Not a validated diagnosis" in body["reliability_note"]


def test_a_card_from_another_training_set_is_not_served(tmp_path):
    stale = tmp_path / "card.json"
    stale.write_text(json.dumps({
        "training_fingerprint": "0000000000000000",
        "validation": {"protocol": "source_photograph", "accuracy": 0.99},
    }), encoding="utf-8")
    bundle = {
        "ref_paths": ["otoscope_reference/normal/normal_0ae4c32e_00.jpg"],
        "ref_y": np.asarray(["normal"]),
        "card": {"validation": {
            "method": "leave-one-source-image-out; probabilities averaged",
            "accuracy": 0.4355, "top3_accuracy": 0.7258, "chance_level": 0.125}},
    }
    card = M._published_card(bundle, stale)
    # The view-level figure must never be served as the model's accuracy.
    assert card["validation"] is None
    assert card["validation_optimistic"]["accuracy"] == 0.4355
    assert card["validation_optimistic"]["optimistic"] is True
    assert "OPTIMISTIC" in card["validation_optimistic"]["method"]
    assert card["reliable"] is False
    assert "has not been measured" in card["reliability_note"]

    # The same artifact with no published card at all behaves identically.
    missing = M._published_card(bundle, tmp_path / "absent.json")
    assert missing["validation"] is None and missing["reliable"] is False


def test_a_matching_published_card_is_served(tmp_path):
    bundle = {"ref_paths": ["otoscope_reference/normal/normal_0ae4c32e_00.jpg"],
              "ref_y": np.asarray(["normal"]), "card": {}}
    published = tmp_path / "card.json"
    published.write_text(json.dumps({
        "training_fingerprint": M.training_fingerprint(bundle["ref_paths"],
                                                       bundle["ref_y"]),
        "validation": {"protocol": "source_photograph", "accuracy": 0.25},
    }), encoding="utf-8")
    card = M._published_card(bundle, published)
    assert card["validation"]["accuracy"] == 0.25
    assert card["reliable"] is False


def test_the_fingerprint_ignores_path_separators():
    a = M.training_fingerprint([r"otoscope_reference\normal\x_0ae4c32e_00.jpg"], ["normal"])
    b = M.training_fingerprint(["otoscope_reference/normal/x_0ae4c32e_00.jpg"], ["normal"])
    c = M.training_fingerprint(["otoscope_reference/normal/x_0ae4c32e_00.jpg"], ["tumor"])
    assert a == b != c


# ------------------------------------------------------------- evaluate ---

@needs_model
def test_evaluate_rewrites_only_the_card_never_the_artifact(monkeypatch, tmp_path):
    """Re-measuring must not refit or overwrite the shipped model."""
    import joblib

    bundle = joblib.load(M.ARTIFACT)
    rel, labels = list(bundle["ref_paths"]), [str(v) for v in bundle["ref_y"]]
    n_features = len(bundle["feature_names"])
    rng = np.random.default_rng(1)
    fake = (rng.normal(size=(len(rel), n_features)).astype(np.float32),
            np.asarray(labels), np.arange(len(rel)),
            [M.DATA_DIR / p.replace("\\", "/") for p in rel], [])
    monkeypatch.setattr(M, "load_dataset", lambda roots, augmented=True: fake)

    def no_dump(*args, **kwargs):
        raise AssertionError("evaluate() tried to write the artifact")

    monkeypatch.setattr(joblib, "dump", no_dump)
    before = M.ARTIFACT.stat().st_mtime_ns
    out = tmp_path / "card.json"
    card = M.evaluate(roots=[M.REFERENCE_DIR], card_path=out)
    assert M.ARTIFACT.stat().st_mtime_ns == before
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["training_fingerprint"] == card["training_fingerprint"] \
        == M.training_fingerprint(rel, labels)
    assert written["validation"]["protocol"] == "source_photograph"
    assert written["validation"]["held_out_groups"] == 22
    assert written["validation_optimistic"]["protocol"] == "crop"
    assert written["novelty_threshold"] == round(float(bundle["novelty_cut"]), 3)


@needs_model
def test_evaluate_refuses_data_the_artifact_was_not_trained_on(monkeypatch, tmp_path):
    fake = (np.zeros((2, 391), np.float32), np.asarray(["normal", "normal"]),
            np.asarray([0, 1]),
            [M.DATA_DIR / "otoscope_reference/normal/normal_deadbeef_00.jpg"] * 2, [])
    monkeypatch.setattr(M, "load_dataset", lambda roots, augmented=True: fake)
    out = tmp_path / "card.json"
    with pytest.raises(ValueError, match="retrain"):
        M.evaluate(roots=[M.REFERENCE_DIR], card_path=out)
    assert not out.exists()


# ------------------------------------------------------- the API result ---

@needs_model
def test_a_prediction_says_plainly_it_is_not_validated():
    result = M.predict(_reference_image())
    card = _published_card()
    v = card["validation"]
    assert result["reliable"] is False
    assert result["prediction"]["reliable"] is False
    assert result["prediction"]["kind"] == "closest_reference_pattern"
    assert result["prediction"]["statement"].startswith(
        f"Closest reference pattern: {result['prediction']['name']}.")
    assert "Not a validated diagnosis" in result["prediction"]["statement"]
    note = result["reliability_note"]
    assert note.startswith("Not a validated diagnosis")
    assert f"{v['correct']} of {v['images_tested']} views" in note
    assert f"{v['accuracy']:.0%}" in note
    assert "not the chance that it is right" in note
    assert result["disclaimer"].startswith("Closest reference pattern, not a diagnosis")
    band = result["prediction"]["certainty"]
    if band in v["accuracy_by_certainty"]:
        assert result["prediction"]["certainty_held_out"] == v["accuracy_by_certainty"][band]


@needs_model
def test_the_analyze_endpoint_carries_the_same_statement():
    ok, buf = cv2.imencode(".png", _reference_image("normal"))
    body = client.post("/api/otoscopy/analyze",
                       files={"file": ("ear.png", buf.tobytes(), "image/png")}).json()
    assert body["reliable"] is False
    assert body["prediction"]["kind"] == "closest_reference_pattern"
    assert body["model"]["validation"]["protocol"] == "source_photograph"


def test_the_note_names_the_patterns_it_misses_and_quotes_the_card():
    card = {"validation": {
        "protocol": "source_photograph", "correct": 3, "images_tested": 12,
        "accuracy": 0.25, "chance_level": 0.125, "top3_accuracy": 0.5,
        "accuracy_ci95": [0.09, 0.53], "urgency_accuracy": 0.4,
        "no_information_rate": {"urgency": 0.35},
        "mean_top_probability": {"when_wrong": 0.8},
        "accuracy_by_certainty": {"probable": {"correct": 2, "n": 9}},
        "per_class_recall": {
            "normal": {"correct": 3, "n": 4, "recall": 0.75},
            "tumor": {"correct": 0, "n": 4, "recall": 0.0},
            "perforation_attic": {"correct": 0, "n": 4, "recall": 0.0},
        },
    }}
    note = M.reliability_note(card)
    assert "3 of 12 views (25%, 95% CI 9%-53%; chance 12.5%)" in note
    assert "top three 50%" in note
    assert "against 35% for always answering the commonest band" in note
    assert "averaged 80% even when it was wrong" in note
    assert "right for 2 of 9 views" in note
    assert ("mass in the canal or middle ear (0/4) and "
            "attic perforation or retraction pocket (0/4)") in note
    assert "normal tympanic membrane (" not in note
    assert M.reliability_note({}).startswith("Not a validated diagnosis")
    assert "has not been measured" in M.reliability_note({"validation": None})


def test_predict_quotes_no_accuracy_figures_of_its_own():
    """Figures live on the card; a number in the code drifts out of date."""
    source = inspect.getsource(M.predict)
    assert not re.search(r"\d+\s?%", source), "predict() hard-codes a percentage"


# ----------------------------------------------------------- concordance ---

def test_concordance_speaks_of_a_closest_pattern_not_a_reading():
    analysis = {"rules": {"right": {"abg": {"value": 2}, "type": "Sensorineural"}},
                "immittance": {"right": {"tympanogram": {"type": "A"}}}}
    result = M.concordance({"prediction": {"label": "perforation_central"}},
                           analysis, "right")
    text = json.dumps(result)
    assert "read as" not in text
    assert "closest reference pattern" in text.lower()
    # When an unvalidated image reading disagrees with a measurement, the
    # reading is the first thing to re-check.
    assert all(c["action"].startswith("Re-examine the ear")
               for c in result["conflicts"])


def test_a_type_a_trace_never_corroborates_a_perforation():
    """'B with a LARGE ear-canal volume' contains the letter A; that is not Type A."""
    analysis = {"immittance": {"right": {"tympanogram": {"type": "A"}}}}
    for label in ("perforation_central", "perforation_marginal"):
        result = M.concordance({"prediction": {"label": label}}, analysis, "right")
        assert not result["agreements"]
        assert any("Tympanogram does not match" in c["title"]
                   for c in result["conflicts"])
    # Each type the taxonomy names still matches.
    for label, ttype in (("normal", "A"), ("cerumen_impaction", "B"),
                         ("cerumen_impaction", "A"), ("retraction", "C"),
                         ("perforation_attic", "C"), ("perforation_central", "B")):
        result = M.concordance(
            {"prediction": {"label": label}},
            {"immittance": {"right": {"tympanogram": {"type": ttype}}}}, "right")
        assert any(f"Type {ttype} is consistent" in a["title"]
                   for a in result["agreements"]), (label, ttype)


def test_an_unsafe_closest_pattern_asks_for_a_direct_look_then_referral():
    result = M.concordance({"prediction": {"label": "tumor"}},
                           {"rules": {"right": {"abg": {"value": 0}}}}, "right")
    unsafe = [c for c in result["conflicts"]
              if "regardless of the audiogram" in c["title"]]
    assert unsafe
    assert unsafe[0]["action"].startswith("Examine the ear directly now.")
    assert "Urgent ENT referral" in unsafe[0]["action"]
