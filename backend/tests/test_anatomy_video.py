"""Which anatomy clip a given ear gets, and — more importantly — which it does not.

Every case here is built by calling the real /api/analyze, never by
hand-assembling a dict that looks like its output. A previous panel in this
project passed its whole test suite while 500-ing in the browser, because the
tests and the code shared one wrong guess about a response shape.
"""
import pytest
from fastapi.testclient import TestClient

from app.clinical import anatomy_video as A
from app.main import app

client = TestClient(app)

AC = [250, 500, 1000, 2000, 4000, 8000]
BC = [250, 500, 1000, 2000, 4000]

# Tympanograms that produce each Jerger type, by the numbers the classifier
# actually keys on rather than by the type name.
FLAT_LARGE_ECV = {"tymp_pressure": 0, "tymp_compliance": 0.05, "tymp_ecv": 3.0}
FLAT_SMALL_ECV = {"tymp_pressure": 0, "tymp_compliance": 0.05, "tymp_ecv": 0.3}
FLAT_NORMAL_ECV = {"tymp_pressure": 0, "tymp_compliance": 0.05, "tymp_ecv": 1.2}
NEGATIVE_PRESSURE = {"tymp_pressure": -250, "tymp_compliance": 0.6, "tymp_ecv": 1.2}
SHALLOW_PEAK = {"tymp_pressure": 0, "tymp_compliance": 0.2, "tymp_ecv": 1.2}
DEEP_PEAK = {"tymp_pressure": 0, "tymp_compliance": 1.9, "tymp_ecv": 1.2}


def analyze(right_ac, right_bc=None, tymp=None, age=40, left_ac=15):
    ear = {"ac": {f: right_ac for f in AC}}
    if right_bc is not None:
        ear["bc"] = {f: right_bc for f in BC}
    if tymp:
        ear.update(tymp)
    body = {"patient": {"name": "T", "age": age, "sex": "male"},
            "right": ear,
            "left": ({"ac": {f: left_ac for f in AC},
                      "bc": {f: left_ac for f in BC}} if left_ac is not None
                     else {"ac": {}, "bc": {}})}
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def pick(analysis, side="right", otoscopy=None):
    r = client.post("/api/anatomy/video",
                    json={"analysis": analysis, "side": side,
                          "otoscopy": otoscopy})
    assert r.status_code == 200, r.text
    return r.json()


def oto(label, side="right"):
    """An otoscopy result in the shape the router actually stores."""
    return {"side": side, "prediction": {"label": label, "name": label}}


# ------------------------------------------------- the ear-canal volume ----
#
# A flat trace means three completely different things at three volumes, and
# the difference is what the patient is shown. Getting this wrong shows
# somebody a hole in their eardrum that they do not have.


@pytest.mark.parametrize("tymp,expected", [
    (FLAT_LARGE_ECV, "perforation"),
    (FLAT_SMALL_ECV, "wax_occlusion"),
    (FLAT_NORMAL_ECV, "effusion"),
])
def test_a_flat_tympanogram_is_read_through_the_canal_volume(tymp, expected):
    got = pick(analyze(55, 15, tymp))
    assert got["key"] == expected
    assert "ear-canal volume" in " ".join(got["because"])


@pytest.mark.parametrize("tymp,expected", [
    (NEGATIVE_PRESSURE, "retraction"),
    (SHALLOW_PEAK, "ossicular_fixation"),
    (DEEP_PEAK, "ossicular_discontinuity"),
])
def test_the_other_tympanogram_types_name_their_own_mechanism(tymp, expected):
    assert pick(analyze(45, 15, tymp))["key"] == expected


# --------------------------------------------------------- the audiogram ----


def test_a_conductive_loss_with_no_immittance_says_so_rather_than_guessing():
    got = pick(analyze(45, 15))
    assert got["key"] == "conductive_unspecified"
    assert "not yet identified" in " ".join(got["because"])


def test_a_sensorineural_loss_gets_the_cochlear_clip():
    assert pick(analyze(55, 55))["key"] == "sensorineural"


def test_an_ac_only_loss_is_still_typed_through_the_provisional_suffix():
    """rules.py emits "Sensorineural (provisional)" when BC was never tested."""
    a = analyze(50, None)
    assert a["rules"]["right"]["type"] == "Sensorineural (provisional)"
    assert pick(a)["key"] == "sensorineural"


def test_normal_hearing_gets_the_normal_pathway():
    assert pick(analyze(10, 10))["key"] == "normal"


# ------------------------------------------------------------- otoscopy ----


def test_otoscopy_names_the_mechanism_when_immittance_is_absent():
    got = pick(analyze(45, 15), otoscopy=oto("perforation_central"))
    assert got["key"] == "perforation"
    assert "otoscopy" in " ".join(got["because"])


def test_an_image_of_the_other_ear_never_drives_this_ear():
    """The stored result carries its own side. Filing it under the wrong ear
    would show a patient a perforation that is in their other ear."""
    got = pick(analyze(45, 15), side="right",
               otoscopy=oto("perforation_central", side="left"))
    assert got["key"] == "conductive_unspecified"
    assert "otoscopy" not in " ".join(got["because"])


def test_an_untagged_otoscopy_result_is_ignored_rather_than_assumed():
    got = pick(analyze(45, 15),
               otoscopy={"prediction": {"label": "perforation_central"}})
    assert got["key"] == "conductive_unspecified"


@pytest.mark.parametrize("label", ["normal", "tumor"])
def test_patterns_that_name_no_mechanism_do_not_choose_a_clip(label):
    """A normal drum names nothing, and a mass is a referral — not an
    animation to reassure somebody with."""
    assert pick(analyze(45, 15), otoscopy=oto(label))["key"] \
        == "conductive_unspecified"


def test_a_middle_ear_finding_shows_even_when_hearing_is_still_normal():
    """A retracted drum with thresholds inside normal limits is exactly the
    case worth explaining before it progresses."""
    assert pick(analyze(10, 10), otoscopy=oto("retraction"))["key"] == "retraction"


# ---------------------------------------------------------------- mixed ----


def test_a_mixed_loss_with_no_mechanism_gets_the_mixed_clip():
    got = pick(analyze(65, 40))
    assert got["ear_type"] == "Mixed"
    assert got["key"] == "mixed"
    assert got["plus_sensorineural"] is False


def test_a_mixed_loss_keeps_its_mechanism_and_flags_the_cochlear_half():
    """The middle-ear part is what a picture can show; the cochlear part has
    to be said out loud, so it must not be silently dropped."""
    got = pick(analyze(65, 40, FLAT_NORMAL_ECV))
    assert got["ear_type"] == "Mixed"
    assert got["key"] == "effusion"
    assert got["plus_sensorineural"] is True


# ------------------------------------------------------- refusing to guess ----


def test_an_untested_ear_gets_no_clip_at_all():
    """An animation for an ear nobody tested is a claim about a measurement
    that was never made."""
    got = pick(analyze(45, 15, left_ac=None), side="left")
    assert got["available"] is False
    assert got.get("key") is None
    assert "No thresholds" in got["reason"]


@pytest.mark.parametrize("body", [
    {}, {"analysis": None}, {"analysis": {}},
    {"analysis": {"rules": None}},
    {"analysis": {"rules": {"right": None}}, "side": "right"},
])
def test_a_missing_or_null_analysis_degrades_rather_than_crashing(body):
    r = client.post("/api/anatomy/video", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["available"] is False


def test_an_unknown_side_falls_back_to_the_right_ear():
    got = pick(analyze(45, 15), side="middle")
    assert got["side"] == "right"


# ----------------------------------------------------------- the promise ----


def test_every_selection_states_that_it_is_not_the_patients_own_ear():
    """The disclaimer travels in the payload, not as a caption the interface
    may forget to render — including on the refusal path."""
    for got in (pick(analyze(45, 15, FLAT_LARGE_ECV)),
                pick(analyze(55, 55)),
                pick(analyze(10, 10)),
                pick(analyze(45, 15, left_ac=None), side="left")):
        assert got["illustration_only"] is True
        assert "not a picture or scan of your own ear" in got["note"]


def test_every_clip_in_the_catalogue_is_complete():
    body = client.get("/api/anatomy/reference").json()
    assert len(body["videos"]) == len(A.VIDEOS)
    for clip in body["videos"]:
        for field in ("key", "file", "poster", "title", "patient_title",
                      "shows", "plain", "mechanism"):
            assert clip.get(field), f"{clip.get('key')} is missing {field}"
        assert clip["file"] == f"{clip['key']}.mp4"


def test_every_reachable_key_exists_in_the_catalogue():
    """A selector that can name a clip the catalogue does not hold would be a
    KeyError in front of a patient."""
    reachable = (set(A._TYMP_MECHANISM.values())
                 | set(A._OTOSCOPY_MECHANISM.values())
                 | set(A._TYPE_B_BY_VOLUME.values())
                 | {"normal", "sensorineural", "mixed", "conductive_unspecified"})
    assert reachable <= set(A.VIDEOS), reachable - set(A.VIDEOS)


def test_the_patient_facing_copy_names_no_disease():
    """Naming a disease from an animation is a diagnosis this module has no
    basis for. Mechanisms only."""
    blob = " ".join(f"{v['patient_title']} {v['plain']}" for v in A.VIDEOS.values()).lower()
    for disease in ("otosclerosis", "cholesteatoma", "meniere", "otitis media",
                    "schwannoma", "presbycusis"):
        assert disease not in blob, f"{disease} named in patient-facing copy"
