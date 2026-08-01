"""Cross-modal linkage: history, image, immittance and audiogram reconciled."""
import pytest
from fastapi.testclient import TestClient

from app.clinical import linkage, symptoms as S
from app.clinical.symptom_kb import (
    DISEASES, OTOSCOPY_LINKS, REFLEX_LINKS, TYMPANOGRAM_LINKS,
)
from app.main import app
from app.otoscopy.taxonomy import CLASSES

client = TestClient(app)


def oto(label, name=None):
    return {"prediction": {"label": label, "name": name or label.replace("_", " ")}}


def audiogram(pta=40, ear_type="Conductive", left_pta=None, tymp=None,
              reflex_pattern=None, oae_present=None):
    left = pta if left_pta is None else left_pta
    out = {"rules": {
        "right": {"ac_pta": {"value": pta}, "type": ear_type,
                  "abg": {"value": 30 if "onductive" in ear_type else 0}},
        "left": {"ac_pta": {"value": left}, "type": ear_type,
                 "abg": {"value": 30 if "onductive" in ear_type else 0}},
    }}
    if tymp:
        entry = {"tympanogram": {"type": tymp, "interpretation": "test",
                                 "ecv_flag": "normal", "suggests_conductive": True}}
        if reflex_pattern:
            entry["reflexes"] = {"pattern": reflex_pattern}
        out["immittance"] = {"right": entry, "left": entry}
    if oae_present is not None:
        out["oae"] = {"right": {"present_freqs": [2000] if oae_present else []},
                      "left": {"present_freqs": [2000] if oae_present else []}}
    return out


# ==================================================== otoscopy <-> symptoms

def test_image_and_history_confirming_each_other_is_reported():
    """The classifier is weak; two methods agreeing is what redeems it."""
    assessment = S.assess(age=30, symptoms=["ear pain", "fever", "hearing loss"])
    result = linkage.otoscopy_vs_symptoms(
        oto("otitis_media", "Acute otitis media / middle-ear effusion"), assessment)
    assert result["available"]
    assert result["verdict"] == "consistent"
    assert any("same condition" in a["title"] for a in result["agreements"])


def test_symptoms_the_appearance_cannot_explain_are_a_conflict():
    assessment = S.assess(age=30, symptoms=["ear pain", "fever"])
    result = linkage.otoscopy_vs_symptoms(oto("normal", "Normal tympanic membrane"),
                                          assessment)
    assert result["verdict"] == "conflicting"
    conflict = result["conflicts"][0]
    assert "does not explain" in conflict["title"]
    assert conflict["action"]


def test_a_normal_drum_with_an_unremarkable_history_is_stated_positively():
    """Silence here would read as 'nothing to say' rather than 'excluded'."""
    assessment = S.assess(age=30, symptoms=["ringing", "difficulty in noise"])
    result = linkage.otoscopy_vs_symptoms(oto("normal"), assessment)
    assert result["verdict"] == "consistent"
    assert any("consistent with the history" in a["title"]
               for a in result["agreements"])


def test_hearing_loss_alone_does_not_conflict_with_a_normal_drum():
    """A normal drum is exactly what a sensorineural loss looks like."""
    assessment = S.assess(age=70, symptoms=["hearing loss", "difficulty in noise"])
    result = linkage.otoscopy_vs_symptoms(oto("normal"), assessment)
    assert result["conflicts"] == []


def test_silent_attic_disease_is_flagged_rather_than_reassured():
    """Early cholesteatoma is frequently symptomless — absence must not comfort."""
    assessment = S.assess(age=40, symptoms=["ringing"])
    result = linkage.otoscopy_vs_symptoms(oto("perforation_attic"), assessment)
    assert any("no supporting symptoms" in c["title"] for c in result["conflicts"])


def test_expected_symptoms_are_reported_with_their_presence():
    assessment = S.assess(age=30, symptoms=["ear discharge", "hearing loss"])
    result = linkage.otoscopy_vs_symptoms(oto("perforation_central"), assessment)
    flags = {s["label"]: s["present"] for s in result["expected_symptoms"]}
    assert any(flags.values()) and not all(flags.values())


def test_otoscopy_link_needs_both_inputs():
    assert linkage.otoscopy_vs_symptoms(None, {})["available"] is False
    assert linkage.otoscopy_vs_symptoms(oto("normal"), None)["available"] is False


# ================================================== symptoms <-> audiogram

def leading_kb_disease(assessment):
    return next(d for d in assessment["differential"] if d["key"] in DISEASES)


def test_degree_inside_the_expected_range_is_an_agreement():
    assessment = S.assess(age=70, symptoms=["gradual hearing loss", "difficulty in noise",
                                            "ringing"])
    disease = DISEASES[leading_kb_disease(assessment)["key"]]
    lo, hi = disease["expected_pta"]
    mid = (lo + hi) / 2
    result = linkage.symptoms_vs_audiogram(
        assessment, audiogram(pta=mid, ear_type="Sensorineural"))
    assert any("Degree of loss fits" in a["title"] for a in result["agreements"])


@pytest.mark.parametrize("offset,expected", [(3, "borderline"), (10, "conflict")])
def test_degree_just_outside_is_borderline_and_far_outside_is_a_conflict(offset, expected):
    """A few decibels past the edge is test-retest noise, not a contradiction —
    but it must not be described as inside the range either."""
    assessment = S.assess(age=70, symptoms=["gradual hearing loss", "ringing",
                                            "difficulty in noise"])
    disease = DISEASES[leading_kb_disease(assessment)["key"]]
    hi = disease["expected_pta"][1]
    result = linkage.symptoms_vs_audiogram(
        assessment, audiogram(pta=hi + offset, ear_type="Sensorineural"))
    titles = " ".join(f["title"] for f in result["conflicts"] + result["agreements"])
    if expected == "borderline":
        assert "borderline" in titles
        assert "sits inside" not in " ".join(
            f["detail"] for f in result["agreements"])
    else:
        assert "worse than" in titles


def test_a_bilateral_disease_with_asymmetric_ears_is_a_conflict():
    assessment = S.assess(age=70, symptoms=["gradual hearing loss", "ringing",
                                            "difficulty in noise"])
    result = linkage.symptoms_vs_audiogram(
        assessment, audiogram(pta=30, left_pta=70, ear_type="Sensorineural"))
    assert any("symmetrical" in c["title"] for c in result["conflicts"])


def test_a_unilateral_disease_with_symmetric_ears_is_a_conflict():
    assessment = S.assess(age=45, symptoms=["vertigo", "ringing", "fullness",
                                            "hearing comes and goes"])
    assert leading_kb_disease(assessment)["key"] == "menieres"
    result = linkage.symptoms_vs_audiogram(
        assessment, audiogram(pta=40, left_pta=40, ear_type="Sensorineural"))
    assert any("one-sided" in c["title"] for c in result["conflicts"])


def test_reported_loss_with_normal_thresholds_is_surfaced():
    """The presentation pure tones are least able to explain."""
    assessment = S.assess(age=30, symptoms=["hearing loss", "difficulty in noise"])
    result = linkage.symptoms_vs_audiogram(
        assessment, audiogram(pta=10, ear_type="Normal"))
    assert any("thresholds are normal" in c["title"] for c in result["conflicts"])


def test_significant_loss_the_patient_did_not_report_is_surfaced():
    assessment = S.assess(age=70, symptoms=["ringing"])
    result = linkage.symptoms_vs_audiogram(
        assessment, audiogram(pta=55, ear_type="Sensorineural"))
    assert any("not reported by the patient" in c["title"]
               for c in result["conflicts"])


def test_correlating_against_a_lower_ranked_entry_says_so():
    """Only the disease reference predicts thresholds; the guide does not.

    When the leading possibility is a guide entry, correlation falls to the
    best entry that HAS a prediction — and must declare that, or the panel
    would appear to be reasoning about a diagnosis the page never showed as
    the leader.
    """
    assessment = S.assess(age=40, symptoms=["pain when chewing", "ear pain"])
    assert assessment["differential"][0]["key"] not in DISEASES
    result = linkage.symptoms_vs_audiogram(assessment, audiogram())
    assert result["available"]
    assert result["diagnosis_rank"] > 1
    assert assessment["differential"][0]["name"] in result["rank_note"]


def test_correlating_against_the_leader_carries_no_rank_note():
    assessment = S.assess(age=45, symptoms=["vertigo", "ringing", "fullness",
                                            "hearing comes and goes"])
    result = linkage.symptoms_vs_audiogram(
        assessment, audiogram(pta=40, left_pta=70, ear_type="Sensorineural"))
    assert result["diagnosis_rank"] == 1
    assert result["rank_note"] == ""


def test_no_disease_reference_entry_at_all_reports_unavailable():
    result = linkage.symptoms_vs_audiogram(
        {"differential": [{"key": "guide:otitis externa", "name": "Otitis externa"}]},
        audiogram())
    assert result["available"] is False


def test_audiogram_link_needs_both_inputs():
    assert linkage.symptoms_vs_audiogram(None, audiogram())["available"] is False
    assert linkage.symptoms_vs_audiogram({}, None)["available"] is False


# ================================================= immittance <-> diseases

@pytest.mark.parametrize("jerger", ["A", "As", "Ad", "Add", "B", "C", "D", "E"])
def test_every_tympanogram_type_links_to_diseases(jerger):
    """All eight types from the immittance reference, not just the abnormal ones."""
    entry = TYMPANOGRAM_LINKS[jerger]
    assert entry["label"] and entry["meaning"]
    assert entry["supports"] or entry["also_consider"]
    result = linkage.immittance_vs_diseases(audiogram(tymp=jerger))
    assert result["available"]
    assert result["type"] == jerger
    assert len(result["all_types"]) == 8


def test_type_a_removes_the_conductive_differential():
    """The 'argues against' half is the one usually left out."""
    result = linkage.immittance_vs_diseases(audiogram(tymp="A"))
    against = {d["key"] for d in result["argues_against"]}
    assert {"etd", "cholesteatoma", "mastoiditis"} <= against


def test_type_b_splits_on_ear_canal_volume():
    normal = audiogram(tymp="B")
    large = audiogram(tymp="B")
    large["immittance"]["right"]["tympanogram"]["ecv_flag"] = "large"

    normal_first = linkage.immittance_vs_diseases(normal)["also_consider"][0]
    large_first = linkage.immittance_vs_diseases(large)["also_consider"][0]
    assert "effusion" in normal_first.lower()
    assert "perforation" in large_first.lower()


def test_a_supported_disease_on_the_differential_is_an_agreement():
    assessment = S.assess(age=30, symptoms=["blocked ear", "popping", "muffled"])
    result = linkage.immittance_vs_diseases(audiogram(tymp="C"), assessment)
    assert any("supports" in a["title"] for a in result["agreements"])


def test_a_contradicted_disease_on_the_differential_is_a_conflict():
    assessment = S.assess(age=30, symptoms=["blocked ear", "popping", "muffled"])
    result = linkage.immittance_vs_diseases(audiogram(tymp="A"), assessment)
    assert any("argues against" in c["title"] for c in result["conflicts"])


def test_reflexes_absent_with_emissions_present_points_beyond_the_cochlea():
    record = audiogram(tymp="A", reflex_pattern="absent", oae_present=True,
                       ear_type="Sensorineural")
    result = linkage.immittance_vs_diseases(record)
    assert any("emissions are present" in r["when"] for r in result["reflex_findings"])


def test_reflexes_present_with_a_severe_loss_is_flagged():
    record = audiogram(pta=75, tymp="A", reflex_pattern="present",
                       ear_type="Sensorineural")
    result = linkage.immittance_vs_diseases(record)
    assert any("severe loss" in r["when"] for r in result["reflex_findings"])


def test_no_tympanogram_reports_unavailable():
    assert linkage.immittance_vs_diseases(audiogram())["available"] is False
    assert linkage.immittance_vs_diseases(None)["available"] is False


# ============================================================== assembly

def test_conflicts_sort_above_agreements_and_drive_the_headline():
    """A page of green ticks must not bury the one line that disagrees."""
    assessment = S.assess(age=30, symptoms=["ear pain", "fever"])
    result = linkage.link_case(
        analysis=audiogram(tymp="B"), assessment=assessment, otoscopy=oto("normal"))
    assert result["verdict"] == "conflicting"
    assert result["conflict_count"] >= 1
    assert result["headline"].startswith(result["top_conflicts"][0]["title"])


def test_missing_inputs_are_named_so_the_user_knows_what_to_add():
    result = linkage.link_case(analysis=None, assessment=None, otoscopy=None)
    assert result["verdict"] == "insufficient"
    assert len(result["missing_inputs"]) == 3
    assert result["links_available"] == []


def test_a_fully_recorded_case_reports_every_link():
    assessment = S.assess(age=30, symptoms=["ear pain", "fever", "hearing loss",
                                            "blocked ear"])
    result = linkage.link_case(
        analysis=audiogram(pta=30, tymp="B"), assessment=assessment,
        otoscopy=oto("otitis_media", "Acute otitis media / middle-ear effusion"))
    assert set(result["links_available"]) == {
        "otoscopy_symptoms", "otoscopy_audiogram",
        "symptoms_audiogram", "immittance_diseases",
    }
    assert result["agreement_count"] > 0


def test_otoscopy_against_the_audiogram_appears_in_the_linked_set():
    """It lived only on the otoscopy page before; the dashboard needs it too."""
    result = linkage.link_case(
        analysis=audiogram(pta=40, ear_type="Conductive", tymp="B"),
        otoscopy=oto("normal", "Normal tympanic membrane"))
    link = result["links"]["otoscopy_audiogram"]
    assert link["available"]
    assert any("normal-looking drum" in c["title"] for c in link["conflicts"])


def test_otoscopy_audiogram_link_needs_both_inputs():
    assert linkage.otoscopy_vs_audiogram(None, audiogram(), "right")["available"] is False
    assert linkage.otoscopy_vs_audiogram(oto("normal"), None, "right")["available"] is False


# ============================================================== endpoints

def test_linkage_endpoint_accepts_partial_input():
    body = client.post("/api/linkage", json={"assessment": S.assess(
        age=30, symptoms=["ear pain"])}).json()
    assert body["verdict"] == "insufficient"
    assert body["missing_inputs"]


def test_linkage_endpoint_accepts_an_entirely_empty_case():
    body = client.post("/api/linkage", json={}).json()
    assert body["links_available"] == []


def test_linkage_reference_exposes_every_type_and_pattern():
    body = client.get("/api/linkage/reference").json()
    assert {t["type"] for t in body["tympanogram_types"]} == {"A", "As", "Ad", "Add", "B", "C", "D", "E"}
    assert {p["pattern"] for p in body["otoscopy_patterns"]} == set(CLASSES)


# ================================================== knowledge base shape

def test_every_otoscopy_class_has_a_linkage_rule():
    assert set(OTOSCOPY_LINKS) == set(CLASSES)


def test_linkage_rules_reference_known_symptoms_and_diseases():
    known_symptoms = set(S.SYMPTOM_SYNONYMS)
    for label, link in OTOSCOPY_LINKS.items():
        for key in link["expects"] + link["unexplained"]:
            assert key in known_symptoms, f"{label} references unknown symptom {key}"
    for jerger, link in TYMPANOGRAM_LINKS.items():
        for key in link["supports"] + link["argues_against"]:
            assert key in DISEASES, f"Type {jerger} references unknown disease {key}"
    for name, rule in REFLEX_LINKS.items():
        for key in rule["supports"]:
            assert key in DISEASES, f"{name} references unknown disease {key}"


def test_no_disease_is_both_supported_and_contradicted_by_one_type():
    for jerger, link in TYMPANOGRAM_LINKS.items():
        overlap = set(link["supports"]) & set(link["argues_against"])
        assert not overlap, f"Type {jerger} both supports and excludes {overlap}"


def test_every_disease_declares_an_expected_pta_and_laterality():
    for key, disease in DISEASES.items():
        lo, hi = disease["expected_pta"]
        assert 0 <= lo < hi <= 120, f"{key} has an implausible PTA range"
        assert disease["laterality"] in ("unilateral", "bilateral", "either")


# ============ differentials that need no history at all ====================

def full_oto(label, name, ranked=None):
    """An otoscopy result shaped like the real classifier's output."""
    return {
        "prediction": {"label": label, "name": name, "certainty": "probable"},
        "ranked": ranked or [{"label": label, "probability": 1.0}],
    }


def audiogram_from(ac, ear_type="Sensorineural", left=None):
    pta = round(sum(ac[f] for f in (500, 1000, 2000, 4000)) / 4, 1)
    left_ac = left or ac
    left_pta = round(sum(left_ac[f] for f in (500, 1000, 2000, 4000)) / 4, 1)
    return {
        "thresholds": {"right": {"ac": ac, "bc": {}},
                       "left": {"ac": left_ac, "bc": {}}},
        "rules": {"right": {"ac_pta": {"value": pta}, "type": ear_type},
                  "left": {"ac_pta": {"value": left_pta}, "type": ear_type}},
    }


def test_the_image_alone_produces_a_differential():
    """A scope goes in the ear before the patient is in the booth."""
    result = linkage.otoscopy_vs_diseases(
        full_oto("perforation_attic", "Attic perforation"))
    assert result["available"]
    assert result["differential"][0]["key"] == "cholesteatoma"
    assert result["separated"]


def test_the_image_differential_carries_the_classifier_uncertainty():
    """A picture the model cannot separate yields a less peaked differential.

    Measured by how close the runner-up sits, not by whether the leader is
    separated. Separation can legitimately stay high when several uncertain
    patterns converge on the same disease — three appearances that all imply
    Eustachian tube dysfunction make it likely even if the image cannot say
    which of the three it is. That is convergent evidence, not overconfidence.
    """
    confident = linkage.otoscopy_vs_diseases(full_oto(
        "tumor", "Mass", [{"label": "tumor", "probability": 0.95},
                          {"label": "normal", "probability": 0.05}]))
    unsure = linkage.otoscopy_vs_diseases(full_oto(
        "tumor", "Mass", [{"label": "tumor", "probability": 0.34},
                          {"label": "retraction", "probability": 0.33},
                          {"label": "otitis_media", "probability": 0.33}]))
    assert unsure["differential"][1]["score"] > confident["differential"][1]["score"]


def test_negligible_candidates_are_dropped_from_the_image_differential():
    """A 3% pattern drags its whole disease list in at 3% of the weight."""
    result = linkage.otoscopy_vs_diseases(full_oto(
        "tumor", "Mass", [{"label": "tumor", "probability": 0.97},
                          {"label": "normal", "probability": 0.03}]))
    assert all(d["score"] >= 0.05 for d in result["differential"])
    assert "sensory_presbycusis" not in {d["key"] for d in result["differential"]}


def test_a_normal_drum_says_it_cannot_rank_the_cochlear_causes():
    """Every cochlear cause scores equally; a tie is not a ranking."""
    result = linkage.otoscopy_vs_diseases(full_oto("normal", "Normal drum"))
    assert not result["separated"]
    assert "cannot rank" in result["headline"]
    assert "cholesteatoma" in {d["key"] for d in result["argues_against"]}


def test_every_otoscopy_pattern_has_a_disease_link():
    from app.clinical.symptom_kb import OTOSCOPY_DISEASE_LINKS
    assert set(OTOSCOPY_DISEASE_LINKS) == set(CLASSES)
    for label, link in OTOSCOPY_DISEASE_LINKS.items():
        for key in list(link["supports"]) + link["excludes"]:
            assert key in DISEASES, f"{label} references unknown disease {key}"
        assert link["reasoning"]


def test_a_disease_is_never_both_supported_and_excluded_by_one_appearance():
    from app.clinical.symptom_kb import OTOSCOPY_DISEASE_LINKS
    for label, link in OTOSCOPY_DISEASE_LINKS.items():
        overlap = {k for k, v in link["supports"].items() if v > 0} & set(link["excludes"])
        assert not overlap, f"{label} both supports and excludes {overlap}"


def test_the_audiogram_alone_recognises_a_noise_notch():
    from app.clinical.symptom_kb import DISEASE_AUDIOGRAM
    result = linkage.audiogram_vs_diseases(
        audiogram_from(dict(DISEASE_AUDIOGRAM["nihl"]["ac"])), "right")
    assert result["available"]
    assert result["differential"][0]["key"] == "nihl"
    assert result["differential"][0]["shape_match"] > 0.9


def test_shape_matching_ignores_overall_level():
    """A notch is a notch whether it is 20 dB deep or 50."""
    shallow = {250: 5, 500: 5, 1000: 10, 2000: 15, 4000: 40, 8000: 25}
    deep = {f: v + 20 for f, v in shallow.items()}
    a = linkage.audiogram_vs_diseases(audiogram_from(shallow), "right")
    b = linkage.audiogram_vs_diseases(audiogram_from(deep), "right")
    assert a["differential"][0]["key"] == b["differential"][0]["key"] == "nihl"


def test_a_normal_audiogram_is_not_reported_as_a_disease():
    """Two conditions present with normal pure tones; neither is a diagnosis here."""
    normal = {250: 5, 500: 5, 1000: 10, 2000: 10, 4000: 10, 8000: 15}
    result = linkage.audiogram_vs_diseases(audiogram_from(normal, "Normal"), "right")
    assert result["normal_audiogram"] is True
    assert result["separated"] is False
    assert "within normal limits" in result["headline"]


def test_the_type_can_veto_a_perfect_shape_match():
    from app.clinical.symptom_kb import DISEASE_AUDIOGRAM
    shape = dict(DISEASE_AUDIOGRAM["sensory_presbycusis"]["ac"])
    sensorineural = linkage.audiogram_vs_diseases(
        audiogram_from(shape, "Sensorineural"), "right")["differential"]
    conductive = linkage.audiogram_vs_diseases(
        audiogram_from(shape, "Conductive"), "right")["differential"]
    presby_sn = next(d for d in sensorineural if d["key"] == "sensory_presbycusis")
    presby_cd = next((d for d in conductive if d["key"] == "sensory_presbycusis"), None)
    assert presby_sn["type_match"] == 1.0
    assert presby_cd is None or presby_cd["type_match"] < 0.3


def test_each_component_of_the_audiogram_match_is_reported_separately():
    from app.clinical.symptom_kb import DISEASE_AUDIOGRAM
    result = linkage.audiogram_vs_diseases(
        audiogram_from(dict(DISEASE_AUDIOGRAM["nihl"]["ac"])), "right")
    top = result["differential"][0]
    assert {"shape_match", "level_match", "type_match", "laterality_match"} <= set(top)


def test_every_disease_has_a_characteristic_audiogram():
    from app.clinical.symptom_kb import DISEASE_AUDIOGRAM
    assert set(DISEASE_AUDIOGRAM) == set(DISEASES)
    for key, entry in DISEASE_AUDIOGRAM.items():
        assert set(entry["ac"]) == {250, 500, 1000, 2000, 4000, 8000}
        assert set(entry["bc"]) == {250, 500, 1000, 2000, 4000}
        for freq, value in entry["ac"].items():
            assert -10 <= value <= 120
            # Bone conduction can never be worse than air conduction.
            if freq in entry["bc"]:
                assert entry["bc"][freq] <= value, f"{key} at {freq} Hz"


def test_standalone_differentials_need_only_their_own_input():
    from app.clinical.symptom_kb import DISEASE_AUDIOGRAM
    result = linkage.link_case(
        analysis=audiogram_from(dict(DISEASE_AUDIOGRAM["nihl"]["ac"])),
        assessment=None,
        otoscopy=full_oto("normal", "Normal drum"))
    assert result["standalone"]["from_audiogram"]["available"]
    assert result["standalone"]["from_otoscopy"]["available"]
    # No history at all, yet both differentials exist.
    assert result["links"]["otoscopy_symptoms"]["available"] is False


def test_image_and_audiogram_agreeing_without_a_history_is_surfaced():
    from app.clinical.symptom_kb import DISEASE_AUDIOGRAM
    result = linkage.link_case(
        analysis=audiogram_from(dict(DISEASE_AUDIOGRAM["etd"]["ac"]), "Conductive"),
        otoscopy=full_oto("retraction", "Retracted drum"))
    agreed = {a["key"] for a in result["standalone_agreement"]}
    assert "etd" in agreed


def test_standalone_endpoints_work_from_one_input():
    from app.clinical.symptom_kb import DISEASE_AUDIOGRAM
    body = client.post("/api/linkage/from-otoscopy", json={
        "otoscopy": full_oto("tumor", "Mass")}).json()
    assert body["differential"][0]["key"] == "glomus_tumor"

    body = client.post("/api/linkage/from-audiogram", json={
        "analysis": audiogram_from(dict(DISEASE_AUDIOGRAM["nihl"]["ac"])),
        "side": "right"}).json()
    assert body["differential"][0]["key"] == "nihl"
