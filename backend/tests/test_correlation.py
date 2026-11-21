"""Cross-modality correlations no single module could make.

``consistency.py`` sees immittance, reflexes, emissions and speech against the
audiogram. ``linkage.py`` sees the image against the history and the
thresholds. ``tuning_fork.py`` sees the forks against the audiogram. None of
them could see emissions against evoked potentials, an objective response
against a volunteered threshold, the otoscope against the emissions, the forks
against the tympanogram, or an infant's response level against a measured one
— so nobody was making those checks. These tests pin them, and pin the cases
where each must stay silent.
"""
import pytest
from fastapi.testclient import TestClient

from app.clinical import correlation as X
from app.clinical.boa import analyze_boa
from app.main import app

client = TestClient(app)


def analyse(record):
    response = client.post("/api/analyze", json=record)
    assert response.status_code == 200, response.text
    return response.json()


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


def emissions(present=True, freqs=(1000, 2000, 4000)):
    """A DP-gram clearly present or clearly absent in a quiet recording."""
    amplitude = 12 if present else -20
    return [{"freq": f, "amplitude": amplitude, "noise_floor": -14}
            for f in freqs]


def abr(status="normal", intensity=80, ear="right", interpretation=None):
    return {
        "battery": {"levels": [{
            "test": "ABR", "status": status,
            "ears": [{"ear": ear, "status": status,
                      "interpretation": interpretation}],
        }]},
        "recorded": {"abr": [{"ear": ear, "intensity_db_nhl": intensity}]},
    }


def kinds(result):
    return [f["kind"] for f in result["findings"]]


def titles(result):
    return " | ".join(f["title"] for f in result["findings"])


# ============================================ emissions <-> evoked potentials

def test_present_emissions_with_an_abnormal_abr_is_auditory_neuropathy():
    """The one configuration where the cochlea is fine and the nerve is not.

    Neither half says it alone: present emissions are reassuring on their own,
    and an abnormal ABR is usually explained by the loss that produced it.
    """
    analysis = analyse({
        "patient": {"name": "A", "age": 30},
        "right": {"ac": flat(50), "bc": flat(45, (250, 500, 1000, 2000, 4000)),
                  "oae": emissions(present=True)},
        "left": {"ac": flat(10)},
    })
    result = X.correlate_case(analysis=analysis,
                              aep=abr("abnormal", interpretation="retrocochlear"))
    assert "conflict" in kinds(result)
    assert "auditory neuropathy" in titles(result)
    finding = result["conflicts"][0]
    assert finding["tests"] == ["oae", "aep"]
    assert finding["side"] == "right"
    assert "neuro-otological" in finding["action"]


def test_a_normal_abr_with_present_emissions_says_nothing():
    """Two normal tests agreeing is not a finding this module reports."""
    analysis = analyse({
        "patient": {"name": "A", "age": 30},
        "right": {"ac": flat(10), "oae": emissions(present=True)},
        "left": {"ac": flat(10)},
    })
    assert X.correlate_case(analysis=analysis, aep=abr("normal"))["findings"] == []


def test_an_abnormal_abr_with_absent_emissions_is_not_neuropathy():
    """Absent emissions mean the cochlea may be the problem — the pattern needs
    a WORKING cochlea behind the bad nerve."""
    analysis = analyse({
        "patient": {"name": "A", "age": 30},
        "right": {"ac": flat(50), "bc": flat(45, (250, 500, 1000, 2000, 4000)),
                  "oae": emissions(present=False)},
        "left": {"ac": flat(10)},
    })
    result = X.correlate_case(analysis=analysis, aep=abr("abnormal"))
    assert "auditory neuropathy" not in titles(result)


def test_an_outcome_only_oae_screen_cannot_support_the_neuropathy_pattern():
    """A PASS is not per-frequency evidence of working outer hair cells."""
    analysis = analyse({
        "patient": {"name": "A", "age": 30},
        "right": {"ac": flat(50), "bc": flat(45, (250, 500, 1000, 2000, 4000)),
                  "oae": [], "oae_outcome": "pass"},
        "left": {"ac": flat(10)},
    })
    assert analysis["oae"]["right"]["entry_mode"] == "outcome"
    result = X.correlate_case(analysis=analysis, aep=abr("abnormal"))
    assert "auditory neuropathy" not in titles(result)


# ========================================= evoked potentials <-> behavioural

def test_a_normal_abr_below_the_volunteered_threshold_is_a_conflict():
    """An objective response better than the voluntary one is non-organic."""
    analysis = analyse({
        "patient": {"name": "B", "age": 40},
        "right": {"ac": flat(75), "bc": flat(70, (250, 500, 1000, 2000, 4000))},
        "left": {"ac": flat(10)},
    })
    result = X.correlate_case(analysis=analysis, aep=abr("normal", intensity=30))
    assert "conflict" in kinds(result)
    assert "normal at a level the audiogram says is inaudible" in titles(result)
    assert "do not certify" in result["conflicts"][0]["action"].lower()


def test_an_abr_recorded_near_the_behavioural_average_is_consistent():
    analysis = analyse({
        "patient": {"name": "B", "age": 40},
        "right": {"ac": flat(75), "bc": flat(70, (250, 500, 1000, 2000, 4000))},
        "left": {"ac": flat(10)},
    })
    result = X.correlate_case(analysis=analysis, aep=abr("normal", intensity=70))
    assert result["findings"] == []


def test_an_abnormal_abr_at_a_low_level_is_not_read_as_exaggeration():
    """That is what a real hearing loss produces.

    Reading it as an inconsistency would turn every genuine loss into a
    suspicion of non-organic hearing loss.
    """
    analysis = analyse({
        "patient": {"name": "B", "age": 40},
        "right": {"ac": flat(75), "bc": flat(70, (250, 500, 1000, 2000, 4000))},
        "left": {"ac": flat(10)},
    })
    result = X.correlate_case(analysis=analysis, aep=abr("abnormal", intensity=30))
    assert "inaudible" not in titles(result)


def test_a_no_response_average_is_not_compared_against_an_abr():
    """With an NR in it the behavioural figure is a floor, not a measurement."""
    analysis = analyse({
        "patient": {"name": "B", "age": 40},
        "right": {"ac": {250: 90, 500: 95, 1000: "NR", 2000: "NR", 4000: "NR",
                         8000: "NR"}},
        "left": {"ac": flat(10)},
    })
    result = X.correlate_case(analysis=analysis, aep=abr("normal", intensity=30))
    assert "inaudible" not in titles(result)


# =============================================== otoscopy <-> emissions

def absent_oae_case(gap=False):
    bc = flat(10, (250, 500, 1000, 2000, 4000)) if not gap \
        else flat(5, (250, 500, 1000, 2000, 4000))
    ac = flat(15) if not gap else flat(45)
    return analyse({
        "patient": {"name": "C", "age": 35},
        "right": {"ac": ac, "bc": bc, "oae": emissions(present=False,
                                                       freqs=(2000, 4000))},
        "left": {"ac": flat(10)},
    })


def otoscopy(label, side="right", confirmed=True):
    return {"side": side,
            "prediction": {"label": label, "name": label,
                           "kind": "clinician_confirmed" if confirmed
                           else "closest_reference_pattern"}}


def test_absent_emissions_behind_a_normal_drum_point_at_the_cochlea():
    result = X.correlate_case(analysis=absent_oae_case(),
                              otoscopy_ears={"right": otoscopy("normal")})
    assert "agreement" in kinds(result)
    assert "point at the cochlea" in titles(result)


def test_absent_emissions_behind_wax_are_explained_by_the_wax():
    """An emission has to travel out through the canal to be recorded."""
    result = X.correlate_case(
        analysis=absent_oae_case(),
        otoscopy_ears={"right": otoscopy("cerumen_impaction")})
    assert "note" in kinds(result)
    assert "explained by the ear canal" in titles(result)
    assert "not evidence of cochlear damage" in result["notes"][0]["detail"]


def test_a_perforation_also_explains_absent_emissions():
    result = X.correlate_case(
        analysis=absent_oae_case(),
        otoscopy_ears={"right": otoscopy("perforation_central")})
    assert "perforated drum" in result["notes"][0]["detail"]


def test_a_normal_drum_with_an_air_bone_gap_does_not_point_at_the_cochlea():
    """Something is blocking conduction even though the drum looks normal."""
    result = X.correlate_case(analysis=absent_oae_case(gap=True),
                              otoscopy_ears={"right": otoscopy("normal")})
    assert "point at the cochlea" not in titles(result)


def test_one_ear_s_image_is_never_read_against_the_other_ear_s_emissions():
    """The correctness fix the per-ear otoscopy store exists for."""
    analysis = absent_oae_case()          # absent emissions in the RIGHT ear
    left_image = otoscopy("normal", side="left")
    result = X.correlate_case(analysis=analysis,
                              otoscopy_ears={"left": left_image})
    assert result["findings"] == []


# =========================================== tuning forks <-> tympanometry

def fork_case(tymp):
    record = {
        "patient": {"name": "D", "age": 45},
        "right": {"ac": flat(45), "bc": flat(10, (250, 500, 1000, 2000, 4000)),
                  **tymp},
        "left": {"ac": flat(10)},
    }
    return analyse(record)


TYPE_A = {"tymp_pressure": -20, "tymp_compliance": 0.8, "tymp_ecv": 1.1}
TYPE_B = {"tymp_pressure": 0, "tymp_compliance": 0.02, "tymp_ecv": 1.0}


def test_conductive_forks_and_a_flat_trace_agree():
    result = X.correlate_case(
        analysis=fork_case(TYPE_B),
        tuning_fork={"grid": {"side": "right", "loss_type": "conductive"}})
    assert "agreement" in kinds(result)
    assert "not conducting" in titles(result)
    assert result["agreements"][0]["tests"] == ["tuning_fork", "immittance"]


def test_conductive_forks_against_a_normal_trace_is_a_conflict():
    """Both cannot describe the same ear — and the resolution is specific."""
    result = X.correlate_case(
        analysis=fork_case(TYPE_A),
        tuning_fork={"grid": {"side": "right", "loss_type": "conductive"}})
    assert "conflict" in kinds(result)
    finding = result["conflicts"][0]
    assert "masked" in finding["action"]
    # The two real explanations are named rather than left to the reader.
    assert "otosclerosis" in finding["action"]
    assert "third-window" in finding["detail"]


def test_an_infant_probe_trace_is_not_compared_against_the_forks():
    """A 1000 Hz infant outcome is not a Jerger type, so there is no pair."""
    result = X.correlate_case(
        analysis=fork_case(TYPE_A),
        tuning_fork={"grid": {"side": "right", "loss_type": "conductive"}})
    # Sanity: with a real Jerger type it DOES fire, so the guard below is
    # testing the infant case rather than a silent no-op.
    assert result["findings"]
    infant = {"immittance": {"right": {"tympanogram": {"type": "1k-no-peak"}}}}
    assert X.forks_vs_tympanometry(
        infant, {"grid": {"side": "right", "loss_type": "conductive"}}) == []


def test_forks_with_no_tympanogram_produce_nothing():
    analysis = fork_case({})
    result = X.correlate_case(
        analysis=analysis,
        tuning_fork={"grid": {"side": "right", "loss_type": "conductive"}})
    assert "tuning_fork" not in [t for f in result["findings"] for t in f["tests"]]


# ============================================ behavioural observation <-> PTA

def test_a_response_level_better_than_the_threshold_is_impossible():
    """An MRL sits tens of dB ABOVE threshold, never below it."""
    analysis = analyse({
        "patient": {"name": "E", "age": 1},
        "right": {"ac": flat(75)}, "left": {"ac": flat(75)},
    })
    boa = analyze_boa(age_months=4, observed_level_db_spl=30,
                      responses=["startle"], observers=1, presentations=3)
    result = X.correlate_case(analysis=analysis, boa=boa)
    assert "conflict" in kinds(result)
    assert "better than the measured threshold" in titles(result)
    # The scale mismatch is part of the finding, not a separate caveat.
    assert "dB SPL" in result["conflicts"][0]["detail"]


def test_a_plausible_response_level_is_not_flagged():
    analysis = analyse({
        "patient": {"name": "E", "age": 1},
        "right": {"ac": flat(75)}, "left": {"ac": flat(75)},
    })
    boa = analyze_boa(age_months=4, observed_level_db_spl=95,
                      responses=["startle"], observers=1, presentations=3)
    assert X.correlate_case(analysis=analysis, boa=boa)["findings"] == []


# ============================================================ the whole case

def test_nothing_is_inferred_from_a_missing_test():
    """Every check needs its inputs; none reads absence as a normal result."""
    assert X.correlate_case()["available"] is False
    assert X.correlate_case(analysis=None, aep=abr("abnormal"))["findings"] == []
    analysis = analyse({"patient": {"name": "F", "age": 30},
                        "right": {"ac": flat(40)}, "left": {"ac": flat(40)}})
    assert X.correlate_case(analysis=analysis)["findings"] == []


def test_conflicts_are_reported_before_agreements():
    """Two measurements that cannot both be true is the finding."""
    analysis = analyse({
        "patient": {"name": "G", "age": 45},
        "right": {"ac": flat(45), "bc": flat(10, (250, 500, 1000, 2000, 4000)),
                  **TYPE_A},
        "left": {"ac": flat(10)},
    })
    result = X.correlate_case(
        analysis=analysis,
        tuning_fork={"grid": {"side": "right", "loss_type": "conductive"}})
    assert result["conflict_count"] == 1
    assert "disagreement" in result["headline"]


def test_every_finding_names_the_two_tests_behind_it():
    """A cross-test finding is only actionable if you know which pair it is."""
    analysis = analyse({
        "patient": {"name": "H", "age": 30},
        "right": {"ac": flat(50), "bc": flat(45, (250, 500, 1000, 2000, 4000)),
                  "oae": emissions(present=True)},
        "left": {"ac": flat(10)},
    })
    result = X.correlate_case(analysis=analysis, aep=abr("abnormal"))
    for finding in result["findings"]:
        assert len(finding["tests"]) == 2, finding
        assert finding["title"] and finding["detail"] and finding["action"]


# ========================================= it reaches the diagnostic picture

def test_the_cross_checks_reach_the_diagnostic_picture():
    """Folded into convergence so they can change the confidence rating.

    A panel of its own that nobody reads is not a cross-check.
    """
    analysis = analyse({
        "patient": {"name": "I", "age": 30},
        "right": {"ac": flat(50), "bc": flat(45, (250, 500, 1000, 2000, 4000)),
                  "oae": emissions(present=True)},
        "left": {"ac": flat(10)},
    })
    picture = client.post("/api/diagnosis/picture", json={
        "analysis": analysis, "aep": abr("abnormal", interpretation="retrocochlear"),
        "age_months": 360,
    }).json()
    assert picture["cross_test"]["available"] is True
    assert picture["cross_test"]["conflict_count"] >= 1
    # The sentence is in the convergence list the confidence rating reads.
    assert any("auditory neuropathy" in str(c).lower()
               or "outer hair cells" in str(c).lower()
               for c in picture["conflicts"])


def test_the_picture_takes_otoscopy_per_ear():
    analysis = absent_oae_case()
    picture = client.post("/api/diagnosis/picture", json={
        "analysis": analysis,
        "otoscopy_ears": {"right": otoscopy("cerumen_impaction"), "left": None},
        "age_months": 420,
    }).json()
    titles_seen = " | ".join(f["title"] for f in picture["cross_test"]["findings"])
    assert "explained by the ear canal" in titles_seen


def test_a_malformed_sub_payload_costs_a_line_not_the_panel():
    """The picture aggregates several independently-evolving payloads."""
    analysis = analyse({"patient": {"name": "J", "age": 30},
                        "right": {"ac": flat(40)}, "left": {"ac": flat(40)}})
    response = client.post("/api/diagnosis/picture", json={
        "analysis": analysis, "aep": {"battery": "not a dict"},
        "age_months": 360,
    })
    assert response.status_code == 200
    assert response.json()["coverage"]
