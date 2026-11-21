"""Regression tests: deep noise notches, one per-frequency normal limit, the AI
report payload, ASHA/OSHA progression wording, symptom age priors and the
CAPD reported-loss penalty, the 2024 Gazette caveat, infant P1 limits,
masking without the other ear's bone conduction, and air-only normal ears.

Every expected value is computed here from the rule it implements — the
Coles et al. (2000) notch, the BSA (2018) per-frequency limit, ASHA (1994)
ototoxicity criteria, OSHA 29 CFR 1910.95(g)(10), the ISO 7029:2000 median
curve, Sharma et al. (2002), the masking rules — never read back from the
module under test.
"""
import io
import json
import math

import pytest
from fastapi.testclient import TestClient

from app.clinical import aep, masking, progression, rules, safety
from app.clinical import symptoms as S
from app.clinical.symptom_kb import COMMONNESS_WEIGHT
from app.main import app
from app.ml import features
from app.ml.classifier import MODEL_PATH, classify_ear
from app.ml.deep import deep_available
from app.models.schemas import ear_to_numeric
from app.services.report import GENERATOR_SYSTEM, _slim, generate_offline

client = TestClient(app)

FREQS = [250, 500, 1000, 2000, 4000, 8000]
BC_FREQS = [250, 500, 1000, 2000, 4000]

needs_model = pytest.mark.skipif(not MODEL_PATH.exists(), reason="model not trained")
needs_deep = pytest.mark.skipif(not deep_available(), reason="deep ensemble not trained")


def num(values):
    return ear_to_numeric({f: v for f, v in zip(FREQS, values) if v is not None})


def json_ear(values, freqs=FREQS):
    return {str(f): v for f, v in zip(freqs, values) if v is not None}


def analyze(right_ac, right_bc=None, left_ac=None, left_bc=None, age=40, **ears):
    left_ac = right_ac if left_ac is None else left_ac
    left_bc = right_bc if left_bc is None else left_bc
    body = {
        "patient": {"name": "T", "age": age, "sex": "male", "occupation": "teacher"},
        "right": {"ac": json_ear(right_ac), "bc": json_ear(right_bc or [], BC_FREQS),
                  **ears.get("right_extra", {})},
        "left": {"ac": json_ear(left_ac), "bc": json_ear(left_bc or [], BC_FREQS),
                 **ears.get("left_extra", {})},
    }
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ============================================ E1-7 the deep noise notch ===

DEEP_NOTCH = [10, 10, 15, 20, 65, 25]      # 4k 40 dB worse than max(20, 25)
SHALLOW_NOTCH = [10, 10, 15, 20, 60, 30]   # 4k 30 dB worse than max(20, 30)


def test_a_deep_classic_notch_is_a_noise_notch_reversal():
    n = num(DEEP_NOTCH)
    # Still an isolated reversal at the 40 dB 4 kHz bar ...
    assert [(o["freq"], o["deviation_db"]) for o in features.isolated_outliers(n)] \
        == [(4000, 40)]
    # ... and a Coles notch with loss: 65 - min(15, 20) = 50 >= 10,
    # 65 - 25 = 40 >= 10, 65 > 20 dB HL.
    assert features.noise_notch_with_loss(n) is True
    # Depth 40 <= 50; recovery 65 - 25 = 40 < 60; worsening 65 - 20 = 45 < 75.
    assert features.noise_notch_reversal(n)["freq"] == 4000


def test_the_notch_does_not_withdraw_a_noise_notch_label_but_does_any_other():
    n = num(DEEP_NOTCH)
    assert features.plausibility_reasons(n, "noise_notch_4k") == []
    for label in (None, "flat", "cookie_bite"):
        reasons = features.plausibility_reasons(n, label)
        assert any("isolated outlier at 4000 Hz" in r for r in reasons), label
    note = features.notch_retest_note(n, "noise_notch_4k")
    assert "40 dB worse" in note and "confirm 4000 Hz on retest" in note
    assert features.notch_retest_note(n, "flat") is None
    assert features.notch_retest_note(num(SHALLOW_NOTCH), "noise_notch_4k") is None


@pytest.mark.parametrize("values, why", [
    # 90 - max(50, 20) = 40 worse, but 90 - 20 = 70 >= 60 dB recovery.
    ([20, 35, 50, 50, 90, 20], "recovery"),
    # 100 dB spike: 100 > 50 dB deep.
    ([0, 0, 0, 0, 100, 0], "depth"),
    # 10 -> 85 = 75 dB worsening from 2 kHz (>= 75), 85 - 30 = 55 deep.
    ([10, 10, 10, 10, 85, 30], "worsening"),
])
def test_reversals_beyond_the_trained_notch_shape_stay_outliers(values, why):
    n = num(values)
    assert features.noise_notch_reversal(n) is None, why
    assert any("isolated outlier at 4000 Hz" in r
               for r in features.plausibility_reasons(n, "noise_notch_4k")), why


def test_the_deepest_trained_notch_is_still_exempt():
    # [10,10,15,25,75,20]: 75 - 25 = 50 deep (the bound itself), recovery 55.
    n = num([10, 10, 15, 25, 75, 20])
    assert features.noise_notch_reversal(n) is not None
    assert features.NOISE_NOTCH_MAX_REVERSAL_DB == 50.0


@needs_model
def test_a_deep_notch_keeps_its_label_with_a_retest_request():
    m = classify_ear({f: v for f, v in zip(FREQS, DEEP_NOTCH)}, {})
    assert m["pattern"] == "noise_notch_4k"
    assert m["reliable"] is True and m["ood"] is False
    assert "confirm 4000 Hz on retest" in m["retest_note"]
    assert m["retest_note"] in m["reliability_note"]
    shallow = classify_ear({f: v for f, v in zip(FREQS, SHALLOW_NOTCH)}, {})
    assert shallow["reliable"] is True and shallow["retest_note"] is None


@needs_model
def test_a_deep_notch_gets_at_least_the_advice_a_shallow_one_gets():
    deep = analyze(DEEP_NOTCH, DEEP_NOTCH[:5])
    shallow = analyze(SHALLOW_NOTCH, SHALLOW_NOTCH[:5])
    for a in (deep, shallow):
        assert "noise notch (4 kHz) configuration" in a["verdict"]["headline"]
        recs = generate_offline(a)["report"]["recommendations"]
        assert any("Mandatory hearing protection" in r for r in recs)
    recs = generate_offline(deep)["report"]["recommendations"]
    retest = [r for r in recs if "confirm 4000 Hz on retest" in r]
    assert [r.split(":")[0] for r in retest] == ["Right ear", "Left ear"]
    assert not any("confirm 4000 Hz on retest" in r
                   for r in generate_offline(shallow)["report"]["recommendations"])


@needs_deep
def test_the_deep_ensemble_judges_the_notch_against_its_own_label():
    body = client.post("/api/model/deep-predict",
                       json={"ac": json_ear(DEEP_NOTCH)}).json()
    if body["pattern"] == "noise_notch_4k":
        assert not any("isolated outlier" in r for r in body["novelty_reasons"])
        assert "confirm 4000 Hz on retest" in body["reliability_note"]
    else:
        assert any("isolated outlier" in r for r in body["novelty_reasons"])


# ===================================== E1-1 one per-frequency normal limit ===

def test_the_configuration_gate_uses_the_headline_limit():
    # BSA 2018: mild from 21 dB HL; the verdict uses safety.NORMAL_LIMIT_DB.
    assert features.NORMAL_FREQ_LIMIT == safety.NORMAL_LIMIT_DB == 20
    assert masking.NORMAL_LIMIT_DB == safety.NORMAL_LIMIT_DB
    assert rules.AC_NORMAL_MAX_DB == safety.NORMAL_LIMIT_DB


@needs_model
@pytest.mark.parametrize("values", [
    [10, 10, 10, 10, 25, 10],   # the critic's case: 25 at 4 kHz
    [10, 10, 10, 10, 20, 10],   # 20 is within the limit
    [25, 10, 10, 10, 10, 10],
    [10, 10, 10, 10, 10, 25],
    [5, 10, 5, 10, 15, 10],
])
def test_the_card_and_the_headline_never_disagree_about_normal(values):
    a = analyze(values, values[:5])
    raised = [f for f, v in zip(FREQS, values) if v > 20]
    headline = a["verdict"]["headline"]
    for side in ("right", "left"):
        card_normal = a["ml"][side]["pattern"] == "normal"
        assert card_normal == (not raised), (side, a["ml"][side]["pattern"])
    if raised:
        assert "outside normal limits" in headline
        assert all(f"{f} Hz" in headline for f in raised)
    else:
        assert headline == "Hearing is within normal limits in both ears."


# ============================== A2-6 / F-4 the AI report's age comparison ===

def test_the_ai_report_is_not_given_the_hearing_age():
    a = analyze([20, 25, 30, 40, 55, 70], [20, 25, 30, 40, 55], age=40)
    assert a.get("norms"), "precondition: the analysis still computes norms"
    slim = _slim(a)
    assert "norms" not in slim
    assert "hearing_age" not in json.dumps(slim)
    assert "hearing age" in GENERATOR_SYSTEM.lower()


# ===================================================== D-2 progression ===

Z = {f: 0 for f in FREQS}


def _ear(**shifts):
    return {**Z, **{int(k[1:]): v for k, v in shifts.items()}}


def test_asha_adjacency_includes_a_measured_3000_hz():
    deltas = progression.ear_deltas(Z, _ear(f2000=10, f4000=10))
    # Without 3 kHz, 2 and 4 kHz are neighbours in the tested series.
    assert progression.asha_ototoxicity(deltas, Z, _ear(f2000=10, f4000=10))["flag"]
    # With 3 kHz measured unchanged, 2000/3000 and 3000/4000 are the adjacent
    # pairs, neither shifted >= 10 dB at both: no ASHA (1994) change.
    r = progression.asha_ototoxicity(deltas, Z, _ear(f2000=10, f4000=10), 0, 0)
    assert r["flag"] is False and r["triggers"] == []
    # A 3 kHz shift counts: 2000/3000 both +10.
    r = progression.asha_ototoxicity(deltas, Z, _ear(f2000=10, f4000=10), 0, 10)
    assert "≥10 dB shift at adjacent frequencies 2000/3000 Hz (+10/+10 dB)" in r["triggers"]
    assert "≥10 dB shift at adjacent frequencies 3000/4000 Hz (+10/+10 dB)" in r["triggers"]
    # A single 3 kHz shift of 20 dB is criterion (a).
    d = progression.ear_deltas(Z, Z)
    assert progression.asha_ototoxicity(d, Z, Z, 0, 20)["triggers"] == [
        "≥20 dB shift at 3000 Hz (+20 dB)"]


def test_asha_loss_of_response_runs_through_3000_hz():
    base = {f: 10 for f in FREQS}
    cur = {**base, 2000: "NR", 4000: "NR"}
    d = progression.ear_deltas(base, cur)
    # 2k and 4k lost, 8k kept: two consecutive without 3 kHz ...
    assert not any("three consecutive" in t for t in
                   progression.asha_ototoxicity(d, base, cur)["triggers"])
    # ... three (2k, 3k, 4k) once 3 kHz was tested and also lost.
    trig = progression.asha_ototoxicity(d, base, cur, 10, "NR")["triggers"]
    assert "loss of response at three consecutive frequencies" in trig


def _narrate(cur, b3=None, c3=None):
    body = {"baseline": {"right": {"ac": json_ear([0] * 6)}, "left": {"ac": json_ear([0] * 6)}},
            "current": {"right": {"ac": json_ear(cur)}, "left": {"ac": json_ear([0] * 6)}}}
    if b3 is not None:
        body["thresholds_3000"] = {"baseline": {"right": b3}, "current": {"right": c3}}
    r = client.post("/api/progression", json=body)
    assert r.status_code == 200, r.text
    return r.json()["progression"]


def test_a_shift_short_of_the_sts_says_so_before_any_other_criterion():
    # 2k +10, 3k 0, 4k +10: OSHA average (10 + 0 + 10) / 3 = 6.67 dB.
    p = _narrate([0, 0, 0, 10, 10, 0], 0, 0)
    lines = p["narrative"]["lines"]
    assert ("This does not meet the OSHA standard threshold shift criterion: the "
            "average shift at 2k/3k/4k Hz is 6.67 dB, below 10 dB.") in lines
    assert p["right"]["asha_ototoxicity"]["flag"] is False
    assert p["narrative"]["flagged"] is False
    # 4k +20 alone: no STS ((0 + 0 + 20) / 3), but ASHA (a) is met — and is not
    # introduced with "also".
    p = _narrate([0, 0, 0, 0, 20, 0], 0, 0)
    lines = p["narrative"]["lines"]
    assert not any(l.startswith("It also meets") for l in lines)
    assert ("Right ear: the change meets ASHA ototoxicity-monitoring criteria: "
            "≥20 dB shift at 4000 Hz (+20 dB).") in lines
    # With the STS met, "also" is right.
    p = _narrate([0, 0, 0, 30, 30, 0], 0, 30)
    assert any(l.startswith("It also meets ASHA") for l in p["narrative"]["lines"])


@pytest.mark.parametrize("cur, needed, phrase", [
    # Proxy 2k/4k: 3k shift needed = 3 x 10 - (2k + 4k).
    ([0, 0, 0, 0, 15, 0], 15, "only if the 3000 Hz shift is 15 dB or more"),
    ([0, 0, 0, 10, 20, 0], 0, "unless the 3000 Hz threshold has improved since the baseline"),
    ([0, 0, 0, 30, 40, 0], -40,
     "unless the 3000 Hz threshold has improved by more than 40 dB since the baseline"),
])
def test_the_proxy_never_states_a_negative_shift_requirement(cur, needed, phrase):
    p = _narrate(cur)
    sts = p["right"]["osha_sts"]
    assert sts["missing_shift_needed_db"] == needed
    assert phrase in sts["missing_shift_note"]
    text = " ".join(p["narrative"]["lines"])
    assert "shift is -" not in text and " -40 dB or more" not in text
    if sts["flag"]:
        assert phrase in text


# ============================================ G-3 the symptom differential ===

LISTENING_WITH_LOSS = ["speech_in_noise_difficulty", "difficulty_following_instructions",
                       "hearing_loss"]
LISTENING_LOSS = ["gradual_hearing_loss", "speech_in_noise_difficulty",
                  "difficulty_following_instructions", "tinnitus"]


def _entry(result, key):
    return next((d for d in result["differential"] if d["key"] == key), None)


def _rank(result, key):
    keys = [d["key"] for d in result["differential"]]
    return keys.index(key) if key in keys else len(keys)


def test_an_adult_reporting_a_loss_is_not_led_by_capd():
    r = S.assess(age=30, symptoms=LISTENING_WITH_LOSS)
    assert r["differential"][0]["key"] != "capd"
    capd = _entry(r, "capd")
    # (3 + 3 - 1) / 11, x 0.35 for the reported loss CAPD's definition rules
    # out until tested, uncommon, adult gate 1 - 0.5 x 13/25 at 30.
    expected = 5 / 11 * 0.35 * COMMONNESS_WEIGHT["uncommon"] * (1 - 0.5 * 13 / 25)
    assert capd["score"] == pytest.approx(expected, abs=1e-3)
    assert capd["report_conflict_factor"] == 0.35
    assert "pure-tone audiometry" in capd["report_conflict_note"]


def test_presbycusis_follows_the_iso_7029_curve_below_fifty():
    r = S.assess(age=30, symptoms=LISTENING_WITH_LOSS)
    presby = _entry(r, "sensory_presbycusis")
    # loss 2 + noise 3 of 13; ISO 7029 median at 30 is (12/32)^2 of that at 50.
    assert presby is None or presby["score"] == pytest.approx(
        5 / 13 * (12 / 32) ** 2, abs=1e-3)
    r = S.assess(age=30, symptoms=LISTENING_LOSS)
    assert r["differential"][0]["key"] != "sensory_presbycusis"
    assert _entry(r, "sensory_presbycusis")["score"] == pytest.approx(
        10 / 13 * (12 / 32) ** 2, abs=1e-3)
    # Paget's: two and a half decades under 55 at 30, halving per decade;
    # gradual 3 + implied loss 2 + tinnitus 2 of 12, rare.
    from app.clinical.symptom_kb import DISEASES
    present = {"gradual_hearing_loss", "hearing_loss", "tinnitus"}
    row = S._score_disease("pagets", DISEASES["pagets"], present, 30,
                           {"hearing_loss": ["gradual_hearing_loss"]})
    assert row["score"] == pytest.approx(
        7 / 12 * COMMONNESS_WEIGHT["rare"] * 0.5 ** 2.5, abs=1e-3)
    pagets = S.assess(age=30, symptoms=["gradual_hearing_loss", "tinnitus"])
    assert pagets["differential"][0]["key"] not in ("pagets", "sensory_presbycusis")


@pytest.mark.parametrize("age", [9, 12, 17, 18, 25, 30, 35])
def test_no_age_bound_condition_leads_a_young_gradual_loss(age):
    for symptoms in (LISTENING_LOSS, ["gradual_hearing_loss", "tinnitus"],
                     LISTENING_WITH_LOSS):
        top = S.assess(age=age, symptoms=symptoms)["differential"][0]["key"]
        assert top not in ("sensory_presbycusis", "pagets", "capd"), (age, symptoms)


def test_the_critics_own_checks_still_hold():
    assert S.assess(age=45, symptoms=LISTENING_LOSS)["differential"][0]["key"] \
        == "sensory_presbycusis"
    r45 = S.assess(age=45, symptoms=LISTENING_LOSS)
    assert _rank(r45, "sensory_presbycusis") < _rank(r45, "pagets")
    assert S.assess(age=70, symptoms=LISTENING_LOSS)["differential"][0]["key"] \
        == "sensory_presbycusis"
    assert S.assess(age=9, symptoms=LISTENING_WITH_LOSS[:2])["differential"][0]["key"] \
        == "capd"


def _ear_flat(level, bc):
    return {"ac": {str(f): level for f in FREQS},
            "bc": {str(f): bc for f in BC_FREQS} if bc is not None else {}}


def _analysis(right, left, age=30):
    r = client.post("/api/analyze", json={
        "patient": {"name": "T", "age": age, "sex": "male"},
        "right": right, "left": left})
    assert r.status_code == 200, r.text
    return r.json()


def test_normal_thresholds_lift_the_reported_loss_penalty():
    history = S.assess(age=30, symptoms=LISTENING_WITH_LOSS)
    normal = _analysis(_ear_flat(10, 10), _ear_flat(10, 10))
    rec = S.reconcile(history, normal)
    assert rec["outcome"] == "replaced"
    assert rec["leading"]["key"] == "capd"
    # The same evidence without the 0.35: 5/11 x 0.85 x (1 - 0.5 x 13/25).
    assert rec["leading"]["score"] == pytest.approx(
        5 / 11 * 0.85 * (1 - 0.5 * 13 / 25), abs=1e-3)
    assert "not measured" in rec["replaced_because"]
    line = next(f for f in client.post("/api/diagnosis/picture", json={
        "analysis": normal, "assessment": history}).json()["findings"]
        if f["key"] == "symptoms")
    assert line["says"] == ("Leading possibility once the audiogram is considered: "
                            "Central auditory processing disorder (CAPD).")
    assert "led, but the hearing loss the history reported was not measured" in line["detail"]


def test_a_measured_loss_or_one_untested_ear_keeps_the_penalty():
    history = S.assess(age=30, symptoms=LISTENING_WITH_LOSS)
    snhl = S.reconcile(history, _analysis(_ear_flat(50, 45), _ear_flat(50, 45)))
    capd = next(r for r in snhl["differential"] if r["key"] == "capd")
    assert capd["audiogram"] == "contradicted" and not capd["report_conflict_lifted"]
    one_ear = S.reconcile(history, _analysis(_ear_flat(10, 10), {"ac": {}, "bc": {}}))
    capd = next(r for r in one_ear["differential"] if r["key"] == "capd")
    assert not capd["report_conflict_lifted"]
    assert one_ear["outcome"] == "unchanged"


# ======================================= A1-1 the 2024 Gazette caveat ===

def test_a_certifiable_figure_states_the_2024_supersession():
    d = rules.rpwd_disability_from_thresholds({500: 60, 1000: 60, 2000: 60, 4000: 60},
                                              {500: 60, 1000: 60, 2000: 60, 4000: 60})
    assert d["certifiable"] is True
    assert "S.O. 1338(E)" in d["certification_note"]
    assert "S.O. 1338(E)" in d["guideline_note"]
    assert "confirm it against the guidelines in force" in d["guideline_note"]
    a = analyze([60] * 6, None, [60] * 6)
    lines = generate_offline(a)["report"]["disability"]
    assert any("S.O. 1338(E)" in l for l in lines)


def test_a_non_certifiable_figure_keeps_its_own_caveat():
    d = rules.rpwd_disability_from_thresholds({500: 60, 1000: 60, 2000: 60},
                                              {500: 60, 1000: 60, 2000: 60, 4000: 60})
    assert d["certifiable"] is False
    assert d["certification_note"].startswith("Not certifiable")
    assert d["guideline_note"]


def test_the_referral_letter_carries_the_caveat():
    pypdf = pytest.importorskip("pypdf")
    a = analyze([60] * 6, None, [60] * 6)
    assert a["rules"]["disability"]["certifiable"] is True
    r = client.post("/api/referral", json={"patient": a["patient"], "analysis": a})
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    text = " ".join((p.extract_text() or "")
                    for p in pypdf.PdfReader(io.BytesIO(r.content)).pages)
    assert "1338(E)" in " ".join(text.split())


# ====================================================== C-3 infant P1 ===

def test_an_infant_p1_verdict_is_provisional_with_its_age_slope():
    e = aep.expected_p1_latency(6)
    assert e["provisional"] is True
    # d(latency)/d(age) = 32.746 / age per year; / 12 per month at 0.5 years.
    per_month = 32.746 / 0.5 / 12
    assert f"{per_month:.1f} ms a month" in e["provisional_note"]
    assert aep.expected_p1_latency(12)["provisional"] is False
    assert aep.expected_p1_latency(60)["provisional"] is False
    # The published width is kept: 155.6 - 32.746 ln(0.5) + 32.
    assert e["upper_95_ms"] == pytest.approx(155.6 - 32.746 * math.log(0.5) + 32, abs=0.05)


def test_a_delayed_infant_p1_is_flagged_and_caveated():
    r = aep.analyze_llr({"P1": 250, "N1": None, "P2": None, "N2": None}, age_months=6)
    assert "cortical_maturation_delayed" in r["flags"]
    assert r["maturation"]["provisional"] is True
    assert "provisional" in r["findings"][0] and "corrected age" in r["findings"][0]
    older = aep.analyze_llr({"P1": 200, "N1": None, "P2": None, "N2": None},
                            age_months=18)
    assert older["maturation"]["provisional"] is False
    assert "provisional" not in older["findings"][0]


# ============================================================= masking ===

def _plans(right, left, transducer="supra_aural"):
    from app.models.schemas import EarData
    return masking.masking_review(EarData(**right), EarData(**left), transducer)


def test_8k_ac_masking_cannot_be_ruled_out_beside_a_conductive_ear():
    # Right: flat 40 dB conductive (BC 0). Left: 45 dB, no BC.
    plans = _plans({"ac": {f: 40 for f in FREQS}, "bc": {f: 0 for f in BC_FREQS}},
                   {"ac": {f: 45 for f in FREQS}, "bc": {}})
    left = plans["left"]
    # Rule 2 at 250-4000: 45 - 0 = 45 >= 40.
    assert left["ac_freqs"] == [250, 500, 1000, 2000, 4000]
    # At 8 kHz rule 1 gives 45 - 40 = 5; BC(R) is estimated from the 40 dB gap
    # at 4 kHz as 40 - 40 = 0, so 45 - 0 = 45 >= 40 could fire.
    assert left["undetermined_freqs"] == [8000]
    row = next(r for r in left["rows"] if r["freq"] == 8000)
    est = next(x for x in row["ac"]["rules"] if x.get("estimated"))
    assert est["value"] == 45 and est["met"] is None
    assert any("cannot be ruled out at [8000] Hz" in r for r in left["reasons"])
    assert left["warning"] is True


def test_no_undetermined_frequency_without_a_gap_in_the_other_ear():
    # Right: sensorineural 40 (no gap). Left 75 at every frequency: rule 1
    # 75 - 40 = 35 < 40, and BC(R) estimated at 8 kHz as 40 - 0 = 40.
    plans = _plans({"ac": {f: 40 for f in FREQS}, "bc": {f: 40 for f in BC_FREQS}},
                   {"ac": {f: 75 for f in FREQS}, "bc": {}})
    assert plans["left"]["undetermined_freqs"] == []


def test_a_bc_dilemma_behind_normal_hearing_does_not_take_over_the_verdict():
    tymp = {"tymp_pressure": 0, "tymp_compliance": 0.8, "tymp_ecv": 1.2}
    a = analyze([15] * 6, [-5] * 5, [10] * 6, [10] * 5, right_extra=tymp)
    plan = a["safety"]["masking_review"]["right"]
    # 250 Hz: floor AC(NTE) 10 + 30 occlusion = 40 > ceiling -5 + 40 - 5 = 30.
    assert plan["dilemma_freqs"] == [250]
    assert plan["consequential_dilemma_freqs"] == []
    alerts = {(x["level"], x["title"]) for x in a["safety"]["alerts"]}
    assert ("validity", "Masking dilemma — these thresholds cannot be masked") not in alerts
    assert ("info", "Bone conduction unmaskable where hearing is normal") in alerts
    assert "insert earphones" not in a["verdict"]["action"]


def test_a_dilemma_that_can_change_the_type_stays_a_validity_alert():
    a = analyze([40] * 6, [0] * 5, [40] * 6, [0] * 5)
    plan = a["safety"]["masking_review"]["right"]
    assert plan["consequential_dilemma_freqs"] == plan["dilemma_freqs"] != []
    assert any(x["level"] == "validity" and x["title"].startswith("Masking dilemma")
               for x in a["safety"]["alerts"])


# ========================================== provisional normal ears ===

def test_air_only_normal_hearing_is_not_provisional():
    t = rules.hearing_type({f: 15 for f in FREQS}, {})
    assert t["type"] == "Normal" and t["provisional"] is False
    assert any(c.startswith("BC not tested — not needed") for c in t["caveats"])
    assert not any(c.startswith("type provisional") for c in t["caveats"])
    # 20 dB HL at 250 and 8000 Hz is within the limit (PTA 15 is normal) ...
    edge = rules.hearing_type({**{f: 15 for f in FREQS}, 250: 20, 8000: 20}, {})
    assert edge["type"] == "Normal" and edge["provisional"] is False
    # ... but a PTA of exactly 20 dB HL is WHO Mild, a loss: still provisional.
    flat20 = rules.hearing_type({f: 20 for f in FREQS}, {})
    assert flat20["type"] == "Sensorineural (provisional)" and flat20["provisional"]
    # 25 dB HL at one frequency is outside the limit.
    raised = rules.hearing_type({**{f: 10 for f in FREQS}, 8000: 25}, {})
    assert raised["type"] == "Normal" and raised["provisional"] is True
    # A loss without bone conduction stays provisional.
    assert rules.hearing_type({f: 40 for f in FREQS}, {})["provisional"] is True


def _batch(rows):
    head = "name,age," + ",".join(f"r_ac_{f}" for f in FREQS) + "," \
        + ",".join(f"l_ac_{f}" for f in FREQS) + "\n"
    csv = head + "".join(f"P{i},35," + ",".join(map(str, r + l)) + "\n"
                         for i, (r, l) in enumerate(rows))
    r = client.post("/api/batch", files={"file": ("c.csv", io.BytesIO(csv.encode()),
                                                  "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_normal_air_only_camp_is_routine_and_the_counts_agree():
    normal = [[5, 10, 5, 10, 15, 10], [10, 10, 15, 10, 15, 20], [0, 5, 5, 0, 10, 15]]
    body = _batch([(normal[i % 3], normal[(i + 1) % 3]) for i in range(12)])
    s = body["summary"]
    assert s["provisional_type"] == 0
    assert s["needs_review"] == 0
    assert all(r["triage"]["level"] == "routine" for r in body["results"])
    assert s["needs_review"] == body["worklist"]["review_required"]


def test_needs_review_counts_the_triage_decision():
    loss = [40, 45, 50, 55, 60, 65]                 # provisional without BC
    normal = [5, 10, 5, 10, 15, 10]
    body = _batch([(loss, loss), (normal, normal), (normal, normal)])
    s = body["summary"]
    reviewed = sum(1 for r in body["results"] if r["triage"]["review_required"])
    assert s["needs_review"] == reviewed == body["worklist"]["review_required"] >= 1
    assert s["atypical_pattern"] == sum(
        1 for r in body["results"] if r["right"]["ood"] or r["left"]["ood"])
    assert s["provisional_type"] == 1


@needs_model
def test_an_air_only_normal_ear_is_not_told_to_complete_bone_conduction():
    a = analyze([10] * 6)
    recs = generate_offline(a)["report"]["recommendations"]
    assert not any("Complete bone-conduction testing" in r for r in recs)
    loss = analyze([45] * 6)
    assert any("Complete bone-conduction testing" in r
               for r in generate_offline(loss)["report"]["recommendations"])
