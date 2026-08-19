"""Tuning forks: the crossover ladder, the grid, and the false-negative Rinne."""
import itertools
import re

import pytest
from fastapi.testclient import TestClient

from app.clinical import tuning_fork as TF
from app.main import app

client = TestClient(app)


def rinne(ear, responses, masked=True, otoscopy="clear"):
    return TF.analyze_rinne(ear, responses, masked=masked, otoscopy=otoscopy)


def weber(side, freq=500, **kw):
    return TF.analyze_weber(side, freq=freq, **kw)


# ===================================================== the crossover ladder


def test_the_forks_that_can_size_a_gap_are_exactly_the_three_classical_ones():
    assert TF.RINNE_FORKS == [250, 500, 1000]
    for f in (2000, 4000):
        assert TF.FORKS[f]["crossover_db"] is None
        assert TF.FORKS[f]["rinne"] is False


def test_crossover_rises_with_frequency():
    """The whole bracketing method depends on this ordering."""
    values = [TF.FORKS[f]["crossover_db"] for f in TF.RINNE_FORKS]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


@pytest.mark.parametrize("negatives,low,high", [
    ({250}, 15, 30),                       # reversed at 256 only
    ({250, 500}, 30, 45),                  # reversed at 256 and 512
    ({250, 500, 1000}, 45, None),          # reversed at all three
])
def test_bracketing_the_gap_from_which_forks_reversed(negatives, low, high):
    signs = {f: ("negative" if f in negatives else "positive")
             for f in TF.RINNE_FORKS}
    b = TF.gap_bracket(signs)
    assert b["detected"] is True
    assert (b["low_db"], b["high_db"]) == (low, high)


def test_all_positive_is_not_reported_as_no_gap():
    """The sensitivity limit of the method must be stated, not hidden."""
    b = TF.gap_bracket({f: "positive" for f in TF.RINNE_FORKS})
    assert b["detected"] is False
    assert b["high_db"] == 15
    assert "not excluded" in b["statement"].lower()


def test_a_2048_hz_answer_never_contributes_a_gap():
    """No crossover value exists for it, so none may be extrapolated."""
    r = rinne("right", {2000: "bc_louder"})
    assert r["gap_bracket"]["detected"] is None
    assert "fork_not_valid_for_rinne" in r["flags"]


def test_a_lower_fork_positive_above_a_negative_one_is_flagged():
    """Crossover rises with frequency, so this ordering cannot happen."""
    r = rinne("right", {250: "ac_louder", 1000: "bc_louder"})
    assert "frequency_order_inconsistent" in r["flags"]


def test_the_inconsistent_order_never_produces_an_inverted_band():
    r = rinne("right", {250: "ac_louder", 1000: "bc_louder"})
    b = r["gap_bracket"]
    assert b["high_db"] is None or b["high_db"] > b["low_db"]


# ============================================================ validity gates


def test_an_unmasked_negative_rinne_is_flagged():
    r = rinne("right", {500: "bc_louder"}, masked=False)
    assert "negative_rinne_unmasked" in r["flags"]


def test_an_occluded_canal_suppresses_the_conductive_conclusion():
    r = rinne("right", {500: "bc_louder"}, otoscopy="obstructed")
    l = rinne("left", {500: "ac_louder"})
    g = TF.combined_grid(r, l, weber("right"))
    assert g["available"] is False
    assert g["level"] == "validity"
    assert g["loss_type"] is None


def test_the_weber_is_required_before_a_type_is_reported():
    r = rinne("right", {500: "bc_louder"})
    l = rinne("left", {500: "ac_louder"})
    g = TF.combined_grid(r, l, None)
    assert g["available"] is False and g["rule"] == "W13"


def test_the_grid_refuses_mismatched_frequencies():
    r = rinne("right", {1000: "bc_louder"})
    l = rinne("left", {1000: "ac_louder"})
    g = TF.combined_grid(r, l, weber("right", freq=500))
    assert g["rule"] == "C6" and g["available"] is False


def test_weber_above_1024_is_invalid():
    w = weber("right", freq=2000)
    assert w["valid"] is False
    assert "fork_not_valid_for_weber" in w["flags"]


def test_the_bing_is_refused_where_the_occlusion_effect_is_absent():
    """'No change' at 1024 Hz is what a NORMAL ear gives."""
    for freq in (1000, 2000, 4000):
        b = TF.analyze_bing("right", "no_change", freq=freq)
        assert b["valid"] is False, freq
        assert b["result"] is None


def test_the_bing_works_at_the_two_low_forks():
    for freq in (250, 500):
        assert TF.analyze_bing("right", "no_change", freq=freq)["result"] == "negative"


def test_an_unsealed_canal_is_invalid_not_negative():
    b = TF.analyze_bing("right", "no_change", freq=250, seal_demonstrated=False)
    assert b["valid"] is False and b["result"] is None


# ================================================= the false-negative Rinne


def test_the_false_negative_rinne_is_flagged_not_diagnosed():
    """A negative Rinne with the Weber lateralising AWAY cannot be conductive."""
    r = rinne("right", {500: "bc_louder"})
    l = rinne("left", {500: "ac_louder"})
    g = TF.combined_grid(r, l, weber("left"))
    assert g["level"] == "contradiction" and g["rule"] == "C1"
    assert g["loss_type"] is None
    assert "false_negative_rinne_suspected" in g["flags"]
    # Not just "some recommendation mentions masking" — every path ends with the
    # generic "audiometry with masked bone conduction" line, so that would pass
    # even if the actionable instruction were deleted. Demand the specific one.
    assert any("non-test ear masked" in r for r in g["recommendations"])
    assert any("Barany" in r for r in g["recommendations"])


def test_reduced_reserve_escalates_the_contradiction_to_c4():
    r = rinne("right", {500: "bc_louder"})
    l = rinne("left", {500: "ac_louder"})
    reserve = TF.analyze_bone_reference("right", abc="reduced",
                                        examiner_normal_hearing=True)
    g = TF.combined_grid(r, l, weber("left"), right_reserve=reserve)
    assert g["rule"] == "C4"
    assert g["loss_type"] is None


def test_the_audiogram_overrules_a_negative_rinne():
    """C8 — a reversed Rinne over an ear with no measured gap is an artefact."""
    r = rinne("right", {500: "bc_louder"})
    l = rinne("left", {500: "ac_louder"})
    g = TF.combined_grid(r, l, weber("right"), measured_gap={"right": 0.0})
    assert g["rule"] == "C8"
    assert g["loss_type"] is None
    assert "contradicted_by_audiogram" in g["flags"]


def test_a_real_gap_does_not_trigger_the_audiogram_override():
    r = rinne("right", {500: "bc_louder"})
    l = rinne("left", {500: "ac_louder"})
    g = TF.combined_grid(r, l, weber("right"), measured_gap={"right": 35.0})
    assert g["rule"] == "D3" and g["loss_type"] == "conductive"


# ===================================================== the grid, cell by cell


GRID = [
    # r_sign,     l_sign,     weber,      rule, loss_type
    ("positive", "positive", "midline", "D1", "normal_or_symmetric"),
    ("positive", "positive", "left", "D2", "sensorineural"),
    ("positive", "positive", "right", "D2", "sensorineural"),
    ("negative", "positive", "right", "D3", "conductive"),
    ("positive", "negative", "left", "D3", "conductive"),
    ("negative", "positive", "midline", "D4", "conductive"),
    ("positive", "negative", "midline", "D4", "conductive"),
    ("negative", "negative", "midline", "D5", "conductive_bilateral"),
    ("negative", "negative", "right", "D6", "conductive_bilateral"),
    ("negative", "negative", "left", "D6", "conductive_bilateral"),
]

RESP = {"positive": "ac_louder", "negative": "bc_louder"}


@pytest.mark.parametrize("r_sign,l_sign,lat,rule,loss", GRID)
def test_every_consistent_grid_cell(r_sign, l_sign, lat, rule, loss):
    g = TF.combined_grid(rinne("right", {500: RESP[r_sign]}),
                         rinne("left", {500: RESP[l_sign]}),
                         weber(lat))
    assert g["rule"] == rule
    assert g["loss_type"] == loss


def test_d2_names_the_ear_opposite_the_lateralisation():
    g = TF.combined_grid(rinne("right", {500: "ac_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("left"))
    assert g["side"] == "right"


def test_the_grid_is_complete_and_exclusive_over_all_twelve_cells():
    """The docstring claims exactly one rule fires on any complete input."""
    seen = set()
    for r_sign, l_sign, lat in itertools.product(
            ("positive", "negative"), ("positive", "negative"),
            ("right", "left", "midline")):
        g = TF.combined_grid(rinne("right", {500: RESP[r_sign]}),
                             rinne("left", {500: RESP[l_sign]}),
                             weber(lat))
        assert g["rule"] is not None, (r_sign, l_sign, lat)
        assert g["rule"] != "unmatched", (r_sign, l_sign, lat)
        seen.add((r_sign, l_sign, lat))
    assert len(seen) == 12


def test_a_midline_weber_is_never_reported_as_normal_alone():
    g = TF.combined_grid(rinne("right", {500: "ac_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("midline"))
    joined = (g["headline"] + " ".join(g["notes"])).lower()
    assert "symmetric" in joined


def test_bilateral_negative_never_yields_a_definitive_conductive_diagnosis():
    """D5's other reading is bilateral dead ears, which is the dangerous one."""
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "bc_louder"}), weber("midline"))
    joined = g["headline"] + " ".join(g["notes"])
    # The alternative reading must be offered explicitly...
    assert "sensorineural" in joined.lower()
    # ...the headline must not read as a settled conductive diagnosis...
    assert " OR " in g["headline"]
    # ...and the note must say why no definitive answer is issued.
    assert "no definitive conductive" in joined.lower()
    assert g["loss_type"] == "conductive_bilateral"


# =========================================================== D7 and D9, D10


def test_reduced_reserve_turns_a_conductive_result_mixed():
    reserve = TF.analyze_bone_reference("right", schwabach="shortened",
                                        examiner_normal_hearing=True)
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "ac_louder"}),
                         weber("right"), right_reserve=reserve)
    assert g["rule"] == "D7" and g["loss_type"] == "mixed" and g["side"] == "right"


def test_d7_never_overrides_a_contradiction():
    """C1/C4 outrank D7 — a flagged contradiction must not become a diagnosis."""
    reserve = TF.analyze_bone_reference("right", abc="reduced",
                                        examiner_normal_hearing=True)
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "ac_louder"}),
                         weber("left"), right_reserve=reserve)
    assert g["rule"] == "C4" and g["loss_type"] is None


def test_an_equivocal_rinne_is_not_forced_into_a_sign():
    g = TF.combined_grid(rinne("right", {500: "equal"}),
                         rinne("left", {500: "ac_louder"}), weber("midline"))
    assert g["rule"] == "D9" and g["available"] is False


def test_nothing_heard_anywhere_is_d10():
    g = TF.combined_grid(rinne("right", {500: "not_heard"}),
                         rinne("left", {500: "not_heard"}), weber("none"))
    assert g["rule"] == "D10"


def test_an_uncalibrated_examiner_is_flagged():
    r = TF.analyze_bone_reference("right", schwabach="shortened")
    assert "examiner_uncalibrated" in r["flags"]


# ================================================================== safety


def test_vertigo_during_the_gelle_stops_the_test_and_is_itself_the_finding():
    g = TF.analyze_gelle("right", "no_change", vertigo=True)
    assert g["result"] == "fistula_sign"
    assert "stop_test" in g["flags"]
    assert g["valid"] is False


def test_the_gelle_is_refused_on_a_perforated_drum():
    g = TF.analyze_gelle("right", "no_change", drum_intact=False)
    assert g["valid"] is False


# ====================================================== against the audiogram


def ac_bc(gap):
    return ({f: 30 + gap for f in (250, 500, 1000, 2000, 4000)},
            {f: 30 for f in (250, 500, 1000, 2000, 4000)})


def test_cross_check_agrees_when_the_gap_matches_the_reversal():
    ac, bc = ac_bc(35)          # 35 dB: reverses 256 and 512, not 1024
    r = rinne("right", {250: "bc_louder", 500: "bc_louder", 1000: "ac_louder"})
    c = TF.cross_check(r, ac, bc)
    assert c["available"] is True
    assert c["disagreements"] == []
    assert c["agreement"] == "3/3"


def test_cross_check_catches_a_reversal_over_no_gap():
    ac, bc = ac_bc(0)
    r = rinne("right", {500: "bc_louder"})
    c = TF.cross_check(r, ac, bc)
    assert c["disagreements"]
    # "crossover" appears in BOTH explanatory branches, so matching it proves
    # nothing. Match the clause that only the alarming branch carries.
    assert "signature of crossover from a poor cochlea" in c["disagreements"][0]
    assert "mask and repeat" in c["disagreements"][0]


def test_measured_gaps_are_per_frequency_not_averaged():
    ac = {250: 60, 500: 30, 1000: 30, 2000: 30, 4000: 30}
    bc = {250: 30, 500: 30, 1000: 30, 2000: 30, 4000: 30}
    assert TF.measured_gaps(ac, bc)[250] == 30
    assert TF.measured_gaps(ac, bc)[500] == 0


def test_cross_check_without_bone_conduction_is_unavailable():
    ac = {f: 40 for f in (250, 500)}
    c = TF.cross_check(rinne("right", {500: "bc_louder"}), ac, {})
    assert c["available"] is False


# ===================================================================== API


def test_reference_endpoint_states_its_criteria():
    r = client.get("/api/tuning-fork/reference")
    assert r.status_code == 200
    body = r.json()
    assert len(body["forks"]) == 5
    assert body["rinne_forks"] == [250, 500, 1000]
    assert body["bing_forks"] == [250, 500]
    assert body["limits"] and body["citations"]


def test_analyze_endpoint_end_to_end():
    r = client.post("/api/tuning-fork/analyze", json={
        "right": {"responses": {"500": "bc_louder"}, "masked": True,
                  "otoscopy": "clear"},
        "left": {"responses": {"500": "ac_louder"}, "masked": True,
                 "otoscopy": "clear"},
        "weber": "right", "weber_freq": 500,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["grid"]["loss_type"] == "conductive"
    assert body["grid"]["side"] == "right"


def test_analyze_endpoint_with_thresholds_lets_the_audiogram_win():
    flat = {str(f): 20 for f in (250, 500, 1000, 2000, 4000)}
    r = client.post("/api/tuning-fork/analyze", json={
        "right": {"responses": {"500": "bc_louder"}, "masked": True,
                  "otoscopy": "clear"},
        "left": {"responses": {"500": "ac_louder"}, "masked": True,
                 "otoscopy": "clear"},
        "weber": "right", "weber_freq": 500,
        "right_thresholds": {"ac": flat, "bc": flat},
    })
    assert r.status_code == 200
    assert r.json()["grid"]["rule"] == "C8"


def test_no_output_ever_quotes_a_hearing_level():
    """The module may report a band of gap size, never a threshold in dB HL."""
    r = client.post("/api/tuning-fork/analyze", json={
        "right": {"responses": {"250": "bc_louder", "500": "bc_louder"},
                  "masked": True, "otoscopy": "clear"},
        "left": {"responses": {"500": "ac_louder"}, "masked": True,
                 "otoscopy": "clear"},
        "weber": "right", "weber_freq": 500,
    })
    body = r.json()
    text = str(body)
    # Positive control: the response DOES talk about dB, so a substring search
    # over it is capable of matching. Without this the assertion below could
    # pass simply because nothing in the payload mentions decibels at all.
    assert "dB" in text
    assert re.search(r"\d+\s*dB HL", text) is None
    assert "dB HL" not in text
    # And the permitted-output contract: a type, a side, a band — never a level.
    assert body["grid"]["loss_type"] in (
        None, "normal_or_symmetric", "sensorineural", "conductive",
        "conductive_bilateral", "mixed")


# ============================== the twelve cells, as an explicit expected map

#: Every cell of {positive, negative} x {positive, negative} x {R, L, midline},
#: with the rule that must fire. Written out rather than derived, so that a
#: change in the implementation has to be argued for here too.
TWELVE = {
    ("positive", "positive", "right"): "D2",
    ("positive", "positive", "left"): "D2",
    ("positive", "positive", "midline"): "D1",
    ("positive", "negative", "right"): "C1",     # Weber away from the negative
    ("positive", "negative", "left"): "D3",
    ("positive", "negative", "midline"): "D4",
    ("negative", "positive", "right"): "D3",
    ("negative", "positive", "left"): "C1",      # Weber away from the negative
    ("negative", "positive", "midline"): "D4",
    ("negative", "negative", "right"): "D6",
    ("negative", "negative", "left"): "D6",
    ("negative", "negative", "midline"): "D5",
}


def test_the_twelve_cells_map_to_exactly_the_expected_rules():
    """Completeness AND correctness: every cell, named, not merely non-empty."""
    actual = {}
    for r_sign, l_sign, lat in itertools.product(
            ("positive", "negative"), ("positive", "negative"),
            ("right", "left", "midline")):
        g = TF.combined_grid(rinne("right", {500: RESP[r_sign]}),
                             rinne("left", {500: RESP[l_sign]}), weber(lat))
        actual[(r_sign, l_sign, lat)] = g["rule"]
    assert actual == TWELVE


def test_the_two_contradiction_cells_are_exactly_the_weber_away_ones():
    """Not an arbitrary pair: they are the cells a conductive loss cannot make."""
    contradictions = {k for k, v in TWELVE.items() if v == "C1"}
    assert contradictions == {("positive", "negative", "right"),
                              ("negative", "positive", "left")}


# ============================================ censored thresholds ("NR")


def test_a_no_response_bone_threshold_yields_an_unknown_gap_not_a_negative_one():
    """NR computes as 120 dB HL elsewhere; subtracting it fabricates a gap."""
    ac = {250: 85, 500: 90, 1000: 95, 2000: 100, 4000: 105}
    bc = {f: "NR" for f in (250, 500, 1000, 2000, 4000)}
    gaps = TF.measured_gaps(ac, bc)
    assert all(g is None for g in gaps.values())
    assert not any((g or 0) < 0 for g in gaps.values())


def test_no_response_in_both_conductions_does_not_read_as_a_zero_gap():
    nr = {f: "NR" for f in (250, 500, 1000, 2000, 4000)}
    assert all(g is None for g in TF.measured_gaps(nr, nr).values())


def test_a_censored_gap_never_triggers_the_audiogram_override():
    """A dead ear must not have its conductive finding retracted on a fake 0 dB."""
    nr = {f: "NR" for f in (250, 500, 1000, 2000, 4000)}
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("right"),
                         measured_gap={"right": TF.measured_gaps(nr, nr)[500]})
    assert g["rule"] == "D3"
    assert "contradicted_by_audiogram" not in g["flags"]


# =================================== the override must not bury the other ear


def test_retracting_one_ear_does_not_hide_a_real_conductive_loss_in_the_other():
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "bc_louder"}), weber("left"),
                         measured_gap={"right": 0.0, "left": 40.0})
    assert g["loss_type"] == "conductive"
    assert g["side"] == "left"
    assert "contradicted_by_audiogram" in g["flags"]
    assert any("right" in n and "withdrawn" in n for n in g["notes"])


@pytest.mark.parametrize("gap,rule", [(9.0, "C8"), (10.0, "C8"), (11.0, "D3")])
def test_the_significance_boundary_matches_the_rest_of_the_codebase(gap, rule):
    """ABG > 10 dB is significant everywhere else; exactly 10 is not."""
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("right"),
                         measured_gap={"right": gap})
    assert g["rule"] == rule


# ============================================ the crossover is a band, not a point


def test_a_gap_inside_the_crossover_band_is_not_a_disagreement():
    """25 dB with a reversed 512 Hz Rinne is ordinary otosclerosis, not a dead ear."""
    ac = {f: 45 for f in (250, 500, 1000, 2000, 4000)}
    bc = {f: 20 for f in (250, 500, 1000, 2000, 4000)}
    c = TF.cross_check(rinne("right", {500: "bc_louder"}), ac, bc)
    row = next(r for r in c["rows"] if r["freq"] == 500)
    assert row["expected"] == "either"
    assert row["agrees"] is True
    assert c["disagreements"] == []


def test_the_band_upper_bound_governs_not_the_headline_crossover():
    """256 Hz is where the two differ: crossover_db is 15, the band runs to 20.

    A 17 dB gap sits inside the band, so a POSITIVE Rinne there is ordinary
    insensitivity rather than a contradiction. Judging against the bare 15 would
    call it a disagreement.
    """
    assert TF.FORKS[250]["crossover_db"] == 15
    assert TF.FORKS[250]["crossover_range"] == [15, 20]
    ac = {250: 37, 500: 20, 1000: 20, 2000: 20, 4000: 20}
    bc = {250: 20, 500: 20, 1000: 20, 2000: 20, 4000: 20}
    c = TF.cross_check(rinne("right", {250: "ac_louder"}), ac, bc)
    row = next(r for r in c["rows"] if r["freq"] == 250)
    assert row["measured_gap_db"] == 17
    assert row["expected"] == "either"
    assert row["agrees"] is True
    assert c["disagreements"] == []


def test_a_gap_below_the_whole_band_still_disagrees():
    ac = {f: 25 for f in (250, 500, 1000, 2000, 4000)}
    bc = {f: 20 for f in (250, 500, 1000, 2000, 4000)}
    c = TF.cross_check(rinne("right", {500: "bc_louder"}), ac, bc)
    assert c["disagreements"]


# ====================================================== the L2 warning rules


def test_bilateral_negative_lateralising_to_the_smaller_gap_is_flagged():
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "bc_louder"}), weber("right"),
                         measured_gap={"right": 20.0, "left": 45.0})
    assert "lateralises_to_lesser_gap" in g["flags"]
    assert any("SMALLER" in n for n in g["notes"])


def test_a_subjective_worse_ear_that_the_rinne_does_not_support_is_flagged():
    g = TF.combined_grid(rinne("right", {500: "ac_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("right"),
                         worse_ear_reported="right")
    assert "discordant_subjective" in g["flags"]
    assert any("Bing" in n for n in g["notes"])


# ========================================================= the L4 annotations


def test_a_negative_bing_under_a_positive_rinne_suggests_a_small_gap():
    """The one thing the Bing adds over the Rinne: it sees a smaller gap."""
    bing = {"right": TF.analyze_bing("right", "no_change", freq=250)}
    g = TF.combined_grid(rinne("right", {500: "ac_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("midline"),
                         bing=bing)
    assert "bing_suggests_small_gap" in g["flags"]
    assert any("below the reversal threshold" in n for n in g["notes"])


def test_a_positive_bing_under_a_negative_rinne_downgrades_the_conductive_call():
    bing = {"right": TF.analyze_bing("right", "louder", freq=250)}
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("right"),
                         bing=bing)
    assert "bing_disagrees" in g["flags"]
    assert any("provisional" in n.lower() for n in g["notes"])


def test_an_invalid_bing_contributes_no_annotation():
    """A 1024 Hz Bing is uninterpretable and must not colour the grid."""
    bing = {"right": TF.analyze_bing("right", "no_change", freq=1000)}
    g = TF.combined_grid(rinne("right", {500: "ac_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("midline"),
                         bing=bing)
    assert "bing_suggests_small_gap" not in g["flags"]


# ======================================================== D7 across both ears


def test_bilateral_reduced_reserve_reports_both_ears_as_mixed():
    res = lambda e: TF.analyze_bone_reference(e, abc="reduced",
                                              examiner_normal_hearing=True)
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "bc_louder"}), weber("midline"),
                         right_reserve=res("right"), left_reserve=res("left"))
    assert g["rule"] == "D7" and g["loss_type"] == "mixed"
    assert set(g["sides"]) == {"right", "left"}


def test_a_bilateral_conductive_picks_up_reserve_on_the_ear_weber_missed():
    """D6 names one side; the sensorineural component may be on the other."""
    res = TF.analyze_bone_reference("left", abc="reduced",
                                    examiner_normal_hearing=True)
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "bc_louder"}), weber("right"),
                         left_reserve=res)
    assert g["rule"] == "D7" and g["sides"] == ["left"]


def test_reserve_on_the_wrong_ear_of_a_unilateral_conductive_does_not_override():
    res = TF.analyze_bone_reference("left", abc="reduced",
                                    examiner_normal_hearing=True)
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "ac_louder"}), weber("right"),
                         left_reserve=res)
    assert g["rule"] == "D3" and g["loss_type"] == "conductive"


# ================================================ Weber gates and precedence


def test_an_off_midline_weber_suppresses_the_grid():
    g = TF.combined_grid(rinne("right", {500: "bc_louder"}),
                         rinne("left", {500: "ac_louder"}),
                         weber("right", site="left_mastoid"))
    assert g["rule"] == "C7" and g["available"] is False
    assert g["loss_type"] is None


def test_a_noisy_room_lowers_confidence_without_invalidating():
    w = weber("right", quiet_room=False)
    assert w["valid"] is True
    assert "ambient_noise" in w["flags"]


def test_1024_hz_weber_is_valid_but_flagged_low_confidence():
    w = weber("right", freq=1000)
    assert w["valid"] is True
    assert "low_confidence_frequency" in w["flags"]


def test_an_occluded_canal_outranks_a_frequency_mismatch():
    """G2 is a validity gate; C6 is only a warning. Precedence must hold."""
    r = rinne("right", {1000: "bc_louder"})              # wrong frequency
    l = rinne("left", {500: "ac_louder"}, otoscopy="obstructed")
    g = TF.combined_grid(r, l, weber("right", freq=500))
    assert g["rule"] == "G2" and g["level"] == "validity"


# ================================================ Bing and Gelle, both arms


def test_a_positive_bing_reads_as_intact_occlusion_effect():
    b = TF.analyze_bing("right", "louder", freq=250)
    assert b["result"] == "positive" and b["valid"] is True
    assert "conductive_pattern" not in b["flags"]


def test_a_negative_bing_is_the_conductive_pattern():
    b = TF.analyze_bing("right", "no_change", freq=250)
    assert b["result"] == "negative"
    assert "conductive_pattern" in b["flags"]


def test_a_positive_gelle_argues_against_stapes_fixation():
    g = TF.analyze_gelle("right", "quieter", freq=500)
    assert g["result"] == "positive" and g["valid"] is True
    assert "stapes_fixation_pattern" not in g["flags"]


def test_a_negative_gelle_is_the_fixation_pattern_and_asks_for_tympanometry():
    g = TF.analyze_gelle("right", "no_change", freq=500)
    assert g["result"] == "negative"
    assert "stapes_fixation_pattern" in g["flags"]
    assert "tympanometry" in g["interpretation"].lower()


def test_the_all_equivocal_bracket_is_not_reported_as_untested():
    b = TF.gap_bracket({f: "equivocal" for f in TF.RINNE_FORKS})
    assert b["label"] == "equivocal"
    assert "no usable fork was tested" not in b["statement"].lower()


# ============================================ safety propagates to the battery


def test_the_fistula_sign_reaches_the_battery_output():
    """analyze_gelle flagging it is not enough — the clinician must SEE it."""
    gelle = {"right": TF.analyze_gelle("right", "no_change", vertigo=True)}
    b = TF.tuning_fork_battery(
        right_rinne=rinne("right", {500: "ac_louder"}),
        left_rinne=rinne("left", {500: "ac_louder"}),
        weber=weber("midline"), gelle=gelle)
    assert b["urgent"], "a positive fistula sign vanished between the sub-test and the battery"
    assert "fistula" in b["urgent"][0].lower()
    assert "refer" in b["urgent"][0].lower()


def test_no_fistula_means_no_urgent_noise():
    gelle = {"right": TF.analyze_gelle("right", "no_change", freq=500)}
    b = TF.tuning_fork_battery(
        right_rinne=rinne("right", {500: "ac_louder"}),
        left_rinne=rinne("left", {500: "ac_louder"}),
        weber=weber("midline"), gelle=gelle)
    assert b["urgent"] == []


def test_the_api_carries_the_fistula_sign_through():
    r = client.post("/api/tuning-fork/analyze", json={
        "right": {"responses": {"500": "ac_louder"}, "masked": True, "otoscopy": "clear"},
        "left": {"responses": {"500": "ac_louder"}, "masked": True, "otoscopy": "clear"},
        "weber": "midline", "weber_freq": 500,
        "gelle": {"right": {"response": "no_change", "vertigo": True}},
    })
    assert r.status_code == 200
    assert r.json()["urgent"]
