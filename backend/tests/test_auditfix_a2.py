"""Regression tests: emergency / asymmetry alerts and the verdict headline.

Each expected value is worked out from the published criterion it cites, not
read back from the code:

- Sudden SNHL — AAO-HNSF guideline (Stachler 2012; Chandrasekhar 2019):
  ≥30 dB sensorineural loss at 3 consecutive frequencies; without a prior
  audiogram the loss is measured against the opposite ear.
- Asymmetry — ≥20 dB at one frequency 0.5–4 kHz (DoH, Neary 1996) or
  ≥15 dB at two frequencies (Cueva 2004), with the poorer ear outside normal
  limits (> 20 dB HL; BSA 2018 "mild" starts at 21). Imaging is for an
  asymmetric SENSORINEURAL loss; a conductive asymmetry goes to ENT (BAA
  Onward Referral Guidance 2023). The BAA reads the asymmetry in "air or
  bone conduction", so a cochlear asymmetry counts even in the ear that is
  better by air.
- WHO World Report on Hearing (2021): unilateral = better ear < 20 dB HL,
  worse ear ≥ 35 dB HL.
"""
import io

from fastapi.testclient import TestClient

from app.clinical.safety import asymmetry_check, safety_review, sudden_loss_check
from app.clinical.triage import triage_case
from app.main import app
from app.models.schemas import EarData
from app.services.verdict import build_verdict

client = TestClient(app)

AC = (250, 500, 1000, 2000, 4000, 8000)
BC = (250, 500, 1000, 2000, 4000)


def flat(level, freqs=AC):
    return {f: level for f in freqs}


def ear(ac, bc=None, **kw):
    return EarData(ac=ac, bc=bc or {}, **kw)


NORMAL = ear(flat(10), flat(10, BC))

# Right ear 35/35/30 dB worse than a normal left ear at 250/500/1000 Hz, no
# air-bone gap (5 dB). PTA4 = (45 + 40 + 10 + 10) / 4 = 26.25 dB HL — under 30.
LOW_SUDDEN = ear({250: 45, 500: 45, 1000: 40, 2000: 10, 4000: 10, 8000: 10},
                 {250: 40, 500: 40, 1000: 35, 2000: 10, 4000: 10})
# 35/40/50 dB worse at 2/4/8 kHz. PTA4 = (10 + 10 + 45 + 50) / 4 = 28.75.
HIGH_SUDDEN = ear({250: 10, 500: 10, 1000: 10, 2000: 45, 4000: 50, 8000: 60},
                  {250: 10, 500: 10, 1000: 10, 2000: 40, 4000: 45})


def _alert_titles(review, level=None):
    return [a["title"] for a in review["alerts"] if level in (None, a["level"])]


def _analyze(right, left, onset="unknown", age=45):
    body = {"patient": {"name": "Regression", "age": age, "sex": "male", "onset": onset},
            "right": right, "left": left}
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _json_ear(e: EarData):
    return {"ac": {str(k): v for k, v in e.ac.items()},
            "bc": {str(k): v for k, v in e.bc.items()}, "masked": e.masked}


# ====================================================== A2-1 sudden SNHL ====

def test_low_frequency_sudden_loss_is_an_emergency_against_the_opposite_ear():
    review = safety_review(LOW_SUDDEN, NORMAL, onset="sudden")
    assert review["has_emergency"] is True
    s = review["sudden"]["right"]
    assert s["urgency"] == "emergency"
    assert s["freqs"] == [250, 500, 1000]
    assert s["basis"] == "opposite_ear"
    assert s["confirmed"] is False     # no premorbid audiogram
    assert review["alerts"][0]["level"] == "emergency"
    assert review["alerts"][0]["ear"] == "right"


def test_high_frequency_sudden_loss_is_an_emergency_against_the_opposite_ear():
    review = safety_review(HIGH_SUDDEN, NORMAL, onset="sudden")
    assert review["has_emergency"] is True
    assert review["sudden"]["right"]["freqs"] == [2000, 4000, 8000]


def test_unknown_onset_with_the_interaural_criterion_asks_when_it_started():
    review = safety_review(LOW_SUDDEN, NORMAL, onset="unknown")
    assert review["has_emergency"] is False
    s = review["sudden"]["right"]
    assert s["urgency"] == "ask"
    assert "72 hours" in s["message"]
    assert any(a["level"] == "info" and a["title"] == "Onset not recorded"
               and a["ear"] == "right" for a in review["alerts"])


def test_gradual_onset_is_not_sudden_snhl():
    review = safety_review(LOW_SUDDEN, NORMAL, onset="gradual")
    assert review["has_emergency"] is False
    assert review["sudden"]["right"]["urgency"] == "none"


def test_two_consecutive_frequencies_do_not_meet_the_interaural_criterion():
    two = ear({250: 45, 500: 45, 1000: 10, 2000: 10, 4000: 10, 8000: 10},
              {250: 40, 500: 40, 1000: 10, 2000: 10, 4000: 10})
    assert sudden_loss_check(two.ac, two.bc, "sudden",
                             opposite_ac=NORMAL.ac)["flag"] is False


def test_a_conductive_interaural_difference_is_not_sudden_snhl():
    # AC 45 with BC 5: a 40 dB air-bone gap at every one of the frequencies.
    conductive = ear({250: 45, 500: 45, 1000: 45, 2000: 10, 4000: 10, 8000: 10},
                     {250: 5, 500: 5, 1000: 5, 2000: 10, 4000: 10})
    assert sudden_loss_check(conductive.ac, conductive.bc, "sudden",
                             opposite_ac=NORMAL.ac)["flag"] is False


def test_a_prior_audiogram_replaces_the_opposite_ear_as_reference():
    # The same thresholds a year ago: nothing is new, and the PTA (26.25) is
    # under 30, so neither remaining rule fires.
    result = sudden_loss_check(LOW_SUDDEN.ac, LOW_SUDDEN.bc, "sudden",
                               baseline_ac=dict(LOW_SUDDEN.ac),
                               opposite_ac=NORMAL.ac)
    assert result["flag"] is False


def test_the_pta_trigger_still_catches_a_bilateral_sudden_loss():
    both = ear(flat(50), flat(45, BC))
    review = safety_review(both, ear(flat(50), flat(45, BC)), onset="sudden")
    assert review["sudden"]["right"]["flag"] is True
    assert review["sudden"]["left"]["flag"] is True
    assert review["sudden"]["right"]["basis"] == "pta"


def test_low_frequency_sudden_loss_leads_the_verdict_end_to_end():
    body = _analyze(_json_ear(LOW_SUDDEN), _json_ear(NORMAL), onset="sudden")
    assert body["safety"]["has_emergency"] is True
    assert body["verdict"]["tone"] == "emergency"
    assert body["triage"]["priority"] == 1


# ===================================================== A2-2 asymmetry ======

def test_two_normal_ears_are_not_an_asymmetric_hearing_loss():
    # Left 20 dB HL at 2 and 4 kHz is a 15 dB difference at two frequencies,
    # but 20 dB HL is within normal limits: there is no loss to refer.
    right = ear(flat(5), flat(5, BC))
    left = ear({250: 5, 500: 5, 1000: 5, 2000: 20, 4000: 20, 8000: 10})
    review = safety_review(right, left)
    assert review["asymmetry"]["flag"] is False
    assert review["asymmetry"]["kind"] is None
    assert not any("symmetric" in t for t in _alert_titles(review))
    assert review["has_urgent"] is False


def test_a_poorer_ear_just_outside_normal_limits_does_flag():
    # 25 dB HL is outside normal limits; 20 dB worse at 2 kHz and 4 kHz.
    left = ear({250: 5, 500: 5, 1000: 5, 2000: 25, 4000: 25, 8000: 5},
               {250: 5, 500: 5, 1000: 5, 2000: 25, 4000: 25})
    result = asymmetry_check(flat(5), left.ac, flat(5, BC), left.bc)
    assert result["flag"] is True
    assert result["poorer_ear"] == "left"


def test_a_normal_hearing_camp_raises_no_asymmetry_referral():
    """40 people, every threshold 0–20 dB HL: none has a hearing loss."""
    head = ("name,age,sex,occupation,test_date,"
            + ",".join(f"r_ac_{f}" for f in AC) + ","
            + ",".join(f"r_bc_{f}" for f in BC) + ","
            + ",".join(f"l_ac_{f}" for f in AC) + ","
            + ",".join(f"l_bc_{f}" for f in BC) + "\n")
    levels = (0, 5, 10, 15, 20)
    rows = []
    for i in range(40):
        r = [levels[(i + k) % 5] for k in range(6)]
        l = [levels[(i * 3 + 2 * k + 1) % 5] for k in range(6)]
        rows.append(",".join(map(str, [f"P{i}", 30, "male", "office", "2026-01-01",
                                       *r, *r[:5], *l, *l[:5]])))
    csv = head + "\n".join(rows) + "\n"
    body = client.post("/api/batch",
                       files={"file": ("camp.csv", io.BytesIO(csv.encode()), "text/csv")}).json()
    assert body["count"] == 40
    flagged = [r["name"] for r in body["results"]
               if any("symmetric" in t for t in r["alerts"])]
    assert flagged == []


def test_a_conductive_asymmetry_goes_to_ent_without_imaging():
    right = ear(flat(10), flat(5, BC))
    left = ear(flat(45), flat(5, BC))
    review = safety_review(right, left)
    asym = review["asymmetry"]
    assert asym["flag"] is False            # no retrocochlear screen
    assert asym["kind"] == "conductive"
    assert asym["poorer_ear"] == "left"
    alert = next(a for a in review["alerts"] if "symmetric" in a["title"])
    assert alert["level"] == "urgent"
    assert "ENT" in alert["title"] and "conductive" in alert["title"].lower()
    text = " ".join([alert["title"], alert["detail"], alert["action"]])
    assert "MRI" not in text and "schwannoma" not in text
    # Bone conduction was unmasked though masking was indicated, so the
    # sensorineural question is left open, not closed.
    assert "masked" in alert["action"]


def test_a_masked_conductive_asymmetry_needs_no_masking_caveat():
    right = ear(flat(10), flat(5, BC), masked=True)
    left = ear(flat(45), flat(5, BC), masked=True)
    alert = next(a for a in safety_review(right, left)["alerts"]
                 if "symmetric" in a["title"])
    assert "not masked" not in alert["action"]


def test_mixed_loss_with_an_asymmetric_cochlear_component_still_flags():
    # Left AC 70 / BC 40: bone conduction is 30 dB worse than the right's 10.
    review = safety_review(ear(flat(10), flat(10, BC)), ear(flat(70), flat(40, BC)))
    asym = review["asymmetry"]
    assert asym["flag"] is True
    assert asym["kind"] == "sensorineural"
    assert asym["type_confirmed"] is True
    titles = _alert_titles(review, "urgent")
    assert "Asymmetric sensorineural hearing loss — retrocochlear screen" in titles


def test_mixed_loss_with_symmetric_cochlear_component_is_conductive_asymmetry():
    # Right AC 25 / BC 25; left AC 60 / BC 30 — cochleae 5 dB apart, the 35 dB
    # air difference is the left ear's air-bone gap.
    result = asymmetry_check(flat(25), flat(60), flat(25, BC), flat(30, BC))
    assert result["flag"] is False
    assert result["kind"] == "conductive"


def test_a_gap_of_exactly_10_db_is_not_conductive():
    # Left AC 30 / BC 20: the 10 dB gap is not significant (must exceed 10),
    # so the loss is sensorineural and its 25 dB asymmetry is a VS question.
    result = asymmetry_check(flat(5), flat(30), flat(0, BC), flat(20, BC))
    assert result["flag"] is True
    assert result["kind"] == "sensorineural"


def test_without_bone_conduction_the_asymmetry_is_assumed_sensorineural():
    review = safety_review(ear(flat(10)), ear(flat(50)))
    asym = review["asymmetry"]
    assert asym["flag"] is True
    assert asym["type_confirmed"] is False
    assert asym["assumed_sensorineural_freqs"]
    alert = next(a for a in review["alerts"] if "retrocochlear" in a["title"])
    assert alert["title"] == "Asymmetric hearing loss — retrocochlear screen"
    assert "not measured" in alert["detail"]


def test_8khz_is_read_from_a_conductive_4khz():
    result = asymmetry_check(flat(10), flat(45), flat(5, BC), flat(5, BC))
    assert result["kind"] == "conductive"
    assert result["untested_read_as_conductive"] == [8000]


def test_a_conductive_low_frequency_does_not_vouch_for_an_untested_high_one():
    # Bone conduction only at 250/500 Hz (conductive there). The 40/45 dB
    # losses at 4 and 8 kHz have no tested neighbour, so they stay assumed
    # sensorineural: 40 dB at 4 kHz meets the single-frequency criterion.
    left_ac = {250: 45, 500: 45, 1000: 10, 2000: 10, 4000: 50, 8000: 55}
    result = asymmetry_check(flat(10), left_ac, flat(10, BC), {250: 5, 500: 5})
    assert result["flag"] is True
    assert result["kind"] == "sensorineural"
    assert result["type_confirmed"] is False
    assert result["assumed_sensorineural_freqs"] == [4000, 8000]


def test_a_single_8khz_difference_meets_no_cited_protocol():
    # 25 dB worse at 8 kHz only: the single-frequency rule is 0.5–4 kHz (DoH),
    # and the two-frequency rule needs a second frequency.
    left = {**flat(10), 8000: 35}
    assert asymmetry_check(flat(10), left, flat(10, BC), flat(10, BC))["kind"] is None


# ============================================== verdict helpers ============

def _rules_ear(type_, grade, pta, provisional=False, abg=5.0):
    return {"type": type_, "provisional": provisional,
            "who_grade": {"grade": grade} if grade else None,
            "ac_pta": {"value": pta} if pta is not None else None,
            "abg": {"value": abg} if abg is not None else None}


def _verdict(right, left, ml=None, disability=None, **extra):
    analysis = {"rules": {"right": right, "left": left, "disability": disability},
                "ml": ml or {"right": None, "left": None},
                "safety": {"alerts": []}, "triage": {}, **extra}
    return build_verdict(analysis)


NORMAL_EAR = _rules_ear("Normal", "Normal hearing", 10)


# ================================================ A2-3 type per ear =========

def test_headline_names_each_ear_type_when_they_differ():
    v = _verdict(_rules_ear("Sensorineural", "Mild hearing loss", 25),
                 _rules_ear("Conductive", "Moderate hearing loss", 45, abg=40))
    assert v["headline"] == ("Asymmetric hearing loss: moderate conductive in the "
                             "left ear, mild sensorineural in the right ear.")


def test_mixed_type_case_end_to_end_does_not_call_the_left_ear_sensorineural():
    body = _analyze({"ac": flat(25), "bc": flat(20, BC)},
                    {"ac": flat(45), "bc": flat(5, BC)})
    headline = body["verdict"]["headline"].lower()
    assert "moderate conductive in the left ear" in headline
    assert "sensorineural moderate" not in headline


# ========================================== A2-4 provisional type ===========

def test_headline_says_the_type_is_provisional_without_bone_conduction():
    prov = _rules_ear("Sensorineural (provisional)", "Moderately severe hearing loss",
                      50, provisional=True, abg=None)
    v = _verdict(prov, dict(prov))
    assert v["headline"] == ("Bilateral moderately severe sensorineural hearing loss "
                             "(type provisional — bone conduction not measured).")


def test_provisional_type_end_to_end():
    body = _analyze({"ac": flat(50), "bc": {}}, {"ac": flat(50), "bc": {}})
    headline = body["verdict"]["headline"]
    assert "provisional" in headline and "bone conduction not measured" in headline


# ============================================ A2-5 WHO wording ==============

def test_who_unilateral_wording():
    v = _verdict(NORMAL_EAR, _rules_ear("Sensorineural", "Severe hearing loss", 70))
    assert v["headline"] == "Unilateral severe sensorineural hearing loss (left ear)."


def test_unilateral_wording_on_the_right():
    v = _verdict(_rules_ear("Sensorineural", "Moderate hearing loss", 40), NORMAL_EAR)
    assert v["headline"] == "Unilateral moderate sensorineural hearing loss (right ear)."


def test_a_mild_loss_beside_a_normal_ear_is_not_who_unilateral():
    # Worse ear 30 dB HL < 35: one-sided, but below the WHO unilateral bar.
    v = _verdict(NORMAL_EAR, _rules_ear("Sensorineural", "Mild hearing loss", 30))
    assert "unilateral" not in v["headline"].lower()
    assert v["headline"] == ("Mild sensorineural hearing loss in the left ear; the "
                             "right ear is within normal limits.")


def test_who_unilateral_boundaries():
    # Better ear 19.75 (< 20) and worse exactly 35 (≥ 35): unilateral.
    v = _verdict(_rules_ear("Normal", "Normal hearing", 19.75),
                 _rules_ear("Sensorineural", "Moderate hearing loss", 35))
    assert v["headline"].startswith("Unilateral moderate")
    # Better ear exactly 20 is a mild loss: both ears have a loss.
    v = _verdict(_rules_ear("Sensorineural", "Mild hearing loss", 20),
                 _rules_ear("Sensorineural", "Moderate hearing loss", 35))
    assert v["headline"] == ("Asymmetric sensorineural hearing loss: moderate in "
                             "the left ear, mild in the right ear.")


def test_a_single_ear_test_is_not_called_unilateral():
    v = _verdict(_rules_ear("Sensorineural", "Moderate hearing loss", 40),
                 _rules_ear("Indeterminate", None, None, provisional=True, abg=None))
    assert "unilateral" not in v["headline"].lower()
    assert v["headline"] == ("Moderate sensorineural hearing loss in the right ear; "
                             "the left ear was not tested.")


def test_a_single_normal_ear_is_not_both_ears_normal():
    v = _verdict(NORMAL_EAR, _rules_ear("Indeterminate", None, None, abg=None))
    assert "both ears" not in v["headline"]
    assert v["headline"] == ("Hearing in the right ear is within normal limits; "
                             "the left ear was not tested.")


def test_single_ear_end_to_end():
    body = _analyze({"ac": flat(40), "bc": flat(35, BC)}, {"ac": {}, "bc": {}})
    headline = body["verdict"]["headline"]
    assert "left ear was not tested" in headline
    assert "nilateral" not in headline


def test_bilateral_same_grade_same_type():
    sn = _rules_ear("Sensorineural", "Moderate hearing loss", 40)
    assert _verdict(sn, dict(sn))["headline"] == \
        "Bilateral moderate sensorineural hearing loss."


# ======================================= A2-6 no hearing-age number =========

def test_verdict_never_shows_a_hearing_age():
    v = _verdict(_rules_ear("Sensorineural", "Moderate hearing loss", 40),
                 _rules_ear("Sensorineural", "Moderate hearing loss", 40),
                 norms={"hearing_age": 85, "age_gap": 40},
                 patient={"age": 45})
    assert not any("age" in n["label"].lower() for n in v["numbers"])
    assert not any("vs actual" in str(n.get("unit")) for n in v["numbers"])


# ===================================== A2-7 configuration reliability =======

SEVERE = _rules_ear("Sensorineural", "Severe hearing loss", 72.5)


def _ml(pattern="corner_audiogram", label="Corner audiogram", confidence=0.67, **kw):
    return {"pattern": pattern, "pattern_label": label, "confidence": confidence, **kw}


def test_an_unconfident_configuration_is_not_headlined():
    v = _verdict(SEVERE, dict(SEVERE), ml={"right": _ml(), "left": _ml()})
    assert "corner" not in v["headline"].lower()
    assert v["headline"] == "Bilateral severe sensorineural hearing loss."


def test_a_confident_configuration_is_headlined():
    m = _ml(confidence=0.95)
    v = _verdict(SEVERE, dict(SEVERE), ml={"right": m, "left": dict(m)})
    assert v["headline"].endswith(", corner audiogram configuration.")


def test_the_reliable_flag_overrides_confidence():
    unreliable = _ml(confidence=0.99, reliable=False,
                     reliability_note="extrapolated beyond the training range")
    v = _verdict(SEVERE, dict(SEVERE), ml={"right": unreliable, "left": dict(unreliable)})
    assert "corner" not in v["headline"].lower()


def test_a_normal_or_missing_pattern_names_no_configuration():
    normal = _ml(pattern="normal", label="Within normal limits", confidence=1.0,
                 reliable=False)
    v = _verdict(SEVERE, dict(SEVERE), ml={"right": normal, "left": None})
    assert "configuration" not in v["headline"]
    assert "within normal limits" not in v["headline"].lower()


def test_the_configuration_comes_from_the_ear_with_the_loss():
    # The normal right ear's "flat" must not describe the left ear's loss.
    flat_right = _ml(pattern="flat", label="Flat", confidence=0.95)
    v = _verdict(NORMAL_EAR, SEVERE, ml={"right": flat_right, "left": None})
    assert "flat" not in v["headline"].lower()


def test_severe_sloping_with_no_response_is_not_headlined_as_corner():
    ac = dict(zip(AC, [40, 45, 55, 70, "NR", "NR"]))
    body = _analyze({"ac": ac, "bc": {}}, {"ac": ac, "bc": {}}, age=60)
    assert "corner" not in body["verdict"]["headline"].lower()


# ===================================== A2-8 certifiable disability ==========

def test_a_non_certifiable_disability_figure_is_labelled_provisional():
    v = _verdict(SEVERE, dict(SEVERE),
                 disability={"binaural_pct": 47.5, "benchmark_disability": True,
                             "certifiable": False,
                             "certification_note": "4 kHz not tested in the left ear"})
    d = next(n for n in v["numbers"] if n["label"].startswith("Disability"))
    assert "provisional" in d["label"]
    assert "not certifiable" in d["hint"]
    assert d["emphasis"] is False
    assert d["note"] == "4 kHz not tested in the left ear"


def test_a_missing_certifiable_key_reads_as_certifiable():
    v = _verdict(SEVERE, dict(SEVERE),
                 disability={"binaural_pct": 47.5, "benchmark_disability": True})
    d = next(n for n in v["numbers"] if n["label"].startswith("Disability"))
    assert d["label"] == "Disability (RPwD 2016)"
    assert d["hint"] == "meets the 40% benchmark"
    assert d["emphasis"] is True


def test_triage_does_not_call_a_provisional_figure_certifiable():
    t = triage_case({"safety": {"alerts": []}, "ml": {}, "battery": {},
                     "rules": {"right": {}, "left": {},
                               "disability": {"benchmark_disability": True,
                                              "binaural_pct": 47.5,
                                              "certifiable": False}}})
    reason = next(r for r in t["reasons"] if r["code"] == "benchmark_disability")
    assert "not certifiable" in reason["detail"]
    assert t["review_required"] is True


# ================================== triage reads the new ML contract ========

def test_triage_tolerates_a_pattern_without_confidence():
    t = triage_case({"safety": {"alerts": []}, "battery": {},
                     "rules": {"right": {}, "left": {}, "disability": {}},
                     "ml": {"right": {"pattern": None, "confidence": None, "ood": False},
                            "left": {"pattern": "normal", "confidence": None,
                                     "reliable": False}}})
    assert t["priority"] == 4


# ======================= A2-2: cochlear asymmetry in either direction =======
#
# The cochlear threshold at a frequency is bone conduction where measured
# (never poorer than air), so for each case below the cochlear difference is
# computed by hand from the bone-conduction values.

def test_cochlear_asymmetry_in_the_ear_better_by_air_still_flags():
    # Right AC 50 / BC 10 (conductive); left AC 35 / BC 30 (sensorineural).
    # Right is 15 dB poorer by air, but the left cochlea (30, outside normal
    # limits) is 20 dB worse than the right cochlea (10) at 250–4000 Hz:
    # ≥20 dB at 0.5–4 kHz (DoH) and ≥15 dB at two frequencies — BAA "air or
    # bone conduction". An MRI question in the LEFT ear.
    right = ear(flat(50), flat(10, BC), masked=True)
    left = ear(flat(35), flat(30, BC), masked=True)
    review = safety_review(right, left)
    asym = review["asymmetry"]
    assert asym["flag"] is True
    assert asym["kind"] == "sensorineural"
    assert asym["poorer_ear"] == "left"
    assert asym["type_confirmed"] is True
    assert asym["bone_only_freqs"] == [250, 500, 1000, 2000, 4000]
    assert asym["bone_conduction_only"] is True
    assert all("in bone conduction" in r for r in asym["reasons"])
    # The right ear's conductive asymmetry is still reported, not dropped.
    assert asym["other_ear_conductive"] == {"ear": "right",
                                            "freqs": [250, 500, 1000, 2000, 4000]}
    alert = next(a for a in review["alerts"] if "symmetric" in a["title"])
    assert alert["title"] == "Asymmetric sensorineural hearing loss — retrocochlear screen"
    assert alert["ear"] == "left"
    assert "MRI" in alert["action"]
    assert "right ear is the poorer by air conduction" in alert["detail"]
    assert "middle ear" in alert["detail"]


def test_larger_cochlear_asymmetry_behind_a_conductive_ear_flags():
    # Right AC 60 / BC 5; left AC 45 / BC 40: cochleae 35 dB apart.
    review = safety_review(ear(flat(60), flat(5, BC), masked=True),
                           ear(flat(45), flat(40, BC), masked=True))
    assert review["asymmetry"]["flag"] is True
    assert review["asymmetry"]["poorer_ear"] == "left"


def test_symmetric_air_with_asymmetric_bone_conduction_flags():
    # Air 50 / 50 — no air asymmetry at all. Bone 5 / 45: the left cochlea is
    # 40 dB worse at every bone-conduction frequency.
    asym = asymmetry_check(flat(50), flat(50), flat(5, BC), flat(45, BC))
    assert asym["flag"] is True
    assert asym["poorer_ear"] == "left"
    assert asym["bone_conduction_only"] is True


def test_bone_conduction_asymmetry_below_the_criterion_does_not_flag():
    # Left cochlea 24 vs right cochlea 10: 14 dB at every frequency — below
    # 15 dB (pair) and 20 dB (single). Right remains conductively poorer.
    asym = asymmetry_check(flat(50), flat(35), flat(10, BC), flat(24, BC))
    assert asym["flag"] is False
    assert asym["kind"] == "conductive"
    # 15 dB at two or more frequencies meets the pair criterion.
    asym = asymmetry_check(flat(50), flat(35), flat(10, BC), flat(25, BC))
    assert asym["flag"] is True
    assert asym["poorer_ear"] == "left"


def test_a_bone_conduction_difference_within_normal_limits_does_not_flag():
    # Left cochlea 20 dB HL is within normal limits, however far from 0.
    asym = asymmetry_check(flat(45), flat(30), flat(0, BC), flat(20, BC))
    assert asym["flag"] is False


def test_an_untested_cochlea_beside_a_conductive_asymmetry_is_not_excluded():
    # Right AC 50 / BC 10, left AC 35 with no bone conduction. The left
    # cochlea is somewhere at or better than 35, i.e. up to 25 dB worse than
    # the right cochlea at 250–4000 Hz. Not shown, so no MRI flag — but the
    # referral must say it is not excluded and how to settle it.
    review = safety_review(ear(flat(50), flat(10, BC), masked=True), ear(flat(35)))
    asym = review["asymmetry"]
    assert asym["flag"] is False
    assert asym["kind"] == "conductive"
    assert asym["other_ear_bc_not_measured"] == [250, 500, 1000, 2000, 4000]
    alert = next(a for a in review["alerts"] if "symmetric" in a["title"])
    assert "Measure masked bone conduction in the left ear" in alert["action"]
    assert "not excluded" in alert["action"]


def test_a_measured_normal_cochlea_needs_no_untested_cochlea_caveat():
    asym = asymmetry_check(flat(10), flat(45), flat(5, BC), flat(5, BC))
    assert asym["kind"] == "conductive"
    assert asym["other_ear_bc_not_measured"] == []


def test_cochlear_asymmetry_reaches_triage_end_to_end():
    body = _analyze({"ac": flat(50), "bc": flat(10, BC), "masked": True},
                    {"ac": flat(35), "bc": flat(30, BC), "masked": True})
    assert body["safety"]["asymmetry"]["flag"] is True
    assert body["triage"]["priority"] <= 2
    assert "MRI" in body["verdict"]["action"]


# ===================== A2-1: sudden SNHL in a mixed ear, and one ear =======

def test_a_sudden_cochlear_loss_beneath_a_conductive_one_is_an_emergency():
    # Right AC 70 / BC 45: a 25 dB air-bone gap, so the sensorineural
    # threshold is bone conduction, 45 — 35 dB worse than the normal left ear
    # (10) at 250–4000 Hz; 8 kHz has no bone conduction and reads as air (70,
    # 60 dB worse). Six consecutive frequencies ≥ 30 dB: SSNHL on a mixed ear.
    mixed = ear(flat(70), flat(45, BC))
    review = safety_review(mixed, NORMAL, onset="sudden")
    s = review["sudden"]["right"]
    assert s["urgency"] == "emergency"
    assert s["basis"] == "opposite_ear"
    assert s["freqs"] == [250, 500, 1000, 2000, 4000, 8000]
    assert "bone conduction" in s["message"]
    assert review["alerts"][0]["level"] == "emergency"


def test_a_mixed_ear_with_unknown_onset_asks_when_it_started():
    review = safety_review(ear(flat(70), flat(45, BC)), NORMAL, onset="unknown")
    assert review["sudden"]["right"]["urgency"] == "ask"


def test_a_conductive_opposite_ear_does_not_hide_a_sudden_cochlear_loss():
    # This ear: 40 dB HL at 2/4/8 kHz with no gap (PTA (10+10+40+40)/4 = 25,
    # under 30). Opposite: AC 45 / BC 5 at 250–4000 (conductive), 10 at 8 kHz.
    # By air the opposite is poorer at 2 and 4 kHz; its sensorineural
    # thresholds are 5, 5, 10, so this ear is 35, 35, 30 dB worse at 2/4/8 kHz.
    this = ear({250: 10, 500: 10, 1000: 10, 2000: 40, 4000: 40, 8000: 40},
               {250: 10, 500: 10, 1000: 10, 2000: 38, 4000: 38})
    opposite = ear({250: 45, 500: 45, 1000: 45, 2000: 45, 4000: 45, 8000: 10},
                   flat(5, BC))
    result = sudden_loss_check(this.ac, this.bc, "sudden",
                               opposite_ac=opposite.ac, opposite_bc=opposite.bc)
    assert result["flag"] is True
    assert result["freqs"] == [2000, 4000, 8000]


def test_a_sudden_loss_in_a_single_tested_ear_is_not_silent():
    # LOW_SUDDEN with no left ear: 45/45/40 dB HL at 250–1000 Hz, ≥30 dB from
    # audiometric zero at three consecutive frequencies; PTA 26.25 < 30.
    review = safety_review(LOW_SUDDEN, ear({}), onset="sudden")
    s = review["sudden"]["right"]
    assert s["urgency"] == "emergency"
    assert s["basis"] == "audiometric_zero"
    assert s["unreferenced_freqs"] == [250, 500, 1000]
    assert "assumes this ear heard normally before" in s["message"]
    assert "Test the opposite ear" in s["action"]
    unknown = safety_review(LOW_SUDDEN, ear({}), onset="unknown")
    assert unknown["sudden"]["right"]["urgency"] == "ask"


def test_a_tested_opposite_ear_is_the_reference_not_audiometric_zero():
    # Left 20 dB HL at 250–1000: LOW_SUDDEN is only 25/25/20 dB worse.
    left = ear({250: 20, 500: 20, 1000: 20, 2000: 10, 4000: 10, 8000: 10},
               {250: 20, 500: 20, 1000: 20, 2000: 10, 4000: 10})
    review = safety_review(LOW_SUDDEN, left, onset="sudden")
    assert review["sudden"]["right"]["urgency"] == "none"


def test_a_mild_single_ear_loss_is_not_sudden_snhl():
    # 25 dB HL everywhere: under 30 dB HL even from audiometric zero.
    assert sudden_loss_check(flat(25), flat(25, BC), "sudden")["flag"] is False


# ================= verdict: a normal average with a loss it cannot see =====

def test_a_normal_average_with_a_raised_frequency_is_not_called_normal():
    # Left PTA (10 + 10 + 10 + 40) / 4 = 17.5: WHO normal; 4 kHz is 40 dB HL.
    thresholds = {"right": {"ac": flat(10)}, "left": {"ac": {**flat(10), 4000: 40}}}
    v = _verdict(NORMAL_EAR, _rules_ear("Normal", "Normal hearing", 17.5),
                 thresholds=thresholds)
    assert v["headline"] == ("The four-frequency average is within normal limits in "
                             "both ears, but hearing is outside normal limits at "
                             "4000 Hz in the left ear.")
    assert v["tone"] == "loss"
    assert "No action required" not in v["action"]


def test_the_same_raised_frequency_in_both_ears_reads_both_ears():
    thresholds = {s: {"ac": {**flat(10), 8000: 30}} for s in ("right", "left")}
    v = _verdict(NORMAL_EAR, dict(NORMAL_EAR), thresholds=thresholds)
    assert v["headline"].endswith("outside normal limits at 8000 Hz in both ears.")


def test_20_db_hl_is_still_within_normal_limits():
    thresholds = {s: {"ac": flat(20)} for s in ("right", "left")}
    v = _verdict(NORMAL_EAR, dict(NORMAL_EAR), thresholds=thresholds)
    assert v["headline"] == "Hearing is within normal limits in both ears."
    assert v["tone"] == "normal"


def test_a_raised_frequency_in_a_single_tested_ear():
    v = _verdict(NORMAL_EAR, _rules_ear("Indeterminate", None, None, abg=None),
                 thresholds={"right": {"ac": {**flat(10), 8000: 35}},
                             "left": {"ac": {}}})
    assert v["headline"] == ("Hearing in the right ear is within normal limits on "
                             "the four-frequency average, but outside normal limits "
                             "at 8000 Hz; the left ear was not tested.")


def test_the_better_ears_raised_frequency_is_named_beside_a_loss():
    v = _verdict(NORMAL_EAR, _rules_ear("Sensorineural", "Mild hearing loss", 30),
                 thresholds={"right": {"ac": {**flat(10), 8000: 30}},
                             "left": {"ac": flat(30)}})
    assert v["headline"] == ("Mild sensorineural hearing loss in the left ear; the "
                             "right ear is within normal limits on the four-frequency "
                             "average, but outside normal limits at 8000 Hz.")


def test_a_4khz_only_loss_headline_agrees_with_its_mri_referral_end_to_end():
    body = _analyze(_json_ear(NORMAL),
                    {"ac": {**flat(10), 4000: 40}, "bc": {**flat(10, BC), 4000: 35}})
    assert body["safety"]["asymmetry"]["flag"] is True
    headline = body["verdict"]["headline"]
    assert "within normal limits in both ears." not in headline
    assert "4000 Hz in the left ear" in headline
    assert "MRI" in body["verdict"]["action"]


# =================== verdict: provisional wording and punctuation ==========

def test_a_bone_conduction_no_response_is_named_not_called_incomplete():
    prov = {**_rules_ear("Mixed", "Profound hearing loss", 90, provisional=True,
                         abg=30.0),
            "bc_nr_freqs": [2000, 4000], "bc_pta": {"missing_freqs": []}}
    v = _verdict(prov, dict(prov))
    assert v["headline"] == ("Bilateral profound mixed hearing loss (type provisional "
                             "— no bone-conduction response within the vibrator's "
                             "limit at 2000 and 4000 Hz).")


def test_bone_conduction_untested_at_some_frequencies_is_incomplete():
    prov = {**_rules_ear("Sensorineural", "Moderate hearing loss", 45,
                         provisional=True, abg=5.0),
            "bc_nr_freqs": [], "bc_pta": {"missing_freqs": [2000, 4000]}}
    v = _verdict(prov, dict(prov))
    assert "(type provisional — bone conduction incomplete)" in v["headline"]


def test_a_provisional_unilateral_headline_has_one_parenthesis():
    prov = _rules_ear("Sensorineural (provisional)", "Severe hearing loss", 70,
                      provisional=True, abg=None)
    v = _verdict(NORMAL_EAR, prov)
    assert v["headline"] == ("Unilateral severe sensorineural hearing loss (left ear; "
                             "type provisional — bone conduction not measured).")
    assert ") (" not in v["headline"]


# ====================== verdict: a conductive loss goes to ENT first =======

def test_a_conductive_loss_without_alerts_is_referred_to_ent_first():
    cond = _rules_ear("Conductive", "Moderate hearing loss", 45, abg=35.0)
    v = _verdict(cond, dict(cond))
    assert v["action"].startswith("Refer for ENT / otology assessment of the "
                                  "conductive component in both ears")
    assert v["action"].endswith("hearing-aid evaluation if the loss persists.")
    mild = _rules_ear("Conductive", "Mild hearing loss", 30, abg=25.0)
    v = _verdict(NORMAL_EAR, mild)
    assert "in the left ear" in v["action"]
    assert "hearing-aid" not in v["action"]


def test_a_sensorineural_loss_still_goes_to_hearing_aids():
    sn = _rules_ear("Sensorineural", "Moderate hearing loss", 45)
    assert _verdict(sn, dict(sn))["action"] == "Refer for hearing-aid evaluation and fitting."
