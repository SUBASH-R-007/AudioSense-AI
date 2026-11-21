"""Disability, WHO grades, typing and masking — pinned to their published sources.

Every expected value below is computed independently of the implementation:
the RPwD figures from the Gazette of India S.O. 76(E) (4 Jan 2018) paras
20.2.2-20.2.3 by hand, the WHO grades from the World Report on Hearing (2021)
table, and the masking floor from the formula method written out in full.
"""
import io

import pytest

from app.clinical import masking as M
from app.clinical.rules import (
    RPWD_READY_RECKONER,
    WHO_GRADES,
    analyze_test,
    hearing_type,
    pta,
    rpwd_disability,
    rpwd_disability_from_thresholds,
    rpwd_monaural_pct,
    who_grade,
)
from app.services.demo_cases import DEMO_CASES
from app.services.languages import GRADE_SIMPLE
from app.services.referral import build_referral_pdf
from app.services.validation import normalize_grade, normalize_type

AC_F = (250, 500, 1000, 2000, 4000, 8000)
BC_F = (250, 500, 1000, 2000, 4000)


def flat(level, freqs=AC_F):
    return {f: level for f in freqs}


def pta4(level):
    return {500: level, 1000: level, 2000: level, 4000: level}


# ===================================================== A1-1 Gazette method ===

def gazette_row(db: int) -> float:
    """The ready reckoner's rows as the Gazette prints them, re-derived from
    their pattern: 0-25 -> 0; 26-33 -> 1; 34-59 -> PTA-32; 60 -> 40;
    61-94 -> 40 + 1.71 per dB; 95 -> 100."""
    if db <= 25:
        return 0.0
    if db <= 33:
        return 1.0
    if db <= 59:
        return float(db - 32)
    if db == 60:
        return 40.0
    if db < 95:
        return round(40 + 1.71 * (db - 60), 2)
    return 100.0


def test_the_transcribed_table_matches_every_gazette_row():
    assert sorted(RPWD_READY_RECKONER) == list(range(26, 96))
    for db, pct in RPWD_READY_RECKONER.items():
        assert float(pct) == gazette_row(db), f"row {db} dB"


@pytest.mark.parametrize("db", range(-10, 121))
def test_monaural_percentage_at_every_whole_db(db):
    assert float(rpwd_monaural_pct(db)[1]) == gazette_row(db)


@pytest.mark.parametrize("right,left,expected,benchmark", [
    (40, 40, 8.0, False),
    (50, 50, 18.0, False),
    (52, 52, 20.0, False),     # 1.5 x (52-25) gave 40.5% and a false benchmark
    (55, 55, 23.0, False),
    (59, 59, 27.0, False),
    (60, 60, 40.0, True),
    (65, 60, 41.43, True),     # (5 x 40 + 48.55) / 6 = 41.425 -> 41.43
    (70, 80, 59.95, True),     # (5 x 57.1 + 74.2) / 6 = 59.95
    (92, 92, 94.72, True),
    (30, 90, 16.05, False),    # (5 x 1 + 91.3) / 6 = 16.05
    (52, 100, 33.33, False),   # (5 x 20 + 100) / 6 = 33.33
])
def test_gazette_golden_cases(right, left, expected, benchmark):
    d = rpwd_disability_from_thresholds(pta4(right), pta4(left))
    assert d["binaural_pct"] == expected
    assert d["benchmark_disability"] is benchmark
    assert d["certifiable"] is True


def test_no_response_counts_as_95_db_for_disability_only():
    ac = {500: 60, 1000: 70, 2000: 79, 4000: "NR"}
    d = rpwd_disability_from_thresholds(ac, ac)
    # (60 + 70 + 79 + 95) / 4 = 76 dB -> 67.36%
    assert d["right"]["pta"] == 76.0
    assert d["right"]["pct"] == 67.36
    assert d["binaural_pct"] == 67.36
    assert d["right"]["nr_freqs"] == [4000]
    assert "95 [NR]" in d["right"]["formula"]
    # Everywhere else NR stays at the audiometer maximum, 120 dB HL.
    assert pta(ac)["value"] == pytest.approx((60 + 70 + 79 + 120) / 4)


def test_measured_thresholds_above_95_hold_at_100_percent():
    ac = {500: 100, 1000: 110, 2000: "NR", 4000: "NR"}
    d = rpwd_disability_from_thresholds(ac, ac)
    assert d["right"]["pta"] == 100.0  # (100 + 110 + 95 + 95) / 4
    assert d["right"]["pct"] == 100.0


def test_only_a_no_response_is_replaced_by_95_db():
    """Para 20.2.2(a)(i) substitutes 95 dB for a no-response and caps nothing
    else, so a measured threshold above 95 enters at its measured value. Read
    literally, a no-response ear computes lower than a measured-100 ear."""
    with_nr = rpwd_disability_from_thresholds({500: 90, 1000: 90, 2000: "NR", 4000: "NR"},
                                              pta4(10))
    measured = rpwd_disability_from_thresholds({500: 90, 1000: 90, 2000: 100, 4000: 100},
                                               pta4(10))
    # (90 + 90 + 95 + 95) / 4 = 92.5 -> 93 dB -> Gazette row 93 = 96.43%
    assert with_nr["right"]["pta"] == 92.5
    assert with_nr["right"]["pta_rounded"] == 93
    assert with_nr["right"]["pct"] == 96.43
    assert with_nr["right"]["formula"].count("95 [NR]") == 2
    # (90 + 90 + 100 + 100) / 4 = 95 dB -> Gazette row 95 = 100%
    assert measured["right"]["pta"] == 95.0
    assert measured["right"]["pct"] == 100.0
    assert "[NR]" not in measured["right"]["formula"]


def test_fractional_pta_is_rounded_half_up_and_says_so():
    # (50 + 50 + 55 + 55) / 4 = 52.5 -> 53 dB -> 21%
    d = rpwd_disability_from_thresholds({500: 50, 1000: 50, 2000: 55, 4000: 55},
                                        pta4(10))
    assert d["right"]["pta"] == 52.5
    assert d["right"]["pta_rounded"] == 53
    assert d["right"]["pct"] == 21.0
    assert "53 dB (nearest whole dB, halves up)" in d["right"]["formula"]
    assert "halves rounded up" in d["rounding_rule"]
    # (60 + 60 + 60 + 58) / 4 = 59.5 -> 60 dB -> 40%: the rule is applied at
    # the benchmark step too, not only between neighbouring rows.
    at_step = rpwd_disability_from_thresholds({500: 60, 1000: 60, 2000: 60, 4000: 58},
                                              {500: 60, 1000: 60, 2000: 60, 4000: 58})
    assert at_step["right"]["pta_rounded"] == 60
    assert at_step["binaural_pct"] == 40.0
    # 5 dB steps give quarter-dB means: 58.75 -> 59 dB -> 27%.
    below = rpwd_disability_from_thresholds({500: 60, 1000: 60, 2000: 60, 4000: 55},
                                            {500: 60, 1000: 60, 2000: 60, 4000: 55})
    assert below["right"]["pta_rounded"] == 59
    assert below["binaural_pct"] == 27.0
    assert below["benchmark_disability"] is False


def test_better_ear_is_the_one_with_the_lower_percentage():
    d = rpwd_disability_from_thresholds(pta4(65), pta4(60))
    assert d["better_ear"] == "left" and d["worse_ear"] == "right"
    assert d["binaural_formula"].startswith("(5 × 40 [better: left] + 48.55 [poorer: right])")


def test_formula_strings_name_the_gazette_method_not_the_old_one():
    d = rpwd_disability_from_thresholds(pta4(55), pta4(55))
    assert "1.5" not in d["right"]["formula"]
    assert "ready reckoner 55 dB = 23%" in d["right"]["formula"]
    assert "S.O. 76(E)" in d["method"]
    assert d["nr_value_db"] == 95


# ========================================= A1-2 certifiability ===========

def test_a_missing_4khz_makes_the_percentage_not_certifiable():
    left = {250: 40, 500: 40, 1000: 40, 2000: 40, 8000: 40}  # 4 kHz untested
    d = rpwd_disability_from_thresholds(pta4(50), left)
    assert d["certifiable"] is False
    assert "left: 4000 Hz" in d["certification_note"]
    assert "not certifiable" in d["left"]["formula"].lower()
    assert d["left"]["missing_freqs"] == [4000]
    # Estimate from the three tested frequencies: 40 dB -> 8%.
    assert d["left"]["pct"] == 8.0


def test_all_four_frequencies_in_both_ears_is_certifiable():
    d = rpwd_disability_from_thresholds(pta4(50), pta4(50))
    assert d["certifiable"] is True
    assert d["certification_note"]


def test_a_no_response_is_tested_and_stays_certifiable():
    d = rpwd_disability_from_thresholds({**pta4(80), 4000: "NR"}, pta4(80))
    assert d["certifiable"] is True


def test_a_bare_pta_uses_the_same_table_and_is_never_certifiable():
    # 52.5 -> 53 dB -> 21%; 61.25 -> 61 dB -> 41.71%; (5 x 21 + 41.71) / 6
    d = rpwd_disability(52.5, 61.25)
    assert d["binaural_pct"] == 24.45
    assert d["certifiable"] is False
    assert "cannot be verified" in d["certification_note"]


def test_an_incomplete_ac_pta_is_caveated_on_the_ear():
    result = hearing_type({500: 40, 1000: 40, 2000: 40}, {})
    assert any("3/4 frequencies" in c and "4000" in c for c in result["caveats"])


def test_analyze_test_carries_certifiability():
    ac_incomplete = {500: 60, 1000: 60, 2000: 60}
    result = analyze_test(flat(60), {}, ac_incomplete, {})
    assert result["disability"]["certifiable"] is False


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader
    text = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    return " ".join(text.split())  # wrapped lines read as one sentence


def test_referral_letter_states_the_certification_caveat():
    rules = analyze_test(flat(60), {}, {500: 60, 1000: 60, 2000: 60}, {})
    text = _pdf_text(build_referral_pdf({"analysis": {"rules": rules}}))
    assert "Not certifiable" in text
    assert "4000" in text


def test_referral_letter_has_no_caveat_when_certifiable():
    rules = analyze_test(flat(60), {}, flat(60), {})
    text = _pdf_text(build_referral_pdf({"analysis": {"rules": rules}}))
    assert "Disability assessment" in text
    assert "Not certifiable" not in text


def test_referral_reads_a_missing_key_as_certifiable():
    rules = analyze_test(flat(60), {}, flat(60), {})
    rules["disability"].pop("certifiable")
    text = _pdf_text(build_referral_pdf({"analysis": {"rules": rules}}))
    assert "Not certifiable" not in text


# ================================== A1-3 WHO "Complete or total" grade ====

@pytest.mark.parametrize("value,grade", [
    (80.0, "Profound hearing loss"),
    (94.75, "Profound hearing loss"),
    (95.0, "Complete or total hearing loss"),
    (100.0, "Complete or total hearing loss"),
    (120.0, "Complete or total hearing loss"),
])
def test_who_2021_grades_95_and_above_as_complete_or_total(value, grade):
    assert who_grade(value)["grade"] == grade


def test_every_grade_has_plain_language_in_every_language():
    grades = {g for _lo, _hi, g, _note in WHO_GRADES}
    for lang, table in GRADE_SIMPLE.items():
        assert set(table) == grades, lang
        assert all(table.values()), lang


@pytest.mark.parametrize("raw,expected", [
    ("Complete or total hearing loss", "Complete or total hearing loss"),
    ("total deafness", "Complete or total hearing loss"),
    ("complete", "Complete or total hearing loss"),
    ("Profound hearing loss", "Profound hearing loss"),
    ("severe-to-profound", "Profound hearing loss"),
])
def test_validation_normalizes_the_new_grade(raw, expected):
    assert normalize_grade(raw) == expected


@pytest.mark.parametrize("raw", [
    "incomplete",
    "Incomplete test",
    "not graded (incomplete)",
    "subtotal",
    "near-total",
    "almost complete",
    "abnormal",
])
def test_a_grade_word_inside_another_word_is_not_that_grade(raw):
    """An unrecognised label comes back as written, to be counted as a
    disagreement, rather than being read as the grade it happens to contain."""
    assert normalize_grade(raw) == raw


@pytest.mark.parametrize("raw,expected", [
    ("Total hearing loss", "Complete or total hearing loss"),
    ("moderately-severe", "Moderately severe hearing loss"),
    ("moderately_severe", "Moderately severe hearing loss"),
    ("profound (near-total)", "Profound hearing loss"),
    ("within normal limits", "Normal hearing"),
])
def test_grade_words_still_match_as_whole_words(raw, expected):
    assert normalize_grade(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # The adverb names the same degree as the adjective.
    ("profoundly deaf", "Profound hearing loss"),
    ("severely impaired", "Severe hearing loss"),
    ("mildly impaired", "Mild hearing loss"),
    ("moderately impaired", "Moderate hearing loss"),
    ("totally deaf", "Complete or total hearing loss"),
    ("completely deaf", "Complete or total hearing loss"),
    # A qualified adverb is still short of complete.
    ("almost completely deaf", "almost completely deaf"),
    ("not totally deaf", "not totally deaf"),
    # A word that only contains a grade word is not that grade.
    ("test completed", "test completed"),
    ("severed", "severed"),
])
def test_grade_adverbs_name_the_grade_and_other_endings_do_not(raw, expected):
    assert normalize_grade(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("abnormal", "abnormal"),
    ("Conductive (provisional)", "Conductive"),
    ("sensory", "Sensorineural"),
    ("Mixed hearing loss", "Mixed"),
    ("Normal", "Normal"),
])
def test_type_words_match_at_word_starts_only(raw, expected):
    assert normalize_type(raw) == expected


def test_the_corner_audiogram_demo_is_labelled_by_its_grade():
    case = next(c for c in DEMO_CASES if c["id"] == "profound")
    rec = case["record"]
    r = analyze_test(rec["right"]["ac"], rec["right"]["bc"],
                     rec["left"]["ac"], rec["left"]["bc"])
    assert r["right"]["who_grade"]["grade"] == "Complete or total hearing loss"
    assert r["left"]["who_grade"]["grade"] == "Complete or total hearing loss"
    assert "Total" in case["label"]


# ===================================== A1-4 bone-conduction no-response ====

def test_bc_no_response_does_not_cancel_a_real_gap():
    ac = {250: 60, 500: 70, 1000: 80, 2000: 90, 4000: 100, 8000: "NR"}
    bc = {250: 25, 500: 30, 1000: 40, 2000: "NR", 4000: "NR"}
    result = hearing_type(ac, bc)
    # Gaps 40 and 40 at 500/1000 Hz; 2k/4k indeterminate. BC 30-40 is
    # abnormal, so the loss is mixed, not sensorineural.
    assert result["type"] == "Mixed"
    assert result["abg"]["value"] == 40.0
    assert result["abg"]["freqs_used"] == [500, 1000]
    assert result["abg"]["bc_nr_excluded"] == [2000, 4000]
    assert result["provisional"] is True
    assert any("No Response" in c for c in result["caveats"])


def test_bc_no_response_everywhere_leaves_the_gap_indeterminate():
    result = hearing_type(flat("NR"), flat("NR", BC_F))
    assert result["abg"] is None
    assert result["type"] == "Sensorineural (provisional)"
    assert result["provisional"] is True
    assert any("conductive component cannot be excluded" in c for c in result["caveats"])
    assert "type provisional — BC not tested" not in result["caveats"]


def test_a_gap_never_goes_negative_from_a_bc_no_response():
    ac = {500: 50, 1000: 50, 2000: 50, 4000: 50}
    bc = {500: 45, 1000: 45, 2000: "NR", 4000: 45}
    result = hearing_type(ac, bc)
    assert result["abg"]["value"] == 5.0  # mean of 5, 5, 5 — not (5+5-70+5)/4
    assert result["type"] == "Sensorineural"


# ===================================================== A1-5 PTA of 20 ======

def test_pta_exactly_20_is_mild_and_typed_as_a_loss():
    result = analyze_test(flat(20), flat(20, BC_F), flat(20), flat(20, BC_F))
    assert result["right"]["who_grade"]["grade"] == "Mild hearing loss"
    assert result["right"]["type"] == "Sensorineural"


def test_pta_exactly_20_without_bc_is_a_provisional_loss():
    assert hearing_type(flat(20), {})["type"] == "Sensorineural (provisional)"


def test_pta_just_under_20_is_normal():
    ac = {250: 20, 500: 20, 1000: 20, 2000: 20, 4000: 19, 8000: 20}
    assert hearing_type(ac, flat(20, BC_F))["type"] == "Normal"


# ============================== A1-6 normal hearing with an air-bone gap ===

def test_normal_air_conduction_with_a_gap_is_typed_normal_and_noted():
    result = hearing_type(flat(15), flat(-5, BC_F))
    assert result["type"] == "Normal"
    assert result["abg"]["value"] == 20.0
    assert result["significant_air_bone_gap"] is True
    assert "within normal limits" in result["air_bone_gap_note"]
    assert "20 dB air-bone gap" in result["air_bone_gap_note"]


def test_no_note_without_a_significant_gap():
    result = hearing_type(flat(10), flat(5, BC_F))
    assert result["type"] == "Normal"
    assert result["significant_air_bone_gap"] is False
    assert result["air_bone_gap_note"] is None


def test_conductive_and_mixed_keep_their_type_and_flag_the_gap():
    conductive = hearing_type(flat(40), flat(5, BC_F))
    mixed = hearing_type(flat(70), flat(40, BC_F))
    assert conductive["type"] == "Conductive" and mixed["type"] == "Mixed"
    assert conductive["significant_air_bone_gap"] and mixed["significant_air_bone_gap"]
    assert conductive["air_bone_gap_note"] is None


def test_referral_letter_carries_the_gap_note_for_a_normal_ear():
    rules = analyze_test(flat(15), flat(-5, BC_F), flat(10), flat(10, BC_F))
    text = _pdf_text(build_referral_pdf({"analysis": {"rules": rules}}))
    assert "air-bone gap" in text
    assert "no loss to type" in text


# ============================================ A1-7 minimum masking level ===

SUPRA = M.TRANSDUCERS["supra_aural"]  # IA 40


def test_minimum_masking_carries_the_10_db_safety_factor():
    assert M.MIN_MASKING_SAFETY_DB == 10
    # M_min = AC(TE) - IA + ABG(NTE) + 10 = 70 - 40 + (10 - 10) + 10 = 40
    levels = M.masking_levels("ac", 1000, ac_te=70, bc_te=65, ac_nte=10,
                              spec=SUPRA, bc_nte=10)
    assert levels["minimum"] == 40


def test_minimum_masking_adds_back_the_non_test_ear_gap():
    # 75 - 40 + (45 - 5) + 10 = 85
    levels = M.masking_levels("ac", 1000, ac_te=75, bc_te=70, ac_nte=45,
                              spec=SUPRA, bc_nte=5)
    assert levels["minimum"] == 85


def test_unknown_non_test_bone_assumes_the_largest_gap():
    # BC(NTE) untested -> ABG taken as AC(NTE): 70 - 40 + 10 + 10 = 50
    levels = M.masking_levels("ac", 1000, ac_te=70, bc_te=65, ac_nte=10, spec=SUPRA)
    assert levels["minimum"] == 50


def test_a_non_test_bone_no_response_is_treated_as_unknown():
    plan = M.masking_plan(flat(105), flat(70, BC_F), flat(60), flat("NR", BC_F),
                          transducer="supra_aural")
    row = next(r for r in plan["rows"] if r["freq"] == 1000)
    # 105 - 40 + 60 (gap assumed = AC(NTE)) + 10 = 135
    assert row["ac_levels"]["minimum"] == 135


def test_a_sensorineural_non_test_ear_is_not_a_false_dilemma():
    """Covering the crossed signal does not need the non-test ear's own
    threshold added on top: with no gap in the non-test ear the floor is
    95 - 40 + 0 + 10 = 65, under the ceiling of 60 + 40 - 5 = 95."""
    plan = M.masking_plan(flat(95), flat(60, BC_F), flat(50), flat(50, BC_F),
                          transducer="supra_aural")
    row = next(r for r in plan["rows"] if r["freq"] == 1000)
    assert row["ac"]["required"] is True
    assert row["ac_levels"]["minimum"] == 65
    assert row["ac_levels"]["maximum"] == 95
    assert row["ac_levels"]["dilemma"] is False


def test_the_minimum_is_never_below_the_initial_masking_level():
    # AC(NTE) + 10 = 60 exceeds the formula's 45 - 40 + 0 + 10 = 15.
    levels = M.masking_levels("ac", 1000, ac_te=45, bc_te=45, ac_nte=50,
                              spec=SUPRA, bc_nte=50)
    assert levels["minimum"] == 60


def test_the_bone_masking_floor_is_the_bsa_starting_level_plus_occlusion():
    """BSA (2018) 8.8 starts the noise at the non-test ear's threshold; the
    occlusion effect is added, Martin's 10 dB safety factor is not."""
    insert = M.TRANSDUCERS["insert"]  # IA 50, occlusion 10 dB at 250 Hz
    low = M.masking_levels("bc", 250, ac_te=50, bc_te=15, ac_nte=50, spec=insert)
    assert low["minimum"] == 60    # 50 + 10 occlusion
    assert low["maximum"] == 60    # 15 + 50 - 5
    assert low["dilemma"] is False
    mid = M.masking_levels("bc", 1000, ac_te=50, bc_te=15, ac_nte=50, spec=insert)
    assert mid["minimum"] == 50    # 50 + 0 occlusion


def test_a_very_sensitive_bone_threshold_is_a_250_hz_dilemma_only_on_supra_aurals():
    """Test ear AC 15 / BC -5 (gap 20 dB, so bone masking is indicated),
    non-test ear 10 dB. Supra-aural: floor 10 + 30 occlusion = 40, ceiling
    -5 + 40 - 5 = 30, so 250 Hz cannot be masked; 500 Hz (10 + 20 = 30
    against 30) can. Inserts: floor 10 + 10 = 20, ceiling -5 + 50 - 5 = 40."""
    t_ac = {f: 15 for f in (250, 500, 1000, 2000, 4000, 8000)}
    t_bc = {f: -5 for f in (250, 500, 1000, 2000, 4000)}
    o_ac = {f: 10 for f in t_ac}
    o_bc = {f: 10 for f in t_bc}
    supra = M.masking_plan(t_ac, t_bc, o_ac, o_bc, "supra_aural")
    assert supra["dilemma_freqs"] == [250]
    row = next(r for r in supra["rows"] if r["freq"] == 250)
    assert (row["bc_levels"]["minimum"], row["bc_levels"]["maximum"]) == (40, 30)
    inserts = M.masking_plan(t_ac, t_bc, o_ac, o_bc, "insert")
    assert inserts["bc_freqs"] == [250, 500, 1000, 2000, 4000]
    assert inserts["dilemma_freqs"] == []
    row = next(r for r in inserts["rows"] if r["freq"] == 250)
    assert (row["bc_levels"]["minimum"], row["bc_levels"]["maximum"]) == (20, 40)


def test_the_clinical_team_choices_are_kept_and_cited():
    assert M.BC_MASKING_GAP_DB == 15
    assert M.TRANSDUCERS["insert"]["ia_ac"] == 50
    assert "BSA" in M.__doc__ and "55 dB" in M.__doc__ and "10 dB or more" in M.__doc__
    assert any("safety factor" in c for c in M.CITATIONS)
