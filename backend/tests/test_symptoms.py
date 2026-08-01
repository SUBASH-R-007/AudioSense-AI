"""Symptom-led assessment: matching, ranking, red flags and battery order."""
import pytest

from app.clinical import symptoms as S
from app.clinical.symptom_kb import COMPLAINTS, DISEASES, RED_FLAGS, age_band


def names(result, n=4):
    return [d["name"] for d in result["differential"][:n]]


# ------------------------------------------------------------ age bands ---

@pytest.mark.parametrize("age,key", [
    (0, "pediatric"), (17, "pediatric"), (18, "adult"),
    (64, "adult"), (65, "geriatric"), (99, "geriatric"),
])
def test_age_band_boundaries(age, key):
    assert age_band(age)["key"] == key


# --------------------------------------------------------- free text ------

def test_free_text_matches_the_way_patients_actually_speak():
    parsed = S.parse_symptoms(["water discharge from ears"])
    assert "ear_discharge" in parsed["symptoms"]
    assert not parsed["unmatched"]


def test_longer_phrase_wins_over_its_substring():
    # "severe deep ear pain" must not be filed as plain ear pain only.
    parsed = S.parse_symptoms(["severe deep ear pain"])
    assert "severe_ear_pain" in parsed["symptoms"]


def test_unrecognised_text_is_reported_not_discarded():
    parsed = S.parse_symptoms(["my left elbow aches"])
    assert parsed["unmatched"] == ["my left elbow aches"]
    assert parsed["symptoms"] == []


def test_canonical_keys_pass_through_unchanged():
    parsed = S.parse_symptoms(["tinnitus", "vertigo"])
    assert set(parsed["symptoms"]) == {"tinnitus", "vertigo"}


# -------------------------------------------------------- differential ----

def test_meniere_tetrad_leads_the_differential():
    r = S.assess(age=45, symptoms=["spinning", "ringing", "fullness",
                                   "hearing comes and goes"])
    assert r["differential"][0]["name"] == "Meniere's disease"


def test_absent_defining_feature_demotes_a_diagnosis():
    """Meniere's without vertigo or fluctuation is not a weak Meniere's."""
    with_vertigo = S.assess(age=45, symptoms=["vertigo", "tinnitus", "fullness"])
    without = S.assess(age=45, symptoms=["tinnitus", "fullness"])

    def score(result):
        return next((d["score"] for d in result["differential"]
                     if d["name"] == "Meniere's disease"), 0.0)

    assert score(without) < score(with_vertigo) * 0.6


def test_noise_exposure_is_required_for_noise_induced_loss():
    without = S.assess(age=45, symptoms=["ringing", "difficulty in noise"])
    with_noise = S.assess(age=45, symptoms=["works in factory", "ringing",
                                            "difficulty in noise"])
    assert with_noise["differential"][0]["name"] == "Noise-induced hearing loss"
    assert "Noise-induced hearing loss" not in names(without, 1)


def test_bullous_myringitis_needs_blisters_not_just_pain():
    """Plain ear pain must not summon a diagnosis defined by its bullae."""
    r = S.assess(age=30, symptoms=["ear pain", "hearing loss"])
    top = names(r, 2)
    assert "Bullous myringitis" not in top


def test_capd_is_argued_against_by_a_real_hearing_loss():
    listening = S.assess(age=10, symptoms=["cannot follow instructions",
                                           "difficulty in noise"])
    with_loss = S.assess(age=10, symptoms=["cannot follow instructions",
                                           "difficulty in noise",
                                           "hearing loss"])

    def score(result):
        return next((d["score"] for d in result["differential"]
                     if d["name"].startswith("Central auditory")), 0.0)

    assert score(with_loss) < score(listening)


# ----------------------------------------------- complaint guide merge ----

def test_guide_only_conditions_reach_the_differential():
    """CSOM is in the complaint guide but not the disease reference."""
    r = S.assess(age=34, complaints=["otorrhea"],
                 symptoms=["ear discharge", "hearing loss"])
    assert "Chronic suppurative otitis media" in names(r, 3)


def test_guide_rank_is_modulated_by_how_well_the_patient_fits():
    """The commonest cause must not win when the history points elsewhere.

    Otitis externa is rank 1 for adult otorrhoea, but its described
    presentation is pain on touching the ear. Persistent discharge with
    hearing loss is chronic suppurative otitis media, rank 2.
    """
    r = S.assess(age=34, complaints=["otorrhea"],
                 symptoms=["ear discharge", "hearing loss"])
    assert r["differential"][0]["name"] == "Chronic suppurative otitis media"


def test_both_sources_agreeing_beats_either_alone():
    r = S.assess(age=45, symptoms=["vertigo", "ringing"])
    meniere = next(d for d in r["differential"] if d["name"] == "Meniere's disease")
    assert meniere["symptom_overlap"] > 0
    assert meniere["guide_score"] > 0
    assert meniere["score"] > max(meniere["symptom_overlap"], meniere["guide_score"])
    assert len(meniere["sources"]) == 2


def test_age_changes_the_differential_for_the_same_complaint():
    child = S.assess(age=6, complaints=["vertigo"], symptoms=["vertigo"])
    elder = S.assess(age=78, complaints=["vertigo"], symptoms=["vertigo"])
    assert names(child, 6) != names(elder, 6)
    assert any("stroke" in n.lower() for n in names(elder, 6))


# ------------------------------------------------------------ red flags ---

def test_meningitis_triad_is_an_emergency():
    r = S.assess(age=6, symptoms=["fever", "stiff neck", "drowsy"])
    assert r["urgency"] == "emergency"
    assert r["red_flags"][0]["id"] == "meningitis"


def test_sudden_onset_promotes_hearing_loss_to_an_emergency():
    gradual = S.assess(age=40, symptoms=["hearing loss"], onset="gradual")
    sudden = S.assess(age=40, symptoms=["hearing loss"], onset="sudden")
    assert gradual["urgency"] != "emergency"
    assert sudden["urgency"] == "emergency"
    assert any(f["id"] == "sudden_snhl" for f in sudden["red_flags"])


def test_malignant_otitis_externa_needs_the_risk_factor():
    plain = S.assess(age=72, symptoms=["severe deep ear pain", "discharge"])
    diabetic = S.assess(age=72, symptoms=["severe deep ear pain", "discharge",
                                          "diabetic"])
    assert not any(f["id"] == "malignant_otitis_externa" for f in plain["red_flags"])
    assert any(f["id"] == "malignant_otitis_externa"
               for f in diabetic["red_flags"])


def test_cerebellar_stroke_flag_is_age_restricted():
    young = S.assess(age=30, symptoms=["vertigo", "unsteady"])
    old = S.assess(age=78, symptoms=["vertigo", "unsteady"])
    assert not any(f["id"] == "cerebellar_stroke" for f in young["red_flags"])
    assert any(f["id"] == "cerebellar_stroke" for f in old["red_flags"])


def test_red_flags_are_ordered_by_urgency():
    r = S.assess(age=70, symptoms=["hearing loss", "facial weakness",
                                   "foul smell from ear", "ringing"],
                 onset="sudden")
    levels = [f["level"] for f in r["red_flags"]]
    assert levels == sorted(levels, key=lambda l: {"emergency": 0, "urgent": 1,
                                                   "watch": 2}[l])


def test_red_flag_drives_the_summary_over_the_differential():
    r = S.assess(age=6, symptoms=["fever", "stiff neck"])
    assert "meningitis" in r["summary"].lower()


# ------------------------------------------------------------- battery ----

def test_battery_is_ordered_by_clinic_sequence_not_alphabetically():
    r = S.assess(age=34, complaints=["otorrhea"],
                 symptoms=["ear discharge", "hearing loss"])
    tests = [b["test"] for b in r["recommended_battery"]]
    assert tests[0] in ("Otoscopy / video otoscopy", "Pure-tone audiometry")
    assert tests[0] != "Acoustic reflex testing"


def test_battery_folds_qualified_duplicates_together():
    """'Pure-tone audiometry once stable' is still pure-tone audiometry."""
    r = S.assess(age=6, symptoms=["fever", "stiff neck", "drowsy"])
    tests = [b["test"] for b in r["recommended_battery"]]
    assert len(tests) == len(set(tests))
    assert sum(1 for t in tests if t.startswith("Pure-tone")) == 1


def test_every_disease_names_at_least_one_test():
    for key, disease in DISEASES.items():
        assert disease["tests"], f"{key} has no audiological tests"


# --------------------------------------------------------- empty input ----

def test_no_symptoms_returns_an_invitation_not_a_diagnosis():
    r = S.assess(age=40)
    assert r["differential"] == []
    assert r["urgency"] == "none"
    assert "no symptoms" in r["summary"].lower()


def test_catalog_covers_every_complaint_and_disease():
    cat = S.catalog()
    assert len(cat["complaints"]) == len(COMPLAINTS)
    assert len(cat["diseases"]) == len(DISEASES)
    assert all(g["symptoms"] for g in cat["symptom_groups"])


# -------------------------------------------------------- correlation -----

def test_correlation_flags_an_audiogram_that_does_not_fit():
    assessment = S.assess(age=45, symptoms=["works in factory", "ringing",
                                            "difficulty in noise"])
    conductive = {"rules": {
        "right": {"ac_pta": {"value": 40}, "type": "Conductive hearing loss"},
        "left": {"ac_pta": {"value": 40}, "type": "Conductive hearing loss"},
    }}
    result = S.correlate(assessment, conductive)
    assert result["available"]
    assert result["against"]
    assert "does not fit" in result["verdict"]


def test_correlation_without_audiometry_says_so():
    assessment = S.assess(age=45, symptoms=["vertigo"])
    assert S.correlate(assessment, None)["available"] is False


# ------------------------------------------------- knowledge base shape ---

def test_red_flag_rules_reference_known_symptoms():
    known = set(S.SYMPTOM_SYNONYMS)
    for rule in RED_FLAGS:
        for key in rule["all"] + rule["any"]:
            assert key in known, f"{rule['id']} references unknown symptom {key}"


def test_disease_symptom_weights_reference_known_symptoms():
    known = set(S.SYMPTOM_SYNONYMS)
    for key, disease in DISEASES.items():
        for symptom in disease["symptoms"]:
            assert symptom in known, f"{key} references unknown symptom {symptom}"
        for symptom in disease["requires_any"]:
            assert symptom in known


def test_every_complaint_has_all_three_age_bands():
    for key, entry in COMPLAINTS.items():
        assert set(entry["by_age"]) == {"pediatric", "adult", "geriatric"}
        for band, rows in entry["by_age"].items():
            assert len(rows) == 5, f"{key}/{band} should list five causes"
