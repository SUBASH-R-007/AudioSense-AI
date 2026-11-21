"""Symptom engine and diagnostic picture: implied symptoms, the SSNHL entry,
age and commonness priors, the history reconciled against the audiogram, and
the occupational-noise prompt.

Every expected number here is computed by hand from the declared weights in
``symptom_kb`` rather than read back from the engine, so a change to the
scoring arithmetic shows up as a failure rather than as a new baseline.
"""
import pytest
from fastapi.testclient import TestClient

from app.clinical import diagnosis as D
from app.clinical import symptoms as S
from app.clinical.symptom_kb import (
    AGE_DEFINING_FLOOR, AGE_FIT_FLOOR, AGE_TAPER_YEARS, COMMONNESS_WEIGHT,
    DISEASE_AUDIOGRAM, DISEASES, IMPLIED_SYMPTOMS, NOISY_OCCUPATIONS,
    SYMPTOM_SYNONYMS,
)
from app.main import app

client = TestClient(app)

AC = [250, 500, 1000, 2000, 4000, 8000]
BC = [250, 500, 1000, 2000, 4000]

#: The audit's 45-year-old: a gradual loss, trouble in noise and with
#: instructions, and tinnitus.
LISTENING_LOSS = ["gradual_hearing_loss", "speech_in_noise_difficulty",
                  "difficulty_following_instructions", "tinnitus"]


def entry(result, key):
    return next((d for d in result["differential"] if d["key"] == key), None)


def rank(result, key):
    keys = [d["key"] for d in result["differential"]]
    return keys.index(key) if key in keys else len(keys)


def analyze(right_ac, right_bc, left_ac=None, left_bc=None, age=45,
            occupation=""):
    left_ac = right_ac if left_ac is None else left_ac
    left_bc = right_bc if left_bc is None else left_bc
    body = {"patient": {"name": "T", "age": age, "sex": "male",
                        "occupation": occupation},
            "right": {"ac": {f: right_ac for f in AC},
                      "bc": {f: right_bc for f in BC}},
            "left": {"ac": {f: left_ac for f in AC},
                     "bc": {f: left_bc for f in BC}}}
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def picture(**kw):
    r = client.post("/api/diagnosis/picture", json=kw)
    assert r.status_code == 200, r.text
    return r.json()


def history_line(p):
    return next(f for f in p["findings"] if f["key"] == "symptoms")


# ======================================================== G-1 implication

@pytest.mark.parametrize("specific", IMPLIED_SYMPTOMS["hearing_loss"])
def test_a_specific_hearing_loss_is_reported_as_an_implied_hearing_loss(specific):
    r = S.assess(age=40, symptoms=[specific])
    rows = {s["key"]: s for s in r["reported"]["symptoms"]}
    assert "hearing_loss" in rows
    assert rows["hearing_loss"]["implied"] is True
    assert "implied by" in rows["hearing_loss"]["matched_on"]
    assert rows[specific]["implied"] is False


def test_an_explicit_hearing_loss_is_not_labelled_implied():
    r = S.assess(age=40, symptoms=["hearing_loss", "gradual_hearing_loss"])
    rows = {s["key"]: s for s in r["reported"]["symptoms"]}
    assert rows["hearing_loss"]["implied"] is False


def test_gradual_loss_now_fires_the_capd_hearing_loss_demotion():
    """A precisely described loss must demote CAPD exactly as a plain one does."""
    gradual = S.assess(age=10, symptoms=["gradual_hearing_loss",
                                         "speech_in_noise_difficulty",
                                         "difficulty_following_instructions"])
    plain = S.assess(age=10, symptoms=["hearing_loss",
                                       "speech_in_noise_difficulty",
                                       "difficulty_following_instructions"])
    capd_g, capd_p = entry(gradual, "capd"), entry(plain, "capd")
    assert capd_g["argues_against"], "the hearing-loss demotion did not fire"
    assert "implied" in capd_g["argues_against"][0]
    # (3 noise + 3 instructions - 1 hearing loss) / 11 possible, x 0.35 for a
    # reported loss CAPD's definition (normal pure tones) rules out until
    # tested, uncommon tier, a 10-year-old inside the 7+ range, no adult gate.
    expected = (3 + 3 - 1) / 11 * 0.35 * COMMONNESS_WEIGHT["uncommon"]
    assert capd_g["score"] == pytest.approx(expected, abs=1e-3)
    assert capd_g["score"] == pytest.approx(capd_p["score"], abs=1e-9)


def test_conditions_weighting_hearing_loss_get_credit_for_a_specific_loss():
    r = S.assess(age=70, symptoms=["gradual_hearing_loss"])
    presby = entry(r, "sensory_presbycusis")
    matched = {m["key"]: m for m in presby["matched"]}
    assert "hearing_loss" in matched and matched["hearing_loss"]["implied"]
    assert "implied by" in matched["hearing_loss"]["label"]
    # gradual 3 + implied hearing loss 2, of 3+2+3+2+2+1 = 13 possible.
    assert presby["symptom_overlap"] == pytest.approx(5 / 13, abs=1e-3)


def test_every_condition_weighting_hearing_loss_scores_the_implied_symptom():
    present = {"fluctuating_hearing_loss"}
    implied = S._implied(present)
    present |= set(implied)
    weighted = [k for k, d in DISEASES.items()
                if d["symptoms"].get("hearing_loss", 0) > 0]
    assert len(weighted) >= 13
    for key in weighted:
        row = S._score_disease(key, DISEASES[key], present, 40, implied)
        assert row is not None, key
        assert "hearing_loss" in {m["key"] for m in row["matched"]}, key


def test_an_implied_hearing_loss_reaches_the_red_flags():
    """Facial weakness with a sudden loss is facial palsy with ear disease."""
    r = S.assess(age=40, symptoms=["sudden_hearing_loss", "facial_weakness"])
    assert {"sudden_snhl", "facial_palsy"} <= {f["id"] for f in r["red_flags"]}


# =============================================================== G-2 SSNHL

def test_sudden_loss_alone_leads_with_ssnhl_and_keeps_its_red_flag():
    r = S.assess(age=40, symptoms=["sudden_hearing_loss"])
    assert r["differential"][0]["key"] == "ssnhl"
    assert r["urgency"] == "emergency"
    assert any(f["id"] == "sudden_snhl" for f in r["red_flags"])


def test_ssnhl_scores_its_typical_presentation_from_the_declared_weights():
    r = S.assess(age=40, symptoms=["sudden_hearing_loss", "tinnitus", "fullness"])
    top = r["differential"][0]
    assert top["key"] == "ssnhl"
    # sudden 3 + implied loss 1 + tinnitus 2 + fullness 2 of 3+1+2+2+1+1 = 10;
    # a red-flag condition carries no commonness weight; 40 is in range.
    assert top["score"] == pytest.approx(8 / 10, abs=1e-3)
    assert top["commonness_factor"] == 1.0


def test_ssnhl_outranks_a_fistula_without_a_pressure_history():
    r = S.assess(age=40, symptoms=["sudden_hearing_loss", "vertigo"])
    assert rank(r, "ssnhl") < rank(r, "perilymphatic_fistula")
    # sudden 3 + loss 1 + vertigo 1 = 5 of 10.
    assert entry(r, "ssnhl")["score"] == pytest.approx(0.5, abs=1e-3)


def test_ssnhl_needs_the_sudden_onset():
    r = S.assess(age=40, symptoms=["tinnitus", "fullness"])
    row = entry(r, "ssnhl")
    assert row is None or row["missing_defining_feature"]


def test_ssnhl_entry_follows_the_kb_structure_and_names_its_source():
    d = DISEASES["ssnhl"]
    assert "Chandrasekhar" in d["source"] and "2019" in d["source"]
    assert d["requires_any"] == ["sudden_hearing_loss"]
    assert d["expected_type"] == "sensorineural"
    assert d["laterality"] == "unilateral"
    assert d["red_flag"]
    assert set(d["age_bands"]) == {"adult", "geriatric"}
    for symptom in ("tinnitus", "aural_fullness", "vertigo"):
        assert d["symptoms"][symptom] > 0
    tests = " ".join(d["tests"]).lower()
    assert "pure-tone audiometry" in tests and "mri" in tests
    # Defined by onset in any configuration: no invented reference shape.
    assert d["characteristic_audiogram"] is False
    assert "ssnhl" not in DISEASE_AUDIOGRAM


def test_the_added_source_is_shown_on_the_entry_and_in_the_sources():
    r = S.assess(age=40, symptoms=["sudden_hearing_loss"])
    assert any("Chandrasekhar" in s for s in r["differential"][0]["sources"])
    assert any("Chandrasekhar" in s for s in r["sources"])
    assert any("14 conditions" in s for s in r["sources"])
    cat = {d["key"]: d for d in S.catalog()["diseases"]}
    assert "Chandrasekhar" in cat["ssnhl"]["source"]
    assert cat["menieres"]["source"] == "disease reference"


# ============================================================ G-3 ranking

def test_age_taper_values_are_the_declared_linear_taper():
    presby, pagets = DISEASES["sensory_presbycusis"], DISEASES["pagets"]
    # Presbycusis below 50 follows the ISO 7029:2000 median, a x (age - 18)^2:
    # at 45 the shift is (27/32)^2 of the shift at 50, at 30 (12/32)^2, and
    # nothing at or below the 18-year reference.
    assert S._age_factor(45, presby) == pytest.approx((27 / 32) ** 2)
    assert S._age_factor(30, presby) == pytest.approx((12 / 32) ** 2)
    assert S._age_factor(10, presby) == 0.0
    assert S._age_factor(50, presby) == 1.0
    # Paget's below 55 halves per decade (incidence doubling each decade,
    # Ralston et al. 2019): 0.5 at 45, 0.5^2.5 at 30.
    assert S._age_factor(45, pagets) == pytest.approx(0.5)
    assert S._age_factor(30, pagets) == pytest.approx(0.5 ** 2.5)
    assert S._age_factor(55, pagets) == 1.0
    # A band edge is no longer a cliff: an 18-year-old against a condition
    # whose bands are paediatric and geriatric is one year outside.
    menin = DISEASES["bacterial_meningitis"]
    assert S._age_factor(18, menin) == pytest.approx(1 - 0.4 / AGE_TAPER_YEARS)
    assert S._age_factor(40, menin) >= AGE_FIT_FLOOR


def test_a_45_year_old_with_a_gradual_loss_is_not_led_by_capd_or_pagets():
    r = S.assess(age=45, symptoms=LISTENING_LOSS)
    assert r["differential"][0]["key"] == "sensory_presbycusis"
    assert rank(r, "sensory_presbycusis") < rank(r, "pagets")
    assert rank(r, "pagets") > 0 and rank(r, "capd") > 0
    # gradual 3 + loss 2 + noise 3 + tinnitus 2 of 13; common; ISO 7029
    # median shift at 45 is (27/32)^2 of that at 50.
    expected = 10 / 13 * (27 / 32) ** 2
    assert entry(r, "sensory_presbycusis")["score"] == pytest.approx(expected, abs=1e-3)
    # gradual 3 + loss 2 + tinnitus 2 of 12; rare; one decade under 55: 0.5.
    expected = 7 / 12 * COMMONNESS_WEIGHT["rare"] * 0.5
    assert entry(r, "pagets")["score"] == pytest.approx(expected, abs=1e-3)


def test_reported_noise_exposure_puts_nihl_first_and_pagets_below_both():
    r = S.assess(age=45, symptoms=LISTENING_LOSS + ["noise_exposure"])
    assert r["differential"][0]["key"] == "nihl"
    assert rank(r, "pagets") > rank(r, "sensory_presbycusis")
    # noise 3 + gradual 2 + in noise 3 + tinnitus 3 + loss 1 of 14; common.
    assert entry(r, "nihl")["score"] == pytest.approx(12 / 14, abs=1e-3)


def test_at_seventy_presbycusis_leads():
    r = S.assess(age=70, symptoms=LISTENING_LOSS)
    assert r["differential"][0]["key"] == "sensory_presbycusis"
    assert entry(r, "sensory_presbycusis")["score"] == pytest.approx(10 / 13, abs=1e-3)


def test_a_child_with_listening_difficulty_and_no_loss_still_leads_with_capd():
    r = S.assess(age=9, symptoms=["speech_in_noise_difficulty",
                                  "difficulty_following_instructions"])
    top = r["differential"][0]
    assert top["key"] == "capd"
    assert top["context_factor"] == 1.0
    assert top["score"] == pytest.approx(6 / 11 * 0.85, abs=1e-3)
    assert top["score"] - r["differential"][1]["score"] >= 0.15


def test_adult_capd_depends_on_a_neurological_history():
    listening = ["speech_in_noise_difficulty", "difficulty_following_instructions",
                 "asks_repetition"]
    # 45 is past the phase-in, so the full gate applies.
    without = entry(S.assess(age=45, symptoms=listening), "capd")
    with_stroke = entry(S.assess(age=45, symptoms=listening + ["had a stroke"]),
                        "capd")
    gate = DISEASES["capd"]["adult_context"]["factor"]
    assert without["context_factor"] == pytest.approx(gate)
    assert "neurological" in " ".join(without["missing_key_features"]).lower()
    assert without["context_note"]
    assert with_stroke["context_factor"] == 1.0
    # (3 + 3 + 2) / 11, uncommon, with and without the adult gate.
    assert without["score"] == pytest.approx(8 / 11 * 0.85 * gate, abs=1e-3)
    assert with_stroke["score"] == pytest.approx(8 / 11 * 0.85, abs=1e-3)


@pytest.mark.parametrize("age,expected", [
    (17, 1.0),                           # not yet an adult
    (18, 1 - 0.5 * 1 / 25),              # first adult year
    (30, 1 - 0.5 * 13 / 25),
    (42, 0.5),                           # 25 adult years: the full gate
    (70, 0.5),
])
def test_the_adult_capd_gate_phases_in_instead_of_switching_on(age, expected):
    """No step at 18: the gate tapers in over AGE_TAPER_YEARS."""
    assert AGE_TAPER_YEARS == 25 and DISEASES["capd"]["adult_context"]["factor"] == 0.5
    row = entry(S.assess(age=age, symptoms=["speech_in_noise_difficulty",
                                            "difficulty_following_instructions"]),
                "capd")
    assert row["context_factor"] == pytest.approx(expected)


def test_an_eighteen_year_old_is_ranked_like_a_seventeen_year_old():
    at17 = S.assess(age=17, symptoms=LISTENING_LOSS)
    at18 = S.assess(age=18, symptoms=LISTENING_LOSS)
    # (3 + 3 - 1 implied loss) / 11, x 0.35 for the reported loss at any age,
    # uncommon; x 0.98 for the adult gate's first year at 18.
    assert entry(at17, "capd")["score"] == pytest.approx(5 / 11 * 0.35 * 0.85,
                                                         abs=1e-3)
    assert entry(at18, "capd")["score"] == pytest.approx(
        5 / 11 * 0.35 * 0.85 * 0.98, abs=1e-3)
    assert at17["differential"][0]["key"] == at18["differential"][0]["key"]
    assert [d["key"] for d in at17["differential"]] == \
        [d["key"] for d in at18["differential"]]


def test_a_head_injury_stays_trauma_and_a_brain_injury_is_neurological():
    assert S.parse_symptoms(["head injury"])["symptoms"] == ["recent_trauma"]
    assert S.parse_symptoms(["traumatic brain injury"])["symptoms"] == [
        "neurological_history"]


def test_rare_but_not_to_be_missed_conditions_are_not_ranked_down_for_rarity():
    r = S.assess(age=50, symptoms=["pulsatile tinnitus"])
    glomus = entry(r, "glomus_tumor")
    assert glomus["commonness_factor"] == 1.0 and glomus["commonness"] is None
    for key, disease in DISEASES.items():
        if disease.get("red_flag"):
            assert S._commonness(disease) == (None, 1.0), key


def test_every_declared_ranking_field_is_well_formed():
    known = set(SYMPTOM_SYNONYMS)
    for key, d in DISEASES.items():
        for lo, hi in S._age_ranges(d):
            assert 0 <= lo <= hi <= 200, key
        if "commonness" in d:
            assert d["commonness"] in COMMONNESS_WEIGHT, key
        ctx = d.get("adult_context")
        if ctx:
            assert set(ctx["requires_any"]) <= known, key
            assert 0 < ctx["factor"] < 1


# ======================================== G-4 the picture uses the audiogram

def _listening_history(age=30):
    r = client.post("/api/symptoms/analyze", json={
        "age": age, "symptoms": ["speech_in_noise_difficulty",
                                 "difficulty_following_instructions",
                                 "asks_repetition"]})
    assert r.status_code == 200
    body = r.json()
    assert body["differential"][0]["key"] == "capd", "precondition: CAPD leads"
    return body


def test_history_alone_still_reports_its_own_leader():
    p = picture(assessment=_listening_history())
    line = history_line(p)
    assert line["says"] == ("Leading possibility: Central auditory processing "
                            "disorder (CAPD).")


def test_a_measured_sensorineural_loss_overrules_a_capd_leader():
    """CAPD needs normal pure tones; beside a moderate SNHL it cannot lead.

    At 30 nothing else the history raised is well supported — presbycusis is
    outside the age that defines it, ANSD predicts no type — so the line says
    that, rather than naming one of them.
    """
    p = picture(analysis=analyze(50, 50), assessment=_listening_history())
    line = history_line(p)
    assert not line["says"].startswith("Leading possibility")
    assert line["says"].startswith("No well-supported possibility the history "
                                   "raised fits the measured audiogram")
    assert "Central auditory processing disorder (CAPD)" in line["says"]
    assert "predicts normal pure-tone thresholds" in line["detail"]
    assert "sensorineural at 50 dB HL" in line["detail"]
    assert any("no well-supported possibility" in c for c in p["conflicts"])


def test_a_well_supported_alternative_takes_the_lead():
    """55, after a stroke: CAPD leads on history; presbycusis replaces it."""
    history = client.post("/api/symptoms/analyze", json={
        "age": 55, "symptoms": ["speech_in_noise_difficulty",
                                "difficulty_following_instructions",
                                "asks_repetition", "neurological_history"]}).json()
    assert history["differential"][0]["key"] == "capd"
    # CAPD (3+3+2)/11 x 0.85 = 0.618; presbycusis (3+2)/13 = 0.385, which is
    # above CAPD's 0.618 x 0.35 = 0.216 once the audiogram contradicts it.
    rec = S.reconcile(history, analyze(50, 50))
    assert rec["outcome"] == "replaced"
    assert rec["leading"]["key"] == "sensory_presbycusis"
    assert rec["leading"]["score"] == pytest.approx(5 / 13, abs=1e-3)
    line = history_line(picture(analysis=analyze(50, 50), assessment=history))
    assert line["says"] == ("Leading possibility once the audiogram is considered: "
                            "Sensory presbycusis (age-related hearing loss).")
    assert "on the history alone Central auditory" in line["detail"]


def test_normal_thresholds_leave_a_capd_leader_in_place():
    p = picture(analysis=analyze(10, 10), assessment=_listening_history())
    line = history_line(p)
    assert line["says"] == ("Leading possibility: Central auditory processing "
                            "disorder (CAPD).")
    assert "not contradicted" in line["detail"]


#: A stated noise exposure: what singles out NIHL in a hand-built entry.
NOISE = [{"key": "noise_exposure", "implied": False}]


def test_reconcile_ranks_a_contradicted_leader_below_every_open_possibility():
    assessment = {"differential": [
        {"key": "capd", "name": "CAPD", "expected_type": "normal", "score": 0.95},
        {"key": "x", "name": "Guide cause", "expected_type": "any", "score": 0.05},
        {"key": "nihl", "name": "NIHL", "expected_type": "sensorineural",
         "score": 0.2, "matched": NOISE},
    ]}
    rec = S.reconcile(assessment, analyze(50, 50))
    order = [r["key"] for r in rec["differential"]]
    assert order == ["nihl", "x", "capd"]
    capd = rec["differential"][-1]
    assert capd["audiogram"] == "contradicted"
    assert capd["score"] == pytest.approx(0.95 * 0.35, abs=1e-4)
    assert rec["history_leading"]["key"] == "capd"
    # Ranked above CAPD, but only by the ordering rule: 0.2 is below CAPD's
    # 0.3325 after its penalty, so NIHL is not named in CAPD's place, and the
    # guide cause predicts no type at all.
    assert rec["outcome"] == "unresolved" and not rec["changed"]
    assert rec["leading"] is None and not rec["all_contradicted"]
    rows = {r["key"]: r for r in rec["differential"]}
    assert "supports it less" in rows["nihl"]["cannot_lead_because"]
    assert "no particular type" in rows["x"]["cannot_lead_because"]


def test_reconcile_names_an_alternative_at_or_above_the_penalised_leader():
    assessment = {"differential": [
        {"key": "capd", "name": "CAPD", "expected_type": "normal", "score": 0.95},
        {"key": "nihl", "name": "NIHL", "expected_type": "sensorineural",
         "score": 0.95 * 0.35, "matched": NOISE},
    ]}
    rec = S.reconcile(assessment, analyze(50, 50))
    assert rec["outcome"] == "replaced" and rec["changed"]
    assert rec["leading"]["key"] == "nihl"
    # The same entry without the stated exposure is not singled out, and a
    # hand-built entry with no matched list at all has no stated evidence.
    for matched in ([{"key": "noise_exposure", "implied": True}], None):
        entry_ = dict(assessment["differential"][1], matched=matched)
        rec = S.reconcile({"differential": [assessment["differential"][0],
                                            entry_]}, analyze(50, 50))
        assert rec["outcome"] == "unresolved"
    # Presbycusis is singled out by age, so it needs the age on the entry.
    presby = {"key": "sensory_presbycusis", "name": "Presbycusis",
              "expected_type": "sensorineural", "score": 0.5}
    for age_fit, outcome in ((True, "replaced"), (None, "unresolved"),
                             (False, "unresolved")):
        rec = S.reconcile({"differential": [
            assessment["differential"][0], dict(presby, age_fit=age_fit)]},
            analyze(50, 50))
        assert rec["outcome"] == outcome, age_fit


def test_type_contradictions_are_measured_losses_of_the_wrong_kind():
    sn = S._measured_ears(analyze(50, 50))
    cd = S._measured_ears(analyze(50, 10))
    mixed = S._measured_ears(analyze(70, 40))
    normal = S._measured_ears(analyze(10, 10))
    assert S.audiogram_contradiction("normal", sn)
    assert S.audiogram_contradiction("normal", normal) is None
    assert S.audiogram_contradiction("conductive", sn)
    assert S.audiogram_contradiction("conductive", mixed) is None
    assert S.audiogram_contradiction("sensorineural", cd)
    assert S.audiogram_contradiction("sensorineural", mixed) is None
    # Normal thresholds do not contradict a condition that predicts a loss:
    # early noise damage can leave the four-frequency average normal.
    assert S.audiogram_contradiction("sensorineural", normal) is None
    assert S.audiogram_contradiction("conductive", normal) is None
    # Paget's produces sensorineural, conductive and mixed losses.
    for ears in (sn, cd, mixed, normal):
        assert S.audiogram_contradiction("mixed", ears) is None
        assert S.audiogram_contradiction("any", ears) is None


def test_a_history_the_audiogram_wholly_contradicts_is_a_conflict():
    assessment = {"differential": [
        {"key": "capd", "name": "CAPD", "expected_type": "normal", "score": 0.6}],
        "red_flags": []}
    p = picture(analysis=analyze(50, 50), assessment=assessment)
    line = history_line(p)
    assert line["says"].startswith("No possibility the history raised fits")
    assert any("history and audiogram" in c for c in p["conflicts"])


def test_reconcile_tolerates_hand_built_payloads_without_scores():
    rec = S.reconcile({"differential": [{"name": "Presbycusis"}, {}]},
                      analyze(30, 30))
    assert rec["available"] and rec["leading"]["name"] == "Presbycusis"
    assert S.reconcile({}, analyze(30, 30))["available"] is False
    assert S.reconcile({"differential": [{"name": "X"}]}, None)["available"] is False


def test_correlate_names_the_possibility_the_audiogram_leaves_open():
    history = client.post("/api/symptoms/analyze", json={
        "age": 55, "symptoms": ["speech_in_noise_difficulty",
                                "difficulty_following_instructions",
                                "asks_repetition", "stroke"]}).json()
    body = client.post("/api/symptoms/correlate", json={
        "assessment": history, "analysis": analyze(50, 50)}).json()
    assert "does not fit" in body["verdict"]
    assert ("Of the other possibilities the history raised, Sensory presbycusis "
            "(age-related hearing loss) is not contradicted") in body["verdict"]
    assert body["reconciled"]["changed"] is True


def test_correlate_names_nothing_when_nothing_is_well_supported():
    body = client.post("/api/symptoms/correlate", json={
        "assessment": _listening_history(), "analysis": analyze(50, 50)}).json()
    assert "does not fit" in body["verdict"]
    assert "Of the other possibilities" not in body["verdict"]
    assert "None of the other possibilities the history raised is well enough " \
           "supported" in body["verdict"]
    assert body["reconciled"]["outcome"] == "unresolved"


# ======================================================= G-5 occupation

@pytest.mark.parametrize("occupation,sector", [
    ("Weaver", "textile and weaving"),
    ("Weaver (powerloom)", "textile and weaving"),
    ("powerloom operator", "textile and weaving"),
    ("Factory Worker — Textile Mill", "textile and weaving"),
    ("Welder — Shipyard", "manufacturing and metalwork"),
    ("Machine Operator", "manufacturing and metalwork"),
    ("stone quarry", "construction, mining and quarrying"),
])
def test_a_noisy_occupation_prompts_a_noise_history(occupation, sector):
    r = S.assess(age=45, symptoms=["tinnitus"], occupation=occupation)
    assert len(r["history_prompts"]) == 1
    prompt = r["history_prompts"][0]
    assert prompt["sector"] == sector
    assert prompt["asserts_exposure"] is False
    assert "Ask about it" in prompt["text"]
    # A prompt, never an exposure: NIHL stays gated on the answer.
    assert "noise_exposure" not in {s["key"] for s in r["reported"]["symptoms"]}
    nihl = entry(r, "nihl")
    assert nihl is None or nihl["missing_defining_feature"]


@pytest.mark.parametrize("occupation", [
    "", "Software Engineer", "Bank Manager", "Retired Teacher", "Student",
    "Pharmacist", "Examiner", "Husband's shop assistant",
])
def test_other_occupations_raise_no_prompt(occupation):
    assert S.assess(age=45, symptoms=["tinnitus"],
                    occupation=occupation)["history_prompts"] == []


def test_a_recorded_exposure_silences_the_prompt():
    r = S.assess(age=45, symptoms=["tinnitus", "noise_exposure"],
                 occupation="Weaver")
    assert r["history_prompts"] == []


def test_the_router_passes_the_occupation_through():
    body = client.post("/api/symptoms/analyze", json={
        "age": 45, "symptoms": ["tinnitus"], "occupation": "Weaver"}).json()
    assert body["history_prompts"][0]["id"] == "occupational_noise"
    assert body["occupation"] == "Weaver"


def test_the_picture_prompts_from_the_patient_record_occupation():
    history = client.post("/api/symptoms/analyze", json={
        "age": 45, "symptoms": LISTENING_LOSS}).json()
    an = analyze(50, 50, occupation="Weaver (powerloom)")
    line = history_line(picture(analysis=an, assessment=history))
    assert "high-noise sector" in line["detail"]

    asked = client.post("/api/symptoms/analyze", json={
        "age": 45, "symptoms": LISTENING_LOSS + ["noise_exposure"]}).json()
    line = history_line(picture(analysis=an, assessment=asked))
    assert "high-noise sector" not in (line["detail"] or "")


def test_a_missing_history_in_a_noisy_trade_asks_for_the_noise_history():
    an = analyze(50, 50, occupation="Weaver")
    gap = next(g for g in picture(analysis=an)["next_tests"]
               if g["modality"] == "symptoms")
    assert "noise exposure" in gap["why"]
    plain = next(g for g in picture(analysis=analyze(50, 50))["next_tests"]
                 if g["modality"] == "symptoms")
    assert "noise exposure" not in plain["why"]


def test_noisy_occupation_patterns_compile():
    import re
    for sector, patterns in NOISY_OCCUPATIONS.items():
        for p in patterns:
            re.compile(p)


def test_a_null_occupation_does_not_fail_the_history():
    """Patient records carry ``occupation: null`` when it was never asked."""
    r = client.post("/api/symptoms/analyze", json={
        "age": 45, "symptoms": ["tinnitus"], "occupation": None})
    assert r.status_code == 200, r.text
    assert r.json()["history_prompts"] == []
    assert r.json()["occupation"] == ""


@pytest.mark.parametrize("occupation", [
    "Machine learning engineer", "Data mining analyst", "Spinning instructor",
    "Spinning class coach",
])
def test_office_and_fitness_senses_of_a_noisy_stem_raise_no_prompt(occupation):
    assert S.occupation_prompt(occupation, []) is None


@pytest.mark.parametrize("occupation,sector", [
    ("Machinist", "manufacturing and metalwork"),
    ("Spinning mill worker", "textile and weaving"),
    ("Coal mining", "construction, mining and quarrying"),
])
def test_the_shop_floor_senses_still_prompt(occupation, sector):
    assert S.occupation_prompt(occupation, [])["sector"] == sector


# ============================ provisional types: no bone conduction measured

def analyze_ears(right, left, age=45):
    r = client.post("/api/analyze", json={
        "patient": {"name": "T", "age": age, "sex": "male"},
        "right": right, "left": left})
    assert r.status_code == 200, r.text
    return r.json()


def flat(level, freqs):
    return {f: level for f in freqs}


def ac_only(level):
    """Air conduction only — the screening flow's audiogram."""
    return analyze_ears({"ac": flat(level, AC)}, {"ac": flat(level, AC)})


def bc_no_response(level):
    """Bone conduction at the vibrator's limit everywhere: gap indeterminate."""
    nr = {f: "NR" for f in BC}
    return analyze_ears({"ac": flat(level, AC), "bc": nr},
                        {"ac": flat(level, AC), "bc": nr})


def partial_bc(level):
    """Bone conduction at two of the four PTA frequencies, no gap there."""
    bc = {500: level, 1000: level}
    return analyze_ears({"ac": flat(level, AC), "bc": bc},
                        {"ac": flat(level, AC), "bc": bc})


CONDUCTIVE_HISTORIES = [
    (8, ["postauricular_swelling", "fever", "ear_pain", "hearing_loss"],
     "Mastoiditis"),
    (40, ["foul_smelling_discharge", "hearing_loss"], "Cholesteatoma"),
    (30, ["blocked_ear", "popping", "muffled_hearing"],
     "Eustachian tube dysfunction"),
]


@pytest.mark.parametrize("audiogram", [lambda: ac_only(45),
                                       lambda: bc_no_response(70)],
                         ids=["ac-only", "bc-no-response"])
@pytest.mark.parametrize("age,symptoms,leader", CONDUCTIVE_HISTORIES)
def test_a_provisional_type_sets_no_conductive_history_aside(audiogram, age,
                                                             symptoms, leader):
    """rules.py: "a conductive component cannot be excluded" — so it isn't."""
    an = audiogram()
    assert an["rules"]["right"]["type"] == "Sensorineural (provisional)", (
        "precondition: the provisional path")
    history = S.assess(age=age, symptoms=symptoms)
    assert history["differential"][0]["name"] == leader

    rec = S.reconcile(history, an)
    assert rec["outcome"] == "unchanged" and rec["type_provisional"]
    assert rec["history_leading"]["audiogram"] == "undetermined"
    assert rec["leading"]["name"] == leader

    p = picture(analysis=an, assessment=history)
    line = history_line(p)
    assert line["says"] == f"Leading possibility: {leader}."
    assert "neither confirm nor set it aside by type" in line["detail"]
    assert "conductive component can be neither confirmed nor excluded" \
        in line["detail"]
    assert "conflict" not in line
    assert not any("history and audiogram" in c for c in p["conflicts"])


def test_a_provisional_loss_still_contradicts_normal_hearing():
    """Degree needs air conduction only; CAPD is still set aside."""
    for an in (ac_only(45), bc_no_response(70)):
        ears = S._measured_ears(an)
        assert all(e["impaired"] and e["provisional"] for e in ears)
        assert S.audiogram_contradiction("normal", ears)
        assert S.audiogram_contradiction("conductive", ears) is None
        assert S.audiogram_contradiction("sensorineural", ears) is None
        assert S._type_status("conductive", ears)[0] == "undetermined"
        assert S._type_status("sensorineural", ears)[0] == "undetermined"
        assert S._type_status("mixed", ears)[0] == "undetermined"
        assert S._type_status("normal", ears)[0] == "contradicted"


def test_partial_bone_conduction_settles_only_what_it_measured():
    an = partial_bc(45)
    assert an["rules"]["right"]["type"] == "Sensorineural"
    assert an["rules"]["right"]["provisional"] is True
    ears = S._measured_ears(an)
    # Bone conduction elevated where tested: a sensorineural part was measured;
    # a gap at the untested frequencies was not excluded.
    assert all(e["sensorineural"] is True and e["conductive"] is None for e in ears)
    assert S._type_status("sensorineural", ears)[0] == "compatible"
    assert S._type_status("conductive", ears)[0] == "undetermined"


@pytest.mark.parametrize("ear,expected", [
    ({"type": "Sensorineural (provisional)", "provisional": True},
     (None, None, True)),
    ({"type": "Indeterminate", "provisional": True}, (None, None, True)),
    ({"type": "Sensorineural", "provisional": True}, (None, True, True)),
    ({"type": "Conductive", "provisional": True}, (True, None, True)),
    ({"type": "Mixed", "provisional": True}, (True, True, True)),
    ({"type": "Sensorineural", "provisional": False}, (False, True, False)),
    ({"type": "Conductive hearing loss"}, (True, False, False)),
    ({"type": "Normal"}, (False, False, False)),
    ({}, (None, None, True)),
])
def test_what_an_ear_type_determines(ear, expected):
    assert S._ear_parts(ear) == expected


def test_correlate_reads_a_provisional_type_as_undetermined():
    history = S.assess(age=70, symptoms=LISTENING_LOSS)
    assert history["differential"][0]["key"] == "sensory_presbycusis"
    result = S.correlate(history, ac_only(45))
    assert result["against"] == [] and result["supports"] == []
    assert len(result["undetermined"]) == 2
    assert "provisional" in result["verdict"]
    assert "does not fit" not in result["verdict"]

    mastoid = S.assess(age=8, symptoms=CONDUCTIVE_HISTORIES[0][1])
    result = S.correlate(mastoid, bc_no_response(70))
    assert result["against"] == []
    assert "does not fit" not in result["verdict"]


# ========================= a replacement leader must be supported by history

def test_a_replacement_needs_its_defining_feature():
    """ETD history, measured SNHL: SSNHL (no sudden onset) is not named."""
    history = S.assess(age=30, symptoms=["blocked_ear", "popping",
                                         "muffled_hearing"])
    ssnhl = entry(history, "ssnhl")
    assert ssnhl and ssnhl["missing_defining_feature"]
    an = analyze(50, 50)
    rec = S.reconcile(history, an)
    assert rec["outcome"] == "unresolved" and rec["leading"] is None
    rows = {r["key"]: r for r in rec["differential"]}
    assert rows["ssnhl"]["audiogram"] == "compatible"
    assert rows["ssnhl"]["cannot_lead_because"] == \
        "its defining feature was not reported"

    p = picture(analysis=an, assessment=history)
    line = history_line(p)
    assert "SSNHL" not in line["says"] and "Sudden" not in line["says"]
    assert line["says"].startswith("No well-supported possibility")
    assert any("no well-supported possibility" in c for c in p["conflicts"])
    verdict = S.correlate(history, an)["verdict"]
    assert "Sudden sensorineural" not in verdict


def test_an_age_defined_condition_cannot_replace_outside_its_age():
    history = _listening_history(age=30)
    rows = {r["key"]: r for r in S.reconcile(history, analyze(50, 50))["differential"]}
    assert rows["sensory_presbycusis"]["audiogram"] == "compatible"
    assert rows["sensory_presbycusis"]["cannot_lead_because"] == \
        "the patient is outside the age that defines it"
    assert "no particular type" in rows["ansd"]["cannot_lead_because"]


def test_a_complaint_guide_cause_is_never_promoted_by_the_audiogram():
    """Mastoiditis history, measured SNHL: acute otitis media is not named."""
    history = S.assess(age=8, symptoms=CONDUCTIVE_HISTORIES[0][1])
    rec = S.reconcile(history, analyze(50, 50))
    assert rec["outcome"] == "unresolved"
    rows = {r["key"]: r for r in rec["differential"]}
    assert rows["guide:acute otitis media"]["audiogram"] == "no prediction"
    assert not rows["guide:acute otitis media"]["can_lead"]
    line = history_line(picture(analysis=analyze(50, 50), assessment=history))
    assert "Acute otitis media" not in line["says"]
    assert "Mastoiditis" in line["says"]


# ======================================== one-sided conditions in correlate

def test_correlate_expects_a_normal_ear_opposite_a_one_sided_condition():
    history = S.assess(age=40, symptoms=["sudden_hearing_loss", "tinnitus",
                                         "aural_fullness"])
    assert history["differential"][0]["key"] == "ssnhl"
    result = S.correlate(history, analyze(60, 60, left_ac=10, left_bc=10))
    assert result["against"] == []
    assert any("as expected opposite the affected ear" in s
               for s in result["supports"])
    assert result["verdict"] == ("The audiogram is consistent with the leading "
                                 "diagnosis.")
    # Both ears normal: no support, but no mismatch by type either — a
    # frequency-limited loss can leave the four-frequency average normal.
    result = S.correlate(history, analyze(10, 10))
    assert result["against"] == [] and result["supports"] == []
    assert len(result["within_normal_limits"]) == 2
    assert result["audiogram"] == "within normal limits"
    assert "does not support it" in result["verdict"]
    assert "does not rule it out" in result["verdict"]


# ===================================== SSNHL and the thresholds-only matcher

def test_ssnhl_is_never_matched_from_thresholds_alone():
    """No invented shape: a flat loss with no history is not an emergency."""
    from app.clinical import linkage
    for an in (analyze(50, 50), analyze(60, 60, left_ac=10, left_bc=10)):
        result = linkage.audiogram_vs_diseases(an, "right")
        assert result["available"]
        assert "ssnhl" not in {d["key"] for d in result["differential"]}
        assert "SSNHL" not in result["headline"]
    ref = client.get("/api/linkage/reference").json()
    assert "ssnhl" not in {d["key"] for d in ref["disease_audiograms"]}


# ====================== the complaint guide: stated symptoms and exclusions

def test_the_guide_presentation_is_matched_on_what_the_patient_said():
    """A gradual loss does not satisfy the acute "Vertigo with hearing loss"."""
    r = S.assess(age=55, symptoms=["gradual_hearing_loss", "imbalance",
                                   "headache"])
    assert r["differential"][0]["key"] != "guide:labyrinthitis"
    schwannoma = entry(r, "guide:vestibular schwannoma")
    assert schwannoma["guide_fit"] == 1.0
    assert rank(r, "guide:vestibular schwannoma") < rank(r, "guide:labyrinthitis")
    # The implication still reaches the disease reference.
    presby = entry(r, "sensory_presbycusis")
    assert "hearing_loss" in {m["key"] for m in presby["matched"]}


def _guide_row(complaint, band, present, key):
    guides = S._complaint_guides([complaint], band)
    return next(m for m in S._merge_guide([], guides, set(present))
                if m["key"] == key)


@pytest.mark.parametrize("present,fit", [
    # "Vertigo with hearing loss": vertigo and hearing_loss expected.
    ({"gradual_hearing_loss", "hearing_loss", "vertigo"}, 0.5),
    ({"fluctuating_hearing_loss", "hearing_loss", "vertigo"}, 0.5),
    ({"sudden_hearing_loss", "hearing_loss", "vertigo"}, 1.0),
    ({"hearing_loss", "vertigo"}, 1.0),          # onset not recorded
    ({"gradual_hearing_loss", "hearing_loss", "imbalance"}, 0.0),
])
def test_an_acute_guide_cause_needs_a_loss_that_is_not_gradual(present, fit):
    """Labyrinthitis is an acute vestibular syndrome with an acute hearing loss
    (Strupp et al., 2022): a slow loss does not fit its presentation."""
    lab = _guide_row("headache", "adult", present, "guide:labyrinthitis")
    assert lab["guide_fit"] == fit
    # Adult headache guide rank 2 (0.85), floor 0.35 plus 0.65 x fit.
    assert lab["score"] == pytest.approx(0.85 * (0.35 + 0.65 * fit), abs=1e-4)


def test_a_chronic_guide_cause_counts_any_hearing_loss():
    """CSOM, "Persistent ear discharge with hearing loss": a gradual loss is
    the loss it describes, implied or not."""
    for present in ({"gradual_hearing_loss", "hearing_loss", "ear_discharge"},
                    {"hearing_loss", "ear_discharge"}):
        row = _guide_row("otorrhea", "adult", present,
                         "guide:chronic suppurative otitis media")
        assert row["guide_fit"] == 1.0
        assert row["score"] == pytest.approx(0.85, abs=1e-4)   # adult rank 2


@pytest.mark.parametrize("by_chip,by_onset", [
    (["sudden_hearing_loss", "vertigo"], "sudden"),
    (["gradual_hearing_loss", "vertigo"], "gradual"),
])
def test_a_loss_scores_the_same_however_its_onset_was_entered(by_chip, by_onset):
    chip = S.assess(age=40, symptoms=by_chip)
    form = S.assess(age=40, symptoms=["hearing_loss", "vertigo"], onset=by_onset)
    assert [(d["key"], d["score"]) for d in chip["differential"]] == \
        [(d["key"], d["score"]) for d in form["differential"]]


def test_re_sending_the_implied_hearing_loss_changes_nothing():
    """The Symptoms page restores ticked chips from ``reported.symptoms``,
    implied entries included: a second assessment must rank the same."""
    first = S.assess(age=55, symptoms=["gradual_hearing_loss", "imbalance",
                                       "headache"])
    again = S.assess(age=55, symptoms=[s["key"] for s in
                                       first["reported"]["symptoms"]])
    assert "hearing_loss" in {s["key"] for s in first["reported"]["symptoms"]}
    assert [(d["key"], d["score"]) for d in again["differential"]] == \
        [(d["key"], d["score"]) for d in first["differential"]]
    assert again["differential"][0]["key"] != "guide:labyrinthitis"


def test_vestibular_neuritis_is_argued_against_by_an_acute_hearing_loss():
    """Barany Society: an acute vestibular syndrome without acute audiological
    symptoms (Strupp et al., 2022)."""
    r = S.assess(age=40, symptoms=["sudden_hearing_loss", "vertigo"])
    vn = _guide_row("vertigo", "adult",
                    {"sudden_hearing_loss", "hearing_loss", "vertigo"},
                    "guide:vestibular neuritis")
    # Adult vertigo guide rank 2 (0.85), presentation matched, x 0.35.
    assert vn["score"] == pytest.approx(0.85 * 0.35, abs=1e-4)
    assert vn["argues_against"] == ["Sudden hearing loss"]
    assert "Strupp" in vn["against_note"]
    # Below SSNHL and below labyrinthitis (adult vertigo rank 5, 0.4, fully
    # matched), the two causes an acute loss with vertigo points to — far
    # enough down to leave the six-entry differential.
    assert rank(r, "ssnhl") < rank(r, "guide:vestibular neuritis")
    assert rank(r, "guide:labyrinthitis") < rank(r, "guide:vestibular neuritis")
    assert entry(r, "guide:labyrinthitis")["score"] == pytest.approx(0.4, abs=1e-4)
    assert r["differential"][0]["key"] != "guide:vestibular neuritis"
    assert r["urgency"] == "emergency"
    # Vertigo alone, or with a long-standing loss, is not argued against.
    for symptoms in (["vertigo"], ["vertigo", "gradual_hearing_loss"]):
        vn = entry(S.assess(age=40, symptoms=symptoms), "guide:vestibular neuritis")
        assert vn["score"] == pytest.approx(0.85, abs=1e-4)
        assert vn["argues_against"] == []


# ====================== the summary judges separation on fit, not base rate

@pytest.mark.parametrize("age,symptoms,name", [
    (45, ["vertigo", "tinnitus", "aural_fullness", "fluctuating_hearing_loss"],
     "Meniere's disease"),
    (2, ["not responding to sound", "responds sometimes"],
     "Auditory neuropathy spectrum disorder (ANSD)"),
    (9, ["speech_in_noise_difficulty", "difficulty_following_instructions"],
     "Central auditory processing disorder (CAPD)"),
])
def test_an_uncommon_leader_that_fits_is_still_called_separated(age, symptoms,
                                                                name):
    r = S.assess(age=age, symptoms=symptoms)
    assert r["differential"][0]["name"] == name
    assert r["summary"].startswith(f"Findings fit {name} most closely")


def test_fit_score_is_the_score_before_the_commonness_weight():
    tetrad = S.assess(age=45, symptoms=["vertigo", "tinnitus", "aural_fullness",
                                        "fluctuating_hearing_loss"])
    top = tetrad["differential"][0]
    # All 12 weight points matched (loss implied): overlap 1.0. Guide: adult
    # vertigo rank 3 (0.7), fully matched. Score uses the uncommon weight.
    assert top["score"] == pytest.approx(0.85 + 0.15 * 0.7, abs=1e-4)
    assert top["fit_score"] == 1.0
    capd = S.assess(age=9, symptoms=["speech_in_noise_difficulty",
                                     "difficulty_following_instructions"])
    assert capd["differential"][0]["fit_score"] == pytest.approx(6 / 11, abs=1e-4)


# ============== a defining feature belongs to the condition, not the document

def test_the_guide_rank_does_not_lift_menieres_without_its_defining_feature():
    """45, gradual loss, unsteady, ringing: no vertigo, no fluctuation."""
    r = S.assess(age=45, symptoms=["gradual_hearing_loss", "imbalance",
                                   "tinnitus"])
    assert r["differential"][0]["key"] == "sensory_presbycusis"
    assert rank(r, "menieres") > rank(r, "sensory_presbycusis")
    present = {"gradual_hearing_loss", "hearing_loss", "imbalance", "tinnitus"}
    scored = [x for x in (S._score_disease(k, d, present, 45,
                                           {"hearing_loss": ["gradual_hearing_loss"]})
                          for k, d in DISEASES.items()) if x]
    full = S._merge_guide(scored, S._complaint_guides(["vertigo"], "adult"),
                          present)
    menieres = next(d for d in full if d["key"] == "menieres")
    # Guide: adult vertigo rank 3 (0.7), "Recurrent vertigo with ringing",
    # half matched -> 0.7 x 0.675, then x 0.35 for the absent defining
    # feature. Reference: (3 + 1)/13 x 0.35 x 0.85 (uncommon).
    guide = 0.7 * 0.675 * 0.35
    reference = 4 / 13 * 0.35 * 0.85
    assert menieres["guide_score"] == pytest.approx(guide, abs=1e-4)
    assert menieres["score"] == pytest.approx(guide + 0.15 * reference, abs=1e-4)


# ================ a replacement leader must be singled out by the history

def wax_ear(age=72):
    """Right ear conductive (AC 40, BC 10), left ear 15 dB: a wax-like picture."""
    return analyze(40, 10, left_ac=15, left_bc=15, age=age)


def conductive(level=45):
    return analyze(level, 5)


def test_every_condition_declares_what_distinguishes_it():
    generic = {"hearing_loss", "gradual_hearing_loss", "fluctuating_hearing_loss",
               "tinnitus", "speech_in_noise_difficulty", "asks_repetition",
               "muffled_hearing", "poor_speech_discrimination"}
    for key, d in DISEASES.items():
        assert "distinguishing" in d, key
        for s in d["distinguishing"]:
            assert d["symptoms"].get(s, 0) > 0, (key, s)
            assert s not in IMPLIED_SYMPTOMS, (key, s)
            # A generic complaint distinguishes nothing — except the onset
            # that defines a condition (fluctuating, for Meniere's).
            if s in generic:
                assert s in d["requires_any"], (key, s)
    assert DISEASES["pagets"]["distinguishing"] == []
    assert "hearing_loss" in DISEASES["cholesteatoma"]["requires_any"]
    assert set(DISEASES["cholesteatoma"]["distinguishing"]) == {
        "foul_smelling_discharge", "ear_discharge"}


def test_pagets_is_not_named_for_a_presbycusis_history_with_a_waxy_ear():
    history = client.post("/api/symptoms/analyze", json={
        "age": 72, "symptoms": ["gradual_hearing_loss",
                                "speech_in_noise_difficulty", "tinnitus"]}).json()
    assert history["differential"][0]["key"] == "sensory_presbycusis"
    an = wax_ear()
    rec = S.reconcile(history, an)
    assert rec["outcome"] == "unresolved" and rec["leading"] is None
    rows = {r["key"]: r for r in rec["differential"]}
    # Paget's (mixed) is left open by the conductive ear, and its score clears
    # the floor — only the absence of anything that singles it out stops it.
    assert rows["pagets"]["audiogram"] == "compatible"
    # Paget's 7/12 x 0.7 (rare) = 0.408 is above presbycusis's 10/13 x 0.35.
    assert rows["sensory_presbycusis"]["score"] == pytest.approx(
        10 / 13 * 0.35, abs=1e-3)
    assert rows["pagets"]["score"] == pytest.approx(7 / 12 * 0.7, abs=1e-3)
    assert rows["pagets"]["score"] > rows["sensory_presbycusis"]["score"]
    assert rows["pagets"]["cannot_lead_because"] == (
        "nothing the patient reported distinguishes it from a hearing loss in "
        "general")
    assert rows["cholesteatoma"]["cannot_lead_because"] == \
        rows["pagets"]["cannot_lead_because"]

    p = picture(analysis=an, assessment=history)
    line = history_line(p)
    assert "Paget" not in line["says"]
    assert line["says"] == (
        "No well-supported possibility the history raised fits the measured "
        "audiogram (on the history alone: Sensory presbycusis (age-related "
        "hearing loss)).")
    assert "otoscopy and tympanometry first" in line["detail"]
    assert "right conductive at 40 dB HL" in line["detail"]
    assert any("no well-supported possibility" in c for c in p["conflicts"])

    body = client.post("/api/symptoms/correlate", json={
        "assessment": history, "analysis": an}).json()
    assert "Paget" not in body["verdict"]
    assert "otoscopy and tympanometry first" in body["verdict"]


@pytest.mark.parametrize("age,symptoms", [
    (40, ["noise_exposure", "tinnitus", "gradual_hearing_loss"]),
    (70, ["gradual_hearing_loss", "speech_in_noise_difficulty"]),
    (50, ["ototoxic_medication", "tinnitus", "hearing_loss", "imbalance"]),
    (45, ["vertigo", "tinnitus", "aural_fullness", "fluctuating_hearing_loss"]),
    (40, ["sudden_hearing_loss"]),
    (40, ["sudden_hearing_loss", "vertigo", "tinnitus"]),
], ids=["nihl", "presbycusis", "ototoxicity", "menieres", "ssnhl-alone",
        "ssnhl-vertigo"])
def test_no_rare_or_unspecific_condition_replaces_a_leader(age, symptoms):
    """The verifier's survey: Paget's and discharge-free cholesteatoma were
    named on a conductive audiogram. Now nothing is, and the line points at
    the middle ear instead."""
    history = S.assess(age=age, symptoms=symptoms)
    an = conductive()
    rec = S.reconcile(history, an)
    assert rec["outcome"] == "unresolved", rec["leading"]
    assert "otoscopy and tympanometry first" in rec["next_step"]
    line = history_line(picture(analysis=an, assessment=history))
    assert not line["says"].startswith("Leading possibility")
    for name in ("Paget", "Cholesteatoma"):
        assert name not in line["says"]


def test_a_stated_discharge_lets_cholesteatoma_replace_the_leader():
    """Foul discharge with a conductive ear is cholesteatoma until excluded."""
    history = S.assess(age=72, symptoms=["gradual_hearing_loss",
                                         "speech_in_noise_difficulty", "tinnitus",
                                         "foul_smelling_discharge"])
    # Presbycusis (3+2+3+2)/13; cholesteatoma (3+2+1)/13, no commonness weight
    # (a red-flag condition), above presbycusis's 10/13 x 0.35 once set aside.
    assert history["differential"][0]["score"] == pytest.approx(10 / 13, abs=1e-4)
    chole = entry(history, "cholesteatoma")
    assert chole["score"] == pytest.approx(6 / 13, abs=1e-4)
    rec = S.reconcile(history, wax_ear())
    assert rec["outcome"] == "replaced"
    assert rec["leading"]["key"] == "cholesteatoma"
    # The conductive component still gets its middle-ear step: otoscopy is
    # how a cholesteatoma (or the commoner wax) is seen.
    assert "otoscopy and tympanometry first" in rec["next_step"]
    line = history_line(picture(analysis=wax_ear(), assessment=history))
    assert line["says"] == ("Leading possibility once the audiogram is "
                            "considered: Cholesteatoma.")


def test_a_sudden_conductive_loss_with_a_full_ear_names_eustachian_tube_dysfunction():
    """AAO-HNS 2019 key action statement 1: separate SSNHL from a conductive
    loss. A stated full ear singles out ETD; cholesteatoma, ranked above it
    on the history, has no discharge."""
    history = S.assess(age=40, symptoms=["sudden_hearing_loss", "tinnitus",
                                         "aural_fullness"])
    # SSNHL (3+1+2+2)/10 = 0.8; ETD (3+1)/14, common, at or above 0.8 x 0.35.
    assert history["differential"][0]["score"] == pytest.approx(0.8, abs=1e-4)
    assert entry(history, "etd")["score"] == pytest.approx(4 / 14, abs=1e-4)
    rec = S.reconcile(history, conductive())
    assert rec["outcome"] == "replaced"
    assert rec["leading"]["key"] == "etd"
    rows = {r["key"]: r for r in rec["differential"]}
    assert not rows["cholesteatoma"]["can_lead"]
    assert "otoscopy and tympanometry first" in rec["next_step"]


def test_a_typical_age_range_is_a_prior_not_a_bar_to_replacement():
    """SSNHL's range is the AAO-HNS 2019 guideline's scope (18 and over), not
    an exclusion: a 16-year-old with a sudden one-sided sensorineural loss
    and a stated sudden onset still gets SSNHL named. Only an age-DEFINED
    condition (presbycusis) is barred outside its age."""
    history = S.assess(age=16, symptoms=["aural_fullness", "popping",
                                         "muffled_hearing", "sudden_hearing_loss"])
    # ETD (3+3+3+1)/14; SSNHL (3+1+2+1)/10 x (1 - 0.4 x 2/25), two years
    # below its range.
    assert history["differential"][0]["key"] == "etd"
    assert history["differential"][0]["score"] == pytest.approx(10 / 14, abs=1e-4)
    ssnhl = entry(history, "ssnhl")
    assert ssnhl["age_fit"] is False
    assert ssnhl["score"] == pytest.approx(0.7 * (1 - 0.4 * 2 / 25), abs=1e-4)
    an = analyze(60, 60, left_ac=10, left_bc=10, age=16)
    rec = S.reconcile(history, an)
    assert rec["outcome"] == "replaced" and rec["leading"]["key"] == "ssnhl"
    assert history["urgency"] == "emergency"


def test_the_middle_ear_step_needs_a_conductive_component():
    """An ETD history over a measured sensorineural loss: nothing qualifies,
    and otoscopy is not offered as the answer to a cochlear loss."""
    history = S.assess(age=30, symptoms=["blocked_ear", "popping",
                                         "muffled_hearing"])
    rec = S.reconcile(history, analyze(50, 50))
    assert rec["outcome"] == "unresolved" and rec["next_step"] == ""
    assert "tympanometry" not in rec["headline"]


def test_a_child_with_listening_difficulty_and_a_conductive_loss_is_sent_to_the_middle_ear():
    history = S.assess(age=9, symptoms=["speech_in_noise_difficulty",
                                        "difficulty_following_instructions"])
    assert history["differential"][0]["key"] == "capd"
    rec = S.reconcile(history, conductive())
    assert rec["outcome"] == "unresolved"
    assert rec["next_step"].startswith("the measured loss has a conductive "
                                       "component")
    assert rec["headline"].endswith(" The measured loss has a conductive "
                                    "component (right conductive at 45 dB HL, "
                                    "left conductive at 45 dB HL), whose causes "
                                    "— wax, a middle-ear effusion, a perforation, "
                                    "a fixed ossicular chain — need not show in "
                                    "the history: otoscopy and tympanometry "
                                    "first.")


# ================ Results and the Symptoms page read the ears the same way

def _both_lines(history, an):
    line = history_line(picture(analysis=an, assessment=history))
    return line, S.correlate(history, an)


def test_a_one_sided_condition_with_one_provisional_ear_is_left_open_on_both_screens():
    """ETD can be one-sided: a measured sensorineural left ear does not set it
    aside while the right ear's type is provisional."""
    an = analyze_ears({"ac": flat(45, AC)},
                      {"ac": flat(50, AC), "bc": flat(50, BC)}, age=30)
    assert an["rules"]["right"]["type"] == "Sensorineural (provisional)"
    assert an["rules"]["left"]["type"] == "Sensorineural"
    history = S.assess(age=30, symptoms=CONDUCTIVE_HISTORIES[2][1])
    line, result = _both_lines(history, an)
    explain = ("the left ear's sensorineural loss (50 dB HL) is not the type it "
               "predicts and needs its own explanation")
    assert line["says"] == "Leading possibility: Eustachian tube dysfunction."
    assert "neither confirm nor set it aside by type" in line["detail"]
    assert explain in line["detail"]
    assert result["audiogram"] == "undetermined"
    assert "does not fit" not in result["verdict"]
    assert "neither confirm nor rule out" in result["verdict"]
    assert explain[0].upper() + explain[1:] in result["verdict"]
    assert len(result["against"]) == 1 and len(result["undetermined"]) == 1


def test_normal_thresholds_neither_support_nor_contradict_on_both_screens():
    history = S.assess(age=45, symptoms=["vertigo", "tinnitus", "aural_fullness",
                                         "fluctuating_hearing_loss"])
    line, result = _both_lines(history, analyze(10, 10))
    assert line["says"] == "Leading possibility: Meniere's disease."
    for text in (line["detail"], result["verdict"]):
        assert "within normal limits" in text
        assert "does not support it" in text
        assert "does not rule it out" in text
        assert "does not fit" not in text
    assert "conflict" not in line
    assert result["against"] == []


def test_a_loss_one_ear_does_not_explain_is_named_on_both_screens():
    history = S.assess(age=72, symptoms=["gradual_hearing_loss",
                                         "speech_in_noise_difficulty", "tinnitus"])
    cases = [
        (analyze(50, 50, left_ac=40, left_bc=10, age=72),
         "the left ear's conductive loss (40 dB HL) is not the type it predicts "
         "and needs its own explanation"),
        # Presbycusis is bilateral: a normal ear beside an affected one is
        # itself a finding ("marked asymmetry is not presbycusis").
        (analyze(50, 50, left_ac=10, left_bc=10, age=72),
         "the left ear is within normal limits (10 dB HL), and it usually "
         "affects both ears"),
    ]
    for an, note in cases:
        rec = S.reconcile(history, an)
        assert rec["outcome"] == "unchanged"
        assert rec["history_leading"]["type_note"] == note
        line, result = _both_lines(history, an)
        assert line["says"] == ("Leading possibility: Sensory presbycusis "
                                "(age-related hearing loss).")
        assert f"not contradicted by the measured type of hearing, though {note}" \
            in line["detail"]
        assert result["verdict"] == ("The audiogram fits the leading diagnosis "
                                     f"only in part: {note}.")


@pytest.mark.parametrize("ear,reading", [
    ({"impaired": True, "conductive": False, "sensorineural": True}, "fits"),
    ({"impaired": True, "conductive": True, "sensorineural": False}, "fits"),
    ({"impaired": True, "conductive": True, "sensorineural": True}, "fits"),
    ({"impaired": True, "conductive": None, "sensorineural": None},
     "undetermined"),
    ({"impaired": False, "conductive": False, "sensorineural": False}, "normal"),
])
def test_either_component_fits_a_mixed_prediction(ear, reading):
    """Paget's produces sensorineural, conductive and mixed losses (Ralston et
    al., 2019): correlate and reconcile read a mixed prediction alike."""
    assert S._ear_reading("mixed", ear) == reading
