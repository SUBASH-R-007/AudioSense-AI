"""The complete diagnostic picture: coverage, convergence, and the next test."""
import pytest
from fastapi.testclient import TestClient

from app.clinical import diagnosis as D
from app.main import app

client = TestClient(app)

AC = [250, 500, 1000, 2000, 4000, 8000]
BC = [250, 500, 1000, 2000, 4000]


def analyze(right_ac, right_bc=None, left_ac=25, left_bc=25, age=40, **extra):
    """Run a record through /api/analyze and hand back the response."""
    def ear(a, b):
        d = {"ac": {f: a for f in AC}}
        if b is not None:
            d["bc"] = {f: b for f in BC}
        return d
    body = {"patient": {"name": "T", "age": age, "sex": "male"},
            "right": ear(right_ac, right_bc), "left": ear(left_ac, left_bc)}
    for k, v in extra.items():
        body[k] = v
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def picture(**kw):
    r = client.post("/api/diagnosis/picture", json=kw)
    assert r.status_code == 200, r.text
    return r.json()


def named(p):
    return [g["test"] for g in p["next_tests"]]


def critical(p):
    return [g["test"] for g in p["next_tests"] if g["priority"] == "critical"]


# ================================================================ coverage


def test_an_empty_request_is_answered_honestly_rather_than_refused():
    p = picture()
    assert p["confidence"] == "insufficient"
    assert p["performed"] == 0
    assert "nothing yet to interpret" in p["verdict"]


def test_coverage_counts_every_modality_in_the_battery():
    p = picture(analysis=analyze(45, 15))
    assert p["total"] == len(D.MODALITIES) == 11
    assert len(p["coverage"]) == 11
    assert {c["key"] for c in p["coverage"]} == {m["key"] for m in D.MODALITIES}


def test_pure_tones_alone_register_as_performed():
    p = picture(analysis=analyze(30, 30))
    done = {c["key"]: c["performed"] for c in p["coverage"]}
    assert done["pure_tone"] is True
    assert done["tympanometry"] is False
    assert done["symptoms"] is False


def test_history_and_otoscopy_are_essential_and_reported_missing():
    p = picture(analysis=analyze(30, 30))
    assert "History and symptoms" in p["essential_missing"]
    assert "Otoscopy" in p["essential_missing"]


# ============================================================== next tests


def test_a_conductive_loss_without_immittance_demands_tympanometry():
    """An air-bone gap says the middle ear fails; only immittance says why."""
    p = picture(analysis=analyze(50, 15))
    assert "Tympanometry" in critical(p)
    g = next(x for x in p["next_tests"] if x["test"] == "Tympanometry")
    assert "air-bone gap" in g["because"]


def test_a_conductive_loss_without_otoscopy_demands_a_look_in_the_ear():
    p = picture(analysis=analyze(50, 15))
    assert "Otoscopy" in critical(p)


def test_a_symmetric_sensorineural_loss_does_not_demand_tympanometry():
    """No gap, no mechanism to explain — asking for immittance would be noise."""
    p = picture(analysis=analyze(45, 45, left_ac=45, left_bc=45))
    assert "Tympanometry" not in critical(p)


def test_a_sensorineural_loss_recommends_emissions():
    p = picture(analysis=analyze(45, 45, left_ac=45, left_bc=45))
    assert "Otoacoustic emissions" in named(p)


def test_an_ac_only_sensorineural_loss_still_recommends_emissions():
    """BC untested types the ear "Sensorineural (provisional)".

    That is the ear that most needs emissions, not least — but the rule
    matched the bare literal, so the least-worked-up ear was the one the
    recommendation was withheld from.
    """
    a = analyze(45, None, left_ac=45, left_bc=None)
    assert a["rules"]["right"]["type"] == "Sensorineural (provisional)", (
        "the test no longer exercises the provisional path")
    assert "Otoacoustic emissions" in named(picture(analysis=a))


def test_an_asymmetric_loss_demands_an_abr():
    """The unexcluded vestibular schwannoma is the point of this rule."""
    p = picture(analysis=analyze(60, 60, left_ac=15, left_bc=15))
    assert any("brainstem response" in t for t in critical(p))


def test_a_normal_symmetric_audiogram_raises_no_critical_test_beyond_history():
    p = picture(analysis=analyze(10, 10, left_ac=10, left_bc=10),
                assessment={"differential": [{"name": "None"}]},
                otoscopy={"differential": [{"label": "Normal"}]})
    assert critical(p) == []


def test_any_loss_recommends_speech_audiometry():
    p = picture(analysis=analyze(45, 45, left_ac=45, left_bc=45))
    assert any("Speech audiometry" in t for t in named(p))


def test_normal_thresholds_still_recommend_emissions_for_preclinical_damage():
    p = picture(analysis=analyze(10, 10, left_ac=10, left_bc=10))
    assert "Otoacoustic emissions" in named(p)


def test_the_next_tests_are_ordered_critical_first():
    p = picture(analysis=analyze(50, 15))
    order = [g["priority"] for g in p["next_tests"]]
    rank = {"critical": 0, "recommended": 1, "optional": 2}
    assert order == sorted(order, key=lambda x: rank[x])


def test_no_test_is_recommended_twice():
    p = picture(analysis=analyze(60, 20, left_ac=15, left_bc=15))
    names = named(p)
    assert len(names) == len(set(names))


# ================================================================ infants


def test_an_infant_under_six_months_is_routed_to_objective_testing():
    p = picture(analysis=analyze(30, 30), age_months=3)
    assert any("ABR" in t or "ASSR" in t for t in critical(p))
    g = next(g for g in p["next_tests"] if "ABR" in g["test"])
    assert "3 months old" in g["because"]


def test_an_older_child_is_not_routed_to_abr_on_age_alone():
    p = picture(analysis=analyze(30, 30), age_months=24)
    assert not any("ASSR" in t for t in critical(p))


# ====================================== a completed battery stops nagging


def full_workup():
    """Every essential modality present, symmetric mild sensorineural loss."""
    an = analyze(30, 30, left_ac=30, left_bc=30)
    return dict(
        analysis=an,
        assessment={"differential": [{"name": "Presbycusis"}], "red_flags": []},
        otoscopy={"differential": [{"label": "Normal"}], "urgency": "routine"},
    )


def test_a_complete_battery_reports_no_critical_gap():
    p = picture(**full_workup())
    assert critical(p) == []
    assert p["confidence"] in ("provisional", "adequate", "corroborated")


def test_confidence_never_claims_completeness_while_a_critical_test_is_open():
    p = picture(analysis=analyze(50, 15))
    assert p["confidence"] == "incomplete"
    assert p["confidence"] not in ("adequate", "corroborated")


# ============================================================== findings


def test_each_performed_modality_contributes_one_line():
    p = picture(**full_workup())
    keys = {f["key"] for f in p["findings"]}
    assert {"symptoms", "otoscopy", "pure_tone"} <= keys


def test_a_red_flag_in_the_history_raises_an_alarm():
    p = picture(analysis=analyze(30, 30),
                assessment={"differential": [{"name": "X"}],
                            "red_flags": [{"title": "Sudden onset"}]})
    assert "History and symptoms" in p["alarms"]


def test_the_pure_tone_line_names_both_ears():
    p = picture(analysis=analyze(50, 15, left_ac=20, left_bc=20))
    line = next(f for f in p["findings"] if f["key"] == "pure_tone")["says"]
    assert "right" in line and "left" in line


# =========================================== convergence with the forks


def fork_result(loss_type, side, level="grid", rule="D3"):
    return {"grid": {"loss_type": loss_type, "side": side, "level": level,
                     "rule": rule, "headline": f"{loss_type} in the {side} ear."}}


def test_forks_agreeing_with_the_audiogram_count_as_corroboration():
    p = picture(analysis=analyze(50, 15),
                tuning_fork=fork_result("conductive", "right"))
    assert any("independent measurements" in a for a in p["agreements"])


def test_forks_disagreeing_with_the_audiogram_are_reported_as_a_conflict():
    """Forks say conductive where the audiogram says sensorineural."""
    p = picture(analysis=analyze(50, 50, left_ac=50, left_bc=50),
                tuning_fork=fork_result("conductive", "right"))
    assert any("recheck the forks" in c for c in p["conflicts"])


def test_a_fork_contradiction_propagates_into_the_picture():
    p = picture(analysis=analyze(50, 15),
                tuning_fork=fork_result("conductive", "right",
                                        level="contradiction", rule="C1"))
    assert any("tuning forks" in c for c in p["conflicts"])


def test_a_conflict_is_never_reported_as_corroborated():
    p = picture(**full_workup(),
                tuning_fork=fork_result("conductive", "right",
                                        level="contradiction", rule="C1"))
    assert p["confidence"] == "conflicted"
    assert "do not all agree" in p["verdict"]


# ============================================================ the caveat


def test_the_response_states_that_coverage_is_not_accuracy():
    p = picture(**full_workup())
    assert "not accuracy" in p["caveat"]
    assert "audiologist" in p["caveat"]


def test_no_disease_is_ever_named_by_this_module():
    """Naming diseases belongs to symptom_kb; this module reports type and side.

    The one permitted mention is the vestibular schwannoma, and only as the
    thing an ABR is ordered to EXCLUDE — never as a finding.

    This assertion used to be `not blob.startswith(disease)` against a blob
    that always began with the first recommendation's name, so it could not
    fire; the module could name diseases outright and the test still passed.
    It also ran one bilateral conductive case, which never reaches the rule
    whose text mentions a condition at all.
    """
    cases = [
        picture(analysis=analyze(50, 15)),                            # conductive
        picture(analysis=analyze(45, 45, left_ac=45, left_bc=45)),    # symmetric SN
        picture(analysis=analyze(60, 60, left_ac=15, left_bc=15)),    # asymmetric SN
        picture(analysis=analyze(30, 30), age_months=3),              # infant
    ]
    for p in cases:
        blob = " ".join(f'{g["test"]} {g["why"]}' for g in p["next_tests"]).lower()
        for disease in ("otosclerosis", "cholesteatoma", "meniere",
                        "otitis media", "presbycusis"):
            assert disease not in blob, f"{disease} named in a recommendation"
        if "schwannoma" in blob:
            assert "unexcluded vestibular schwannoma until imaging" in blob, (
                "the schwannoma may appear only as the thing being excluded")


# ================================================================== API


def test_reference_endpoint_states_the_battery_and_its_criteria():
    r = client.get("/api/diagnosis/reference")
    assert r.status_code == 200
    body = r.json()
    assert len(body["modalities"]) == 11
    assert body["significant_abg_db"] == 10
    assert body["infant_months"] == 6
    assert len(body["confidence_levels"]) == 6
    assert body["citations"]


def test_picture_endpoint_accepts_a_partial_workup():
    r = client.post("/api/diagnosis/picture", json={"analysis": analyze(50, 15)})
    assert r.status_code == 200
    assert r.json()["confidence"] == "incomplete"


def test_picture_endpoint_tolerates_unknown_shaped_payloads():
    """A caller passing a half-built otoscopy result must not 500."""
    r = client.post("/api/diagnosis/picture", json={
        "analysis": analyze(30, 30), "otoscopy": {}, "aep": {}, "boa": {},
        "tuning_fork": {}, "assessment": {}})
    assert r.status_code == 200


# ============================ against the REAL payloads, not guessed ones

# The first version of this module read otoscopy's `urgency` as a string and
# `differential[].label` as the display name. Both guesses were wrong — urgency
# is a ranked {key, name, probability} object — and because the tests used the
# same guesses, they passed while the live dashboard 500'd. These tests build
# their inputs by calling the real endpoints.


def real_symptoms():
    r = client.post("/api/symptoms/analyze", json={
        "age": 40, "side": "right", "symptoms": ["ear_discharge"],
        "free_text": "water keeps coming out of my ear"})
    assert r.status_code == 200
    return r.json()


def real_otoscopy():
    import glob
    paths = sorted(glob.glob("data/otoscope_reference/*/*.jpg"))
    if not paths:
        pytest.skip("reference atlas not present")
    with open(paths[0], "rb") as f:
        r = client.post("/api/otoscopy/analyze",
                        files={"file": ("a.jpg", f, "image/jpeg")},
                        data={"side": "right"})
    assert r.status_code == 200
    return r.json()


def test_a_real_otoscopy_payload_does_not_break_the_picture():
    p = picture(analysis=analyze(50, 15), otoscopy=real_otoscopy())
    assert p["confidence"] != "insufficient"
    line = next(f for f in p["findings"] if f["key"] == "otoscopy")
    assert line["says"] != "Image recorded."      # the name was actually read
    assert isinstance(line["alarm"], bool)


def test_a_real_otoscopy_payload_closes_the_otoscopy_gap():
    p = picture(analysis=analyze(50, 15), otoscopy=real_otoscopy())
    assert "Otoscopy" not in critical(p)
    assert "Otoscopy" not in p["essential_missing"]


def test_a_real_symptoms_payload_is_summarised_by_name():
    p = picture(analysis=analyze(50, 15), assessment=real_symptoms())
    line = next(f for f in p["findings"] if f["key"] == "symptoms")
    assert "Leading possibility:" in line["says"]
    assert "{" not in line["says"]                # not a dict stringified in


def test_a_real_full_workup_reaches_a_non_incomplete_confidence():
    p = picture(analysis=analyze(30, 30, left_ac=30, left_bc=30),
                assessment=real_symptoms(), otoscopy=real_otoscopy())
    assert critical(p) == []
    assert p["confidence"] != "incomplete"


@pytest.mark.parametrize("urgency,expected", [
    ({"key": "urgent", "name": "Urgent — see ENT"}, True),
    ({"key": "routine", "name": "Routine"}, False),
    ("emergency", True),
    ("routine", False),
    (None, False),
    (["not", "a", "shape"], False),
])
def test_urgency_is_read_whatever_shape_it_arrives_in(urgency, expected):
    assert D._urgent(urgency) is expected


@pytest.mark.parametrize("payload", [
    {"urgency": {"key": "routine"}, "differential": [{"name": "Normal"}]},
    {"urgency": "routine", "differential": [{"label": "normal"}]},
    {"differential": []},
    {"differential": [{}]},
    {},
])
def test_no_otoscopy_shape_can_500_the_endpoint(payload):
    r = client.post("/api/diagnosis/picture",
                    json={"analysis": analyze(50, 15), "otoscopy": payload})
    assert r.status_code == 200


def test_a_hostile_payload_degrades_instead_of_failing():
    """Coverage and the next test must survive a sub-payload it cannot read."""
    r = client.post("/api/diagnosis/picture", json={
        "analysis": analyze(50, 15),
        "otoscopy": {"differential": "not-a-list", "urgency": 42}})
    assert r.status_code == 200
    body = r.json()
    assert "Tympanometry" in [g["test"] for g in body["next_tests"]]
    assert body["performed"] >= 1


# ======================= skipping changes the prompt, never the result

# A clinic without a tympanometer must be able to say so once instead of being
# asked at every visit. What must NOT happen is a skip quietly reading as a
# normal result: "not performed" and "performed and normal" are different
# clinical facts and the interpretation has to keep telling them apart.


def test_a_skipped_test_is_still_counted_as_not_performed():
    an = analyze(50, 15)
    plain = picture(analysis=an)
    with_skip = picture(analysis=an, skipped={"tympanometry": "No tympanometer"})
    done = {c["key"]: c["performed"] for c in with_skip["coverage"]}
    assert done["tympanometry"] is False
    assert plain["performed"] == with_skip["performed"]


def test_skipping_does_not_change_the_verdict_or_the_confidence():
    an = analyze(50, 15)
    plain = picture(analysis=an)
    with_skip = picture(analysis=an, skipped={"tympanometry": "No tympanometer"})
    assert plain["confidence"] == with_skip["confidence"]
    assert plain["verdict"] == with_skip["verdict"]


def test_skipping_does_not_change_agreements_or_conflicts():
    an = analyze(50, 15)
    plain = picture(analysis=an)
    with_skip = picture(analysis=an,
                        skipped={"tympanometry": "x", "otoscopy": "y",
                                 "oae": "z", "aep": "w"})
    assert plain["agreements"] == with_skip["agreements"]
    assert plain["conflicts"] == with_skip["conflicts"]


def test_skipping_does_not_remove_the_recommendation():
    """The gap is still a gap; only its framing gains the skip."""
    an = analyze(50, 15)
    with_skip = picture(analysis=an, skipped={"tympanometry": "No tympanometer"})
    assert "Tympanometry" in critical(with_skip)


def test_a_skip_that_has_become_critical_is_named():
    p = picture(analysis=analyze(50, 15),
                skipped={"tympanometry": "Equipment not available"})
    assert p["reconsider"], "a skipped test that became critical must be surfaced"
    line = p["reconsider"][0]
    assert "Tympanometry" in line
    assert "Equipment not available" in line
    assert "now makes it critical" in line


def test_a_skip_that_never_became_critical_is_not_nagged_about():
    """Symmetric normal hearing: skipping emissions raises nothing."""
    p = picture(analysis=analyze(10, 10, left_ac=10, left_bc=10),
                assessment={"differential": [{"name": "None"}]},
                otoscopy={"differential": [{"name": "Normal"}]},
                skipped={"oae": "Not indicated"})
    assert p["reconsider"] == []


def test_unknown_skip_keys_are_ignored_rather_than_echoed():
    """The client's step keys and the backend's modality keys are not identical."""
    p = picture(analysis=analyze(30, 30),
                skipped={"not_a_modality": "x", "otoscopy": "No otoscope"})
    assert "not_a_modality" not in p["skipped"]
    assert p["skipped"]["otoscopy"] == "No otoscope"


def test_skipping_everything_optional_still_produces_a_usable_interpretation():
    """The camp case: thresholds and nothing else, every option declined."""
    an = analyze(45, 45, left_ac=45, left_bc=45)
    p = picture(analysis=an, skipped={
        "otoscopy": "No otoscope", "symptoms": "No history taken",
        "tympanometry": "No tympanometer", "oae": "No probe",
        "speech": "No word lists", "aep": "Not available",
        "tuning_fork": "No forks", "boa": "Not applicable"})
    assert p["confidence"] != "insufficient"
    assert p["performed"] >= 1
    line = next(f for f in p["findings"] if f["key"] == "pure_tone")
    assert "45" in line["says"]


@pytest.mark.parametrize("skips", [
    {}, {"otoscopy": "a"}, {"symptoms": "b"},
    {"otoscopy": "a", "symptoms": "b", "tympanometry": "c"},
])
def test_the_findings_are_identical_whatever_was_skipped(skips):
    """The interpretation is built from evidence, and a skip is not evidence."""
    an = analyze(50, 15)
    base = picture(analysis=an)["findings"]
    assert picture(analysis=an, skipped=skips)["findings"] == base


def test_every_recommendation_names_the_modality_it_satisfies():
    """Matching a skip to a gap by label text silently failed for the forks."""
    p = picture(analysis=analyze(50, 15))
    for g in p["next_tests"]:
        assert g.get("modality"), f"{g['test']} carries no modality key"
        assert g["modality"] in {m["key"] for m in D.MODALITIES}


def test_a_skipped_fork_battery_can_still_be_surfaced():
    """Its label starts 'Tuning' but the rule phrases it 'Rinne and Weber'."""
    an = analyze(50, 15)
    g = next(x for x in picture(analysis=an)["next_tests"]
             if x["modality"] == "tuning_fork")
    assert "Rinne" in g["test"]
    with_skip = picture(analysis=an, skipped={"tuning_fork": "No forks on site"})
    tagged = next(x for x in with_skip["next_tests"]
                  if x["modality"] == "tuning_fork")
    assert tagged["was_skipped"] == "No forks on site"


@pytest.mark.parametrize("modality,reason", [
    ("tympanometry", "No tympanometer"),
    ("otoscopy", "No otoscope"),
    ("symptoms", "No history taken"),
    ("speech", "No word lists"),
])
def test_each_skippable_modality_attaches_to_its_own_recommendation(modality, reason):
    p = picture(analysis=analyze(50, 15), skipped={modality: reason})
    tagged = [g for g in p["next_tests"] if g.get("was_skipped")]
    assert [g["modality"] for g in tagged] == [modality]
    assert tagged[0]["was_skipped"] == reason


# ------------------------------------------------ one ear only ----
#
# `_performed` is called outside the broad try/except that guards `_findings`,
# so a crash there is a 500 rather than a degraded panel. It read ac_pta with
# a `{}` default against a producer that emits an explicit None, and `any()`
# short-circuits — so a RIGHT-ear-only case passed by luck while the identical
# LEFT-ear-only case 500'd.

def _one_ear(side):
    other = "left" if side == "right" else "right"
    body = {"patient": {"name": "One Ear", "age": 40, "sex": "male"},
            side: {"ac": {f: 45 for f in AC}, "bc": {f: 20 for f in BC}},
            other: {"ac": {}, "bc": {}}}
    r = client.post("/api/analyze", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _covered(p, key):
    """The `performed` flag for one modality out of the coverage list."""
    return next(c["performed"] for c in p["coverage"] if c["key"] == key)


@pytest.mark.parametrize("side", ["right", "left"])
def test_a_single_ear_case_produces_a_picture_either_side(side):
    p = picture(analysis=_one_ear(side))
    assert _covered(p, "pure_tone") is True


def test_a_case_with_neither_ear_tested_reports_insufficient_not_a_crash():
    r = client.post("/api/analyze", json={"patient": {"name": "None", "age": 40},
                                          "right": {"ac": {}}, "left": {"ac": {}}})
    assert r.status_code == 200, r.text
    p = picture(analysis=r.json())
    assert _covered(p, "pure_tone") is False
    assert p["confidence"] == "insufficient"
