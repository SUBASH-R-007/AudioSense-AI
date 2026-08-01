"""Masking: the two AC rules, the BC rule, the transducer, and the dilemma."""
import pytest
from fastapi.testclient import TestClient

from app.clinical import masking as M
from app.main import app
from app.models.schemas import EarData

client = TestClient(app)

AC = [250, 500, 1000, 2000, 4000, 8000]
BC = [250, 500, 1000, 2000, 4000]


def ac(level):
    return {f: level for f in AC}


def bc(level):
    return {f: level for f in BC}


def ear(a, b=None, masked=False):
    return EarData(ac=ac(a), bc=bc(a if b is None else b), masked=masked)


# ============================================== air conduction, two rules

def test_rule_one_fires_on_the_air_to_air_difference():
    """AC(TE) - AC(NTE) >= IA."""
    result = M.ac_masking_required(ac_te=70, ac_nte=25, bc_nte=25, ia=40)
    rule = next(r for r in result["rules"] if r["rule"].startswith("AC(TE) − AC"))
    assert rule["met"] is True and rule["value"] == 45
    assert result["required"] is True


def test_rule_two_fires_when_rule_one_does_not():
    """The case rule 1 alone misses: a conductive loss in the NON-test ear.

    Air thresholds differ by only 30 dB, but the crossed signal has to clear
    the opposite ear's BONE threshold, which is 45 dB below the test ear.
    """
    result = M.ac_masking_required(ac_te=70, ac_nte=40, bc_nte=25, ia=40)
    by_air = next(r for r in result["rules"] if r["rule"].startswith("AC(TE) − AC"))
    by_bone = next(r for r in result["rules"] if r["rule"].startswith("AC(TE) − BC"))
    assert by_air["met"] is False
    assert by_bone["met"] is True
    assert result["required"] is True


def test_no_masking_below_the_crossover():
    result = M.ac_masking_required(ac_te=40, ac_nte=25, bc_nte=25, ia=40)
    assert result["required"] is False


def test_the_rule_is_inclusive_at_the_interaural_attenuation():
    """The reference writes >=, not >."""
    assert M.ac_masking_required(65, 25, 25, ia=40)["required"] is True   # exactly 40
    assert M.ac_masking_required(64, 25, 25, ia=40)["required"] is False  # 39


def test_an_untested_frequency_is_not_a_masking_decision():
    assert M.ac_masking_required(None, 20, 20, ia=40)["testable"] is False


# ================================================== transducer changes it

def test_inserts_move_the_crossover_and_remove_the_requirement():
    """The single choice that decides how much masking a clinic has to do."""
    supra = M.transducer_spec("supra_aural")["ia_ac"]
    insert = M.transducer_spec("insert")["ia_ac"]
    assert insert > supra
    assert M.ac_masking_required(70, 25, 25, ia=supra)["required"] is True
    assert M.ac_masking_required(70, 25, 25, ia=insert)["required"] is False


def test_every_transducer_declares_its_attenuation_and_occlusion():
    for key, spec in M.TRANSDUCERS.items():
        assert spec["ia_ac"] > 0
        assert spec["ia_range"][0] <= spec["ia_ac"] <= spec["ia_range"][1]
        assert set(spec["occlusion"]) == set(AC)
        # The occlusion effect is a low-frequency phenomenon; it vanishes by 2 kHz.
        assert spec["occlusion"][2000] == 0
        assert spec["occlusion"][250] >= spec["occlusion"][1000]


def test_an_unknown_transducer_falls_back_rather_than_failing():
    assert M.transducer_spec("nonsense")["ia_ac"] == \
        M.TRANSDUCERS[M.DEFAULT_TRANSDUCER]["ia_ac"]


# ============================================================ bone conduction

def test_bc_masking_at_the_fifteen_decibel_gap():
    assert M.bc_masking_required(ac_te=45, bc_unmasked=30)["required"] is True   # 15
    assert M.bc_masking_required(ac_te=44, bc_unmasked=30)["required"] is False  # 14


def test_the_bc_gap_is_reported_with_the_decision():
    result = M.bc_masking_required(ac_te=55, bc_unmasked=25)
    assert result["abg"] == 30
    assert all(r["threshold"] == M.BC_MASKING_GAP_DB for r in result["rules"])


def test_bone_conduction_crosses_the_skull_unattenuated():
    assert M.INTERAURAL_ATTENUATION_BC == 0


def test_bc_masking_needs_both_measurements():
    assert M.bc_masking_required(ac_te=50, bc_unmasked=None)["testable"] is False


# ============================================================ the dilemma

def test_a_bilateral_conductive_loss_leaves_no_usable_masking_level():
    """The floor rises above the ceiling and the threshold cannot be masked."""
    plan = M.masking_plan(ac(75), bc(15), ac(75), bc(15),
                          transducer="supra_aural", masked=False)
    assert plan["has_dilemma"] is True
    assert plan["dilemma_freqs"]
    assert any("cannot be masked" in r for r in plan["reasons"])


def test_inserts_resolve_a_moderate_dilemma_that_supra_aurals_create():
    """The reason the transducer choice is clinical rather than logistical.

    A 35 dB bilateral air-bone gap is unmaskable on supra-aural earphones at
    the low frequencies and entirely maskable on inserts — higher interaural
    attenuation raises the ceiling and a smaller occlusion effect lowers the
    floor, and both work in the same direction.
    """
    supra = M.masking_plan(ac(50), bc(15), ac(50), bc(15), "supra_aural")
    insert = M.masking_plan(ac(50), bc(15), ac(50), bc(15), "insert")
    assert supra["dilemma_freqs"] == [250, 500, 1000]
    assert insert["dilemma_freqs"] == []


def test_a_severe_bilateral_gap_defeats_inserts_too():
    """Honest about the limit: inserts help, they are not a cure.

    At a 60 dB gap there is no usable masking level with either transducer,
    and reporting one would be inventing a threshold.
    """
    supra = M.masking_plan(ac(75), bc(15), ac(75), bc(15), "supra_aural")
    insert = M.masking_plan(ac(75), bc(15), ac(75), bc(15), "insert")
    assert supra["has_dilemma"] is True
    assert insert["has_dilemma"] is True


def test_a_normal_ear_has_no_dilemma():
    plan = M.masking_plan(ac(15), bc(15), ac(15), bc(15), "supra_aural")
    assert plan["has_dilemma"] is False
    assert plan["masking_indicated"] is False


def test_the_plateau_is_reported_when_one_exists():
    plan = M.masking_plan(ac(70), bc(65), ac(10), bc(10), "supra_aural")
    row = next(r for r in plan["rows"] if r["ac_levels"])
    levels = row["ac_levels"]
    assert levels["minimum"] is not None and levels["maximum"] is not None
    assert levels["plateau_width"] == levels["maximum"] - levels["minimum"]


# ================================================================ the plan

def test_the_plan_covers_every_audiometric_frequency():
    plan = M.masking_plan(ac(70), bc(65), ac(10), bc(10), "supra_aural")
    assert [r["freq"] for r in plan["rows"]] == AC


def test_a_warning_only_when_masking_was_indicated_and_not_recorded():
    unmasked = M.masking_plan(ac(70), bc(65), ac(10), bc(10), "supra_aural",
                              masked=False)
    masked = M.masking_plan(ac(70), bc(65), ac(10), bc(10), "supra_aural",
                            masked=True)
    assert unmasked["warning"] is True and unmasked["message"]
    assert masked["warning"] is False and masked["message"] is None
    # Still indicated either way — recording it does not remove the need.
    assert masked["masking_indicated"] is True


def test_the_reason_names_which_rule_fired():
    """Rule 2 alone tells the clinician something about the opposite ear."""
    plan = M.masking_plan(ac(70), bc(70), ac(40), bc(25), "supra_aural")
    assert any("only the AC−BC rule fires" in r for r in plan["reasons"])


def test_the_review_covers_both_ears_with_one_transducer():
    review = M.masking_review(ear(70, 65), ear(10), "insert")
    assert review["right"]["transducer"]["key"] == "insert"
    assert review["left"]["transducer"]["key"] == "insert"
    assert review["headline"]


def test_the_headline_leads_with_the_dilemma_over_the_warning():
    review = M.masking_review(ear(75, 15), ear(75, 15), "supra_aural")
    assert review["any_dilemma"] is True
    assert "dilemma" in review["headline"].lower()


def test_a_normal_test_says_no_masking_is_required():
    review = M.masking_review(ear(15), ear(15), "supra_aural")
    assert review["any_indicated"] is False
    assert "No masking required" in review["headline"]


# =============================================================== endpoints

def test_the_endpoint_returns_a_plan_for_both_ears():
    body = client.post("/api/masking/analyze", json={
        "transducer": "supra_aural",
        "right": {"ac": ac(70), "bc": bc(65)},
        "left": {"ac": ac(10), "bc": bc(10)},
    }).json()
    assert body["right"]["masking_indicated"] is True
    assert body["left"]["masking_indicated"] is False


def test_the_reference_endpoint_states_both_rule_sets():
    body = client.get("/api/masking/reference").json()
    assert len(body["rules"]["air_conduction"]) == 2
    assert len(body["rules"]["bone_conduction"]) == 2
    assert {t["key"] for t in body["transducers"]} == set(M.TRANSDUCERS)


# ============================================= integration with the pipeline

def record(right_ac, right_bc, left_ac, left_bc, transducer="supra_aural"):
    return {"patient": {"name": "T", "age": 40}, "transducer": transducer,
            "right": {"ac": ac(right_ac), "bc": bc(right_bc)},
            "left": {"ac": ac(left_ac), "bc": bc(left_bc)}}


def test_analyze_carries_the_masking_review():
    body = client.post("/api/analyze", json=record(70, 65, 10, 10)).json()
    assert body["safety"]["masking"]["right"]["masking_indicated"] is True
    assert body["safety"]["masking_review"]["headline"]


def test_the_transducer_on_the_record_changes_the_analysis():
    """Same thresholds, different earphones, different answer."""
    supra = client.post("/api/analyze",
                        json=record(65, 65, 20, 20, "supra_aural")).json()
    insert = client.post("/api/analyze",
                         json=record(65, 65, 20, 20, "insert")).json()
    assert supra["safety"]["masking"]["right"]["masking_indicated"] is True
    assert insert["safety"]["masking"]["right"]["masking_indicated"] is False


def test_a_masking_dilemma_raises_a_validity_alert():
    body = client.post("/api/analyze", json=record(75, 15, 75, 15)).json()
    assert any("Masking dilemma" in a["title"] for a in body["safety"]["alerts"])


def test_a_record_without_a_transducer_still_analyses():
    """The field is optional and defaults to the least forgiving transducer."""
    body = client.post("/api/analyze", json={
        "patient": {"name": "T", "age": 40},
        "right": {"ac": ac(20), "bc": bc(20)},
        "left": {"ac": ac(20), "bc": bc(20)},
    }).json()
    assert body["safety"]["masking"]["right"]["transducer"]["key"] == "supra_aural"
