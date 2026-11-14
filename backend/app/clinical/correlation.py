"""Cross-modality correlations no single module can make.

WHAT WAS MISSING. This package already reconciles a great deal:
``consistency.py`` holds immittance, reflexes, emissions and speech against
the audiogram; ``linkage.py`` holds the otoscope image against the history,
the audiogram and the tympanogram; ``tuning_fork.py`` holds the fork battery
against the audiogram; ``diagnosis.py`` counts how many of those converge.

But each of those modules sees two or three modalities. Several of the most
useful correlations in audiology are between modalities that NO module could
see at once, so nobody was making them — not because they are subtle, but
because the two halves were computed in different files and never introduced:

  EMISSIONS vs EVOKED POTENTIALS. Present otoacoustic emissions mean working
  outer hair cells. An abnormal or absent ABR behind working outer hair cells
  is the auditory neuropathy pattern — the one configuration where the
  cochlea is fine and the nerve is not. ``aep.py`` checks the cochlear
  microphonic inside its own recording; it never saw the DP-gram.

  EVOKED POTENTIALS vs BEHAVIOURAL THRESHOLDS. A normal Wave V recorded at
  30 dB nHL is incompatible with a behavioural average of 70 dB HL. One of
  the two measurements is wrong, and which it is matters enormously: an
  objective response better than the voluntary one is the classic
  non-organic picture.

  OTOSCOPY vs EMISSIONS. A perforation or an effusion abolishes emissions by
  blocking them, which means absent emissions behind a drum confirmed normal
  point at the cochlea rather than the middle ear — and absent emissions
  behind a perforated drum say nothing about the cochlea at all.

  TUNING FORKS vs TYMPANOMETRY. Two independent ways of asking whether the
  middle ear conducts. A negative Rinne with a Type A trace is a
  disagreement worth resolving before either is reported.

  BEHAVIOURAL OBSERVATION vs THRESHOLDS. A minimum response level cannot be
  BETTER than a measured threshold: MRLs run tens of decibels above
  threshold by definition, so an MRL below one is an impossible pair.

THE RULES HERE ARE ONE-DIRECTIONAL ABOUT CONFIDENCE. A conflict is reported
whenever the data supports it, because two measurements that cannot both be
true is a finding in itself. An agreement is reported more cautiously: two
tests agreeing corroborates, and this module never upgrades corroboration
into confirmation.

NOTHING IS INFERRED FROM ABSENCE. Every check states the inputs it needs and
returns nothing at all when they are not there, rather than reading a missing
test as a normal one.
"""
from __future__ import annotations

from typing import Dict, List, Optional

#: How much poorer than the stimulus level of a NORMAL ABR a behavioural
#: average may read before the two are called inconsistent.
#:
#: A click ABR is dominated by the 1–4 kHz region and its dB nHL scale sits
#: within about 10 dB of behavioural dB HL for a normal ear (de Jager's
#: nHL-to-eHL correction, used in ``aep.abr_threshold``). Allowing 25 dB on
#: top of that is deliberately generous: it has to absorb the correction, the
#: four-frequency average including 500 Hz where a click says least, and
#: ordinary test-retest. What it will not absorb is a normal response 40 dB
#: below the level the patient claims to hear.
ABR_BEHAVIOURAL_TOLERANCE_DB = 25

#: Air-bone gap above which the middle ear is taken to be conducting poorly,
#: matching ``rules.ABG_SIGNIFICANT_DB``.
GAP_SIGNIFICANT_DB = 10

#: Tympanogram types that mean the middle ear is NOT transmitting normally.
ABNORMAL_TYMPANOGRAMS = {"As", "Ad", "Add", "B", "C", "D", "E"}


def _finding(kind: str, title: str, detail: str, action: str,
             tests: List[str], side: Optional[str] = None) -> dict:
    return {"kind": kind, "title": title, "detail": detail, "action": action,
            "tests": tests, "side": side}


# ==========================================================================
# emissions  <->  evoked potentials
# ==========================================================================

def emissions_vs_aep(analysis: Optional[dict],
                     aep: Optional[dict]) -> List[dict]:
    """Working outer hair cells with an abnormal eighth nerve or brainstem.

    This is the auditory neuropathy spectrum pattern, and it is the reason
    both tests are run. Neither half says it alone: present emissions on
    their own are reassuring, and an abnormal ABR on its own is usually
    explained by the hearing loss that produced it. Together, and only
    together, they localise the problem behind a working cochlea.
    """
    out: List[dict] = []
    if not analysis or not aep:
        return out
    levels = ((aep.get("battery") or {}).get("levels") or [])
    abr = next((l for l in levels if l.get("test") == "ABR"), None)
    if not abr:
        return out

    for ear in (abr.get("ears") or []):
        side = ear.get("ear")
        if side not in ("right", "left"):
            continue
        if ear.get("status") not in ("abnormal", "borderline"):
            continue
        oae = (analysis.get("oae") or {}).get(side) or {}
        # Only a per-frequency recording can show present emissions. An
        # outcome-only screen ("pass") is not enough to put a lesion behind a
        # working cochlea, and ``analyze_oae`` marks that case explicitly.
        if oae.get("entry_mode") == "outcome" or not oae.get("present_freqs"):
            continue
        present = oae["present_freqs"]
        rules_ear = (analysis.get("rules") or {}).get(side) or {}
        pta = (rules_ear.get("ac_pta") or {}).get("value")

        out.append(_finding(
            "conflict" if ear["status"] == "abnormal" else "note",
            "Emissions present with an abnormal ABR — auditory neuropathy pattern",
            f"Otoacoustic emissions are present at {present} Hz, so the outer "
            f"hair cells in the {side} ear are working, yet the ABR is "
            f"{ear['status']}"
            + (f" ({ear['interpretation']})" if ear.get("interpretation") else "")
            + ". A working cochlea with an abnormal brainstem response places "
            "the problem at the eighth nerve or in the brainstem rather than "
            "in the cochlea"
            + (f", and it is not explained by the degree of loss "
               f"({pta:g} dB HL)." if pta is not None else "."),
            "Refer for neuro-otological assessment. Auditory neuropathy "
            "changes management: amplification alone often does not help, and "
            "the decision rests on the ABR and the emissions together, not on "
            "the audiogram.",
            ["oae", "aep"], side))
    return out


def aep_vs_behavioural(analysis: Optional[dict],
                       aep: Optional[dict]) -> List[dict]:
    """An objective response that contradicts what the patient reported.

    Compares the stimulus level at which a NORMAL ABR was recorded against
    the behavioural four-frequency average. A normal Wave V at 30 dB nHL and
    a volunteered average of 75 dB HL cannot both describe the same ear.

    Only normal runs are used. An abnormal ABR at a low level is exactly what
    a real hearing loss produces, and reading that as an inconsistency would
    turn every genuine loss into a suspicion of exaggeration.
    """
    out: List[dict] = []
    if not analysis or not aep:
        return out
    levels = ((aep.get("battery") or {}).get("levels") or [])
    abr = next((l for l in levels if l.get("test") == "ABR"), None)
    recorded = ((aep.get("recorded") or {}).get("abr") or [])
    if not abr or not recorded:
        return out

    by_ear = {r.get("ear"): r for r in recorded if isinstance(r, dict)}
    for ear in (abr.get("ears") or []):
        side = ear.get("ear")
        run = by_ear.get(side)
        if side not in ("right", "left") or not run:
            continue
        if ear.get("status") != "normal":
            continue
        intensity = run.get("intensity_db_nhl")
        if intensity is None:
            continue
        rules_ear = (analysis.get("rules") or {}).get(side) or {}
        pta_block = rules_ear.get("ac_pta") or {}
        pta = pta_block.get("value")
        if pta is None:
            continue
        # A no-response in the average makes the behavioural figure a floor
        # rather than a measurement, and the comparison meaningless.
        if pta_block.get("nr_freqs"):
            continue
        margin = pta - (intensity + ABR_BEHAVIOURAL_TOLERANCE_DB)
        if margin <= 0:
            continue
        out.append(_finding(
            "conflict",
            "The ABR is normal at a level the audiogram says is inaudible",
            f"A normal {side}-ear ABR was recorded at {intensity:g} dB nHL, but "
            f"the behavioural four-frequency average is {pta:g} dB HL — "
            f"{margin:g} dB further than the two scales can differ by. An "
            "objective response better than the voluntary one is the classic "
            "non-organic pattern; the other explanations are a mislabelled "
            "stimulus level or thresholds taken without adequate "
            "re-instruction.",
            "Repeat pure-tone audiometry with re-instruction, and confirm the "
            "stimulus level the ABR was recorded at. Do not certify disability "
            "on the current thresholds.",
            ["pure_tone", "aep"], side))
    return out


# ==========================================================================
# otoscopy  <->  emissions
# ==========================================================================

#: Otoscopic patterns that block an emission on its way out of the ear, so an
#: absent emission behind one says nothing about the cochlea.
BLOCKING_PATTERNS = {
    "cerumen_impaction": "a canal full of wax",
    "otitis_media": "fluid in the middle ear",
    "perforation_central": "a perforated drum",
    "perforation_marginal": "a perforated drum",
    "perforation_attic": "a perforated drum",
    "tumor": "a mass in the canal or middle ear",
}


def otoscopy_vs_emissions(analysis: Optional[dict],
                          otoscopy: Optional[dict],
                          side: str) -> List[dict]:
    """What absent emissions mean depends on what the drum looks like.

    Absent emissions are the app's pre-clinical cochlear damage finding, and
    that inference is only available behind a middle ear that conducts. The
    battery engine already requires a Type A tympanogram for it. The
    otoscope is a second, independent way of answering the same question —
    and the one a clinic in a camp actually has.
    """
    out: List[dict] = []
    if not analysis or not otoscopy:
        return out
    if (otoscopy.get("side") or "right") != side:
        return out
    pattern = (otoscopy.get("prediction") or {}).get("label")
    if not pattern:
        return out
    confirmed = (otoscopy.get("prediction") or {}).get("kind") == "clinician_confirmed"

    oae = (analysis.get("oae") or {}).get(side) or {}
    if oae.get("entry_mode") == "outcome" or not oae.get("absent_freqs"):
        return out
    absent = oae["absent_freqs"]

    if pattern in BLOCKING_PATTERNS:
        what = BLOCKING_PATTERNS[pattern]
        out.append(_finding(
            "note",
            "Absent emissions are explained by the ear canal or middle ear",
            f"Emissions are absent at {absent} Hz, and the {side} ear shows "
            f"{what}"
            + (" on examination." if confirmed else
               " as the image's closest reference pattern.")
            + " An emission has to travel out through the canal and the middle "
            "ear to be recorded, so their absence here is not evidence of "
            "cochlear damage.",
            "Treat or clear the outer and middle ear first, then repeat the "
            "emissions. Only then does an absent emission say anything about "
            "the cochlea.",
            ["otoscopy", "oae"], side))
    elif pattern == "normal":
        rules_ear = (analysis.get("rules") or {}).get(side) or {}
        gap = (rules_ear.get("abg") or {}).get("value")
        if gap is not None and gap > GAP_SIGNIFICANT_DB:
            # The drum looks normal but the ear is not conducting: the
            # emissions could be blocked by whatever is causing the gap.
            return out
        out.append(_finding(
            "agreement",
            "Absent emissions behind a normal drum point at the cochlea",
            f"Emissions are absent at {absent} Hz while the {side} drum is "
            + ("confirmed normal on examination" if confirmed
               else "read as a normal drum from the image")
            + (f" and the air-bone gap is {gap:g} dB" if gap is not None else "")
            + ". With nothing in the canal or middle ear to block them, their "
            "absence is an outer hair cell finding — two independent tests "
            "reaching the same place.",
            "Read with the tympanogram: a Type A trace completes the "
            "confirmation that this is cochlear rather than conductive.",
            ["otoscopy", "oae"], side))
    return out


# ==========================================================================
# tuning forks  <->  tympanometry
# ==========================================================================

def forks_vs_tympanometry(analysis: Optional[dict],
                          tuning_fork: Optional[dict]) -> List[dict]:
    """Two independent answers to "does the middle ear conduct?".

    The fork battery is checked against the audiogram elsewhere. The
    tympanogram is a third measurement of the same mechanism, taken without
    the patient's cooperation — so a fork reading that disagrees with it is
    worth resolving before either is reported.
    """
    out: List[dict] = []
    if not analysis or not tuning_fork:
        return out
    grid = tuning_fork.get("grid") or {}
    side = grid.get("side")
    loss = (grid.get("loss_type") or "").replace("_bilateral", "")
    if side not in ("right", "left") or not loss:
        return out

    tymp = (((analysis.get("immittance") or {}).get(side) or {})
            .get("tympanogram") or {})
    tymp_type = tymp.get("type")
    if not tymp_type:
        return out
    # A 1000 Hz infant trace is not typed on the Jerger scheme, so there is
    # nothing here to compare.
    if str(tymp_type).startswith("1k"):
        return out

    abnormal = tymp_type in ABNORMAL_TYMPANOGRAMS
    if loss == "conductive" and abnormal:
        out.append(_finding(
            "agreement",
            f"Forks and tympanometry agree the {side} middle ear is not conducting",
            f"The fork battery reads conductive and the tympanogram is Type "
            f"{tymp_type} — a bedside test and an objective one, agreeing from "
            "different physics.",
            "Corroboration, not confirmation: several middle-ear disorders "
            "produce both. The type and the canal volume narrow which.",
            ["tuning_fork", "immittance"], side))
    elif loss == "conductive" and tymp_type == "A":
        out.append(_finding(
            "conflict",
            "Forks read conductive but the tympanogram is normal",
            f"The {side} fork battery reads conductive while the tympanogram is "
            "Type A, which means the drum and middle ear move normally. Both "
            "cannot be describing the same ear: the usual causes are an "
            "unmasked fork test picking up the other ear, or a conductive "
            "mechanism behind an intact and mobile drum — ossicular fixation "
            "or a third-window disorder, which a Type A trace does not "
            "exclude.",
            "Repeat the forks with the non-test ear masked, and read the "
            "acoustic reflexes: absent reflexes behind a Type A trace point to "
            "otosclerosis.",
            ["tuning_fork", "immittance"], side))
    elif loss == "sensorineural" and abnormal and tymp_type != "As":
        out.append(_finding(
            "conflict",
            "Forks read sensorineural but the middle ear is abnormal",
            f"The {side} fork battery reads sensorineural, yet the tympanogram "
            f"is Type {tymp_type}. A middle ear that is not transmitting "
            "normally should produce a conductive component the forks would "
            "detect, so either the forks missed a gap or the trace is an "
            "artefact.",
            "Repeat the tympanogram with a fresh probe seal and re-check the "
            "Rinne at 256 and 512 Hz with the non-test ear masked.",
            ["tuning_fork", "immittance"], side))
    return out


# ==========================================================================
# behavioural observation  <->  thresholds
# ==========================================================================

def boa_vs_thresholds(analysis: Optional[dict],
                      boa: Optional[dict]) -> List[dict]:
    """A minimum response level cannot be better than a measured threshold.

    An MRL is the level at which an infant reacts, and reactions run tens of
    decibels above the quietest sound they can actually hear. So an MRL
    recorded BELOW a behavioural threshold from the same child is not a
    borderline finding — it is an impossible pair, and one of the two numbers
    is wrong.
    """
    out: List[dict] = []
    if not analysis or not boa:
        return out
    observed = boa.get("observed_level_db_spl")
    if observed is None:
        observed = (boa.get("observed") or {}).get("level_db_spl")
    if observed is None:
        return out

    best: Optional[float] = None
    best_side = None
    for side in ("right", "left"):
        pta = (((analysis.get("rules") or {}).get(side) or {})
               .get("ac_pta") or {}).get("value")
        if pta is not None and (best is None or pta < best):
            best, best_side = pta, side
    if best is None:
        return out

    if observed < best - 10:
        out.append(_finding(
            "conflict",
            "The behavioural observation level is better than the measured threshold",
            f"A response was recorded at {observed:g} dB SPL, but the best "
            f"pure-tone average is {best:g} dB HL in the {best_side} ear. A "
            "minimum response level sits tens of decibels ABOVE true "
            "threshold, never below it, so these two cannot both be right. "
            "Note also that the two are on different scales — the BOA norms "
            "are labelled dB SPL and the audiogram is dB HL — which is itself "
            "a reason not to read one against the other too finely.",
            "Re-check which scale the response level was recorded on, and "
            "repeat the pure-tone thresholds. A BOA level is never transferred "
            "into the audiogram.",
            ["boa", "pure_tone"], best_side))
    return out


# ==========================================================================
# everything, for one case
# ==========================================================================

def correlate_case(analysis: Optional[dict] = None,
                   otoscopy: Optional[dict] = None,
                   otoscopy_ears: Optional[Dict[str, dict]] = None,
                   aep: Optional[dict] = None,
                   tuning_fork: Optional[dict] = None,
                   boa: Optional[dict] = None) -> dict:
    """Every cross-modality check this module can make for one case.

    ``otoscopy_ears`` is the per-ear map; ``otoscopy`` is accepted for a
    caller that holds only one reading. Both are supported because the two
    ears are examined separately and a right-ear image must never be
    reconciled against the left ear's emissions.
    """
    findings: List[dict] = []

    findings += emissions_vs_aep(analysis, aep)
    findings += aep_vs_behavioural(analysis, aep)
    findings += forks_vs_tympanometry(analysis, tuning_fork)
    findings += boa_vs_thresholds(analysis, boa)

    ears = dict(otoscopy_ears or {})
    if otoscopy and not ears:
        ears[(otoscopy.get("side") or "right")] = otoscopy
    for side, reading in ears.items():
        if reading:
            findings += otoscopy_vs_emissions(analysis, reading, side)

    conflicts = [f for f in findings if f["kind"] == "conflict"]
    agreements = [f for f in findings if f["kind"] == "agreement"]
    notes = [f for f in findings if f["kind"] == "note"]

    return {
        "available": bool(findings),
        "findings": findings,
        # Conflicts first and never folded away: two measurements that cannot
        # both be true is the finding, not a footnote to the ones that agree.
        "conflicts": conflicts,
        "agreements": agreements,
        "notes": notes,
        "conflict_count": len(conflicts),
        "agreement_count": len(agreements),
        "headline": (
            f"{len(conflicts)} cross-test disagreement"
            f"{'' if len(conflicts) == 1 else 's'} to resolve before reporting."
            if conflicts else
            f"{len(agreements)} independent test pair"
            f"{'' if len(agreements) == 1 else 's'} agree."
            if agreements else
            "Nothing to cross-check between these modalities yet."
            if not notes else
            f"{len(notes)} cross-test note{'' if len(notes) == 1 else 's'}."),
        "note": (
            "These are checks BETWEEN modalities that no single test can make: "
            "emissions against evoked potentials, an objective response "
            "against a volunteered threshold, the otoscope against the "
            "emissions, the forks against the tympanogram, and an infant's "
            "response level against a measured one. Agreement between two "
            "tests corroborates a finding; it does not confirm it."),
    }
