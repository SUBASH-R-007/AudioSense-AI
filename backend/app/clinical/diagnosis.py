"""The complete diagnostic picture — what has been done, and what is missing.

Every other module in this package answers one question well. `rules.py` grades
the audiogram, `consistency.py` reconciles immittance against emissions,
`linkage.py` checks the picture against the history. What none of them does is
stand back and ask the question a clinician asks at the end of a session:

    DO I HAVE ENOUGH TO DIAGNOSE THIS PATIENT, AND IF NOT, WHAT DO I DO NEXT?

That is what this module answers. It takes every modality the clinic actually
performed — history, otoscopy, pure tones, masking, immittance, reflexes,
emissions, speech, tuning forks, evoked potentials, behavioural observation —
and produces three things:

  COVERAGE.  Which tests were done and which were not, so a battery with a hole
  in it looks like a battery with a hole in it rather than a finished workup.

  CONVERGENCE.  Where independent modalities say the same thing. A conductive
  loss on the audiogram, a Type B tympanogram, a negative Rinne and a bulging
  drum are four separate observations, and the diagnosis is strong precisely
  because none of them depends on the others. Convergence is counted, and it is
  what drives the confidence rating.

  THE NEXT TEST.  Not a generic checklist — the specific test that would most
  change the answer, given what is already known. A conductive loss with no
  immittance has no mechanism, so tympanometry is critical. An asymmetric
  sensorineural loss with no ABR has an unexcluded vestibular schwannoma, so
  that is critical too. A symmetric mild loss with everything else normal needs
  nothing further, and the module says so rather than inventing work.

WHAT THIS MODULE WILL NOT DO. It names no disease as a finding. Naming diseases
is `symptom_kb.py`'s job and it does it from a declared knowledge base; this
module reports type, side, mechanism and certainty. The single named condition
anywhere in it is the vestibular schwannoma, and only as the thing an ABR is
ordered to EXCLUDE — which is a statement about why a test is worth doing, not
a diagnosis. It does not override any other
module — where `consistency.py` has found a contradiction, that contradiction is
carried through, never smoothed away. And it never reports a diagnosis as
complete while a critical test is outstanding, because a confident answer built
on half a battery is the failure mode this whole product exists to avoid.

Criteria for the "next test" rules are the standard ones cited elsewhere in this
package: an air-bone gap above 10 dB is significant (ASHA); asymmetry warranting
imaging is >= 20 dB at one frequency or >= 15 dB at two (`safety.py`); word
recognition disproportionately poor for the pure-tone average raises
retrocochlear suspicion (rollover, `speech_audiometry.py`); behavioural
audiometry is not obtainable below about six months (`boa.py`).
"""
from __future__ import annotations

from typing import Dict, List, Optional

#: The full battery, in the order a workup runs. ``essential`` marks the tests
#: without which no interpretation should be called complete for ANY patient;
#: the rest become essential only when a finding calls for them.
MODALITIES: List[dict] = [
    {"key": "symptoms", "label": "History and symptoms", "essential": True,
     "why": "The complaint decides which findings matter. The same discharge is "
            "otitis media in a child and necrotizing otitis externa at seventy."},
    {"key": "otoscopy", "label": "Otoscopy", "essential": True,
     "why": "A conductive loss may have a cause visible in ten seconds, and a "
            "canal full of wax invalidates everything measured through it."},
    {"key": "pure_tone", "label": "Pure-tone audiometry", "essential": True,
     "why": "The reference measurement everything else is checked against."},
    {"key": "masking", "label": "Masking", "essential": False,
     "why": "An unmasked threshold can belong to the other ear."},
    {"key": "tympanometry", "label": "Tympanometry", "essential": False,
     "why": "Gives the conductive mechanism the audiogram can only infer."},
    {"key": "reflexes", "label": "Acoustic reflexes", "essential": False,
     "why": "Cross the brainstem, so they separate cochlear from neural."},
    {"key": "oae", "label": "Otoacoustic emissions", "essential": False,
     "why": "Report outer hair cells directly, before thresholds move."},
    {"key": "speech", "label": "Speech audiometry", "essential": False,
     "why": "The pure-tone average does not predict discrimination."},
    {"key": "tuning_fork", "label": "Tuning forks", "essential": False,
     "why": "A bedside cross-check on the side and type of loss."},
    {"key": "aep", "label": "Evoked potentials", "essential": False,
     "why": "Objective, and the only way to localise above the cochlea."},
    {"key": "boa", "label": "Behavioural observation", "essential": False,
     "why": "The entry point for an infant too young to be conditioned."},
]

MODALITY_BY_KEY = {m["key"]: m for m in MODALITIES}

#: Air-bone gap above which a conductive component is significant, dB.
SIGNIFICANT_ABG = 10

#: Age below which behavioural audiometry is not obtainable, months.
INFANT_MONTHS = 6

CITATIONS = (
    "ASHA guidelines for manual pure-tone threshold audiometry",
    "WHO World Report on Hearing (2021)",
    "British Society of Audiology recommended procedures",
)


# ==========================================================================
# Coverage
# ==========================================================================


def _performed(analysis: Optional[dict], assessment, otoscopy, aep,
               tuning_fork, boa) -> Dict[str, bool]:
    """Which modalities actually produced a result."""
    a = analysis or {}
    rules = a.get("rules") or {}
    battery = a.get("battery") or {}
    safety = a.get("safety") or {}

    def either(field: str) -> bool:
        return any(((battery.get(side) or {}).get("tests_available") or {}).get(field)
                   for side in ("right", "left"))

    # `or {}` on ac_pta, not a `{}` default: an untested ear carries an
    # explicit "ac_pta": None. With the default, a LEFT-ear-only case crashed
    # here while a right-ear-only case survived purely because any() had
    # already short-circuited — the panel worked or 500'd depending on which
    # ear the clinician happened to test.
    has_tones = any(((rules.get(side) or {}).get("ac_pta") or {}).get("value") is not None
                    for side in ("right", "left"))
    # Masking counts as handled either when it was actually recorded, or when
    # the review found it was not required anywhere — an ear that never needed
    # masking is not an ear with a missing test.
    masking = safety.get("masking_review") or {}
    masked_done = bool(masking) and (
        masking.get("any_indicated") is False
        or any((masking.get(side) or {}).get("masking_reported")
               for side in ("right", "left")))

    return {
        "symptoms": bool(assessment),
        "otoscopy": bool(otoscopy),
        "pure_tone": has_tones,
        "masking": bool(masked_done),
        "tympanometry": either("tympanometry"),
        "reflexes": either("reflexes"),
        "oae": either("oae"),
        "speech": either("speech"),
        "tuning_fork": bool(tuning_fork),
        "aep": bool(aep),
        "boa": bool(boa),
    }


# ==========================================================================
# What each modality contributes
# ==========================================================================


def _label(value) -> Optional[str]:
    """Coerce a field that may be a string, a ``{key, name}`` dict, or absent.

    This module is the one place that reads the output of five other routers,
    each free to evolve its own response independently. ``urgency`` is already
    a bare string in one payload and a ranked ``{key, name, probability}``
    object in another, and a summary panel must not be the thing that breaks
    when one of them changes shape. Anything unrecognised degrades to ``None``.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        for field in ("name", "label", "key", "headline"):
            got = value.get(field)
            if isinstance(got, str) and got:
                return got
    return None


def _urgent(value) -> bool:
    key = (_label(value) or "").lower()
    return any(word in key for word in ("urgent", "emergency", "immediate"))


def _findings(analysis, assessment, otoscopy, aep, tuning_fork, boa,
              done: Dict[str, bool]) -> List[dict]:
    """One line per modality performed — what it actually said."""
    a = analysis or {}
    rules = a.get("rules") or {}
    out: List[dict] = []

    if done["symptoms"]:
        diff = (assessment or {}).get("differential") or []
        top = _label(diff[0].get("name")) if diff and isinstance(diff[0], dict) else None
        flags = (assessment or {}).get("red_flags") or []
        out.append({
            "key": "symptoms", "label": "History and symptoms",
            "says": (f"Leading possibility: {top}." if top
                     else "Recorded, no ranked possibility returned."),
            "alarm": bool(flags),
            "detail": f"{len(flags)} red flag(s) raised." if flags else None,
        })

    if done["otoscopy"]:
        o = otoscopy or {}
        first = (o.get("differential") or [{}])[0]
        top = _label(first.get("name")) or _label(first.get("label"))
        prob = first.get("probability")
        out.append({
            "key": "otoscopy", "label": "Otoscopy",
            "says": f"Appearance most resembles {top}." if top
                    else "Image recorded.",
            "alarm": _urgent(o.get("urgency")),
            # The classifier is weak and the interface says so everywhere else;
            # a summary that quietly dropped the caveat would undo that.
            "detail": (f"ranked first at {prob:.0%} — a ranked differential, "
                       f"not an identification"
                       if isinstance(prob, (int, float))
                       else _label(o.get("urgency"))),
        })

    if done["pure_tone"]:
        parts = []
        for side in ("right", "left"):
            e = rules.get(side) or {}
            pta = (e.get("ac_pta") or {}).get("value")
            if pta is None:
                continue
            grade = (e.get("who_grade") or {}).get("grade", "")
            parts.append(f"{side} {pta:g} dB HL, {e.get('type', '?').lower()}, "
                         f"{grade.lower()}")
        out.append({
            "key": "pure_tone", "label": "Pure-tone audiometry",
            "says": "; ".join(parts) or "Thresholds recorded.",
            "alarm": bool((a.get("safety") or {}).get("has_emergency")),
            "detail": None,
        })

    if done["masking"]:
        review = (a.get("safety") or {}).get("masking_review") or {}
        warned = bool((a.get("safety") or {}).get("validity_warning"))
        out.append({
            "key": "masking", "label": "Masking",
            "says": (review.get("headline")
                     or "Masking status recorded for the thresholds."),
            "alarm": warned,
            # A bare boolean here rendered as a dangling separator on the
            # dashboard; the detail line has to be a sentence or nothing.
            "detail": ("masking was indicated and not recorded, so a threshold "
                       "may belong to the other ear" if warned else None),
        })

    for key, label, src in (("tympanometry", "Tympanometry", "immittance"),
                            ("oae", "Otoacoustic emissions", "oae")):
        if not done[key]:
            continue
        payload = a.get(src) or {}
        heads = [f"{side}: {(payload.get(side) or {}).get('headline')}"
                 for side in ("right", "left")
                 if (payload.get(side) or {}).get("headline")]
        out.append({"key": key, "label": label,
                    "says": "; ".join(heads) or f"{label} recorded.",
                    "alarm": False, "detail": None})

    if done["speech"]:
        out.append({"key": "speech", "label": "Speech audiometry",
                    "says": "Speech measures recorded and cross-checked "
                            "against the pure tones.",
                    "alarm": False, "detail": None})

    if done["tuning_fork"]:
        grid = (tuning_fork or {}).get("grid") or {}
        out.append({
            "key": "tuning_fork", "label": "Tuning forks",
            "says": grid.get("headline") or "Fork battery recorded.",
            "alarm": grid.get("level") == "contradiction",
            "detail": f"rule {grid.get('rule')}" if grid.get("rule") else None,
        })

    if done["aep"]:
        bat = (aep or {}).get("battery") or aep or {}
        out.append({
            "key": "aep", "label": "Evoked potentials",
            "says": bat.get("headline") or "Evoked potentials recorded.",
            "alarm": bool(bat.get("abnormal")),
            "detail": None,
        })

    if done["boa"]:
        out.append({
            "key": "boa", "label": "Behavioural observation",
            "says": (boa or {}).get("headline") or "Observation recorded.",
            "alarm": bool((boa or {}).get("concern")),
            "detail": "Minimum response levels, not thresholds.",
        })

    return out


# ==========================================================================
# The next test
# ==========================================================================


def next_tests(analysis: Optional[dict], done: Dict[str, bool],
               age_months: Optional[float] = None) -> List[dict]:
    """The specific tests that would most change the answer, given what is known.

    Priority is ``critical`` when the diagnosis cannot be called complete
    without it, ``recommended`` when it would materially strengthen or change
    the picture, and ``optional`` otherwise. Ordered so the first entry is the
    single most useful next thing to do.
    """
    a = analysis or {}
    rules = a.get("rules") or {}
    safety = a.get("safety") or {}
    gaps: List[dict] = []

    def _type(side: str) -> Optional[str]:
        """Ear type with the provisional suffix stripped.

        rules.py types an ear from air conduction alone when bone conduction
        was never tested, and marks that by appending " (provisional)". It is
        still a sensorineural picture — and an ear with no BC is the one where
        emissions are MOST informative, not least — so every rule here reads
        through the suffix rather than matching the bare literal.
        """
        t = ((rules.get(side) or {}).get("type") or "").replace(" (provisional)", "")
        return t or None

    def add(test, why, priority, because, modality=None):
        gaps.append({"test": test, "why": why, "priority": priority,
                     "because": because, "modality": modality})

    # --- the infant case reorders everything else ------------------------
    if age_months is not None and age_months < INFANT_MONTHS:
        if not done["aep"]:
            add("Auditory brainstem response (ABR) or ASSR",
                "Under six months there is no conditioned response to shape, so "
                "an objective, frequency-specific, ear-specific threshold "
                "estimate is the only way to size a loss.",
                "critical", f"patient is {age_months:g} months old", "aep")
        if not done["boa"] and not done["pure_tone"]:
            add("Behavioural observation audiometry",
                "The entry point of paediatric audiometry — a screen, and one "
                "whose levels are minimum response levels rather than thresholds.",
                "recommended", "no behavioural data recorded", "boa")

    # --- conductive component without a mechanism ------------------------
    conductive_sides = [
        s for s in ("right", "left")
        if ((rules.get(s) or {}).get("abg") or {}).get("value") is not None
        and (rules[s]["abg"]["value"] or 0) > SIGNIFICANT_ABG]

    if conductive_sides:
        where = " and ".join(conductive_sides)
        if not done["tympanometry"]:
            add("Tympanometry",
                "An air-bone gap says the middle ear is not transmitting; it "
                "cannot say why. The tympanogram separates effusion from "
                "perforation, from a fixed chain, from wax against the probe.",
                "critical", f"air-bone gap in the {where} ear", "tympanometry")
        if not done["otoscopy"]:
            add("Otoscopy",
                "A conductive loss frequently has a cause that is visible. It "
                "also rules out a canal occluded by wax, which produces the "
                "same audiogram from a trivial and reversible cause.",
                "critical", f"air-bone gap in the {where} ear", "otoscopy")
        if not done["tuning_fork"] and not done["tympanometry"]:
            add("Rinne and Weber",
                "A bedside cross-check that the gap is real and on the side the "
                "audiogram places it — useful when immittance is unavailable.",
                "recommended", "conductive picture with no immittance", "tuning_fork")

    # --- sensorineural loss without a site of lesion ---------------------
    sn_sides = [s for s in ("right", "left")
                if _type(s) in ("Sensorineural", "Mixed")]
    if sn_sides and not done["oae"]:
        add("Otoacoustic emissions",
            "Emissions report outer hair cells directly. Present emissions "
            "with a sensorineural loss point above the cochlea; absent "
            "emissions confirm it as cochlear.",
            "recommended", "sensorineural component present", "oae")

    # --- asymmetry is the retrocochlear question -------------------------
    asym = safety.get("asymmetry") or {}
    if asym.get("flag"):
        if not done["aep"]:
            add("Auditory brainstem response (ABR)",
                "Asymmetric sensorineural loss carries an unexcluded "
                "vestibular schwannoma until imaging or an ABR says otherwise. "
                "Interpeak I-V and the interaural Wave V difference are the "
                "measurements that matter.",
                "critical", "asymmetric loss flagged", "aep")
        if not done["reflexes"]:
            add("Acoustic reflexes",
                "Reflex decay and absent contralateral reflexes with a working "
                "cochlea are classic retrocochlear signs.",
                "recommended", "asymmetric loss flagged", "reflexes")

    # --- any loss at all deserves a speech measure -----------------------
    any_loss = any(_type(s) not in (None, "Normal") for s in ("right", "left"))
    if any_loss and not done["speech"]:
        add("Speech audiometry (SRT and word recognition)",
            "The pure-tone average does not predict how much speech the "
            "patient understands, and word recognition disproportionately poor "
            "for the audiogram is itself a retrocochlear sign.",
            "recommended", "hearing loss present", "speech")

    # --- validity: an unmasked threshold may be the wrong ear ------------
    if safety.get("validity_warning") and not done["masking"]:
        add("Masked thresholds",
            "Masking was indicated and not recorded, so a threshold on the "
            "poorer side may be a shadow of the better ear rather than that "
            "ear's own hearing.",
            "critical", "masking indicated but not recorded", "masking")

    # --- the history is not optional -------------------------------------
    if not done["symptoms"]:
        add("Signs and symptoms history",
            "Without the complaint, the audiogram is a measurement without a "
            "question. Onset in particular decides whether this is an "
            "emergency.",
            "critical" if any_loss else "recommended",
            "no history recorded", "symptoms")

    # --- damage the audiogram cannot yet see ------------------------------
    if not any_loss and done["pure_tone"] and not done["oae"]:
        add("Otoacoustic emissions",
            "Thresholds are normal, and emissions are the only test here that "
            "can show cochlear damage before the audiogram moves.",
            "recommended", "normal thresholds in a symptomatic patient"
            if done["symptoms"] else "normal thresholds", "oae")

    order = {"critical": 0, "recommended": 1, "optional": 2}
    seen, unique = set(), []
    for g in sorted(gaps, key=lambda x: order[x["priority"]]):
        if g["test"] in seen:
            continue
        seen.add(g["test"])
        unique.append(g)
    return unique


# ==========================================================================
# Convergence and conflict
# ==========================================================================


def _convergence(analysis, findings, tuning_fork) -> dict:
    """Independent modalities that agree, and any that cannot both be true."""
    a = analysis or {}
    battery = a.get("battery") or {}
    agrees: List[str] = []
    conflicts: List[str] = []

    for side in ("right", "left"):
        b = battery.get(side) or {}
        for c in b.get("confirmations", []):
            agrees.append(f"{side}: {c}" if isinstance(c, str)
                          else f"{side}: {c.get('detail') or c.get('name')}")
        for c in b.get("contradictions", []):
            conflicts.append(f"{side}: {c}" if isinstance(c, str)
                             else f"{side}: {c.get('detail') or c.get('name')}")

    # The forks are an independent observer of the same air-bone gap.
    grid = (tuning_fork or {}).get("grid") or {}
    if grid.get("loss_type") and grid.get("side"):
        rules = a.get("rules") or {}
        ear = (rules.get(grid["side"]) or {}).get("type", "").lower()
        fork = grid["loss_type"].replace("_bilateral", "")
        if ear and fork in ear:
            agrees.append(
                f"{grid['side']}: the fork battery and the audiogram both read "
                f"{fork}, from independent measurements")
        elif ear and fork not in ear and ear != "normal":
            conflicts.append(
                f"{grid['side']}: the forks read {fork} where the audiogram "
                f"reads {ear} — recheck the forks with the non-test ear masked")
    if grid.get("level") == "contradiction":
        conflicts.append(f"tuning forks: {grid.get('headline')}")

    alarms = [f["label"] for f in findings if f.get("alarm")]
    return {"agreements": agrees, "conflicts": conflicts, "alarms": alarms}


# ==========================================================================
# The picture
# ==========================================================================


def diagnostic_picture(analysis: Optional[dict] = None,
                       assessment: Optional[dict] = None,
                       otoscopy: Optional[dict] = None,
                       aep: Optional[dict] = None,
                       tuning_fork: Optional[dict] = None,
                       boa: Optional[dict] = None,
                       age_months: Optional[float] = None,
                       skipped: Optional[Dict[str, str]] = None) -> dict:
    """Coverage, convergence, and the next test — the whole workup at a glance.

    ``skipped`` maps a modality key to the reason the clinician gave for not
    doing it. It changes the PROMPT, never the interpretation: a skipped test is
    still an absent test, so coverage still counts it missing and a finding that
    makes it critical still escalates. What it buys is that a deliberate
    decision is not re-asked as though it were an oversight — and, more useful,
    that a skip which has since become critical can be named as one.
    """
    done = _performed(analysis, assessment, otoscopy, aep, tuning_fork, boa)
    # A summary that aggregates five independently-evolving payloads must not be
    # the thing that takes the dashboard down when one of them changes shape.
    # Coverage and the next test are derived from the audiogram alone and stay
    # correct regardless, so a malformed sub-payload costs a description line
    # rather than the whole panel.
    try:
        findings = _findings(analysis, assessment, otoscopy, aep, tuning_fork,
                             boa, done)
    except Exception:  # noqa: BLE001 — deliberately broad; see the note above
        findings = [{"key": "unreadable", "label": "Some results",
                     "says": "One or more results could not be summarised here "
                             "and are shown on their own screens instead.",
                     "alarm": False, "detail": None}]
    gaps = next_tests(analysis, done, age_months)
    conv = _convergence(analysis, findings, tuning_fork)

    performed = sum(1 for v in done.values() if v)
    coverage = [
        {**MODALITY_BY_KEY[k], "performed": v}
        for k, v in ((m["key"], done[m["key"]]) for m in MODALITIES)
    ]

    skipped = {k: v for k, v in (skipped or {}).items() if k in MODALITY_BY_KEY}
    for gap in gaps:
        # Each recommendation carries the modality key it satisfies. An earlier
        # version matched on the label's first word, which silently failed for
        # the fork battery: its label starts "Tuning" while the rule phrases the
        # test as "Rinne and Weber", so a skipped fork battery could never be
        # surfaced as one that had become critical.
        key = gap.get("modality")
        if key and key in skipped:
            gap["was_skipped"] = skipped[key]

    reconsider = [g for g in gaps
                  if g.get("was_skipped") and g["priority"] == "critical"]
    critical = [g for g in gaps if g["priority"] == "critical"]
    n_agree = len(conv["agreements"])

    if not done["pure_tone"]:
        confidence, verdict = "insufficient", (
            "No pure-tone thresholds recorded — there is nothing yet to "
            "interpret.")
    elif critical:
        confidence, verdict = "incomplete", (
            f"{len(critical)} test(s) outstanding before this workup can be "
            f"called complete. Next: {critical[0]['test']}.")
    elif conv["conflicts"]:
        confidence, verdict = "conflicted", (
            "The tests performed do not all agree. Resolve the conflict below "
            "before issuing a diagnosis.")
    elif n_agree >= 2:
        confidence, verdict = "corroborated", (
            f"{n_agree} independent findings agree and no critical test is "
            f"outstanding.")
    elif performed >= 4:
        confidence, verdict = "adequate", (
            "The essential battery is complete, with limited independent "
            "corroboration.")
    else:
        confidence, verdict = "provisional", (
            "Interpretable, but resting on few modalities.")

    return {
        "verdict": verdict,
        "confidence": confidence,
        "coverage": coverage,
        "performed": performed,
        "total": len(MODALITIES),
        "essential_missing": [m["label"] for m in MODALITIES
                              if m["essential"] and not done[m["key"]]],
        "findings": findings,
        "agreements": conv["agreements"],
        "conflicts": conv["conflicts"],
        "alarms": conv["alarms"],
        "next_tests": gaps,
        "skipped": skipped,
        # A skip that has since become critical is the one worth naming: the
        # decision was reasonable when it was made and the findings have moved.
        "reconsider": [
            f"{g['test']} was skipped ({g['was_skipped']}), but {g['because']} "
            f"now makes it critical." for g in reconsider],
        "caveat": (
            "Coverage is not accuracy. A complete battery that all points the "
            "same way can still be wrong, and this summary never replaces the "
            "judgement of a qualified audiologist."),
        "citations": list(CITATIONS),
    }
