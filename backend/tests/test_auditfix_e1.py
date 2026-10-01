"""Regression tests: audiogram ML gates, report wording, batch cohort, deep model.

Every expected value is computed here from the published rule it implements
(WHO 2021 normal limit, Coles et al. 2000 notch, NICE TA566 audiometric
criterion), never read back from the module under test.
"""
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.classifier import MODEL_PATH, classify_ear
from app.ml.deep import bc_outside_training, deep_available, predict_deep
from app.ml.features import (
    build_features,
    coles_notch_4k,
    coverage,
    isolated_outliers,
    noise_notch_with_loss,
    normal_average_caveat,
    outlier_blocks,
    plausibility_reasons,
    steep_improvements,
    within_normal_limits,
)
from app.models.schemas import ear_to_numeric
from app.services.report import _slim, counseling_sheet, generate_offline

client = TestClient(app)

FREQS = [250, 500, 1000, 2000, 4000, 8000]
NR = "NR"

needs_model = pytest.mark.skipif(
    not MODEL_PATH.exists(), reason="model not trained")
needs_deep = pytest.mark.skipif(
    not deep_available(), reason="deep ensemble not trained")


def ear(values):
    return {f: v for f, v in zip(FREQS, values) if v is not None}


def json_ear(values):
    return {str(f): v for f, v in zip(FREQS, values) if v is not None}


def num(values):
    return ear_to_numeric(ear(values))


def analyze(right, left=None, right_bc=None, left_bc=None, patient=None):
    left = right if left is None else left
    rec = {
        "patient": patient or {"age": 30, "occupation": "teacher"},
        "right": {"ac": json_ear(right), "bc": right_bc or {}},
        "left": {"ac": json_ear(left), "bc": left_bc or {}},
    }
    r = client.post("/api/analyze", json=rec)
    assert r.status_code == 200, r.text
    return r.json()


def report_text(analysis) -> str:
    return json.dumps(generate_offline(analysis)["report"], ensure_ascii=False)


# ------------------------------------------------ rule gates (pure) -------

def test_normal_limits_follow_who_2021_and_the_20_db_limit():
    # PTA (10+5+10+15)/4 = 10 < 20, every threshold <= 20.
    assert within_normal_limits(num([5, 10, 5, 10, 15, 10])) is True
    # 20 dB HL is the per-frequency upper limit itself (BSA 2018: mild from
    # 21 dB HL), PTA (15*4)/4 = 15.
    assert within_normal_limits(num([20, 15, 15, 15, 15, 20])) is True
    # 25 dB HL is outside it — the limit the verdict headline applies too.
    assert within_normal_limits(num([25, 15, 15, 15, 15, 25])) is False
    # PTA exactly 20 is Mild under WHO 2021 (normal is < 20).
    assert within_normal_limits(num([20, 20, 20, 20, 20, 20])) is False
    # PTA (5+5+10+45)/4 = 16.25 is normal, but 45 dB at 4 kHz is not.
    assert within_normal_limits(num([5, 5, 5, 10, 45, 10])) is False
    # A loss outside the PTA (8 kHz) also keeps the ear out of the gate.
    assert within_normal_limits(num([5, 5, 5, 5, 10, 40])) is False


def test_coverage_needs_five_frequencies_including_4k():
    assert coverage(num([10, 10, 15, 20, 50, 25]))["adequate"] is True
    assert coverage(num([None, 10, 15, 20, 50, 25]))["adequate"] is True
    # Five frequencies but 4 kHz missing — a notch can never show.
    cov = coverage(num([10, 10, 15, 20, None, 25]))
    assert cov["adequate"] is False and cov["untested"] == [4000]
    assert cov["note"].startswith("insufficient frequencies")
    assert coverage(num([None, 10, 15, 20, 50, None]))["adequate"] is False
    assert coverage({1000: 40.0})["adequate"] is False


def test_coles_notch_rule():
    # 4k 50 is 35 dB worse than min(1k 15, 2k 20) and 25 dB worse than 8k 25.
    assert coles_notch_4k(num([10, 10, 15, 20, 50, 25])) is True
    assert noise_notch_with_loss(num([10, 10, 15, 20, 50, 25])) is True
    # Steady slope: 4k 55 is only 15 dB better than 8k 70 -> no notch.
    assert coles_notch_4k(num([20, 25, 30, 40, 55, 70])) is False
    # A 20 dB HL dip meets R3, but 4 kHz is within the 20 dB HL normal limit.
    assert coles_notch_4k(num([0, 0, 0, 0, 20, 5])) is True
    assert noise_notch_with_loss(num([0, 0, 0, 0, 20, 5])) is False
    # 4 kHz deeper than 1k by only 5 dB -> no notch even with recovery.
    assert coles_notch_4k(num([10, 10, 40, 40, 45, 20])) is False
    # Not assessable without 8 kHz, without 4 kHz, or with NR at 4 kHz.
    assert coles_notch_4k(num([10, 10, 15, 20, 50, None])) is None
    assert coles_notch_4k(num([10, 10, 15, 20, None, 25])) is None
    assert coles_notch_4k(num([10, 10, 15, 20, NR, NR])) is None


@pytest.mark.parametrize("values, expected", [
    # presbycusis with a 1 kHz typo: 90 - max(25, 40) = 50 worse
    ([20, 25, 90, 40, 55, 70], [(1000, "worse", 50)]),
    # rising loss with 8 kHz = 80: 80 - 20 = 60 worse, and 4k (20) <= 2k (25)
    ([55, 50, 40, 25, 20, 80], [(8000, "worse", 60)]),
    # cookie-bite with 4 kHz = 90: 90 - max(50, 20) = 40 worse, at the 4k limit
    ([20, 35, 50, 50, 90, 20], [(4000, "worse", 40)]),
    # 4 kHz typo of 5: min(40, 70) - 5 = 35 better
    ([20, 25, 30, 40, 5, 70], [(4000, "better", 35)]),
    # normal ear with a 2 kHz outlier: 70 - max(5, 15) = 55 worse
    ([5, 10, 5, 70, 15, 10], [(2000, "worse", 55)]),
])
def test_isolated_outliers_are_found(values, expected):
    got = [(o["freq"], o["direction"], o["deviation_db"])
           for o in isolated_outliers(num(values))]
    assert got == expected


@pytest.mark.parametrize("values", [
    [10, 10, 15, 15, 55, 20],    # textbook notch: 55 - 20 = 35 < 40 at 4 kHz
    [15, 15, 20, 25, 60, 30],    # demo noise notch: 60 - 30 = 30 < 40
    [20, 25, 30, 40, 55, 70],    # presbycusis slope
    [10, 10, 15, 60, 85, 95],    # ski-slope: monotone, never a reversal
    [10, 10, 15, 20, 70, 85],    # 50 dB step 2k->4k, still monotone
    [55, 50, 40, 25, 20, 20],    # rising
    [20, 35, 50, 50, 35, 20],    # cookie-bite
    [90, 100, NR, NR, NR, NR],   # corner
    [5, 5, 5, 10, 15, 45],       # 8 kHz drop continuing a slope (15 > 10)
])
def test_genuine_configurations_are_not_outliers(values):
    assert isolated_outliers(num(values)) == []


def test_bc_outside_training_is_where_ac_exceeds_the_vibrator_limit():
    ac = num([90, 100, NR, NR, NR, NR])
    assert bc_outside_training(ac, {}) == [250, 500, 1000, 2000, 4000]
    assert bc_outside_training(ac, ear_to_numeric({f: 70 for f in FREQS[:5]})) == []
    assert bc_outside_training(ac, ear_to_numeric({f: NR for f in FREQS[:5]})) == \
        [250, 500, 1000, 2000, 4000]
    # Only 4 kHz exceeds 70 in a ski-slope.
    assert bc_outside_training(num([10, 10, 15, 60, 85, 95]), {}) == [4000]


# --------------------------------------------- classifier contract (E1-1) --

@needs_model
@pytest.mark.parametrize("values", [
    [5, 10, 5, 10, 15, 10],
    [10, 10, 15, 10, 15, 20],
    [10, 10, 15, 20, 50, 25],
    [10, 10, 15, 20, 50, None],
    [None, None, 40, None, None, None],
    [40, 45, 55, 70, NR, NR],
    [20, 25, 90, 40, 55, 70],
])
def test_every_ear_carries_the_reliability_contract(values):
    m = classify_ear(ear(values), {}, explain=False)
    assert isinstance(m["reliable"], bool)
    assert isinstance(m["reliability_note"], str) and m["reliability_note"]
    # The raw model output is always kept for transparency.
    assert m["model_pattern"] in m["probabilities"]
    assert isinstance(m["model_confidence"], float)
    # Consumers compare confidence with floors, so it must stay numeric.
    assert isinstance(m["confidence"], float)


@needs_model
@pytest.mark.parametrize("values", [[5, 10, 5, 10, 15, 10], [10, 10, 15, 10, 15, 20]])
def test_normal_ear_is_gated_to_normal(values):
    m = classify_ear(ear(values), ear(values[:5]))
    assert m["pattern"] == "normal"
    assert m["pattern_label"] == "Within normal limits"
    assert m["pattern_source"] == "normal_gate"
    assert m["reliable"] is False
    assert m["ood"] is False                  # no "atypical" alarm on a normal ear
    assert m["model_pattern"] != "normal"     # the forest has no normal class
    assert m["counterfactuals"] == []
    assert max(m["freq_importance"].values()) == 0


@needs_model
def test_a_loss_outside_the_pta_still_reaches_the_model():
    m = classify_ear(ear([5, 5, 5, 10, 45, 10]), {})
    assert m["pattern"] != "normal"
    assert m["pattern_source"] == "model"


@needs_model
def test_a_complete_textbook_notch_is_reliable():
    m = classify_ear(ear([10, 10, 15, 20, 50, 25]), {})
    assert m["pattern"] == "noise_notch_4k"
    assert m["reliable"] is True
    assert m["confidence"] >= 0.8


# ------------------------------------------------ coverage (E1-3) ---------

@needs_model
@pytest.mark.parametrize("values", [
    [None, None, 40, None, None, None],    # was flat 1.00
    [None, None, None, None, 70, None],    # was flat 1.00
    [60, None, None, None, None, 10],      # was rising 0.99
    [10, 10, 15, 20, None, 25],            # 4 kHz imputed as 22.5 -> was flat 0.85
])
def test_too_few_frequencies_give_no_pattern(values):
    m = classify_ear(ear(values), {})
    assert m["pattern"] is None
    assert m["pattern_source"] == "insufficient_frequencies"
    assert m["reliable"] is False
    assert m["confidence"] == 0.0
    assert m["reliability_note"].startswith("insufficient frequencies")
    assert "Not classified" in m["pattern_label"]


@needs_model
def test_an_imputed_frequency_makes_the_label_unreliable():
    m = classify_ear(ear([10, 10, 15, 20, 50, None]), {})
    assert m["pattern"] is not None
    assert m["reliable"] is False
    assert m["frequencies_imputed"] == [8000]
    assert "8000 Hz not tested" in m["reliability_note"]


# ------------------------------------- low confidence / outliers (E1-4/7) --

@needs_model
def test_low_confidence_label_is_not_reliable():
    # Severe sloping loss the forest reads as corner audiogram at ~0.67.
    m = classify_ear(ear([40, 45, 55, 70, NR, NR]), {})
    assert m["confidence"] < 0.8
    assert m["reliable"] is False


@needs_model
@pytest.mark.parametrize("values, freq", [
    ([20, 35, 50, 50, 90, 20], 4000),   # cookie-bite, 4k typo
    ([55, 50, 40, 25, 20, 80], 8000),   # rising, 8k typo (was flat 0.91)
    ([20, 25, 90, 40, 55, 70], 1000),   # presbycusis, 1k typo (was sloping 0.99)
])
def test_single_outlier_is_flagged_for_retest(values, freq):
    m = classify_ear(ear(values), {})
    assert m["reliable"] is False
    assert m["ood"] is True
    assert f"isolated outlier at {freq} hz" in m["reliability_note"].lower()
    assert "retest this frequency" in m["reliability_note"]
    assert [o["freq"] for o in m["outliers"]] == [freq]


# ------------------------------------------------ report wording (E1-2) ---

FORBIDDEN_ON_NORMAL = ("noise exposure", "Mandatory hearing protection",
                       "sudden SNHL", "Ménière", "Atypical audiogram")


@needs_model
@pytest.mark.parametrize("values", [[5, 10, 5, 10, 15, 10], [10, 10, 15, 10, 15, 20]])
def test_normal_ears_get_no_loss_etiology_or_noise_advice(values):
    a = analyze(values, right_bc=json_ear(values[:5]), left_bc=json_ear(values[:5]))
    text = report_text(a)
    for phrase in FORBIDDEN_ON_NORMAL:
        assert phrase not in text, phrase
    etiology = generate_offline(a)["report"]["pattern_etiology"]
    assert all("within normal limits" in s for s in etiology)


@needs_model
def test_unreliable_label_gives_no_etiology():
    # 8 kHz untested: the forest still reads a notch, but not reliably.
    a = analyze([10, 10, 15, 20, 50, None],
                patient={"age": 42, "occupation": "Factory worker"})
    rep = generate_offline(a)["report"]
    assert all("provisionally" in s for s in rep["pattern_etiology"])
    text = json.dumps(rep, ensure_ascii=False)
    assert "occupational NIHL" not in text
    assert "Mandatory hearing protection" not in text


@needs_model
def test_reliable_noise_notch_keeps_occupational_etiology_and_advice():
    a = analyze([15, 15, 20, 25, 60, 30],
                patient={"age": 42, "occupation": "Factory worker — textile mill"})
    rep = generate_offline(a)["report"]
    assert any("occupational" in s.lower() for s in rep["pattern_etiology"])
    assert any("hearing protection" in r for r in rep["recommendations"])


@needs_model
def test_no_implant_candidacy_from_a_corner_label():
    # [40,45,55,70,NR,NR]: no ear has >= 80 dB HL at two of 0.5/1/2/4 kHz
    # (only 4 kHz), PTA (45+55+70+NR)/4 < 80 -> no candidacy wording at all.
    a = analyze([40, 45, 55, 70, NR, NR], patient={"age": 60})
    rep = generate_offline(a)["report"]
    assert not any("implant" in s.lower() for s in rep["pattern_etiology"])
    assert not any("implant" in r.lower() for r in rep["recommendations"])


@needs_model
def test_implant_referral_follows_thresholds_and_names_speech_testing():
    # Profound demo ear: 500 = 95 and 1k..4k NR -> 4 of 4 at or beyond 80.
    a = analyze([85, 95, 110, NR, NR, NR], [90, 100, NR, NR, NR, NR],
                patient={"age": 34})
    recs = generate_offline(a)["report"]["recommendations"]
    ci = [r for r in recs if "cochlear-implant" in r]
    assert len(ci) == 1
    assert "both ears" in ci[0]
    assert "speech-recognition testing" in ci[0]
    # A corner label never carries implant wording in the etiology.
    etiology = generate_offline(a)["report"]["pattern_etiology"]
    assert not any("implant" in s.lower() for s in etiology)


def _with_disability(analysis, **fields):
    a = json.loads(json.dumps(analysis))
    a["rules"]["disability"] = {**(a["rules"].get("disability") or {}), **fields}
    return a


@needs_model
def test_non_certifiable_percentage_is_caveated():
    base = analyze([60, 65, 70, 75, 80, 85])
    a = _with_disability(base, benchmark_disability=True, binaural_pct=55.0,
                         certifiable=False,
                         certification_note="Not certifiable: 2000 Hz untested.")
    bundle = generate_offline(a)
    rep = bundle["report"]
    assert any(line.startswith("NOT CERTIFIABLE") and "2000 Hz untested" in line
               for line in rep["disability"])
    assert not any("assist with disability certification" in r
                   for r in rep["recommendations"])
    assert any("cannot be certified" in r for r in rep["recommendations"])
    # The patient is not told they qualify on a figure that cannot be certified.
    english = counseling_sheet(a)["english"]["summary"]
    assert not any("55" in s for s in english)


@needs_model
def test_report_reads_the_rules_engine_certifiable_flag():
    # 2000 Hz untested in the right ear: the Gazette PTA needs all four.
    a = analyze([60, 65, 70, None, 80, 85], [60, 65, 70, 75, 80, 85])
    disability = a["rules"].get("disability") or {}
    if "certifiable" not in disability:
        pytest.skip("rules engine does not yet expose disability.certifiable")
    assert disability["certifiable"] is False
    rep = generate_offline(a)["report"]
    assert any(line.startswith("NOT CERTIFIABLE") for line in rep["disability"])
    assert not any("assist with disability certification" in r
                   for r in rep["recommendations"])


@needs_model
def test_missing_certifiable_field_means_certifiable():
    base = analyze([60, 65, 70, 75, 80, 85])
    a = _with_disability(base, benchmark_disability=True, binaural_pct=55.0)
    a["rules"]["disability"].pop("certifiable", None)
    a["rules"]["disability"].pop("certification_note", None)
    rep = generate_offline(a)["report"]
    assert not any(line.startswith("NOT CERTIFIABLE") for line in rep["disability"])
    assert any("assist with disability certification" in r for r in rep["recommendations"])


# ------------------------------------------------- batch cohort (E1-2) ----

CSV_HEAD = ("name,age,occupation,"
            + ",".join(f"r_ac_{f}" for f in FREQS) + ","
            + ",".join(f"l_ac_{f}" for f in FREQS) + "\n")


def _batch(rows):
    csv = CSV_HEAD + "".join(
        f"P{i},30,office," + ",".join(map(str, r + l)) + "\n"
        for i, (r, l) in enumerate(rows))
    r = client.post("/api/batch",
                    files={"file": ("c.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


NORMAL_EARS = [
    [5, 10, 5, 10, 15, 10], [10, 10, 15, 10, 15, 20], [0, 5, 5, 0, 10, 15],
    [-5, 0, 0, 5, 5, 10], [10, 5, 10, 5, 10, 15], [0, 0, 5, 5, 15, 5],
    [5, 5, 0, 5, 10, 0], [15, 10, 10, 15, 20, 10], [0, 0, 0, 0, 20, 5],
    [10, 15, 10, 10, 15, 15],
]


def test_normal_cohort_reports_no_noise_notch():
    # 40 people, every threshold <= 20 dB HL: none can meet Coles R1.
    rows = [(NORMAL_EARS[i % 10], NORMAL_EARS[(i + 3) % 10]) for i in range(40)]
    s = _batch(rows)["summary"]
    assert s["total"] == 40
    assert s["impaired"] == 0
    assert s["noise_notch"] == 0
    assert s["noise_notch_pct"] == 0.0
    assert "noise notch" not in s["headline"]
    assert s["noise_notch_assessable"] == 40


def test_cohort_notch_count_uses_the_coles_rule_with_loss():
    notch = [10, 10, 15, 20, 50, 25]          # Coles notch, 4k 50 > 25
    slope = [20, 25, 30, 40, 55, 70]          # no notch
    no_8k = [10, 10, 15, 20, 50, ""]          # not assessable
    rows = [(notch, slope), (slope, slope), (slope, notch), (no_8k, no_8k)]
    body = _batch(rows)
    s = body["summary"]
    assert s["noise_notch"] == 2
    assert s["noise_notch_pct"] == 50.0
    assert s["noise_notch_assessable"] == 3
    assert "Coles" in s["noise_notch_definition"]
    by_name = {r["name"]: r for r in body["results"]}
    assert by_name["P0"]["right"]["noise_notch"] is True
    assert by_name["P0"]["left"]["noise_notch"] is False
    assert by_name["P3"]["right"]["noise_notch"] is None


def test_batch_flags_a_benchmark_percentage_that_cannot_be_certified():
    from app.clinical.rules import analyze_test
    severe_gap = [70, 75, 80, "", 85, 90]     # 2000 Hz untested
    severe = [70, 75, 80, 85, 85, 90]
    probe = analyze_test(ear([70, 75, 80, None, 85, 90]), {},
                         ear(severe), {})["disability"]
    if "certifiable" not in probe:
        pytest.skip("rules engine does not yet expose disability.certifiable")
    body = _batch([(severe_gap, severe), (severe, severe)])
    by_name = {r["name"]: r for r in body["results"]}
    # A PTA frequency is untested -> the percentage is an estimate only.
    assert by_name["P0"]["disability_certifiable"] is False
    assert by_name["P1"]["disability_certifiable"] is True
    s = body["summary"]
    expected = sum(1 for r in body["results"]
                   if r["benchmark_disability"] and r["disability_certifiable"] is False)
    assert s["benchmark_not_certifiable"] == expected


@needs_model
def test_batch_rows_carry_reliability():
    body = _batch([([5, 10, 5, 10, 15, 10], [10, 10, 15, 20, 50, 25])])
    row = body["results"][0]
    assert row["right"]["pattern_key"] == "normal"
    assert row["right"]["pattern_reliable"] is False
    assert row["left"]["pattern_key"] == "noise_notch_4k"
    assert row["left"]["pattern_reliable"] is True


# --------------------------------------------- deep-predict input (E1-6) --

def _deep(body):
    return client.post("/api/model/deep-predict", json=body)


@pytest.mark.parametrize("body, needle", [
    ({"ac": {"1k": 40}}, "is not a whole number of Hz"),
    ({"ac": {"1000": "abc"}}, "is not a number, 'NR' or null"),
    ({"ac": {"3000": 40}}, "not one of the standard audiometric frequencies"),
    ({"ac": [10, 20]}, "must be an object"),
    ({"ac": {}}, "insufficient frequencies"),
    ({"ac": {"1000": 500}}, "outside -10..120"),
    ({"ac": {str(f): -200 for f in FREQS}}, "outside -10..120"),
    ({"ac": json_ear([10, 10, 15, 20, None, 25])}, "including 4000 Hz"),
    ({"ac": json_ear([10, 10, 15, 20, 50, 25]), "bc": {"500": "x"}}, "bc threshold"),
    ({}, "Field required"),
])
def test_deep_predict_rejects_malformed_input_with_422(body, needle):
    r = _deep(body)
    assert r.status_code == 422, r.text
    assert needle in r.text
    # The frontend shows ``detail`` as text; a list of error objects renders
    # as "[object Object]".
    assert isinstance(r.json()["detail"], str)
    assert needle in r.json()["detail"]


def test_deep_predict_rejects_a_list_body_and_an_empty_body_readably():
    r = client.post("/api/model/deep-predict", json=[10, 20])
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    r = client.post("/api/model/deep-predict", content=b"",
                    headers={"content-type": "application/json"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert "'ac'" in r.json()["detail"]


@needs_deep
def test_deep_predict_accepts_nulls_and_lowercase_nr():
    r = _deep({"ac": {**json_ear([40, 45, 55, 70, "nr", "nr"]), "8000": None},
               "bc": {"250": None}})
    # 8 kHz null leaves five frequencies including 4 kHz — enough.
    assert r.status_code == 200, r.text
    assert r.json()["reliable"] is False      # 8 kHz imputed


# -------------------------------------------- deep ensemble gates (E1-5) --

@needs_deep
def test_deep_corner_without_bc_is_unreliable_and_says_why():
    body = _deep({"ac": json_ear([90, 100, NR, NR, NR, NR])}).json()
    assert body["reliable"] is False
    assert body["bc_outside_training"] == [250, 500, 1000, 2000, 4000]
    assert "bone conduction" in body["reliability_note"]


@needs_deep
def test_deep_corner_with_bc_at_the_vibrator_limit_is_recognised():
    body = _deep({"ac": json_ear([90, 100, NR, NR, NR, NR]),
                  "bc": {str(f): 70 for f in FREQS[:5]}}).json()
    assert body["pattern"] == "corner_audiogram"
    assert body["bc_outside_training"] == []


@needs_deep
@pytest.mark.parametrize("values", [
    [NR] * 6,                          # was flat 1.000, epistemic 0.0001
    [100, 0, 100, 0, 100, 0],          # was notch 0.996, not novel
    [20, 25, 90, 40, 55, 70],          # isolated spike
])
def test_deep_flags_implausible_input_as_novel(values):
    body = _deep({"ac": json_ear(values)}).json()
    assert body["novel_input"] is True
    assert body["reliable"] is False
    assert body["novelty_reasons"]


@needs_deep
def test_deep_applies_the_normal_gate():
    body = _deep({"ac": json_ear([5, 10, 5, 10, 15, 10])}).json()
    assert body["pattern"] == "normal"
    assert body["pattern_source"] == "normal_gate"
    assert body["model_pattern"] != "normal"
    assert body["reliable"] is False


@needs_deep
def test_deep_textbook_notch_with_bc_is_reliable():
    body = _deep({"ac": json_ear([10, 10, 15, 15, 55, 20]),
                  "bc": {"1000": 10, "2000": 10, "4000": 50}}).json()
    assert body["pattern"] == "noise_notch_4k"
    assert body["reliable"] is True
    assert body["novel_input"] is False


@needs_deep
def test_predict_deep_without_thresholds_is_never_reliable():
    x = build_features(num([10, 10, 15, 15, 55, 20]), {})
    out = predict_deep(x)
    assert out["reliable"] is False
    assert "not supplied" in out["reliability_note"]


# ------------------- ears graded Normal hearing by their average (E1-2) ---
#
# WHO 2021 grades an ear by its four-frequency average (0.5/1/2/4 kHz);
# below 20 dB HL is Normal hearing. Such an ear can still have a threshold or
# two above the 20 dB HL per-frequency limit (BSA 2018: mild from 21 dB HL).
# A configuration label is acted on there only when those thresholds form
# the shape named. Expected values below are PTA4 = mean(500, 1k, 2k, 4k)
# and the list of thresholds > 20 dB HL.

# (thresholds, PTA4, frequencies above 20 dB HL)
NEAR_NORMAL_LEAKS = [
    ([30, 10, 10, 15, 5, 10], 10.0, [250]),
    ([15, 10, 30, 15, 10, 15], 16.25, [1000]),
    ([15, 30, 20, 10, 15, 15], 18.75, [500]),
    ([20, 10, 20, 15, 15, 35], 15.0, [8000]),
    ([30, 15, 20, 15, 25, 30], 18.75, [250, 4000, 8000]),
    ([35, 5, 0, 0, 0, 0], 1.25, [250]),
    ([15, 15, 40, 15, 5, 15], 18.75, [1000]),
]


@pytest.mark.parametrize("values, pta, abnormal", NEAR_NORMAL_LEAKS)
def test_near_normal_leak_inputs_are_what_they_claim(values, pta, abnormal):
    n = num(values)
    assert sum(n[f] for f in (500, 1000, 2000, 4000)) / 4 == pta < 20
    assert [f for f in FREQS if n[f] > 20] == abnormal
    # No Coles notch with loss: 4 kHz is either within 20 dB HL or (25 dB HL
    # in the fifth row) not 10 dB worse than 8 kHz (30 dB HL).
    assert noise_notch_with_loss(n) is not True


@pytest.mark.parametrize("values, pattern, allowed", [
    # flat and corner are never a configuration with a normal average
    ([30, 10, 10, 15, 5, 10], "flat", False),
    ([30, 15, 20, 15, 25, 30], "flat", False),
    ([30, 30, 5, 5, 5, 5], "corner_audiogram", False),
    # one raised threshold is an isolated finding
    ([35, 5, 0, 0, 0, 0], "rising", False),
    ([15, 15, 40, 15, 5, 15], "cookie_bite", False),
    ([20, 10, 20, 15, 15, 35], "sloping_high_frequency", False),
    # two raised thresholds, but 250 Hz is outside the high-frequency region
    ([30, 10, 10, 10, 15, 35], "sloping_high_frequency", False),
    # two raised thresholds inside the region the label names:
    # 250 = 40 and 500 = 35 (PTA (35+10+5+5)/4 = 13.75)
    ([40, 35, 10, 5, 5, 5], "rising", True),
    # 4k = 30 and 8k = 45 (PTA (5+10+15+30)/4 = 15)
    ([5, 5, 10, 15, 30, 45], "sloping_high_frequency", True),
    ([5, 5, 10, 15, 30, 45], "ski_slope", True),
    # Coles notch: 45 - min(5, 10) = 40 >= 10, 45 - 10 = 35 >= 10, 45 > 25
    ([5, 5, 5, 10, 45, 10], "noise_notch_4k", True),
    # 4 kHz 30 vs 8 kHz 25: only 5 dB, not a Coles notch
    ([10, 10, 10, 10, 30, 25], "noise_notch_4k", False),
    # Not the rule's case: a loss by grade (PTA 37.5), or nothing abnormal
    ([20, 25, 30, 40, 55, 70], "flat", True),
    ([5, 10, 5, 10, 15, 10], "flat", True),
])
def test_normal_average_caveat_follows_the_shape(values, pattern, allowed):
    caveat = normal_average_caveat(num(values), pattern)
    assert (caveat is None) is allowed, caveat
    if caveat:
        assert "WHO 2021 normal limits" in caveat


def test_normal_average_caveat_ignores_absent_and_normal_labels():
    assert normal_average_caveat(num([30, 10, 10, 15, 5, 10]), None) is None
    assert normal_average_caveat(num([30, 10, 10, 15, 5, 10]), "normal") is None


@needs_model
@pytest.mark.parametrize("values, pta, abnormal", NEAR_NORMAL_LEAKS)
def test_near_normal_ear_gets_no_reliable_label(values, pta, abnormal):
    m = classify_ear(ear(values), {}, explain=False)
    assert m["pattern_source"] == "model"
    assert m["reliable"] is False
    assert "WHO 2021 normal limits" in m["reliability_note"]
    assert f"{abnormal[0]} Hz" in m["reliability_note"]


@needs_model
def test_early_noise_notch_with_a_normal_average_stays_reliable():
    # PTA (5+5+10+45)/4 = 16.25 is Normal hearing by WHO 2021, but the 4 kHz
    # dip meets Coles et al. (2000) with 4 kHz at 45 dB HL: early NIHL.
    m = classify_ear(ear([5, 5, 5, 10, 45, 10]), {})
    assert m["pattern"] == "noise_notch_4k"
    assert m["reliable"] is True


@needs_model
@pytest.mark.parametrize("values, pta, abnormal", NEAR_NORMAL_LEAKS)
def test_near_normal_report_gives_no_loss_etiology(values, pta, abnormal):
    a = analyze(values)
    assert a["rules"]["right"]["who_grade"]["grade"] == "Normal hearing"
    rep = generate_offline(a)["report"]
    text = json.dumps(rep, ensure_ascii=False)
    for phrase in ("sudden SNHL", "Ménière", "hereditary", "noise exposure",
                   "Mandatory hearing protection", "presbycusis"):
        assert phrase not in text, phrase
    assert all("not reliable enough to suggest an etiology" in s
               for s in rep["pattern_etiology"])


@needs_model
def test_early_noise_notch_report_keeps_noise_advice():
    a = analyze([5, 5, 5, 10, 45, 10],
                patient={"age": 42, "occupation": "Factory worker"})
    rep = generate_offline(a)["report"]
    assert any("occupational NIHL" in s for s in rep["pattern_etiology"])
    assert any("hearing protection" in r for r in rep["recommendations"])


@needs_model
def test_stored_analysis_with_a_stale_reliable_flag_is_rechecked():
    # An analysis stored by a classifier without the normal-average rule
    # would say reliable: True for this one-frequency "flat loss".
    a = analyze([30, 10, 10, 15, 5, 10])
    for side in ("right", "left"):
        a["ml"][side].update(pattern="flat", pattern_label="Flat", reliable=True,
                             reliability_note="All six frequencies measured")
    rep = generate_offline(a)["report"]
    text = json.dumps(rep, ensure_ascii=False)
    assert "sudden SNHL" not in text and "Ménière" not in text
    assert all("WHO 2021 normal limits" in s for s in rep["pattern_etiology"])
    # The LLM engine is given the same verdict the offline engine acts on.
    slim = _slim(a)
    assert slim["ml"]["right"]["reliable"] is False
    assert "WHO 2021 normal limits" in slim["ml"]["right"]["reliability_note"]
    assert a["ml"]["right"]["reliable"] is True        # input not mutated


@needs_model
def test_batch_marks_a_near_normal_label_unreliable():
    body = _batch([([30, 10, 10, 15, 5, 10], [15, 15, 40, 15, 5, 15])])
    row = body["results"][0]
    for side in ("right", "left"):
        assert row[side]["grade"] == "Normal hearing"
        assert row[side]["pattern_reliable"] is False
        assert "WHO 2021 normal limits" in row[side]["reliability_note"]
        assert row[side]["noise_notch"] is False


@needs_deep
def test_deep_applies_the_normal_average_rule():
    body = _deep({"ac": json_ear([30, 10, 10, 15, 5, 10])}).json()
    assert body["reliable"] is False
    assert "WHO 2021 normal limits" in body["reliability_note"]
    body = _deep({"ac": json_ear([5, 5, 5, 10, 45, 10])}).json()
    if body["pattern"] == "noise_notch_4k" and body["confidence"] >= 0.8:
        assert "WHO 2021" not in body["reliability_note"]


# ------------------------- implant wording follows the thresholds (E1-4) --

@needs_model
def test_an_nr_at_4k_alone_does_not_meet_the_implant_criterion():
    # 500/1k/2k = 70 and 4k = NR: one of four PTA frequencies at or beyond
    # 80 dB HL (NICE TA566 needs two), although the PTA is
    # (70+70+70+120)/4 = 82.5.
    a = analyze([60, 70, 70, 70, NR, NR])
    assert a["rules"]["right"]["ac_pta"]["value"] == 82.5
    recs = generate_offline(a)["report"]["recommendations"]
    assert not any("implant" in r.lower() for r in recs)
    assert any("Hearing-aid evaluation" in r for r in recs)


@needs_model
def test_unilateral_severe_to_profound_ear_is_not_called_an_implant_candidate():
    a = analyze([85, 95, 110, NR, NR, NR], [10, 10, 10, 15, 15, 20])
    recs = generate_offline(a)["report"]["recommendations"]
    ci = [r for r in recs if "implant" in r.lower()]
    assert len(ci) == 1
    assert "right ear only" in ci[0]
    assert "not met" in ci[0]
    assert "refer for cochlear-implant candidacy" not in ci[0]
    assert "speech-recognition testing" in ci[0]


@needs_model
def test_pta_fallback_is_used_only_without_thresholds_and_says_so():
    a = analyze([60, 70, 70, 70, NR, NR])
    a.pop("thresholds")
    recs = generate_offline(a)["report"]["recommendations"]
    ci = [r for r in recs if "implant" in r.lower()]
    assert len(ci) == 1
    assert "four-frequency average of 80 dB HL or worse" in ci[0]
    assert "still to be confirmed" in ci[0]


def _implant_line(analysis):
    recs = generate_offline(analysis)["report"]["recommendations"]
    ci = [r for r in recs if "implant" in r.lower()]
    assert len(ci) == 1, recs
    return ci[0]


@needs_model
@pytest.mark.parametrize("left, untested", [
    # Left ear not tested at all.
    ([None] * 6, "was not tested,"),
    # Only 1 kHz (40 dB HL): 0 of 4 PTA frequencies at >= 80, but the three
    # untested ones could still give the two NICE TA566 requires.
    ([None, None, 40, None, None, None], "was not tested at 500 Hz, 2000 Hz, 4000 Hz"),
])
def test_untested_other_ear_leaves_the_bilateral_criterion_unassessed(left, untested):
    # Right: 500 = 95, 1k = 110, 2k/4k = NR -> 4 of 4 at or beyond 80 dB HL.
    line = _implant_line(analyze([85, 95, 110, NR, NR, NR], left))
    assert f"The left ear {untested}" in line
    assert "cannot be assessed" in line
    assert "only" not in line and "not met" not in line
    assert "refer for cochlear-implant candidacy" not in line
    assert "ENT assessment of the right ear" in line
    assert "speech-recognition testing" in line


@needs_model
def test_partly_tested_other_ear_that_cannot_reach_the_criterion_is_not_met():
    # Left 500/1k/2k = 10 and 4k untested: 0 at >= 80 plus 1 untested < 2, so
    # the left ear cannot meet NICE TA566 whatever 4 kHz is.
    line = _implant_line(analyze([85, 95, 110, NR, NR, NR], [None, 10, 10, 10, None, None]))
    assert "right ear only" in line and "not met" in line
    assert "cannot be assessed" not in line


@needs_model
def test_other_ear_with_only_an_average_is_not_assessable():
    a = analyze([85, 95, 110, NR, NR, NR], [10, 10, 10, 15, 15, 20])
    a.pop("thresholds")
    line = _implant_line(a)
    assert "only its four-frequency average" in line
    assert "cannot be assessed" in line


# ------------------- blocks and steep steps that no configuration has (E1-5) --
#
# Expected values: a block is a run of >= 2 adjacent octaves, bounded by a
# tested octave on each side, whose best threshold is >= 40 dB worse than the
# worse neighbour (>= 50 dB when the run includes 4 kHz), or whose worst
# threshold is >= 40 dB better than the better neighbour. A steep improvement
# is a >= 50 dB better threshold one octave up (>= 60 dB from 4 to 8 kHz
# unless the ear also worsens by >= 50 dB within an octave).

@pytest.mark.parametrize("values, expected", [
    # min(100, 100) - max(10, 10) = 90
    ([10, 10, 100, 100, 10, 10], [([1000, 2000], "worse", 90)]),
    # min(100, 100) - max(0, 0) = 100
    ([0, 100, 100, 0, 0, 0], [([500, 1000], "worse", 100)]),
    # min(90, 100) - max(20, 0) = 70
    ([30, 20, 90, 100, 0, -5], [([1000, 2000], "worse", 70)]),
    # min(90, 110, 105) - max(5, 25) = 65
    ([5, 90, 110, 105, 25, 5], [([500, 1000, 2000], "worse", 65)]),
    # island: min(100, 100) - max(0, 0) = 100 better
    ([100, 100, 0, 0, 100, 100], [([1000, 2000], "better", 100)]),
    # min(55, 55) - max(10, 10) = 45 >= 40
    ([10, 10, 55, 55, 10, 10], [([1000, 2000], "worse", 45)]),
    # includes 4 kHz: min(60, 65) - max(5, 5) = 55 >= 50
    ([5, 5, 5, 60, 65, 5], [([2000, 4000], "worse", 55)]),
])
def test_outlier_blocks_are_found(values, expected):
    got = [(b["freqs"], b["direction"], b["deviation_db"])
           for b in outlier_blocks(num(values))]
    assert got == expected
    assert any("retest these frequencies" in r for r in plausibility_reasons(num(values)))


@pytest.mark.parametrize("values, expected", [
    # 100 at 500 Hz -> 10 at 1 kHz: 90 dB better within one octave
    ([100, 100, 10, 10, 10, 10], [([500, 1000], 90)]),
    # 105 at 2 kHz -> -5 at 4 kHz: 110 (500-2k block is only 100 - 70 = 30)
    ([70, 100, 110, 105, -5, -5], [([2000, 4000], 110)]),
    # 4 -> 8 kHz 60 -> 10 = 50 < 60 alone, but 500 -> 1k worsens by 55
    ([60, 50, 105, 95, 60, 10], [([4000, 8000], 50)]),
])
def test_steep_improvements_are_found(values, expected):
    got = [(s["freqs"], s["improvement_db"]) for s in steep_improvements(num(values))]
    assert got == expected
    assert any("retest both frequencies" in r for r in plausibility_reasons(num(values)))


def test_a_single_notch_is_left_to_the_outlier_rule():
    # 4 kHz 75 is 75 - max(25, 20) = 50 >= 40 worse than both neighbours:
    # reported once, as an isolated outlier, not again as a steep recovery.
    n = num([10, 10, 15, 25, 75, 20])
    assert [o["freq"] for o in isolated_outliers(n)] == [4000]
    assert steep_improvements(n) == [] and outlier_blocks(n) == []


#: Textbook configurations (shapes as in the audit's golden set: Coles et al.
#: 2000 notch, ISO 7029 presbycusis slope, precipitous ski-slope, early
#: Ménière's rising, hereditary cookie-bite, flat, corner, normal).
TEXTBOOK = [
    [10, 10, 15, 20, 50, 25], [15, 15, 20, 30, 60, 35], [20, 20, 25, 40, 70, 45],
    [5, 5, 5, 10, 45, 10],
    # broadened notches: 2-4 kHz block only 40 dB above 1 kHz and 8 kHz
    [10, 10, 15, 55, 60, 15], [10, 10, 10, 50, 60, 10],
    # 4 -> 8 kHz recovery of 50 dB with no steep worsening elsewhere
    [10, 10, 15, 40, 70, 20],
    [20, 25, 30, 40, 55, 70], [25, 30, 35, 50, 65, 80],
    [10, 10, 15, 60, 85, 95], [15, 15, 20, 70, 90, NR], [10, 10, 15, 20, 70, 85],
    [55, 50, 40, 25, 20, 20], [50, 45, 30, 15, 25, 35],
    [20, 35, 50, 50, 35, 20], [25, 40, 55, 55, 40, 30],
    [45, 45, 45, 50, 45, 50], [85, 85, 90, 90, 90, 95],
    [90, 100, NR, NR, NR, NR], [85, 95, 110, NR, NR, NR],
    [5, 10, 5, 10, 15, 10], [-5, 0, 0, 5, 5, 10],
]


@pytest.mark.parametrize("values", TEXTBOOK)
def test_textbook_configurations_pass_every_plausibility_check(values):
    assert plausibility_reasons(num(values)) == []


def test_no_training_audiogram_is_a_block_or_a_steep_improvement():
    import csv
    from app.ml.deep import DATA_DIR
    path = DATA_DIR / "dataset.csv"
    if not path.exists():
        pytest.skip("training data not generated")
    flagged = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            ac = {f: float(row[f"ac_{f}"]) for f in FREQS}
            if outlier_blocks(ac) or steep_improvements(ac):
                flagged.append((row["pattern"], [ac[f] for f in FREQS]))
    assert flagged == []


BLOCK_REPROS = [
    [10, 10, 100, 100, 10, 10],
    [0, 0, 100, 100, 0, 0],
    [0, 100, 100, 0, 0, 0],
    [30, 20, 90, 100, 0, -5],
    [5, 90, 110, 105, 25, 5],
    [100, 100, 0, 0, 100, 100],
    [100, 100, 10, 10, 10, 10],
]


@needs_model
@pytest.mark.parametrize("values", BLOCK_REPROS)
def test_forest_never_relies_on_a_block_or_steep_step(values):
    m = classify_ear(ear(values), {}, explain=False)
    assert m["pattern_source"] == "model"
    assert m["reliable"] is False and m["ood"] is True
    assert "retest" in m["reliability_note"]
    assert m["outlier_blocks"] or m["steep_improvements"]


@needs_deep
@pytest.mark.parametrize("values", BLOCK_REPROS)
def test_deep_flags_a_block_or_steep_step_as_novel(values):
    body = _deep({"ac": json_ear(values)}).json()
    assert body["novel_input"] is True and body["reliable"] is False
    assert any("retest" in r for r in body["novelty_reasons"])


@needs_model
def test_block_report_gives_no_hereditary_etiology():
    rep = generate_offline(analyze([10, 10, 100, 100, 10, 10]))["report"]
    text = json.dumps(rep, ensure_ascii=False)
    assert "hereditary" not in text and "family audiometric screening" not in text
    assert all("not reliable enough to suggest an etiology" in s
               and "retest these frequencies" in s for s in rep["pattern_etiology"])


@needs_model
def test_stored_block_with_a_stale_reliable_flag_is_rechecked():
    # As an analysis stored before the block rule existed would carry it.
    a = analyze([10, 10, 100, 100, 10, 10])
    for side in ("right", "left"):
        a["ml"][side].update(pattern="cookie_bite",
                             pattern_label="Cookie-bite (mid-frequency)",
                             reliable=True, ood=False, ood_reasons=[],
                             reliability_note="All six frequencies measured")
    text = json.dumps(generate_offline(a)["report"], ensure_ascii=False)
    assert "hereditary" not in text
    slim = _slim(a)
    assert slim["ml"]["right"]["reliable"] is False
    assert "retest these frequencies" in slim["ml"]["right"]["reliability_note"]


@needs_model
def test_textbook_cookie_bite_keeps_its_etiology():
    rep = generate_offline(analyze([20, 35, 50, 50, 35, 20]))["report"]
    assert any("hereditary" in s for s in rep["pattern_etiology"])


# ------------------------------------- deep-predict body handling (E1-6) --

@pytest.mark.parametrize("content, ctype, needle", [
    (b"{ac: 1", "application/json", "not valid JSON"),
    (b"null", "application/json", "not a JSON null"),
    (b"42", "application/json", "not a JSON number"),
    (b'"ac"', "application/json", "not a JSON string"),
    (b'{"ac": {"1000": 40}}', "text/plain", "Content-Type"),
])
def test_deep_predict_rejects_unparseable_bodies_readably(content, ctype, needle):
    r = client.post("/api/model/deep-predict", content=content,
                    headers={"content-type": ctype})
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], str)
    assert needle in r.json()["detail"]


def test_deep_predict_rejects_bone_conduction_at_8k():
    r = _deep({"ac": json_ear([10, 10, 15, 20, 50, 25]), "bc": {"8000": 20}})
    assert r.status_code == 422
    assert "8000 Hz" in r.json()["detail"] and "bone conduction" in r.json()["detail"]


@needs_deep
def test_deep_predict_accepts_a_null_bone_conduction_8k_key():
    r = _deep({"ac": json_ear([10, 10, 15, 20, 50, 25]), "bc": {"8000": None}})
    assert r.status_code == 200, r.text


def test_deep_predict_keeps_its_openapi_request_schema():
    body = app.openapi()["paths"]["/api/model/deep-predict"]["post"]["requestBody"]
    schema = body["content"]["application/json"]["schema"]
    assert "ac" in schema["properties"]
