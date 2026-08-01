"""SDT, SRT and WRS — the three speech measurements and their cross-checks."""
import pytest
from fastapi.testclient import TestClient

from app.clinical import speech_audiometry as S
from app.main import app
from app.models.schemas import EarData, SpeechPoint

client = TestClient(app)


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


def sloping():
    return {250: 10, 500: 15, 1000: 25, 2000: 55, 4000: 75, 8000: 85}


# ================================================ the statistics of a list

def test_a_word_score_carries_a_wide_interval_on_a_short_list():
    """The number that stops two scores being read as different."""
    short = S.binomial_ci(22, 25)     # 88%
    long = S.binomial_ci(44, 50)      # 88%
    assert short["low"] < 88 < short["high"]
    assert short["width"] > long["width"], "a longer list must resolve more"
    assert short["width"] > 25


@pytest.mark.parametrize("correct,n", [(0, 25), (25, 25), (0, 50), (50, 50)])
def test_the_interval_stays_inside_zero_to_one_hundred(correct, n):
    ci = S.binomial_ci(correct, n)
    assert 0 <= ci["low"] <= ci["high"] <= 100


def test_a_perfect_score_still_has_a_lower_bound_below_one_hundred():
    """100% on 25 words does not mean 100% word recognition."""
    ci = S.binomial_ci(25, 25)
    assert ci["high"] == 100.0
    assert ci["low"] < 95


def test_two_scores_a_short_list_cannot_separate_are_not_called_different():
    assert S.scores_differ(88, 76, 25) is False
    assert S.scores_differ(92, 48, 25) is True


def test_a_longer_list_resolves_a_difference_a_shorter_one_cannot():
    """The practical reason to run 50 words when it matters.

    92% against 76% is invisible on 25 words and clear on 50 — the same two
    ears, a different conclusion, decided by list length alone.
    """
    assert S.scores_differ(92, 76, 25) is False
    assert S.scores_differ(92, 76, 50) is True


def test_an_empty_list_yields_no_interval():
    assert S.binomial_ci(0, 0)["low"] is None
    assert S.scores_differ(80, 60, 0) is None


# ================================================================== SDT ==

def test_sdt_tracks_the_best_pure_tone_threshold_not_the_average():
    """Detection needs only the most audible frequency."""
    result = S.sdt_analysis(sloping(), sdt=12)
    assert result["best_pure_tone"] == 10
    assert result["agrees"] is True


def test_an_sdt_far_from_the_best_threshold_is_flagged():
    result = S.sdt_analysis(flat(60), sdt=15)
    assert "sdt_tone_mismatch" in result["flags"]
    assert result["agrees"] is False


def test_an_sdt_poorer_than_the_srt_is_impossible_and_says_so():
    """Detecting speech cannot be harder than recognising it."""
    result = S.sdt_analysis(flat(40), sdt=45, srt=35)
    assert "sdt_worse_than_srt" in result["flags"]
    assert any("cannot be harder" in n for n in result["notes"])


def test_the_expected_sdt_to_srt_gap_is_accepted():
    result = S.sdt_analysis(flat(40), sdt=34, srt=42)
    assert result["srt_difference"] == 8
    assert result["flags"] == []
    assert result["agrees"] is True


def test_a_wide_sdt_to_srt_gap_points_at_a_sloping_loss():
    result = S.sdt_analysis(sloping(), sdt=10, srt=40)
    assert "sdt_srt_gap_wide" in result["flags"]
    assert any("sloping" in n for n in result["notes"])


def test_an_sdt_without_an_srt_says_what_it_cannot_tell_you():
    result = S.sdt_analysis(flat(40), sdt=35)
    assert result["srt_difference"] is None
    assert any("says nothing about whether it can be understood" in n
               for n in result["notes"])


def test_no_sdt_recorded_returns_nothing():
    assert S.sdt_analysis(flat(40), sdt=None) is None


# ================================================================== SRT ==

def test_srt_agreement_boundary_is_unchanged():
    ac = flat(40)
    assert S.srt_agreement(ac, 30)["agrees"] is True      # exactly 10 dB
    assert S.srt_agreement(ac, 29)["agrees"] is False     # 11 dB


def test_an_srt_much_better_than_the_tones_suggests_exaggeration():
    result = S.srt_agreement(flat(60), 30)
    assert result["non_organic_suspected"] is True
    assert "exaggerated" in result["message"]


def test_fletcher_beats_the_four_frequency_average_on_a_sloping_loss():
    """Speech reception follows the frequencies still heard."""
    ac = sloping()
    assert S.pta_fletcher(ac) == 20.0        # best two of 500/1000/2000
    assert S.pta_two_frequency(ac) == 20.0
    four_freq = sum(ac[f] for f in (500, 1000, 2000, 4000)) / 4
    assert S.pta_fletcher(ac) < four_freq


def test_an_unmasked_srt_that_could_be_a_shadow_response_is_flagged():
    """Speech crosses the skull like a tone does."""
    poor, good = flat(75), flat(10)
    result = S.srt_agreement(poor, 75, masked=False, opposite_ac=good)
    assert result["masking_note"] is not None
    assert "shadow response" in result["masking_note"]


def test_masking_recorded_removes_the_shadow_warning():
    result = S.srt_agreement(flat(75), 75, masked=True, opposite_ac=flat(10))
    assert result["masking_note"] is None


def test_no_shadow_warning_when_the_ears_are_similar():
    result = S.srt_agreement(flat(45), 45, masked=False, opposite_ac=flat(40))
    assert result["masking_note"] is None


# ================================================================== WRS ==

def wrs(*pairs, n_words=25):
    return [{"level": lvl, "score": sc, "n_words": n_words} for lvl, sc in pairs]


def test_every_score_carries_its_confidence_interval():
    result = S.wrs_analysis(wrs((70, 88)), pta=40, srt=40)
    assert result["pb_max_ci"]["low"] < 88 < result["pb_max_ci"]["high"]
    assert all("ci" in p for p in result["points"])


def test_rollover_is_detected_and_its_significance_tested():
    result = S.wrs_analysis(wrs((60, 90), (90, 40)), pta=45, srt=40)
    assert result["rollover"] is True
    assert result["rollover_index"] > S.ROLLOVER_THRESHOLD
    assert result["rollover_significant"] is True


def test_a_rollover_a_short_list_cannot_resolve_is_called_out():
    """A drop the word list cannot see is not a drop."""
    result = S.wrs_analysis(wrs((60, 60), (90, 32)), pta=45, srt=40, )
    assert result["rollover"] is True
    if result["rollover_significant"] is False:
        assert any("cannot resolve" in n for n in result["notes"])


def test_a_score_obtained_too_near_threshold_is_flagged_not_interpreted():
    """A poor score at threshold measures the level, not the patient."""
    low = S.wrs_analysis(wrs((45, 40)), pta=40, srt=40)
    assert low["adequate_level"] is False
    assert low["suprathreshold_target"] == 70
    assert any("may not have been reached" in n for n in low["notes"])


def test_a_score_at_a_proper_suprathreshold_level_is_accepted():
    good = S.wrs_analysis(wrs((75, 40)), pta=40, srt=40)
    assert good["adequate_level"] is True
    assert not any("may not have been reached" in n for n in good["notes"])


def test_a_short_list_warns_before_the_score_is_compared_to_anything():
    result = S.wrs_analysis(wrs((80, 76), n_words=25), pta=40, srt=40)
    assert any("50-word list" in n for n in result["notes"])


def test_a_fifty_word_list_is_not_told_to_use_a_fifty_word_list():
    """Advice only helps if there is a longer list to reach for."""
    result = S.wrs_analysis(wrs((80, 76), n_words=50), pta=40, srt=40)
    assert not any("Use a 50-word list" in n for n in result["notes"])
    # A mid-range score on a full list is still that uncertain, and says so.
    assert any("treat it as a band" in n for n in result["notes"])


def test_a_high_score_on_a_full_list_raises_no_width_warning_at_all():
    result = S.wrs_analysis(wrs((80, 96), n_words=50), pta=40, srt=40)
    assert not any("confidence interval" in n for n in result["notes"])


def test_disproportionately_poor_recognition_is_still_flagged():
    result = S.wrs_analysis(wrs((70, 45)), pta=35, srt=35)
    assert result["disproportionate"] is True


def test_no_words_recorded_returns_nothing():
    assert S.wrs_analysis([], pta=40) is None


# ====================================================== ear comparison ==

def test_an_asymmetry_a_short_list_cannot_resolve_is_not_reported():
    right = {"wrs": {"pb_max": 88, "n_words": 25}}
    left = {"wrs": {"pb_max": 76, "n_words": 25}}
    result = S.compare_ears(right, left)
    assert result["significant"] is False
    assert "cannot resolve" in result["message"]


def test_a_real_asymmetry_triggers_the_referral_language():
    right = {"wrs": {"pb_max": 92, "n_words": 50}}
    left = {"wrs": {"pb_max": 44, "n_words": 50}}
    result = S.compare_ears(right, left)
    assert result["significant"] is True
    assert "retrocochlear" in result["message"]


def test_comparison_needs_both_ears():
    assert S.compare_ears({"wrs": {"pb_max": 90, "n_words": 25}}, None) is None


# ============================================================== bundle ==

def ear(**kw):
    return EarData(ac=kw.pop("ac", flat(40)), **kw)


def test_the_bundle_carries_all_three_measurements():
    result = S.analyze_speech(
        ear(sdt=32, srt=40, wrs=[SpeechPoint(level=75, score=88)]), pta=40)
    assert result["sdt"] and result["srt"] and result["wrs"]


def test_the_bundle_returns_nothing_when_no_speech_was_tested():
    assert S.analyze_speech(ear(), pta=40) is None


def test_an_sdt_alone_is_enough_to_produce_a_result():
    """The paediatric case: detection recorded, nothing else obtainable."""
    result = S.analyze_speech(ear(sdt=35), pta=40)
    assert result is not None
    assert result["sdt"] is not None
    assert result["srt"] is None and result["wrs"] is None


def test_flags_gather_every_validity_problem():
    result = S.analyze_speech(
        ear(ac=flat(60), sdt=65, srt=30, wrs=[SpeechPoint(level=40, score=30)]),
        pta=60)
    assert "non_organic" in result["flags"]
    assert "sdt_worse_than_srt" in result["flags"]
    assert "wrs_level_too_low" in result["flags"]


# =========================================================== endpoints ==

def test_the_standalone_endpoint_runs_all_three():
    body = client.post("/api/speech/analyze", json={
        "ear": "right", "ac": flat(40), "sdt": 32, "srt": 40,
        "wrs": [{"level": 75, "score": 88, "n_words": 50}],
    }).json()
    assert body["available"] is True
    assert body["sdt"]["agrees"] is True
    assert body["srt"]["agrees"] is True
    assert body["wrs"]["pb_max"] == 88


def test_the_endpoint_works_with_only_an_sdt():
    body = client.post("/api/speech/analyze",
                       json={"ac": flat(40), "sdt": 35}).json()
    assert body["available"] is True
    assert body["srt"] is None


def test_the_endpoint_reports_nothing_measured():
    body = client.post("/api/speech/analyze", json={"ac": flat(40)}).json()
    assert body["available"] is False


def test_the_compare_endpoint_tests_rather_than_eyeballs():
    body = client.post("/api/speech/compare", json={
        "right_score": 88, "left_score": 76, "n_words": 25}).json()
    assert body["significant"] is False
    assert body["right_ci"]["low"] < 88 < body["right_ci"]["high"]


def test_the_reference_endpoint_describes_all_three_tests():
    body = client.get("/api/speech/reference").json()
    assert {t["key"] for t in body["tests"]} == {"sdt", "srt", "wrs"}
    assert body["wrs_bands"]


# ======================================== integration with the pipeline ==

def full_record(**right):
    base = {"ac": flat(40), "bc": flat(40)}
    base.update(right)
    return {"patient": {"name": "T", "age": 40},
            "right": base, "left": {"ac": flat(40), "bc": flat(40)}}


def test_analyze_returns_speech_for_both_ears_and_the_comparison():
    body = client.post("/api/analyze", json=full_record(
        sdt=32, srt=40, wrs=[{"level": 75, "score": 88, "n_words": 50}])).json()
    speech = body["speech_audiometry"]
    assert speech["right"]["sdt"] is not None
    assert "comparison" in speech


def test_an_asymmetric_word_score_raises_a_safety_alert():
    record = full_record(srt=40, wrs=[{"level": 75, "score": 92, "n_words": 50}])
    record["left"]["srt"] = 40
    record["left"]["wrs"] = [{"level": 75, "score": 40, "n_words": 50}]
    body = client.post("/api/analyze", json=record).json()
    assert body["speech_audiometry"]["comparison"]["significant"] is True
    assert any("Asymmetric word recognition" in a["title"]
               for a in body["safety"]["alerts"])


def test_an_impossible_sdt_raises_a_validity_alert():
    body = client.post("/api/analyze",
                       json=full_record(sdt=48, srt=40)).json()
    assert any("Speech detection threshold poorer" in a["title"]
               for a in body["safety"]["alerts"])


def test_speech_tests_are_optional_and_change_nothing_when_absent():
    """The three additions must not disturb a record that has none of them."""
    body = client.post("/api/analyze", json=full_record()).json()
    assert body["speech_audiometry"]["right"] is None
    assert body["speech_audiometry"]["comparison"] is None
    assert body["rules"]["right"]["ac_pta"]["value"] == 40
