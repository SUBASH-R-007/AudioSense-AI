"""Otoscopy: features, honest validation, retrieval and the battery cross-check."""
import io

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.otoscopy import features as F
from app.otoscopy import model as M
from app.otoscopy.taxonomy import (
    CATEGORY, CLASSES, CONDUCTIVE_CLASSES, TAXONOMY, URGENCY,
)

client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not M.model_available(),
    reason="otoscopy model not trained — run python -m scripts.train_otoscopy",
)


def a_reference_image(label="otitis_media"):
    found, _ = M.scan_directory(M.REFERENCE_DIR)
    paths = found.get(label) or []
    if not paths:
        pytest.skip(f"no reference images for {label}")
    return cv2.imread(str(paths[0]), cv2.IMREAD_COLOR)


def as_png_bytes(image):
    ok, buf = cv2.imencode(".png", image)
    assert ok
    return buf.tobytes()


# ------------------------------------------------------------ taxonomy ---

def test_every_class_has_clinical_guidance():
    for label in CLASSES:
        entry = TAXONOMY[label]
        assert entry["recommended_tests"]
        assert entry["expected_tympanogram"]
        assert entry["referral"]
        assert label in CATEGORY and label in URGENCY


def test_unsafe_patterns_are_marked_urgent():
    for label in ("perforation_attic", "tumor"):
        assert URGENCY[label] == "urgent"
        assert TAXONOMY[label]["red_flags"]


def test_normal_is_the_only_class_without_an_expected_gap():
    assert "normal" not in CONDUCTIVE_CLASSES
    assert "retraction" not in CONDUCTIVE_CLASSES


# ------------------------------------------------------------ features ---

def test_feature_vector_length_matches_the_declared_names():
    vector, _ = F.extract(a_reference_image())
    assert len(vector) == len(F.FEATURE_NAMES)


def test_features_are_deterministic():
    image = a_reference_image()
    first, _ = F.extract(image)
    second, _ = F.extract(image)
    assert np.array_equal(first, second)


def test_features_survive_a_degenerate_image():
    """A solid black frame must not raise or produce NaN."""
    vector, _ = F.extract(np.zeros((80, 80, 3), np.uint8))
    assert len(vector) == len(F.FEATURE_NAMES)
    assert np.isfinite(vector).all()


def test_field_of_view_crops_a_disc_out_of_a_black_surround():
    frame = np.zeros((400, 400, 3), np.uint8)
    cv2.circle(frame, (200, 200), 120, (180, 150, 150), -1)
    crop, mask = F.field_of_view(frame)
    assert crop.shape[0] < 400 and crop.shape[1] < 400
    assert mask.any()


def test_redness_separates_an_inflamed_drum_from_a_pale_one():
    red = np.full((200, 200, 3), (60, 60, 200), np.uint8)   # BGR
    pale = np.full((200, 200, 3), (190, 185, 185), np.uint8)
    _, red_named = F.extract(red)
    _, pale_named = F.extract(pale)
    assert red_named["erythema"] > pale_named["erythema"]


def test_a_dark_centre_registers_as_a_central_defect():
    drum = np.full((240, 240, 3), (170, 170, 190), np.uint8)
    cv2.circle(drum, (120, 120), 40, (10, 10, 10), -1)
    _, named = F.extract(drum)
    assert named["defect_size"] > 0.02
    assert named["defect_offset"] < 0.4       # near the centre


def test_a_superior_defect_registers_above_the_midline():
    drum = np.full((240, 240, 3), (170, 170, 190), np.uint8)
    cv2.circle(drum, (120, 60), 30, (10, 10, 10), -1)
    _, named = F.extract(drum)
    assert named["defect_superior"] > 0.1


# ------------------------------------------------------------- quality ---

def test_a_blurred_image_is_rejected_rather_than_labelled():
    sharp = a_reference_image()
    blurred = cv2.GaussianBlur(sharp, (31, 31), 0)
    assert F.image_quality(blurred)["blur"] < F.image_quality(sharp)["blur"]
    assert not F.image_quality(blurred)["usable"]


def test_a_black_frame_is_reported_as_under_exposed():
    quality = F.image_quality(np.zeros((200, 200, 3), np.uint8))
    assert not quality["usable"]
    assert any("exposed" in issue for issue in quality["issues"])


def test_decode_rejects_data_that_is_not_an_image():
    assert F.decode(b"this is not a picture") is None
    assert F.decode(b"") is None


# ----------------------------------------------------------- inference ---

def test_prediction_returns_a_ranked_differential_over_all_classes():
    result = M.predict(a_reference_image())
    assert len(result["ranked"]) == len(result["model"]["classes"])
    probabilities = [r["probability"] for r in result["ranked"]]
    assert probabilities == sorted(probabilities, reverse=True)
    assert sum(probabilities) == pytest.approx(1.0, abs=0.01)
    assert len(result["differential"]) == 3


def test_category_and_urgency_probabilities_are_rollups_of_the_classes():
    result = M.predict(a_reference_image())
    assert sum(c["probability"] for c in result["category"]["ranked"]) \
        == pytest.approx(1.0, abs=0.01)
    assert sum(u["probability"] for u in result["urgency"]["ranked"]) \
        == pytest.approx(1.0, abs=0.01)


def test_retrieval_returns_displayable_reference_urls():
    result = M.predict(a_reference_image())
    assert result["reference_matches"]
    for match in result["reference_matches"]:
        assert match["image"].startswith("/api/otoscopy/image/")
        assert match["label"] in CLASSES


def test_an_unreadable_image_is_never_called_confident():
    noise = np.random.RandomState(0).randint(0, 255, (200, 200, 3), np.uint8)
    blurred = cv2.GaussianBlur(noise, (31, 31), 0)
    result = M.predict(blurred)
    assert result["prediction"]["certainty"] in (
        "unreliable", "uncertain", "out-of-distribution")


def test_evidence_quotes_measurements_the_model_actually_saw():
    result = M.predict(a_reference_image())
    assert result["evidence"]
    assert any("cone of light" in line.lower() or "reflex" in line.lower()
               for line in result["evidence"])


# ---------------------------------------------------------- model card ---

def test_model_card_reports_validation_honestly():
    card = M.model_card()
    validation = card["validation"]
    assert "leave-one-source-image-out" in validation["method"]
    assert 0 < validation["accuracy"] <= 1
    # The claim that matters: better than guessing, and stated as such.
    assert validation["accuracy"] > validation["chance_level"]
    assert validation["top3_accuracy"] >= validation["accuracy"]


def test_model_card_records_where_its_training_data_came_from():
    card = M.model_card()
    assert card["n_images"] > 0
    assert card["sources"]
    assert "kaggle_present" in card


# ---------------------------------------------------- dataset handling ---

def test_public_dataset_folder_names_map_onto_our_taxonomy():
    for alias, target in M.DATASET_ALIASES.items():
        assert target in TAXONOMY, f"{alias} maps to unknown class {target}"


def test_unknown_folder_names_are_reported_not_guessed():
    assert M._canonical("some unlabelled folder") is None
    assert M._canonical("Acute Otitis Media") == "otitis_media"
    assert M._canonical("earwax_plug") == "cerumen_impaction"


def test_augmentation_preserves_image_shape():
    image = a_reference_image()
    variants = M.augment(image)
    assert len(variants) == len(M.AUG_ROTATIONS) * len(M.AUG_GAINS) * len(M.AUG_FLIP)
    assert all(v.shape == image.shape for v in variants)


# --------------------------------------------------------- concordance ---

def perforation_prediction():
    return {"prediction": {"label": "perforation_central"}}


def test_a_perforation_with_a_matching_gap_is_corroborated():
    analysis = {"rules": {"right": {"abg": {"value": 30}, "type": "Conductive"}},
                "immittance": {"right": {"tympanogram": {"type": "B"}}}}
    result = M.concordance(perforation_prediction(), analysis, "right")
    assert result["available"]
    assert len(result["agreements"]) == 2
    assert not result["conflicts"]


def test_a_perforation_with_no_air_bone_gap_is_a_conflict():
    analysis = {"rules": {"right": {"abg": {"value": 2}, "type": "Sensorineural"}}}
    result = M.concordance(perforation_prediction(), analysis, "right")
    assert result["conflicts"]
    assert "no gap" in result["conflicts"][0]["title"].lower()


def test_a_normal_drum_with_a_conductive_loss_is_a_conflict():
    analysis = {"rules": {"right": {"abg": {"value": 30}, "type": "Conductive"}}}
    result = M.concordance({"prediction": {"label": "normal"}}, analysis, "right")
    assert any("normal-looking drum" in c["title"] for c in result["conflicts"])


def test_attic_disease_demands_referral_whatever_the_audiogram_says():
    """Early cholesteatoma is frequently silent on pure tones."""
    normal_hearing = {"rules": {"right": {"abg": {"value": 0}, "type": "Normal"}}}
    result = M.concordance({"prediction": {"label": "perforation_attic"}},
                           normal_hearing, "right")
    assert any("regardless of the audiogram" in c["title"] for c in result["conflicts"])


def test_no_audiometry_means_nothing_to_reconcile():
    result = M.concordance(perforation_prediction(), None, "right")
    assert result["available"] is False


# ----------------------------------------------------------- endpoints ---

def test_analyze_endpoint_accepts_an_upload():
    files = {"file": ("ear.png", as_png_bytes(a_reference_image()), "image/png")}
    response = client.post("/api/otoscopy/analyze", files=files,
                           data={"side": "left"})
    assert response.status_code == 200
    body = response.json()
    assert body["side"] == "left"
    assert body["prediction"]["label"] in CLASSES
    assert body["concordance"]["available"] is False


def test_analyze_endpoint_rejects_a_non_image():
    files = {"file": ("notes.txt", b"not an image", "text/plain")}
    assert client.post("/api/otoscopy/analyze", files=files).status_code == 400


def test_analyze_endpoint_rejects_an_empty_upload():
    files = {"file": ("empty.png", b"", "image/png")}
    assert client.post("/api/otoscopy/analyze", files=files).status_code == 400


def test_reference_atlas_lists_every_class_with_images():
    body = client.get("/api/otoscopy/reference").json()
    assert {c["label"] for c in body["classes"]} == set(CLASSES)
    assert body["total_images"] > 0
    assert all(c["count"] > 0 for c in body["classes"])


def test_reference_images_are_served_and_path_traversal_is_refused():
    body = client.get("/api/otoscopy/reference").json()
    url = next(c["images"][0] for c in body["classes"] if c["images"])
    assert client.get(url).status_code == 200
    assert client.get("/api/otoscopy/image/normal/..%2f..%2fdataset.csv"
                      ).status_code == 404
    assert client.get("/api/otoscopy/image/not_a_class/x.png").status_code == 404


def test_model_endpoint_states_its_limits():
    body = client.get("/api/otoscopy/model").json()
    assert body["trained"] is True
    assert body["limits"]
    assert "fetch_otoscope_dataset" in body["improve"]
