"""OAE criteria, middle-ear gating of the battery, and infant immittance.

Expected values here come from the published criteria, not from the module
constants, so a constant drifting away from its standard fails the suite:

  BSA (2023) Recommended Procedure, Clinical Application of OAEs
    s.8.1  pass: SNR >= 6 dB with a minimum signal of -5 dB SPL
    s.6.2  "no clear response" only with noise <= -5 dB SPL, else inconclusive
    Table 4  absent OAEs with normal thresholds mean outer hair cell damage
             only once a normal middle ear is confirmed
  Silman & Gelfand (1981): absent reflexes are rare in cochlear loss below
    about 80 dB HL
  Jerger, Anthony, Jerger & Mauldin (1974): middle-ear disorders abolish
    acoustic reflexes
  Jerger (1970): Type C negative pressure commonly brings a mild conductive
    loss
  JCIH (2019): 1000 Hz probe for infants up to 9 months
"""
import pytest
from fastapi.testclient import TestClient

from app.clinical import dpoae
from app.clinical.consistency import battery_review, reconcile_ear
from app.clinical.immittance import (analyze_immittance, analyze_reflexes,
                                     classify_tympanogram)
from app.clinical.oae import classify_oae, oae_audiogram_agreement
from app.main import app
from app.models.schemas import EarData

client = TestClient(app)

FREQS = (250, 500, 1000, 2000, 4000, 8000)
BC_FREQS = (250, 500, 1000, 2000, 4000)

TYMP_A = {"tymp_pressure": 0, "tymp_compliance": 0.8, "tymp_ecv": 1.2}
TYMP_B = {"tymp_pressure": 0, "tymp_compliance": 0.05, "tymp_ecv": 1.2}
TYMP_C = {"tymp_pressure": -250, "tymp_compliance": 0.6, "tymp_ecv": 1.2}


def ear(ac, bc=None, **extra):
    body = {"ac": {str(f): ac for f in FREQS}, **extra}
    if bc is not None:
        body["bc"] = {str(f): bc for f in BC_FREQS}
    return body


def emissions(amplitude, noise_floor, freqs=(1000, 2000, 4000)):
    return [{"freq": f, "amplitude": amplitude, "noise_floor": noise_floor}
            for f in freqs]


def analyze(right, age=40):
    r = client.post("/api/analyze", json={"patient": {"name": "T", "age": age},
                                          "right": right, "left": {}})
    assert r.status_code == 200, r.text
    return r.json()


def oae_instrument(points, protocol="screening", ac=None):
    r = client.post("/api/oae/analyze", json={"ear": "right", "protocol": protocol,
                                              "points": points, "ac": ac or {}})
    assert r.status_code == 200, r.text
    return r.json()


def right_titles(out, key="contradictions"):
    return [c["title"] for c in out["battery"]["right"][key]]


def alerts(out, level=None):
    return [a for a in out["safety"]["alerts"]
            if a.get("ear") in ("right", "both") and (level is None or a["level"] == level)]


# ============================ B2-1 absolute emission floor =================

def test_newborn_emissions_below_minus_5_db_spl_refer_not_pass():
    """SNR 8 dB but only -12 dB SPL: below the -5 dB SPL minimum signal."""
    out = oae_instrument(
        [{"freq": f, "amplitude": -12, "noise_floor": -20} for f in (2000, 3000, 4000)],
        protocol="newborn")
    assert out["outcome"] == "refer"
    assert out["passed_freqs"] == []
    assert {p["status"] for p in out["points"]} == {"reduced"}
    assert all("-5 dB SPL" in p["reason"] for p in out["points"])


@pytest.mark.parametrize("amplitude,noise,expected", [
    (-5.0, -11.0, "pass"),     # exactly the -5 dB SPL minimum, SNR 6
    (-4.0, -14.0, "pass"),
    (-5.1, -11.1, "refer"),    # SNR 6 but just below the minimum level
])
def test_minimum_emission_level_is_inclusive(amplitude, noise, expected):
    out = oae_instrument(
        [{"freq": f, "amplitude": amplitude, "noise_floor": noise}
         for f in (2000, 3000, 4000)], protocol="newborn")
    assert out["outcome"] == expected


def test_weak_emission_is_not_a_working_cochlea_in_the_battery():
    out = analyze(ear(70, 65, oae=emissions(-12, -20), **TYMP_A))
    assert "Working cochlea with poor pure-tone thresholds" not in right_titles(out)
    assert "oae_threshold_mismatch" not in out["battery"]["patterns"]
    assert out["oae"]["right"]["present_freqs"] == []
    assert out["oae"]["right"]["reduced_freqs"] == [1000, 2000, 4000]


def test_a_real_emission_with_poor_thresholds_is_still_flagged():
    out = analyze(ear(70, 65, oae=emissions(15, -10), **TYMP_A))
    assert "Working cochlea with poor pure-tone thresholds" in right_titles(out)


# =================== B2-2 pre-clinical damage needs a normal middle ear ====

@pytest.mark.parametrize("name,right,screen", [
    ("type_b_normal_thresholds", ear(15, 5, oae=emissions(-15, -20), **TYMP_B), True),
    ("type_c_negative_pressure", ear(15, 10, oae=emissions(-15, -20), **TYMP_C), True),
    # AC 20 dB HL flat is a PTA of 20: WHO 2021 grades it a mild loss.
    ("type_b_conductive_gap", ear(20, 0, oae=emissions(-15, -20), **TYMP_B), False),
])
def test_absent_emissions_behind_an_abnormal_middle_ear_are_not_cochlear_damage(
        name, right, screen):
    out = analyze(right)
    assert "preclinical_nihl" not in out["battery"]["patterns"], name
    assert "oae_middle_ear_limited" in out["battery"]["patterns"], name
    assert not alerts(out, "urgent"), name
    assert "being damaged" not in out["verdict"]["headline"], name
    assert "Enforce hearing protection" not in out["verdict"]["action"], name
    # Not urgent, but not a footnote either while the audiogram grades the
    # ear normal: the cochlear question the emissions were run for is still
    # open, so the repeat is a validity item. Once the audiogram grades a
    # loss, that loss's own referral leads and the note is information.
    note = next(a for a in alerts(out)
                if a["title"] == "Absent emissions explained by the middle ear")
    assert note["level"] == ("validity" if screen else "info"), name
    if not screen:
        assert "repeat the emissions" not in out["verdict"]["action"], name


def test_absent_emissions_without_a_tympanogram_are_only_possible_damage():
    out = analyze(ear(15, 10, oae=emissions(-15, -20)))
    patterns = out["battery"]["patterns"]
    assert "preclinical_nihl" not in patterns
    assert "preclinical_nihl_possible" in patterns
    assert not alerts(out, "urgent")
    titles = [a["title"] for a in alerts(out, "validity")]
    assert any("confirm middle-ear status first" in t for t in titles)
    assert "tympanometry" in out["verdict"]["action"].lower()
    assert "middle ear" in out["battery"]["headline"]


def test_absent_emissions_behind_a_normal_middle_ear_remain_urgent():
    out = analyze(ear(15, 10, oae=emissions(-15, -20), **TYMP_A))
    assert "preclinical_nihl" in out["battery"]["patterns"]
    assert any(a["title"] == "Pre-clinical cochlear damage detected"
               for a in alerts(out, "urgent"))


def test_an_infant_type_a_does_not_confirm_a_normal_middle_ear():
    out = analyze(ear(15, 10, oae=emissions(-15, -20), **TYMP_A), age=0)
    assert "preclinical_nihl" not in out["battery"]["patterns"]
    assert "preclinical_nihl_possible" in out["battery"]["patterns"]


def test_cochlear_confirmation_uses_the_same_middle_ear_gate():
    absent = classify_oae(emissions(-15, -20))
    rules_ear = {"type": "Sensorineural", "ac_pta": {"value": 60},
                 "abg": {"value": 0.0}}
    type_a = {"tympanogram": classify_tympanogram(-10, 0.7, 1.2), "reflexes": None}
    type_c = {"tympanogram": classify_tympanogram(-250, 0.6, 1.2), "reflexes": None}
    flat60 = {f: 60 for f in FREQS}
    assert "cochlear_confirmed" in reconcile_ear(
        "right", rules_ear, type_a, absent, None, flat60)["patterns"]
    for immittance in (None, type_c):
        assert "cochlear_confirmed" not in reconcile_ear(
            "right", rules_ear, immittance, absent, None, flat60)["patterns"]


def test_the_agreement_detail_does_not_assert_damage_unconditionally():
    findings = oae_audiogram_agreement(classify_oae(emissions(-15, -20)),
                                       {1000: 10.0})
    assert "once a normal middle ear is confirmed" in findings[0]["detail"]


# ===================== B2-3 noisy recordings are "could not test" ==========

def test_noisy_emissions_with_normal_thresholds_are_not_damage():
    out = analyze(ear(10, 10, oae=emissions(18, 15), **TYMP_A))
    oae = out["oae"]["right"]
    assert oae["inconclusive_freqs"] == [1000, 2000, 4000]
    assert oae["present_freqs"] == [] and oae["absent_freqs"] == []
    assert oae["all_absent"] is False and oae["all_present"] is False
    assert oae["valid"] is False
    assert oae["preclinical_damage"] == []
    assert "preclinical_nihl" not in out["battery"]["patterns"]
    assert not alerts(out, "urgent")
    # Thresholds of 10 dB HL: an emission was expected at every frequency, so
    # the repeat is owed and has to reach the verdict.
    assert any(a["title"] == "Emissions could not be judged at some frequencies"
               for a in alerts(out, "validity"))
    assert "Repeat [1000, 2000, 4000] Hz in quiet" in out["verdict"]["action"]


def test_a_plus_5_db_spl_noise_floor_is_inconclusive_not_refer():
    out = oae_instrument([{"freq": f, "amplitude": 8, "noise_floor": 5}
                          for f in (2000, 3000, 4000)])
    assert out["outcome"] == "incomplete"
    assert out["referred_freqs"] == []
    assert out["invalid_freqs"] == [2000, 3000, 4000]


def test_a_noisy_recording_never_passes_however_large_the_snr():
    out = oae_instrument([{"freq": f, "amplitude": 25, "noise_floor": 15}
                          for f in (2000, 3000, 4000)], protocol="newborn")
    assert out["outcome"] == "incomplete"
    assert out["passed_freqs"] == []
    # The response that cleared the floor is kept for a repeat, not dropped.
    assert all(p["noisy_response"] for p in out["points"])
    assert "Repeat in quiet" in out["points"][0]["reason"]


def test_a_robust_emission_over_a_noisy_floor_keeps_the_non_organic_question_open():
    """SNR 13 dB, +10 dB SPL over a -3 dB SPL floor at 70 dB HL thresholds.
    The floor is above -5 dB SPL, so it is not a result (BSA 2023 s.6.2) —
    but the response is the finding emissions exist to catch, so the battery
    holds the case for a repeat in quiet instead of saying no repeat is
    needed (the routine hearing-aid referral must not lead)."""
    out = analyze(ear(70, 70, oae=emissions(10, -3), **TYMP_A))
    assert out["oae"]["right"]["present_freqs"] == []
    assert out["oae"]["right"]["noisy_response_freqs"] == [1000, 2000, 4000]
    titles = [c["title"] for c in out["battery"]["right"]["contradictions"]]
    assert "Possible emission despite poor pure-tone thresholds" in titles
    assert out["verdict"]["action_level"] == "validity"
    assert "Refer for hearing-aid evaluation" not in out["verdict"]["action"]


@pytest.mark.parametrize("noise,verdict", [(-5.0, "refer"), (-4.9, "invalid")])
def test_noise_floor_ceiling_is_minus_5_db_spl_inclusive(noise, verdict):
    gram = dpoae.dp_gram([{"freq": 2000, "amplitude": -15, "noise_floor": noise}])
    assert gram["points"][0]["verdict"] == verdict


def test_all_invalid_rows_are_kept_out_of_the_audiogram_cross_check():
    out = oae_instrument([{"freq": f, "amplitude": 18, "noise_floor": 15}
                          for f in (2000, 3000, 4000)],
                         ac={"2000": 10, "3000": 10, "4000": 10})
    assert out["outcome"] == "incomplete"
    assert out["preclinical_damage"] == []
    assert out["cochlear_profile"]["pattern"] == "undetermined"
    text = " ".join(out["interpretation"])
    assert "outer hair cell damage" not in text
    assert "is present across the tested range" not in text


def test_a_noisy_frequency_that_decides_the_outcome_makes_it_incomplete():
    """2-of-3 rule: 1 pass, 1 refer, 1 noisy — the noisy one could tip it."""
    out = oae_instrument([
        {"freq": 2000, "amplitude": 10, "noise_floor": -10},
        {"freq": 3000, "amplitude": -15, "noise_floor": -10},
        {"freq": 4000, "amplitude": 18, "noise_floor": 15},
    ])
    assert out["outcome"] == "incomplete"


def test_a_noisy_frequency_that_cannot_change_the_outcome_does_not_block_it():
    refer = oae_instrument([
        {"freq": 2000, "amplitude": -15, "noise_floor": -10},
        {"freq": 3000, "amplitude": -15, "noise_floor": -10},
        {"freq": 4000, "amplitude": 18, "noise_floor": 15},
    ])
    assert refer["outcome"] == "refer"       # 0 passes + 1 unknown < 2
    passed = oae_instrument([
        {"freq": 2000, "amplitude": 10, "noise_floor": -10},
        {"freq": 3000, "amplitude": 10, "noise_floor": -10},
        {"freq": 4000, "amplitude": 18, "noise_floor": 15},
    ])
    assert passed["outcome"] == "pass"       # 2 valid passes already


def test_intact_profile_names_the_frequencies_it_could_not_judge():
    out = oae_instrument([
        {"freq": 2000, "amplitude": 10, "noise_floor": -10},
        {"freq": 3000, "amplitude": 10, "noise_floor": -10},
        {"freq": 4000, "amplitude": 18, "noise_floor": 15},
    ])
    assert out["cochlear_profile"]["pattern"] == "intact"
    assert "4000" in out["cochlear_profile"]["summary"]


# ========================= B2-4 SNR compared unrounded =====================

def test_true_snr_of_5_96_db_does_not_pass_a_6_db_criterion():
    gram = dpoae.dp_gram([{"freq": 2000, "amplitude": 0.96, "noise_floor": -5.0}])
    row = gram["points"][0]
    assert row["present"] is False
    assert row["verdict"] == "refer"
    assert row["snr"] == 5.96                 # displayed without rounding up to 6
    assert classify_oae([{"freq": 2000, "amplitude": 0.96,
                          "noise_floor": -5.0}])["present_freqs"] == []


def test_an_entered_6_db_snr_survives_binary_floating_point():
    # -2.2 - (-8.2) is 5.999999999999999 in IEEE doubles.
    assert (-2.2) - (-8.2) < 6.0
    gram = dpoae.dp_gram([{"freq": 2000, "amplitude": -2.2, "noise_floor": -8.2}])
    assert gram["points"][0]["present"] is True


# ================= B2-5 Type C with a conductive loss is consistent ========

def test_type_c_with_an_air_bone_gap_is_not_a_contradiction():
    out = analyze(ear(30, 5, **TYMP_C))
    assert "Air-bone gap without middle-ear pathology" not in right_titles(out)
    assert "conductive_confirmed" in out["battery"]["right"]["patterns"]
    assert out["battery"]["right"]["contradictions"] == []


def test_type_a_with_an_air_bone_gap_is_still_flagged():
    out = analyze(ear(30, 5, **TYMP_A))
    assert "Air-bone gap without middle-ear pathology" in right_titles(out)


# ====================== B2-6 infant probe-tone caveat ======================

def _never_a_confident_infant_type(immittance):
    """An infant 226 Hz-or-unknown trace is either refused or provisional —
    never a plain "Type A, normal middle-ear function"."""
    tymp = immittance["tympanogram"]
    assert tymp is None or tymp["provisional"] is True
    if tymp is not None:
        assert tymp["interpretation"].startswith("Provisional")
    assert "1000 Hz" in immittance["infant_warning"]


def test_infant_tympanogram_is_provisional_in_the_battery():
    r = client.post("/api/analyze", json={
        "patient": {"name": "b", "age": 0},
        "right": {"tymp_pressure": 0, "tymp_compliance": 0.8, "tymp_ecv": 1.2}})
    assert r.status_code == 200, r.text
    out = r.json()
    _never_a_confident_infant_type(out["immittance"]["right"])
    assert any(a["title"] == "Infant tympanogram — probe tone not recorded"
               for a in alerts(out, "validity"))
    assert out["battery"]["right"]["middle_ear"]["status"] == "unknown"


def test_a_one_year_old_is_not_given_the_infant_caveat():
    out = analyze(ear(15, 10, **TYMP_A), age=1)
    tymp = out["immittance"]["right"]["tympanogram"]
    assert not tymp.get("provisional")
    assert not any("Infant tympanogram" in a["title"] for a in out["safety"]["alerts"])


def test_fractional_infant_age_marks_reflexes_provisional_too():
    ear_data = EarData(tymp_pressure=0, tymp_compliance=0.8, tymp_ecv=0.6,
                       reflexes={"ipsi": 85, "contra": 90})
    result = analyze_immittance(ear_data, None, age_years=0.25)
    _never_a_confident_infant_type(result)
    assert result["reflexes"]["provisional"] is True
    adult = analyze_immittance(ear_data, None, age_years=30)
    assert adult["infant_warning"] is None
    assert not adult["tympanogram"].get("provisional")
    assert not adult["reflexes"].get("provisional")


# ============== B2-7 reflexes present in moderate-severe cochlear loss =====

def test_reflexes_with_a_70_db_cochlear_loss_are_not_a_contradiction():
    out = analyze(ear(70, 70, reflexes={"ipsi": 100, "contra": 105}, **TYMP_A))
    assert not any("Reflexes present" in t for t in right_titles(out))
    assert "reflex_threshold_mismatch" not in out["battery"]["patterns"]


@pytest.mark.parametrize("pta,flagged", [(80, False), (85, True), (90, True)])
def test_reflex_presence_is_questioned_only_above_80_db_hl(pta, flagged):
    reflexes = analyze_reflexes({"ipsi": 105, "contra": 110})
    result = reconcile_ear("right", {"type": "Sensorineural", "ac_pta": {"value": pta}},
                           {"tympanogram": None, "reflexes": reflexes}, None, None,
                           {f: pta for f in FREQS})
    assert ("reflex_threshold_mismatch" in result["patterns"]) is flagged


# ============ B2-8 absent reflexes are not neural behind a sick middle ear ==

@pytest.mark.parametrize("name,right", [
    ("type_b_conductive", ear(25, 5, oae=emissions(10, -10),
                              reflexes={"ipsi": None, "contra": None}, **TYMP_B)),
    ("type_c", ear(15, 10, oae=emissions(10, -10),
                   reflexes={"ipsi": None, "contra": None}, **TYMP_C)),
])
def test_absent_reflexes_behind_an_abnormal_middle_ear_are_not_retrocochlear(
        name, right):
    out = analyze(right)
    patterns = out["battery"]["right"]["patterns"]
    assert "retrocochlear" not in patterns, name
    assert "reflexes_middle_ear_limited" in patterns, name
    assert "Reflexes absent despite a functioning cochlea" not in right_titles(out), name


def test_absent_reflexes_behind_a_normal_middle_ear_remain_retrocochlear():
    out = analyze(ear(15, 10, oae=emissions(10, -10),
                      reflexes={"ipsi": None, "contra": None}, **TYMP_A))
    assert "retrocochlear" in out["battery"]["right"]["patterns"]


def test_without_a_tympanogram_the_retrocochlear_flag_asks_for_one():
    out = analyze(ear(15, 10, oae=emissions(10, -10),
                      reflexes={"ipsi": None, "contra": None}))
    flag = next(c for c in out["battery"]["right"]["contradictions"]
                if c["title"] == "Reflexes absent despite a functioning cochlea")
    assert "confirm the middle ear is normal" in flag["detail"]


def test_ansd_inference_is_gated_on_the_middle_ear_too():
    oae = classify_oae(emissions(10, -10))
    reflexes = analyze_reflexes({"ipsi": None, "contra": None})
    speech = {"wrs": {"pb_max": 32}, "srt": None, "retrocochlear_suspicion": False}
    rules_ear = {"type": "Conductive", "ac_pta": {"value": 30}, "abg": {"value": 25.0}}
    type_b = {"tympanogram": classify_tympanogram(None, 0.1, 1.0), "reflexes": reflexes}
    result = reconcile_ear("right", rules_ear, type_b, oae, speech,
                           {f: 30 for f in FREQS})
    assert "auditory_neuropathy" not in result["patterns"]
    assert "ABR" in result["notes"][0]["action"]


# ================================ headline =================================

def test_notes_alone_do_not_claim_the_audiogram_is_corroborated():
    out = analyze(ear(15, 10, oae=emissions(-15, -20), **TYMP_C))
    assert "corroborated" not in out["battery"]["headline"]
    assert "could not be interpreted" in out["battery"]["headline"]


def test_extra_tests_without_findings_are_not_called_audiogram_only():
    rules_ear = {"type": "Normal", "ac_pta": {"value": 10}, "abg": {"value": 0.0}}
    type_a = {"tympanogram": classify_tympanogram(-10, 0.7, 1.2), "reflexes": None}
    review = battery_review({
        "right": reconcile_ear("right", rules_ear, type_a, None, None,
                               {f: 10 for f in FREQS}),
    })
    assert "Only pure-tone audiometry" not in review["headline"]


# ================ follow-up actions reach the verdict ======================

@pytest.mark.parametrize("pressure", [-250, -110])
def test_emissions_the_middle_ear_explains_still_get_a_next_step(pressure):
    """Type C, normal thresholds, absent emissions: the verdict must not say
    "no action required" while the cochlear question is unanswered."""
    out = analyze(ear(15, 10, oae=emissions(-15, -20), tymp_pressure=pressure,
                      tymp_compliance=0.6, tymp_ecv=1.2))
    assert "oae_middle_ear_limited" in out["battery"]["patterns"]
    assert "No action required" not in out["verdict"]["action"]
    assert "repeat the emissions" in out["verdict"]["action"]
    assert out["verdict"]["action_level"] == "validity"
    assert "being damaged" not in out["verdict"]["headline"]


def test_a_noisy_frequency_above_the_emission_ceiling_stays_informational():
    """At 70 dB HL a cochlear loss leaves no emission (oae.py: absent above
    ~50 dB HL), so the noisy frequency stays informational — but a present
    emission there is the ANSD / non-organic finding, so the note never says
    a repeat would add nothing."""
    oae = classify_oae([{"freq": 4000, "amplitude": 18, "noise_floor": 15}])
    rules_ear = {"type": "Sensorineural", "ac_pta": {"value": 70},
                 "abg": {"value": 0.0}}
    result = reconcile_ear("right", rules_ear, None, oae, None, {4000: 70.0})
    note = next(n for n in result["notes"]
                if n["title"] == "Emissions could not be judged at some frequencies")
    assert note["follow_up"] is False
    assert "would add nothing" not in note["detail"]
    assert "auditory neuropathy" in note["detail"]
    assert "No repeat needed" not in note["action"]
    assert "auditory neuropathy or non-organic loss" in note["action"]
    # The same noisy frequency at a normal threshold is a repeat still owed.
    normal = reconcile_ear("right", {"type": "Normal", "ac_pta": {"value": 10},
                                     "abg": {"value": 0.0}},
                           None, oae, None, {4000: 10.0})
    assert normal["notes"][0]["follow_up"] is True


def test_middle_ear_explained_reflexes_follow_up_only_with_poor_speech():
    oae = classify_oae(emissions(10, -10))
    reflexes = analyze_reflexes({"ipsi": None, "contra": None})
    rules_ear = {"type": "Conductive", "ac_pta": {"value": 30}, "abg": {"value": 25.0}}
    type_b = {"tympanogram": classify_tympanogram(None, 0.1, 1.0), "reflexes": reflexes}
    poor = {"wrs": {"pb_max": 32}, "srt": None, "retrocochlear_suspicion": False}
    good = {"wrs": {"pb_max": 96}, "srt": None, "retrocochlear_suspicion": False}
    flat = {f: 30 for f in FREQS}
    with_poor = reconcile_ear("right", rules_ear, type_b, oae, poor, flat)
    with_good = reconcile_ear("right", rules_ear, type_b, oae, good, flat)
    assert with_poor["notes"][0]["follow_up"] is True
    assert with_good["notes"][0]["follow_up"] is False


# ========== cochlear confirmation needs the noisy frequencies resolved ======

def test_one_judged_absence_does_not_confirm_a_cochlear_site():
    """1 absent + 2 noisy at 30 dB HL: the noisy two could hold emissions, and
    one present emission is what separates cochlear from neural."""
    points = [{"freq": 1000, "amplitude": -15, "noise_floor": -20},
              {"freq": 2000, "amplitude": 18, "noise_floor": 15},
              {"freq": 4000, "amplitude": 18, "noise_floor": 15}]
    oae = classify_oae(points)
    assert oae["all_absent"] is True          # over the judged frequency only
    rules_ear = {"type": "Sensorineural", "ac_pta": {"value": 30},
                 "abg": {"value": 0.0}}
    type_a = {"tympanogram": classify_tympanogram(0, 0.8, 1.2), "reflexes": None}
    result = reconcile_ear("right", rules_ear, type_a, oae, None,
                           {f: 30 for f in FREQS})
    assert "cochlear_confirmed" not in result["patterns"]
    assert "oae_inconclusive" in result["patterns"]


def test_noisy_frequencies_beyond_the_emission_ceiling_do_not_block_it():
    points = [{"freq": 1000, "amplitude": -15, "noise_floor": -20},
              {"freq": 2000, "amplitude": -15, "noise_floor": -20},
              {"freq": 4000, "amplitude": 18, "noise_floor": 15}]
    rules_ear = {"type": "Sensorineural", "ac_pta": {"value": 60},
                 "abg": {"value": 0.0}}
    type_a = {"tympanogram": classify_tympanogram(0, 0.8, 1.2), "reflexes": None}
    result = reconcile_ear("right", rules_ear, type_a, classify_oae(points), None,
                           {1000: 60.0, 2000: 60.0, 4000: 70.0})
    assert "cochlear_confirmed" in result["patterns"]


# ===================== failing SNR never displays as passing ===============

def test_a_failing_snr_is_never_displayed_as_the_criterion():
    # True SNR 5.9999 dB: below 6, and round(…, 2) alone would print 6.0.
    gram = dpoae.dp_gram([{"freq": 2000, "amplitude": -0.0001, "noise_floor": -6.0}])
    row = gram["points"][0]
    assert row["verdict"] == "refer"
    assert row["snr"] == 5.99
    assert "5.99 dB SNR" in row["reason"]
    battery = classify_oae([{"freq": 2000, "amplitude": -0.0001, "noise_floor": -6.0}])
    assert battery["points"][0]["snr"] == 5.99
    # A value that meets the criterion still reads as it.
    passed = dpoae.dp_gram([{"freq": 2000, "amplitude": -2.2, "noise_floor": -8.2}])
    assert passed["points"][0]["snr"] == 6.0


# ================== infant reflexes without a tympanogram ==================

def test_infant_reflexes_alone_carry_the_probe_tone_caveat():
    r = client.post("/api/analyze", json={
        "patient": {"name": "b", "age": 0},
        "right": {"reflexes": {"ipsi": 85, "contra": 90}}})
    assert r.status_code == 200, r.text
    out = r.json()
    imm = out["immittance"]["right"]
    assert imm["reflexes"]["provisional"] is True
    assert "1000 Hz" in imm["infant_warning"]
    assert any(a["title"] == "Infant acoustic reflexes — probe tone not recorded"
               for a in alerts(out, "validity"))
    # No tympanogram was entered, so none is said to have been refused.
    assert out["battery"]["right"]["middle_ear"]["reason"] == "no tympanogram was recorded"


def test_infant_absent_reflexes_ask_for_a_1000_hz_probe_before_neural_inference():
    ear_data = EarData(reflexes={"ipsi": None, "contra": None})
    imm = analyze_immittance(ear_data, None, age_years=0.25)
    result = reconcile_ear("right", {"type": "Normal", "ac_pta": {"value": 10},
                                     "abg": {"value": 0.0}},
                           imm, classify_oae(emissions(10, -10)), None,
                           {f: 10 for f in FREQS})
    flag = next(c for c in result["contradictions"]
                if c["title"] == "Reflexes absent despite a functioning cochlea")
    assert "1000 Hz probe" in flag["detail"]


# ===== a noisy emission repeat never displaces a threshold-based referral ===
#
# An emission is expected from a healthy cochlea only at a normal threshold:
# DPOAE test-performance work classes <= 20 dB HL as normal and above it as
# impaired (Johnson et al. 2010, Ear Hear 31:74-83). Above that the audiogram
# already shows the loss and sets the management; the emission would only
# help place it.

NOISY_TITLE = "Emissions could not be judged at some frequencies"


def _noisy_note(threshold):
    oae = classify_oae([{"freq": 2000, "amplitude": 10, "noise_floor": 5}])
    rules_ear = {"type": "Sensorineural" if (threshold or 0) > 20 else "Normal",
                 "ac_pta": {"value": threshold}, "abg": {"value": 0.0}}
    result = reconcile_ear("right", rules_ear, None, oae, None,
                           {} if threshold is None else {2000: float(threshold)})
    return next(n for n in result["notes"] if n["title"] == NOISY_TITLE)


@pytest.mark.parametrize("threshold,follow_up", [
    (None, True),    # no audiogram there: the emission may be all there is
    (10, True),
    (20, True),      # the normal limit itself
    (25, False),     # outside normal limits, below the emission ceiling
    (45, False),
    (50, False),
    (55, False),     # above the ceiling: no emission was possible
])
def test_a_noisy_frequency_is_a_follow_up_only_where_an_emission_was_expected(
        threshold, follow_up):
    assert _noisy_note(threshold)["follow_up"] is follow_up


def test_a_noisy_frequency_inside_a_known_loss_offers_a_site_repeat_only():
    note = _noisy_note(45)
    assert note["action"] == ("Repeat [2000] Hz in quiet if the site of the loss "
                              "needs confirming.")
    assert "would not change the management" in note["detail"]


def test_a_mixed_recording_still_asks_for_the_repeat_it_owes():
    """A noise-notch ear the audiogram still grades normal: 1 kHz normal,
    4 kHz in the notch, 8 kHz beyond the emission ceiling — all noisy."""
    oae = classify_oae([{"freq": f, "amplitude": 10, "noise_floor": 5}
                        for f in (1000, 4000, 8000)])
    rules_ear = {"type": "Normal", "ac_pta": {"value": 18.8},
                 "who_grade": {"grade": "Normal hearing"}, "abg": {"value": 0.0}}
    result = reconcile_ear("right", rules_ear, None, oae, None,
                           {1000: 10.0, 4000: 40.0, 8000: 70.0})
    note = next(n for n in result["notes"] if n["title"] == NOISY_TITLE)
    assert note["follow_up"] is True                # 1000 Hz is normal
    assert note["action"].startswith("Repeat [1000, 4000] Hz in quiet")
    assert "[4000] Hz the threshold is already outside normal limits" in note["detail"]
    assert "[8000] Hz the threshold is above 50 dB HL" in note["detail"]


@pytest.mark.parametrize("grade,follow_up", [
    (None, True),                       # no audiogram grade: emissions screen
    ("Normal hearing", True),
    ("Mild hearing loss", False),       # WHO 2021: PTA from 20 dB HL
    ("Moderate hearing loss", False),
])
def test_an_owed_repeat_leads_only_while_the_audiogram_grades_the_ear_normal(
        grade, follow_up):
    oae = classify_oae([{"freq": 1000, "amplitude": 10, "noise_floor": 5}])
    rules_ear = {"type": "Sensorineural", "ac_pta": {"value": 37.5},
                 "who_grade": {"grade": grade} if grade else None,
                 "abg": {"value": 0.0}}
    result = reconcile_ear("right", rules_ear, None, oae, None, {1000: 15.0})
    note = next(n for n in result["notes"] if n["title"] == NOISY_TITLE)
    assert note["follow_up"] is follow_up
    # The repeat is still named either way; only its rank changes.
    assert note["action"].startswith("Repeat [1000] Hz in quiet")


def test_a_sloping_loss_keeps_its_referral_over_a_noisy_normal_frequency():
    """1 kHz normal (15 dB HL) but too noisy to judge, in ears whose PTA of
    37.5 dB HL grades a moderate loss: the hearing-aid referral leads."""
    ac = {"250": 15, "500": 15, "1000": 15, "2000": 50, "4000": 70, "8000": 75}
    bc = {"250": 15, "500": 15, "1000": 15, "2000": 50, "4000": 70}
    r = client.post("/api/analyze", json={
        "patient": {"name": "T", "age": 40},
        "right": {"ac": ac, "bc": bc, **TYMP_A,
                  "oae": [{"freq": f, "amplitude": 18, "noise_floor": 15}
                          for f in (1000, 2000)]},
        "left": {"ac": ac, "bc": bc, **TYMP_A}})
    assert r.status_code == 200, r.text
    out = r.json()
    note = next(a for a in out["safety"]["alerts"] if a["title"] == NOISY_TITLE)
    assert note["level"] == "info"
    assert out["verdict"]["action"] == "Refer for hearing-aid evaluation and fitting."


def test_a_noisy_emission_in_a_moderate_loss_keeps_the_hearing_aid_referral():
    """Both ears 45 dB HL sensorineural, Type A; right 1 kHz too noisy to
    judge, 2-4 kHz absent. No emission was expected at 45 dB HL, so the
    repeat must not take the verdict's action or the case out of release."""
    noisy_mixed = ([{"freq": 1000, "amplitude": 10, "noise_floor": 5}]
                   + [{"freq": f, "amplitude": -20, "noise_floor": -20}
                      for f in (2000, 4000)])
    r = client.post("/api/analyze", json={
        "patient": {"name": "T", "age": 40},
        "right": ear(45, 45, oae=noisy_mixed, **TYMP_A),
        "left": ear(45, 45, **TYMP_A)})
    assert r.status_code == 200, r.text
    out = r.json()
    note = next(a for a in out["safety"]["alerts"] if a["title"] == NOISY_TITLE)
    assert note["level"] == "info"
    assert out["verdict"]["action"] == "Refer for hearing-aid evaluation and fitting."
    assert out["verdict"]["action_level"] == "routine"
    assert not any(reason["detail"] == NOISY_TITLE
                   for reason in out["triage"]["reasons"])
    # The site of the loss stays unconfirmed while 1 kHz is unresolved.
    assert "cochlear_confirmed" not in out["battery"]["right"]["patterns"]


def test_battery_note_alerts_are_marked_apart_from_contradictions():
    out = analyze(ear(15, 10, oae=emissions(-15, -20), **TYMP_C))
    note = next(a for a in out["safety"]["alerts"]
                if a["title"] == "Absent emissions explained by the middle ear")
    assert note["battery_note"] is True
    contradiction = analyze(ear(30, 5, **TYMP_A))
    flag = next(a for a in contradiction["safety"]["alerts"]
                if a["title"] == "Air-bone gap without middle-ear pathology")
    assert not flag.get("battery_note")


@pytest.mark.parametrize("threshold,damage", [(20, True), (21, False)])
def test_pre_clinical_damage_is_judged_only_at_a_normal_threshold(threshold, damage):
    findings = oae_audiogram_agreement(
        classify_oae([{"freq": 4000, "amplitude": -15, "noise_floor": -20}]),
        {4000: float(threshold)})
    assert bool([f for f in findings if f["kind"] == "preclinical_damage"]) is damage
