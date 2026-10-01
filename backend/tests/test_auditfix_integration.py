"""Cross-group contracts and the open items closed at integration.

Expected values are worked out by hand from the published rule each test
names, not read back from the code:

  Gazette of India S.O. 76(E) 2018, paras 20.2.2-20.2.3: PTA of 500/1k/2k/4k
    Hz with no response = 95 dB, ready reckoner, binaural (5 x better +
    poorer) / 6.
  WHO World Report on Hearing (2021): grades on the four-frequency average.
  BSA (2023) OAE Recommended Procedure s.6.2 / s.8.1: SNR >= 6 dB and
    >= -5 dB SPL is a clear response; "Inconclusive" only when a response
    could be obscured by noise.
  Silman & Gelfand (1981): reflex absence is rare below ~80 dB HL cochlear loss.
  Jerger, Anthony, Jerger & Mauldin (1974): middle-ear disorders abolish the
    acoustic reflex.
"""
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clinical import consistency, diagnosis, linkage, symptoms as S
from app.clinical.dpoae import cochlear_profile, dp_gram
from app.clinical.forecast import forecast
from app.clinical.immittance import classify_tympanogram
from app.clinical.oae import judge_emission
from app.main import app
from app.ml.features import label_shape_caveat, plausibility_reasons, steep_worsenings
from app.services import report
from app.services.validation import normalize_grade, normalize_pattern

client = TestClient(app)

AC = (250, 500, 1000, 2000, 4000, 8000)
BC = (250, 500, 1000, 2000, 4000)
REPO = Path(__file__).resolve().parents[2]
TYMP_A = {"tymp_pressure": 0, "tymp_compliance": 0.8, "tymp_ecv": 1.2}
TYMP_B = {"tymp_pressure": 0, "tymp_compliance": 0.05, "tymp_ecv": 1.2}


def ear(ac, bc=None, **extra):
    body = {"ac": {str(f): ac for f in AC}, **extra}
    if bc is not None:
        body["bc"] = {str(f): bc for f in BC}
    return body


def analyze(right, left=None, patient=None, transducer="supra_aural"):
    r = client.post("/api/analyze", json={
        "patient": patient or {"name": "T", "age": 40}, "transducer": transducer,
        "right": right, "left": left if left is not None else ear(10, 10)})
    assert r.status_code == 200, r.text
    return r.json()


# ======= a significant air-bone gap behind normal hearing (rules: "Normal") ===

# R AC 15 / BC -5: PTA 15 dB HL (WHO normal, < 20), gap 20 dB (> 10).
GAP_EAR = dict(ac=15, bc=-5)


def test_gap_behind_normal_hearing_with_type_b_is_confirmed_not_contradicted():
    out = analyze(ear(**GAP_EAR, **TYMP_B))
    assert out["rules"]["right"]["type"] == "Normal"
    assert out["rules"]["right"]["significant_air_bone_gap"] is True
    right = out["battery"]["right"]
    titles = [c["title"] for c in right["contradictions"]]
    assert "Middle-ear pathology without an air-bone gap" not in titles
    assert any(c["title"].startswith("Air-bone gap confirmed by tympanometry")
               for c in right["confirmations"])


def test_gap_behind_normal_hearing_with_type_a_raises_the_third_window_prompt():
    out = analyze(ear(**GAP_EAR, **TYMP_A))
    titles = [c["title"] for c in out["battery"]["right"]["contradictions"]]
    assert "Air-bone gap without middle-ear pathology" in titles


def test_gap_behind_normal_hearing_reaches_report_verdict_and_triage():
    # Insert earphones: with supra-aural phones this ear has a genuine
    # bone-conduction masking dilemma at 250 Hz (occlusion effect), whose
    # validity alert would rightly lead the verdict instead.
    # A 20 dB air-bone gap makes masked bone conduction indicated (BSA
    # 2018); the test records it as done so the gap is the only finding.
    out = analyze(ear(**GAP_EAR, masked=True), transducer="insert")
    assert not out["safety"]["masking_review"]["any_dilemma"]
    assert not out["safety"]["masking_review"]["any_unmasked"]
    rep = client.post("/api/report", json=out)
    assert rep.status_code == 200, rep.text
    recs = rep.json()["report"]["recommendations"]
    assert any(r.startswith("ENT referral for the conductive component") for r in recs)
    assert any("20 dB air-bone gap" in r for r in recs)

    v = out["verdict"]
    assert "air-bone gap of 20 dB in the right ear" in v["headline"]
    assert v["tone"] == "loss"
    assert v["action"].startswith("Check the air-bone gap in the right ear")

    codes = [r["code"] for r in out["triage"]["reasons"]]
    assert "air_bone_gap_normal_hearing" in codes
    assert out["triage"]["review_required"] is True


def test_gap_behind_normal_hearing_is_a_measured_conductive_finding_not_a_loss():
    rules_ear = {"type": "Normal", "provisional": False,
                 "significant_air_bone_gap": True, "ac_pta": {"value": 15},
                 "abg": {"value": 20}}
    assert S._ear_parts(rules_ear) == (True, False, False)
    ears = S._measured_ears({"rules": {"right": rules_ear}})
    assert ears[0]["impaired"] is False and ears[0]["gap_only"] is True


def test_linkage_reads_the_gap_as_conductive_for_disease_typing():
    out = analyze(ear(**GAP_EAR))
    result = linkage.audiogram_vs_diseases(out, "right")
    assert result["normal_audiogram"] is True
    assert "air-bone gap" in result["headline"]
    conductive_rows = [r for r in result["differential"]
                       if r["expected_type"] == "conductive"]
    assert all(r["type_match"] == 1.0 for r in conductive_rows)


def test_forks_reading_conductive_agree_with_a_gap_behind_normal_hearing():
    out = analyze(ear(**GAP_EAR))
    conv = diagnosis._convergence(
        out, [], {"grid": {"loss_type": "conductive", "side": "right"}})
    assert any("fork battery reads conductive" in a for a in conv["agreements"])
    assert not any("forks read conductive" in c for c in conv["conflicts"])


# ============================ masking row reads the masking review ===========

def test_masking_row_is_quiet_when_masking_was_not_indicated():
    """AC 15 / BC 10 with a Type B tympanogram: a battery contradiction sets
    safety.validity_warning, but no frequency reaches the crossover point."""
    out = analyze(ear(15, 10, **TYMP_B), ear(15, 10, **TYMP_A))
    assert out["safety"]["validity_warning"] is True
    assert out["safety"]["masking_review"]["any_indicated"] is False
    p = client.post("/api/diagnosis/picture", json={"analysis": out}).json()
    rows = {f["key"]: f for f in p["findings"]}
    assert rows["masking"]["alarm"] is False
    assert rows["masking"]["detail"] is None
    assert not any(t["test"] == "Masked thresholds" for t in p["next_tests"])


# ===================================== OAE: a clear response is not noise ====

@pytest.mark.parametrize("amp,noise,status,noisy_response", [
    (10.0, -3.0, "inconclusive", True),   # SNR 13 over a floor above -5
    (25.0, 15.0, "inconclusive", True),   # SNR 10 over a +15 floor
    (18.0, 15.0, "inconclusive", False),  # SNR 3 over a noisy floor
    (-15.0, -20.0, "absent", False),      # SNR 5 in a quiet recording
    (-12.0, -20.0, "reduced", False),     # SNR 8 but below the -5 dB SPL minimum
    (-5.0, -11.0, "present", False),      # exactly at all three criteria
])
def test_a_noisy_floor_is_never_a_result_but_a_response_above_it_is_kept(
        amp, noise, status, noisy_response):
    judged = judge_emission(amp, noise)
    assert judged["status"] == status
    assert judged["noisy_response"] is noisy_response


def test_preclinical_damage_beside_a_graded_loss_does_not_say_thresholds_are_normal():
    """Sloping loss, PTA4 (10 + 15 + 40 + 85) / 4 = 37.5 dB HL (WHO moderate),
    Type A, emission absent at 1 kHz where the threshold is 15 dB HL."""
    thresholds = dict(zip(map(str, AC), (10, 10, 15, 40, 85, 90)))
    right = {"ac": thresholds, "bc": {k: v for k, v in thresholds.items() if k != "8000"},
             "oae": [{"freq": f, "amplitude": -15, "noise_floor": -20}
                     for f in (1000, 2000, 4000)], **TYMP_A}
    out = analyze(right)
    assert "preclinical_nihl" in out["battery"]["patterns"]
    head = out["verdict"]["headline"]
    assert not head.startswith("Hearing thresholds are still normal")
    assert "moderate" in head.lower()
    assert "cochlear damage is ahead of the audiogram" in head


def test_a_possible_emission_at_poor_thresholds_reaches_the_instrument_page():
    out = client.post("/api/oae/analyze", json={
        "ear": "right", "protocol": "diagnostic",
        "points": [{"freq": f, "amplitude": 10, "noise_floor": -3}
                   for f in (1000, 2000, 4000)],
        "ac": {"1000": 70, "2000": 70, "4000": 70}}).json()
    assert out["passed_freqs"] == []
    assert [m["freq"] for m in out["possible_unexplained_emissions"]] == [1000, 2000, 4000]
    assert any("thresholds overstate the loss" in line for line in out["interpretation"])


# ================================ reflex rules shared with the battery =======

def _reflex_record(tymp_type, provisional=False, abg=0):
    tymp = {"type": tymp_type, "label": f"Type {tymp_type}",
            "interpretation": "x", "ecv_flag": "normal",
            "suggests_conductive": tymp_type != "A", "provisional": provisional}
    return {
        "rules": {"right": {"ac_pta": {"value": 40}, "type": "Sensorineural",
                            "abg": {"value": abg}}},
        "immittance": {"right": {"tympanogram": tymp,
                                 "reflexes": {"pattern": "absent"}}},
        "oae": {"right": {"present_freqs": [2000]}},
    }


def test_absent_reflexes_with_emissions_are_not_read_past_an_abnormal_middle_ear():
    result = linkage.immittance_vs_diseases(_reflex_record("B"))
    assert not any("emissions are present" in r["when"]
                   for r in result["reflex_findings"])


def test_absent_reflexes_with_emissions_carry_a_caveat_when_the_middle_ear_is_unknown():
    result = linkage.immittance_vs_diseases(_reflex_record("A", provisional=True))
    beyond = [r for r in result["reflex_findings"] if "emissions are present" in r["when"]]
    assert beyond and "confirm the middle ear is normal" in beyond[0]["meaning"]


# ======================= forecast uses the Gazette's 95 dB for no response ===

def test_forecast_current_disability_matches_the_dashboard():
    """AC 65/75/85/NR at 500-4k in both ears: (65+75+85+95)/4 = 80 dB ->
    ready reckoner 74.2%; both ears equal, so binaural 74.2%."""
    cur = {f: v for f, v in zip((250, 500, 1000, 2000, 4000, 8000),
                                (60, 65, 75, 85, "NR", "NR"))}
    base = {f: (v if v == "NR" else v - 10) for f, v in cur.items()}
    f = forecast({"right": base, "left": base}, {"right": cur, "left": cur},
                 "2023-01-01", "2026-01-01", age=50)
    assert f["disability_now"]["binaural_pct"] == pytest.approx(74.2)
    dashboard = analyze({"ac": {str(k): v for k, v in cur.items()}},
                        {"ac": {str(k): v for k, v in cur.items()}})
    assert dashboard["rules"]["disability"]["binaural_pct"] == pytest.approx(74.2)
    assert f["disability_projected"]["certifiable"] is False
    assert "95 [NR]" in f["disability_projected"]["right"]["formula"]


# ================== stored visits never show a superseded disability figure ==

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    import app.services.records as rec
    monkeypatch.setattr(rec, "DB_PATH", tmp_path / "records.db")
    monkeypatch.setattr(rec, "DATA_DIR", tmp_path)
    return rec


def test_a_visit_saved_under_the_old_formula_is_recomputed_on_read(temp_db):
    """52 dB in all four PTA frequencies: the superseded 1.5 x (PTA - 25)
    gave 40.5%; the Gazette ready reckoner gives 52 dB = 20%."""
    analysis = {
        "patient": {"name": "Legacy Visit", "test_date": "2025-01-01"},
        "rules": {"right": {"ac_pta": {"value": 52}}, "left": {"ac_pta": {"value": 52}},
                  "disability": {"binaural_pct": 40.5}},
        "thresholds": {side: {"ac": {str(f): 52 for f in (500, 1000, 2000, 4000)},
                              "bc": {}} for side in ("right", "left")},
    }
    pid = temp_db.save_visit(analysis)["patient_id"]
    visit = temp_db.patient_history(pid)["visits"][0]
    assert visit["disability_pct"] == pytest.approx(20.0)
    assert visit["disability_superseded"] is True
    assert visit["disability_pct_as_stored"] == pytest.approx(40.5)
    assert visit["benchmark_disability"] is False
    assert visit["disability_certifiable"] is True


def test_a_visit_without_thresholds_does_not_show_its_stored_figure(temp_db):
    pid = temp_db.save_visit({
        "patient": {"name": "No Thresholds"},
        "rules": {"disability": {"binaural_pct": 40.5}},
        "thresholds": {"right": {}, "left": {}}})["patient_id"]
    visit = temp_db.patient_history(pid)["visits"][0]
    assert visit["disability_pct"] is None
    assert visit["disability_certifiable"] is False


# ====================================== validation label normalisation ======

@pytest.mark.parametrize("label,expected", [
    ("completely normal", "Normal hearing"),
    ("Completely normal hearing", "Normal hearing"),
    ("totally normal", "Normal hearing"),
    ("normal (complete audiogram)", "Normal hearing"),
    ("Mild - test complete", "Mild hearing loss"),
    ("Moderate (total of 4 freqs)", "Moderate hearing loss"),
    ("sub-total hearing loss", "sub-total hearing loss"),
    ("partial deafness", "partial deafness"),
    ("Total deafness", "Complete or total hearing loss"),
    ("totally deaf", "Complete or total hearing loss"),
    ("Complete or total hearing loss", "Complete or total hearing loss"),
    ("profoundly deaf", "Profound hearing loss"),
])
def test_complete_or_total_only_when_it_qualifies_the_loss(label, expected):
    assert normalize_grade(label) == expected


@pytest.mark.parametrize("label,expected", [
    ("normal", "normal"), ("Normal hearing", "normal"),
    ("within normal limits", "normal"), ("WNL", "normal"),
    ("noise notch", "noise_notch_4k"),
])
def test_normal_pattern_labels_match_the_classifier(label, expected):
    assert normalize_pattern(label) == expected


def test_bundled_sample_labels_its_within_normal_limits_cases_normal():
    import csv
    for path in (REPO / "samples" / "validation_labelled.csv",
                 REPO / "frontend" / "public" / "samples" / "validation_labelled.csv"):
        rows = {r["name"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}
        for case in ("Case 04", "Case 08"):
            assert rows[case]["expert_grade"] == "Normal hearing"
            assert rows[case]["expert_pattern"] == "normal"
        assert rows["Case 05"]["expert_grade"] == "Complete or total hearing loss"


# ========================== implausible worsening steps and forced labels ====

def test_a_worsening_step_beyond_any_trained_configuration_is_flagged():
    # 250 -> 500 Hz worsens by 70 dB; the steepest training step there is 35.
    ac = dict(zip(AC, (5.0, 75.0, 75.0, 80.0, 80.0, 85.0)))
    assert steep_worsenings(ac) == [{"freqs": [250, 500], "worsening_db": 70.0}]
    assert any("worsens by 70 dB from 250 Hz to 500 Hz" in r
               for r in plausibility_reasons(ac))


def test_a_textbook_ski_slope_is_not_flagged():
    # 2 -> 4 kHz worsens by 60 dB, the steepest step in the training data.
    ac = dict(zip(AC, (10.0, 10.0, 15.0, 30.0, 90.0, 100.0)))
    assert steep_worsenings(ac) == []


def test_a_no_response_is_not_a_measured_step():
    ac = dict(zip(AC, (10.0, 10.0, 15.0, 20.0, 120.0, 120.0)))
    assert steep_worsenings(ac) == []


def test_a_flat_label_must_describe_a_flat_audiogram():
    assert label_shape_caveat(dict(zip(AC, (60.0, 45, 45, 5, 25, 75))), "flat")
    assert label_shape_caveat(dict(zip(AC, (40.0, 45, 45, 40, 45, 50))), "flat") is None
    assert label_shape_caveat(dict(zip(AC, (60.0, 45, 45, 5, 25, 75))), "ski_slope") is None


def test_deep_second_opinion_refuses_a_deeply_nested_body():
    r = client.post("/api/model/deep-predict", content=b"[" * 100000,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert "nested too deeply" in r.json()["detail"]


def test_atlas_projection_refuses_an_unreadable_frequency_key():
    from app.ml.classifier import model_available
    if not model_available():
        pytest.skip("model not trained on this install")
    r = client.post("/api/atlas/project", json={"ac": {"1k": 40}})
    assert r.status_code == 422
    assert "1k" in r.json()["detail"]


# ================================================= history and occupation ====

def test_a_null_occupation_is_not_recorded_rather_than_a_422():
    r = client.post("/api/analyze", json={
        "patient": {"name": "T", "age": 40, "occupation": None},
        "right": ear(10, 10), "left": ear(10, 10)})
    assert r.status_code == 200, r.text
    assert r.json()["patient"]["occupation"] == ""


@pytest.mark.parametrize("job,noisy", [
    ("Weaver", True), ("Powerloom operator", True), ("Factory worker", True),
    ("Industrial worker", True), ("Examiner", False), ("Teacher", False),
    ("", False), (None, False),
])
def test_report_uses_the_sourced_noisy_occupation_list(job, noisy):
    assert report._noisy_occupation(job) is noisy


def _stroke_history(age):
    return client.post("/api/symptoms/analyze", json={
        "age": age, "symptoms": ["speech_in_noise_difficulty",
                                 "difficulty_following_instructions",
                                 "asks_repetition", "neurological_history"]}).json()


def _lr(right, left, age=60):
    body = {"patient": {"name": "T", "age": age},
            "right": {"ac": {str(f): right for f in AC}, "bc": {str(f): right for f in BC}},
            "left": {"ac": {str(f): left for f in AC}, "bc": {str(f): left for f in BC}}}
    return client.post("/api/analyze", json=body).json()


def test_presbycusis_is_not_promoted_on_a_one_sided_loss():
    """Presbycusis is declared bilateral; R 60 / L 10 is a one-sided loss that
    needs investigating, not an age-related loss."""
    rec = S.reconcile(_stroke_history(60), _lr(60, 10))
    assert not (rec["outcome"] == "replaced"
                and rec["leading"]["key"] == "sensory_presbycusis")
    row = next(r for r in rec["differential"] if r["key"] == "sensory_presbycusis")
    assert "usually affects both ears" in row["cannot_lead_because"]


def test_presbycusis_still_replaces_capd_on_a_symmetric_loss():
    rec = S.reconcile(_stroke_history(55), _lr(50, 50, age=55))
    assert rec["outcome"] == "replaced"
    assert rec["leading"]["key"] == "sensory_presbycusis"


def test_a_one_sided_condition_is_judged_on_the_affected_ear():
    """A textbook one-sided Meniere's picture: right 60 dB sensorineural,
    left 10. The normal left ear is the expected half of the picture."""
    assessment = S.assess(age=45, symptoms=["vertigo", "fluctuating hearing loss",
                                            "aural fullness", "tinnitus"])
    top = next(d for d in assessment["differential"] if d["key"] in S.DISEASES)
    assert top["key"] == "menieres"
    result = linkage.symptoms_vs_audiogram(assessment, _lr(60, 10, age=45))
    titles = [c["title"] for c in result["conflicts"]]
    assert not any("Thresholds are better than" in t for t in titles)
    assert not any(t.startswith("Left ear type does not match") for t in titles)
    assert result["degree_judged_on"] == "worse"


# ================================================ instrument wording ========

def test_unjudged_frequencies_beside_a_basal_loss_are_not_called_unaffected():
    gram = dp_gram([{"freq": 2000, "amplitude": 18, "noise_floor": 15},
                    {"freq": 3000, "amplitude": -20, "noise_floor": -25},
                    {"freq": 4000, "amplitude": -20, "noise_floor": -25}],
                   protocol="diagnostic")
    summary = cochlear_profile(gram)["summary"]
    assert "confined" not in summary
    assert "[2000] Hz could not be judged" in summary


def test_points_marked_off_scale_are_not_called_a_dropout():
    sg = 60 / 2.355
    pts = [(p, 0.6 + 3.5 * math.exp(-((p + 55) ** 2) / (2 * sg * sg)))
           for p in range(-400, 201, 10)]
    trace = [{"pressure": p, "admittance": None, "off_scale": True} if a > 4.0
             else {"pressure": p, "admittance": round(a, 4)} for p, a in pts]
    out = client.post("/api/tympanometry/analyze",
                      json={"age_years": 30, "trace": trace}).json()
    if out["curve"]["gap"] == "apex":
        assert out["curve"]["gap_marked_off_scale"] is True
        assert "marked beyond the instrument's range" in out["not_typed"]
        assert "dropout" not in out["not_typed"]
        assert not any("dropout rather than" in f for f in out["flags"])
    else:
        assert out["curve"]["gap"] == "off_scale"


def test_a_1000_hz_peak_whose_criterion_cannot_be_measured_is_not_a_pass():
    """Sweep -300 to +200 daPa: the -400 daPa tail the Margolis et al. (2003)
    0.6 mmho criterion is measured from was never recorded."""
    from app.clinical import tympanometry as T
    sg = 90 / 2.355
    trace = [{"pressure": p,
              "admittance": round(0.8 + 0.5 * math.exp(-(p ** 2) / (2 * sg * sg)), 4)}
             for p in range(-300, 201, 10)]
    typed = T.analyze(trace=trace, age_years=0.1, probe_hz=1000)["tympanogram"]
    assert typed["static_admittance"] is None
    assert typed["refer"] is True and typed["provisional"] is True
    assert any("this is not a pass" in c for c in typed["caveats"])


def test_an_entered_but_untypable_adult_tympanogram_says_why():
    out = analyze(ear(10, 10, tymp_compliance=0.8, tymp_ecv=1.2))
    imm = out["immittance"]["right"]
    assert imm["tympanogram"] is None and imm["tympanogram_untyped"] is True
    assert imm["not_typed"].startswith("Not typed. Peak pressure was not recorded.")
    assert out["battery"]["right"]["middle_ear"]["reason"] == (
        "the tympanogram values entered were not enough to type it")


def test_srt_that_cannot_confirm_the_tones_is_raised_for_certification():
    # 20/70/90 dB at 500/1k/2k with SRT 25: a precipitous configuration in
    # which the SRT may follow the best single threshold (Schoepflin 2012).
    steep = {"250": 15, "500": 20, "1000": 70, "2000": 90, "4000": 95, "8000": 100}
    out = analyze({"ac": steep, "bc": {k: v for k, v in steep.items() if k != "8000"},
                   "srt": 25})
    alerts = [a for a in out["safety"]["alerts"]
              if a["title"] == "SRT cannot confirm the pure tones"]
    assert alerts and alerts[0]["ear"] == "right"
    assert "before certifying disability" in alerts[0]["action"]


def test_otoscopy_model_limits_no_longer_claim_image_level_validation():
    body = client.get("/api/otoscopy/model").json()
    text = " ".join(body["limits"])
    assert "leave-one-image-out" not in text


def test_tympanometry_reference_calls_the_gradient_cut_off_a_heuristic():
    body = client.get("/api/tympanometry/reference").json()
    assert "Normal > 0.2" not in body["gradient_formula"]
    assert "heuristic" in body["gradient_formula"]
    assert body["high_frequency"]["newborn_admittance_p95"] == 4.3


def test_otoscopy_reference_images_vary_on_origin():
    atlas = client.get("/api/otoscopy/reference").json()
    src = atlas["classes"][0]["images"][0]
    r = client.get(src)
    assert r.status_code == 200
    assert "Origin" in r.headers.get("vary", "")
    assert r.headers["content-type"] == "image/jpeg"


# ============================================== the AEP line in the picture ==

def test_a_borderline_aep_battery_is_not_shown_as_a_clean_normal():
    aep = {"battery": {"headline": "Not a normal result: ABR borderline",
                       "abnormal": False, "uncertain_levels": ["ABR"],
                       "limitations": ["eighth nerve not assessed"]}}
    done = {k: False for k in ("symptoms", "otoscopy", "pure_tone", "masking",
                               "tympanometry", "oae", "speech", "tuning_fork",
                               "aep", "boa", "reflexes")}
    done["aep"] = True
    rows = diagnosis._findings({}, None, None, aep, None, None, done)
    line = next(r for r in rows if r["key"] == "aep")
    assert line["alarm"] is False and line["caution"] is True
    assert "borderline or indeterminate: ABR" in line["detail"]
    assert "eighth nerve not assessed" in line["detail"]


# ======================================================== frontend checks ===

def test_cochlea_map_bands_are_the_who_2021_grades():
    import re

    from app.clinical.rules import WHO_GRADES
    src = (REPO / "frontend" / "src" / "components" / "CochleaMap.jsx").read_text(
        encoding="utf-8")
    edges = re.search(r"const BAND_EDGES = \[([^\]]+)\]", src).group(1)
    assert [float(x) for x in edges.split(",")] == [hi for _lo, hi, *_ in WHO_GRADES[:-1]]
    for ramp in re.findall(r"(?:right|left): \[([^\]]+)\]", src):
        assert len(ramp.split(",")) == len(WHO_GRADES)


STAIR_HARNESS = r"""
import { pathToFileURL } from 'node:url'
const { Staircase } = await import(pathToFileURL(process.argv[2]).href)
function run(respond) {
  const est = new Staircase(40, -10, 90)
  const played = []
  let guard = 0
  while (!est.done && guard++ < 200) { played.push(est.level); est.record(respond(est.level)) }
  return { threshold: est.threshold, maxPlayed: Math.max(...played) }
}
const out = {}
for (const T of [-10, 0, 45, 85, 88, 90]) out[T] = run((L) => L >= T)
out.never = run(() => false)
console.log(JSON.stringify(out))
"""


def test_staircase_plays_the_maximum_before_no_response_and_ends_at_the_floor(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    tone = tmp_path / "tone.mjs"
    tone.write_text((REPO / "frontend" / "src" / "audio" / "toneAudiometer.js")
                    .read_text(encoding="utf-8"), encoding="utf-8")
    harness = tmp_path / "harness.mjs"
    harness.write_text(STAIR_HARNESS, encoding="utf-8")
    run = subprocess.run([node, str(harness), str(tone)], capture_output=True,
                         text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    # A listener who hears 88 dB and above first responds at the 90 dB step.
    assert out["88"]["threshold"] == 90 and out["90"]["threshold"] == 90
    assert out["85"]["threshold"] == 85
    # "No Response" only after a tone at the 90 dB maximum went unanswered.
    assert out["never"] == {"threshold": "NR", "maxPlayed": 90}
    # A listener answering at the -10 dB floor ends there, not at a cap.
    assert out["-10"]["threshold"] == -10


# ================================================= the end-to-end case ======

def test_moderate_snhl_end_to_end():
    """Right AC 20/30/40/50/60/70, BC 30/40/50/60 at 500-4k; left AC/BC 10.

    Right PTA4 (30+40+50+60)/4 = 45 -> WHO moderate; air-bone gap 0 ->
    sensorineural. Gazette: 45 dB -> 13%; left 10 dB -> 0%; binaural
    (5 x 0 + 13) / 6 = 2.1667 -> 2.17%.
    """
    right = {"ac": dict(zip(map(str, AC), (20, 30, 40, 50, 60, 70))),
             "bc": {"500": 30, "1000": 40, "2000": 50, "4000": 60}}
    left = {"ac": {str(f): 10 for f in AC}, "bc": {str(f): 10 for f in BC}}
    out = analyze(right, left)
    r = out["rules"]["right"]
    assert r["who_grade"]["grade"] == "Moderate hearing loss"
    assert r["type"] == "Sensorineural"
    d = out["rules"]["disability"]
    assert d["right"]["pct"] == 13.0
    assert d["binaural_pct"] == pytest.approx(2.17)
    assert d["certifiable"] is True
    assert out["safety"]["asymmetry"]["flag"] is True
    head = out["verdict"]["headline"].lower()
    assert "moderate" in head and "sensorineural" in head


def test_normal_pair_end_to_end():
    out = analyze(ear(10, 10), ear(10, 10))
    assert not out["safety"]["has_urgent"] and not out["safety"]["has_emergency"]
    rep = client.post("/api/report", json=out).json()["report"]
    text = json.dumps(rep, ensure_ascii=False)
    assert "Mandatory hearing protection" not in text
    assert "noise-induced" not in text.lower()
    assert out["verdict"]["tone"] == "normal"
