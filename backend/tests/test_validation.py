"""Tests for the expert-label validation harness."""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.validation import (
    normalize_grade,
    normalize_pattern,
    normalize_type,
    validate_csv,
)

client = TestClient(app)
SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.mark.parametrize("raw,expected", [
    ("noise notch", "noise_notch_4k"),
    ("Noise Notch (4 kHz)", "noise_notch_4k"),
    ("noise_notch_4k", "noise_notch_4k"),
    ("4k notch", "noise_notch_4k"),
    ("ski slope", "ski_slope"),
    ("Sloping high frequency", "sloping_high_frequency"),
    ("cookie bite", "cookie_bite"),
    ("corner", "corner_audiogram"),
    ("flat", "flat"),
])
def test_pattern_aliases_normalize(raw, expected):
    assert normalize_pattern(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("mild", "Mild hearing loss"),
    ("Moderate hearing loss", "Moderate hearing loss"),
    ("moderately severe", "Moderately severe hearing loss"),
    ("PROFOUND", "Profound hearing loss"),
    ("normal", "Normal hearing"),
])
def test_grade_aliases_normalize(raw, expected):
    assert normalize_grade(raw) == expected


def test_moderately_severe_is_not_matched_as_moderate():
    """Substring order matters — 'moderately severe' must win over 'moderate'."""
    assert normalize_grade("moderately severe hearing loss") == \
        "Moderately severe hearing loss"


@pytest.mark.parametrize("raw,expected", [
    ("conductive", "Conductive"),
    ("Sensorineural", "Sensorineural"),
    ("mixed loss", "Mixed"),
    ("normal", "Normal"),
])
def test_type_aliases_normalize(raw, expected):
    assert normalize_type(raw) == expected


def test_empty_labels_return_none():
    assert normalize_grade("") is None
    assert normalize_type(None) is None
    assert normalize_pattern("") is None


def test_validation_on_bundled_labelled_sample():
    raw = (SAMPLES / "validation_labelled.csv").read_bytes()
    result = validate_csv(raw)
    assert result["cases"] == 12

    grade = result["metrics"]["grade"]
    ear_type = result["metrics"]["type"]
    # Degree and type are deterministic implementations of the guidelines, so
    # agreement with correctly-labelled cases must be perfect.
    assert grade["agreement"] == 100.0, grade["disagreements"]
    assert grade["cohens_kappa"] == 1.0
    assert ear_type["agreement"] == 100.0, ear_type["disagreements"]

    disability = result["metrics"]["disability"]
    assert disability["mean_absolute_error_pct"] < 0.5
    assert "kappa" in result["summary"].lower() or "κ" in result["summary"]


def test_validation_reports_pattern_agreement_when_model_present():
    raw = (SAMPLES / "validation_labelled.csv").read_bytes()
    result = validate_csv(raw)
    pattern = result["metrics"].get("pattern")
    if pattern is None:
        pytest.skip("model not trained")
    assert 0 <= pattern["agreement"] <= 100
    assert -1 <= pattern["cohens_kappa"] <= 1
    assert pattern["kappa_interpretation"] in (
        "worse than chance", "slight", "fair", "moderate", "substantial",
        "almost perfect")
    assert len(pattern["confusion_matrix"]) == len(pattern["labels"])


def test_validation_states_the_synthetic_caveat():
    result = validate_csv((SAMPLES / "validation_labelled.csv").read_bytes())
    assert "synthetic" in result["caveat"].lower()


def test_unlabelled_csv_says_so_rather_than_inventing_metrics():
    csv = ("name,r_ac_250,r_ac_500,r_ac_1000,r_ac_2000,r_ac_4000,r_ac_8000\n"
           "A,10,10,10,10,10,10\n B,20,20,20,20,20,20\n")
    result = validate_csv(csv.encode())
    assert result["metrics"] == {}
    assert "No expert labels found" in result["summary"]


def test_disagreements_are_listed_for_review():
    """A deliberately mislabelled row must show up as a disagreement."""
    csv = (
        "name,expert_grade,r_ac_250,r_ac_500,r_ac_1000,r_ac_2000,r_ac_4000,r_ac_8000,"
        "l_ac_250,l_ac_500,l_ac_1000,l_ac_2000,l_ac_4000,l_ac_8000\n"
        "Right,Normal hearing,10,10,10,10,10,10,10,10,10,10,10,10\n"
        "Wrong,Profound hearing loss,10,10,10,10,10,10,10,10,10,10,10,10\n"
    )
    result = validate_csv(csv.encode())
    grade = result["metrics"]["grade"]
    assert grade["agreement"] == 50.0
    assert grade["disagreements"][0]["expert"] == "Profound hearing loss"
    assert grade["disagreements"][0]["predicted"] == "Normal hearing"


def test_validate_endpoint():
    raw = (SAMPLES / "validation_labelled.csv").read_bytes()
    r = client.post("/api/validate",
                    files={"file": ("v.csv", io.BytesIO(raw), "text/csv")})
    assert r.status_code == 200
    assert r.json()["cases"] == 12


def test_validate_endpoint_rejects_garbage():
    r = client.post("/api/validate",
                    files={"file": ("v.csv", io.BytesIO(b"\x00\x01\x02"), "text/csv")})
    assert r.status_code == 400


# ------------------------------------------------- bulk photo ingestion ----

def test_batch_photos_digitizes_and_triages():
    photos = [SAMPLES / "audiogram_photo_1.png", SAMPLES / "audiogram_photo_2.png"]
    if not all(p.exists() for p in photos):
        pytest.skip("sample photos not generated")
    files = [("files", (p.name, io.BytesIO(p.read_bytes()), "image/png")) for p in photos]
    r = client.post("/api/batch-photos", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["failed"] == []
    assert body["worklist"]["total"] == 2
    assert body["performance"]["photos"] == 2
    assert all("triage" in c for c in body["results"])
    # Photo 1 is the noise-notch chart; its thresholds must have come through.
    assert body["results"][0]["right"]["pta"] is not None


def test_batch_photos_reports_unreadable_files_without_failing():
    files = [("files", ("junk.png", io.BytesIO(b"not-an-image"), "image/png"))]
    body = client.post("/api/batch-photos", files=files).json()
    assert body["count"] == 0
    assert len(body["failed"]) == 1
    assert body["failed"][0]["file"] == "junk.png"


def test_bulk_reports_zip():
    from app.services.demo_cases import DEMO_CASES
    analysis = client.post("/api/analyze", json=DEMO_CASES[0]["record"]).json()
    r = client.post("/api/bulk-reports", json={"cases": [
        {"name": "One", "analysis": analysis},
        {"name": "Two", "analysis": analysis},
    ]})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.content[:2] == b"PK"

    import zipfile
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert len(names) == 2
        assert zf.read(names[0])[:5] == b"%PDF-"


def test_bulk_reports_requires_cases():
    assert client.post("/api/bulk-reports", json={"cases": []}).status_code == 400
