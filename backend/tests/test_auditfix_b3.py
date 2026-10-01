"""Speech audiometry: the SRT comparator, one PTA for both endpoints, the SDT
gap messages, the rollover inequality and the word-recognition categories.

Every expected value is worked out by hand from the thresholds in the test,
not read back from the code.
"""
import pytest
from fastapi.testclient import TestClient

from app.clinical import speech_audiometry as S
from app.main import app

client = TestClient(app)


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


# A reverse-slope (rising) loss: poor lows, normal highs.
RISING = {250: 60, 500: 60, 1000: 50, 2000: 10, 4000: 10, 8000: 10}


def record(right, left=None):
    return {"patient": {"name": "T", "age": 40},
            "right": right, "left": left or {"ac": flat(20), "bc": flat(20)}}


# ======================================================= SRT comparator ==

def test_a_rising_loss_with_an_honest_srt_is_not_called_non_organic():
    """500/1000/2000 = 60/50/10. Three-frequency PTA = 120/3 = 40; Fletcher
    (best two: 50, 10) = 30. The 1000→2000 step is 40 dB > 20, so Fletcher is
    the comparator: 30 − 30 = 0 dB. The 500/1000 average (55) is not."""
    body = client.post("/api/speech/analyze",
                       json={"ac": RISING, "srt": 30}).json()
    srt = body["srt"]
    assert srt["pta_500_1000_2000"] == 40.0
    assert srt["pta_fletcher"] == 30.0
    assert srt["configuration"] == "rising"
    assert srt["comparator_basis"] == "fletcher"
    assert srt["comparator"] == 30.0
    assert srt["difference"] == 0.0
    assert srt["agrees"] is True
    assert srt["non_organic_suspected"] is False
    assert "non_organic" not in body["flags"]
    assert "Fletcher" in srt["message"]


def test_the_full_analysis_does_not_withhold_certification_for_a_rising_loss():
    rising_ear = {"ac": RISING, "bc": RISING, "srt": 30}
    body = client.post("/api/analyze", json=record(rising_ear)).json()
    titles = [a["title"] for a in body["safety"]["alerts"]]
    assert "Possible non-organic (functional) hearing loss" not in titles
    assert "Objective tests disagree with the pure tones" not in titles
    assert "non_organic" not in body["speech_audiometry"]["right"]["flags"]


def test_a_gradual_rise_with_an_srt_better_than_both_averages_is_flagged():
    """60/45/25: steps −15/−20, none over 20 dB. PTA3 = 130/3 = 43.3;
    Fletcher (45, 25) = 35. SRT 20 is 15 dB better than Fletcher and 23.3 dB
    better than PTA3 — better than both, and nothing steep to explain it."""
    result = S.srt_agreement({500: 60, 1000: 45, 2000: 25, 4000: 20}, 20)
    assert result["configuration"] == "gradual"
    assert result["comparator_basis"] == "fletcher"
    assert result["comparator"] == 35.0
    assert result["difference"] == 15.0
    assert result["non_organic_suspected"] is True
    assert result["agrees"] is False
    assert "exaggerated" in result["message"]


def test_a_steep_rise_with_an_srt_near_the_best_threshold_is_indeterminate():
    """RISING 60/50/10 has a −40 dB step at 1000→2000 Hz. SRT 15 is 15 dB
    better than Fletcher (30) and 25 dB better than PTA3 (40), but only 5 dB
    poorer than the best threshold (10 dB at 2000 Hz), which the SRT can
    follow in a precipitous configuration (Schoepflin 2012)."""
    result = S.srt_agreement(RISING, 15)
    assert result["agrees"] is None
    assert result["non_organic_suspected"] is False
    assert result["indeterminate_reason"] == "steep_configuration"
    assert result["comparator_basis"] == "best_threshold"
    assert result["comparator"] == 10.0
    assert result["best_threshold_freq"] == 2000
    assert result["difference"] == -5.0
    assert "neither confirm nor refute" in result["message"]


# The verifier's sloping and gentle-rising cases: steps of 20 dB or less, an
# SRT within 10 dB of the best-two average but more than 10 dB better than
# the three-frequency average. (ac, SRT, PTA3, Fletcher), averages by hand.
NEAR_FLETCHER = [
    ({500: 25, 1000: 40, 2000: 60, 4000: 70}, 30, 41.7, 32.5),   # 125/3
    ({500: 20, 1000: 30, 2000: 50, 4000: 65}, 20, 33.3, 25.0),   # 100/3
    ({500: 30, 1000: 45, 2000: 65, 4000: 75}, 35, 46.7, 37.5),   # 140/3
    ({500: 20, 1000: 40, 2000: 60, 4000: 75}, 25, 40.0, 30.0),
    ({500: 15, 1000: 25, 2000: 45, 4000: 60}, 15, 28.3, 20.0),   # 85/3
    ({500: 55, 1000: 40, 2000: 25, 4000: 20}, 25, 40.0, 32.5),   # rising
    ({500: 50, 1000: 30, 2000: 10, 4000: 10}, 15, 30.0, 20.0),   # rising
]


@pytest.mark.parametrize("ac,srt,pta3,fletcher", NEAR_FLETCHER)
def test_an_srt_near_fletchers_average_agrees_in_a_sloping_or_rising_loss(
        ac, srt, pta3, fletcher):
    """ASHA (1988): in a sloping loss agreement "may be better" with the
    best-two average. Against PTA3 alone each of these would be flagged."""
    result = S.srt_agreement(ac, srt)
    assert result["configuration"] == "gradual"
    assert result["pta_500_1000_2000"] == pta3
    assert result["pta_fletcher"] == fletcher
    assert pta3 - srt > 10
    assert result["agrees"] is True
    assert result["non_organic_suspected"] is False
    assert result["comparator_basis"] == "fletcher"
    assert result["difference"] == round(fletcher - srt, 1)


def test_the_full_analysis_does_not_withhold_certification_for_a_sloping_loss():
    """Both ears 25/40/60/70, masked, SRT 30: Fletcher (25+40)/2 = 32.5, so
    the SRT is 2.5 dB from it — no exaggeration on either ear."""
    ac = {250: 20, 500: 25, 1000: 40, 2000: 60, 4000: 70, 8000: 75}
    bc = {250: 20, 500: 25, 1000: 40, 2000: 60, 4000: 70}
    ear = {"ac": ac, "bc": bc, "srt": 30, "masked": True, "speech_masked": True}
    body = client.post("/api/analyze", json={
        "patient": {"name": "T", "age": 60}, "right": ear, "left": ear}).json()
    titles = [a["title"] for a in body["safety"]["alerts"]]
    assert "Possible non-organic (functional) hearing loss" not in titles
    assert "Objective tests disagree with the pure tones" not in titles
    for side in ("right", "left"):
        assert "non_organic" not in body["speech_audiometry"][side]["flags"]


@pytest.mark.parametrize("srt,non_organic", [(33, False), (32, True)])
def test_the_ten_db_boundary_is_measured_from_fletchers_average(srt, non_organic):
    """40/45/50: PTA3 45, Fletcher 42.5. SRT 33 is 9.5 dB better than
    Fletcher (agrees, though 12 dB better than PTA3); SRT 32 is 10.5 dB better
    than Fletcher and 13 dB better than PTA3 — better than both."""
    result = S.srt_agreement({500: 40, 1000: 45, 2000: 50, 4000: 55}, srt)
    assert result["non_organic_suspected"] is non_organic
    assert result["agrees"] is (not non_organic)


@pytest.mark.parametrize("hf,shape", [
    (50, "gradual"),    # 30/30/50: a step of exactly 20 is not > 20
    (55, "sloping"),    # 30/30/55: a step of 25 is
])
def test_a_steep_configuration_needs_an_adjacent_step_greater_than_20_db(hf, shape):
    assert S.speech_configuration({500: 30, 1000: 30, 2000: hf})["shape"] == shape


def test_the_best_threshold_exception_needs_a_steep_step():
    """SRT 15 on both. 20/40/60 (steps 20, 20 — gradual): Fletcher 30, so
    15 dB better than both averages — flagged. 20/45/60 (a 25 dB step):
    Fletcher 32.5, 17.5 dB better — but 5 dB from the best threshold (20 dB
    at 500 Hz), so indeterminate."""
    gradual = S.srt_agreement({500: 20, 1000: 40, 2000: 60}, 15)
    steep = S.srt_agreement({500: 20, 1000: 45, 2000: 60}, 15)
    assert gradual["non_organic_suspected"] is True
    assert steep["non_organic_suspected"] is False
    assert steep["agrees"] is None
    assert steep["indeterminate_reason"] == "steep_configuration"


@pytest.mark.parametrize("ac,srt", [
    # 20/70/90: Fletcher (20+70)/2 = 45, SRT 25 is 20 dB better; 5 dB poorer
    # than the best threshold, 20 dB at 500 Hz.
    ({250: 15, 500: 20, 1000: 70, 2000: 90, 4000: 100}, 25),
    # 30/NR/NR: NR counts as 120, Fletcher (30+120)/2 = 75, SRT 40 is 35 dB
    # better; 10 dB poorer than the best threshold, 30 dB at 500 Hz.
    ({250: 25, 500: 30, 1000: "NR", 2000: "NR", 4000: "NR"}, 40),
])
def test_a_precipitous_slope_with_an_srt_near_the_best_threshold_is_indeterminate(
        ac, srt):
    result = S.srt_agreement(ac, srt)
    assert result["configuration"] == "sloping"
    assert result["agrees"] is None
    assert result["non_organic_suspected"] is False
    assert result["comparator"] == ac[500]
    assert result["best_threshold_freq"] == 500
    assert "objective measure" in result["message"]


def test_an_srt_between_the_best_threshold_and_fletcher_is_indeterminate():
    """10/60/90: Fletcher (10+60)/2 = 35. SRT 22 is 13 dB better than it and
    12 dB poorer than the best threshold (10 dB at 500 Hz) — between the two
    comparators a precipitous configuration allows."""
    result = S.srt_agreement({500: 10, 1000: 60, 2000: 90}, 22)
    assert result["agrees"] is None
    assert result["non_organic_suspected"] is False
    assert result["difference"] == -12.0
    assert "between that average and the best single threshold" in result["message"]


def test_the_full_analysis_reports_a_precipitous_slope_as_indeterminate():
    ear = {"ac": {250: 15, 500: 20, 1000: 70, 2000: 90, 4000: 100},
           "bc": {250: 15, 500: 20, 1000: 70, 2000: 70, 4000: 70},
           "srt": 25, "masked": True, "speech_masked": True}
    body = client.post("/api/analyze", json=record(ear, ear)).json()
    titles = [a["title"] for a in body["safety"]["alerts"]]
    assert "Possible non-organic (functional) hearing loss" not in titles
    flags = body["speech_audiometry"]["right"]["flags"]
    assert "non_organic" not in flags
    assert "srt_indeterminate" in flags


def test_an_srt_far_better_than_even_the_best_threshold_is_flagged_in_a_steep_loss():
    """20/70/90, SRT 5: 15 dB better than the best threshold (20 dB) and
    45 − 5 = 40 dB better than Fletcher."""
    result = S.srt_agreement({500: 20, 1000: 70, 2000: 90}, 5)
    assert result["non_organic_suspected"] is True
    assert result["comparator"] == 45.0
    assert result["difference"] == 40.0
    assert "even a precipitous configuration" in result["message"]


def test_an_srt_near_the_three_frequency_average_agrees_in_a_sloping_loss():
    """15/20/60 (a 40 dB step): Fletcher 17.5, PTA3 95/3 = 31.7. SRT 30 is
    1.7 dB from PTA3 — the nearer average — so it agrees."""
    ac = {250: 10, 500: 15, 1000: 20, 2000: 60, 4000: 70}
    result = S.srt_agreement(ac, 30)
    assert result["configuration"] == "sloping"
    assert result["comparator_basis"] == "three_frequency"
    assert result["comparator"] == 31.7
    assert result["difference"] == 1.7
    assert result["agrees"] is True
    assert result["non_organic_suspected"] is False


def test_an_srt_between_widely_separated_averages_agrees_with_neither():
    """0/0/NR: PTA3 (0+0+120)/3 = 40, Fletcher 0. SRT 25 is 15 dB better than
    PTA3 and 25 dB poorer than Fletcher. Not exaggeration (the SRT does not
    beat Fletcher), but not agreement either; PTA3 is the nearer average."""
    result = S.srt_agreement({500: 0, 1000: 0, 2000: "NR"}, 25)
    assert result["agrees"] is False
    assert result["non_organic_suspected"] is False
    assert result["comparator"] == 40.0
    assert result["difference"] == 15.0
    assert "within 10 dB of neither" in result["message"]


def test_an_srt_poorer_than_both_averages_still_disagrees():
    """Same sloping ear, SRT 45: 13.3 dB poorer than PTA3 (31.7)."""
    ac = {250: 10, 500: 15, 1000: 20, 2000: 60, 4000: 70}
    result = S.srt_agreement(ac, 45)
    assert result["agrees"] is False
    assert result["non_organic_suspected"] is False
    assert "poorer" in result["message"]


def test_an_irregular_configuration_also_uses_fletcher():
    """10/50/10: steps +40 then −40. Fletcher (10, 10) = 10."""
    result = S.srt_agreement({500: 10, 1000: 50, 2000: 10}, 10)
    assert result["configuration"] == "irregular"
    assert result["comparator"] == 10.0
    assert result["agrees"] is True


def test_an_incomplete_comparator_is_indeterminate():
    """2000 Hz untested: 500/1000 = 40/50 → mean 45 for reference, but the
    configuration that decides the comparator is unknown."""
    result = S.srt_agreement({500: 40, 1000: 50}, 42)
    assert result["configuration"] == "incomplete"
    assert result["comparator"] == 45.0
    assert result["comparator_label"] == "average of 500/1000 Hz"
    assert result["difference"] == 3.0
    assert result["agrees"] is None
    assert result["indeterminate_reason"] == "incomplete"
    assert "cannot be judged" in result["message"]
    single = S.srt_agreement({1000: 40}, 40)
    assert single["comparator"] == 40.0
    assert single["comparator_label"] == "threshold at 1000 Hz"
    assert single["agrees"] is None


def test_a_rising_ear_with_2000_hz_untested_is_not_called_non_organic():
    """500/1000 = 60/50 → mean 55, 25 dB above an SRT of 30; but 2000 Hz is
    untested and 4000 Hz is 10 dB, so the ear may well rise steeply."""
    ac = {250: 60, 500: 60, 1000: 50, 4000: 10, 8000: 10}
    result = S.srt_agreement(ac, 30)
    assert result["difference"] == 25.0
    assert result["agrees"] is None
    assert result["non_organic_suspected"] is False
    ear = {"ac": ac, "bc": {250: 60, 500: 60, 1000: 50, 4000: 10}, "srt": 30}
    body = client.post("/api/analyze", json=record(ear)).json()
    titles = [a["title"] for a in body["safety"]["alerts"]]
    assert "Possible non-organic (functional) hearing loss" not in titles
    assert "srt_indeterminate" in body["speech_audiometry"]["right"]["flags"]


def test_no_speech_frequency_thresholds_means_the_srt_cannot_be_judged():
    """Only 4000 Hz tested: no comparator, no verdict either way."""
    result = S.srt_agreement({4000: 60}, 20)
    assert result["comparator"] is None
    assert result["agrees"] is None
    assert result["indeterminate_reason"] == "no_speech_frequencies"
    assert result["non_organic_suspected"] is False
    assert "cannot be checked" in result["message"]


# ================================================ one PTA, two endpoints ==

DISPROPORTIONATE_AC = {250: 20, 500: 30, 1000: 40, 2000: 55, 4000: 70, 8000: 90}
WRS_50_AT_90 = [{"level": 90, "score": 50, "n_words": 25}]


def test_both_endpoints_use_the_four_frequency_pta_for_disproportion():
    """PTA4 = (30+40+55+70)/4 = 48.75 < 50, with PB max 50% < 60%: both
    endpoints call it disproportionate. The mean of all six (50.8) would not."""
    standalone = client.post("/api/speech/analyze", json={
        "ac": DISPROPORTIONATE_AC, "srt": 40, "wrs": WRS_50_AT_90}).json()
    full = client.post("/api/analyze", json=record({
        "ac": DISPROPORTIONATE_AC, "bc": DISPROPORTIONATE_AC,
        "srt": 40, "wrs": WRS_50_AT_90})).json()["speech_audiometry"]["right"]
    assert standalone["wrs"]["disproportionate"] is True
    assert full["wrs"]["disproportionate"] is True
    assert standalone["retrocochlear_suspicion"] is full["retrocochlear_suspicion"] is True
    assert "disproportionate_wrs" in standalone["flags"]
    assert standalone["flags"] == full["flags"]


def test_no_response_counts_as_120_on_both_endpoints():
    """30/30/30/NR → PTA4 = (30+30+30+120)/4 = 52.5, not < 50, so a 40% score
    is not disproportionate on either endpoint."""
    ac = {500: 30, 1000: 30, 2000: 30, 4000: "NR"}
    wrs = [{"level": 80, "score": 40, "n_words": 25}]
    standalone = client.post("/api/speech/analyze",
                             json={"ac": ac, "srt": 30, "wrs": wrs}).json()
    full = client.post("/api/analyze", json=record(
        {"ac": ac, "bc": {500: 30, 1000: 30, 2000: 30}, "srt": 30, "wrs": wrs}
    )).json()["speech_audiometry"]["right"]
    assert standalone["wrs"]["disproportionate"] is False
    assert full["wrs"]["disproportionate"] is False


def test_the_standalone_endpoint_rejects_an_unsupported_frequency():
    resp = client.post("/api/speech/analyze",
                       json={"ac": {3000: 40}, "srt": 40})
    assert resp.status_code == 422


# ====================================================== SDT gap messages ==

def sdt_note(gap, srt=40):
    result = S.sdt_analysis(flat(srt - gap), sdt=srt - gap, srt=srt)
    return result, result["notes"][-1]


@pytest.mark.parametrize("gap", [5, 8, 10])
def test_a_gap_inside_five_to_ten_db_is_called_expected(gap):
    result, note = sdt_note(gap)
    assert "within the expected 5-10 dB" in note
    assert result["flags"] == []


@pytest.mark.parametrize("gap", [0, 3])
def test_a_gap_narrower_than_five_db_is_not_called_expected(gap):
    result, note = sdt_note(gap)
    assert "within the expected" not in note
    assert "narrower than the expected 5-10 dB" in note
    assert result["flags"] == []


def test_an_sdt_equal_to_the_srt_says_so():
    _, note = sdt_note(0)
    assert note.startswith("SDT equals the SRT")


@pytest.mark.parametrize("gap", [11, 15])
def test_a_gap_one_step_wider_is_reported_but_not_flagged(gap):
    result, note = sdt_note(gap)
    assert "within the expected" not in note
    assert "wider than the expected 5-10 dB" in note
    assert "sdt_srt_gap_wide" not in result["flags"]


def test_a_gap_beyond_one_step_is_flagged_wide():
    result, _ = sdt_note(16)
    assert "sdt_srt_gap_wide" in result["flags"]


# ================================================== rollover inequality ==

def pi(*pairs, n_words=50):
    return [{"level": lvl, "score": sc, "n_words": n_words} for lvl, sc in pairs]


def test_an_index_of_exactly_045_meets_but_does_not_exceed_the_criterion():
    """(80 − 44) / 80 = 36/80 = 0.45. The criterion is index > 0.45."""
    result = S.wrs_analysis(pi((60, 80), (90, 44)))
    assert result["rollover_index"] == 0.45
    assert result["rollover"] is False
    assert any("meets but does not exceed" in n for n in result["notes"])


@pytest.mark.parametrize("pb_max,pb_min,index", [
    (80, 42, 0.475),   # 38/80
    (100, 54, 0.46),   # 46/100
])
def test_an_index_above_045_is_rollover(pb_max, pb_min, index):
    result = S.wrs_analysis(pi((60, pb_max), (90, pb_min)))
    assert result["rollover_index"] == index
    assert result["rollover"] is True
    assert not any("not 0.46" in n for n in result["notes"])


def test_an_index_between_045_and_046_is_rollover_with_a_borderline_note():
    """(88 − 48) / 88 = 40/88 = 0.4545: rollover under "> 0.45", short of the
    0.46 form of Dirks et al.'s criterion. The referral stands."""
    result = S.wrs_analysis(pi((60, 88), (90, 48)))
    assert result["rollover_index"] == 0.455
    assert result["rollover"] is True
    assert any("not 0.46" in n for n in result["notes"])


def test_an_index_between_the_nu6_and_pb50_criteria_is_caveated_not_flagged():
    """(80 − 50) / 80 = 0.375: above 0.35 (NU-6), below 0.45 (PB-50)."""
    result = S.wrs_analysis(pi((60, 80), (90, 50)))
    assert result["rollover_index"] == 0.375
    assert result["rollover"] is False
    assert any("Meyer & Mishler" in n for n in result["notes"])


@pytest.mark.parametrize("pb_max,pb_min", [(80, 56), (100, 65)])
def test_an_index_at_or_below_035_carries_no_rollover_caveat(pb_max, pb_min):
    """24/80 = 0.30, and 35/100 = 0.35 (not > 0.35)."""
    result = S.wrs_analysis(pi((60, pb_max), (90, pb_min)))
    assert result["rollover"] is False
    assert not any("rollover" in n.lower() for n in result["notes"])


# ===================================== word-recognition categories ==

@pytest.mark.parametrize("score,category", [
    (100, "Excellent"), (90, "Excellent"),
    (89, "Good"), (88, "Good"), (78, "Good"),
    (77, "Fair"), (76, "Fair"), (66, "Fair"),
    (65, "Poor"), (64, "Poor"), (54, "Poor"),
    (53, "Very poor"), (52, "Very poor"), (0, "Very poor"),
])
def test_word_recognition_follows_goetzinger_categories(score, category):
    """Goetzinger (1978): 90-100, 78-88, 66-76, 54-64, < 52. Scores in the
    gaps between published bands take the poorer category."""
    result = S.wrs_analysis(pi((80, score)), pta=30, srt=30)
    assert result["interpretation"].startswith(category)


def test_the_reference_endpoint_publishes_the_goetzinger_cut_points():
    body = client.get("/api/speech/reference").json()
    assert [b["low"] for b in body["wrs_bands"]] == [90, 78, 66, 54, 0]
    assert body["rollover_rule"] == "index > 0.45"
    assert any("Goetzinger" in c for c in body["citations"])
    assert body["steep_step_db"] == 20
    assert "Fletcher's best-two average" in body["srt_rule"]
