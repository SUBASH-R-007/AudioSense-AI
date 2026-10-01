"""Symptom-led assessment: what the patient says, before any test is run.

A woman walks in and says water keeps coming out of her ear. That sentence
already narrows the differential, already determines which tests are worth
running, and — if she is seventy and diabetic — already carries a red flag
that outranks everything the audiogram will say. This module turns the
complaint into a ranked differential, a recommended test battery, and an
urgency level, using only the clinical documents encoded in ``symptom_kb``.

Design decisions worth stating:

FREE TEXT IS MATCHED, NOT PARSED. There is no language model here and none is
needed. Patients and clerks type a small, highly repetitive vocabulary, and a
synonym table covers it deterministically, offline, in microseconds — and
reports exactly which words it did not understand rather than quietly
dropping them.

TWO INDEPENDENT SOURCES, KEPT SEPARATE. The complaint guide ranks causes by
age band; the disease reference scores symptom overlap. They are combined,
but each contribution is reported, so a clinician can see whether a diagnosis
is ranked highly because it matches the symptoms or because the guide places
it first for this age group.

ABSENCE IS EVIDENCE. A disease whose defining feature is missing is
demoted, not merely un-promoted. Meniere's without vertigo or fluctuation is
not a weak Meniere's; it is a different diagnosis.

A SPECIFIC SYMPTOM IMPLIES THE GENERAL ONE. "Gradually worsening hearing" is
a hearing loss, and is scored as one against the disease reference, the
complaint guide and the red flags — labelled as implied wherever it is shown,
so nobody reads it as something the patient said separately. Where the guide
describes an acute loss (labyrinthitis, a traumatic perforation), onset
decides: a loss recorded as gradual or fluctuating does not fit it, however
it was entered.

AGE AND COMMONNESS ARE PRIORS, NOT FILTERS. Each condition has a typical age
range; outside it the score tapers rather than dropping at a band edge, and
never below the old out-of-band factor. Commonness weights the symptom score
for conditions the complaint guide does not rank, except those flagged as not
to be missed, which are never ranked down for being rare. It orders the list;
it does not decide whether the summary calls the leader separated, which is
judged on fit alone (``fit_score``).

RED FLAGS DO NOT COMPETE WITH THE DIFFERENTIAL. They are evaluated
separately and reported above it, because "this might be meningitis" is not
a fourth-place possibility.

THE AUDIOGRAM CAN OVERRULE THE HISTORY. Once thresholds exist, a possibility
that predicts a type of hearing the audiogram did not measure — CAPD, which
needs normal pure tones, in an ear with a moderate sensorineural loss — is
ranked below every possibility the audiogram leaves open, in ``reconcile``.
It is ranked down rather than removed, and the reason is stated, because a
measured conflict points at the history or the thresholds as often as at the
diagnosis. Only what was measured overrules: a type rules.py marks
provisional (no bone conduction) contradicts nothing by type. And the
audiogram adds no evidence for what ranks next, so a replacement leader must
be one the history singles out — a distinguishing feature the patient stated,
or for presbycusis the age that defines it. A rare bone disease or a
cholesteatoma without discharge, matched only on a hearing loss and
tinnitus, is never promoted; the summary says nothing qualifies instead.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.clinical.norms import REFERENCE_AGE as ISO7029_REFERENCE_AGE
from app.clinical.symptom_kb import (
    AGE_BANDS, AGE_DEFINING_FLOOR, AGE_FIT_FLOOR, AGE_TAPER_YEARS,
    COMMONNESS_WEIGHT, COMPLAINTS,
    DISEASES, GUIDE_ACUTE_CAUSES, GUIDE_ARGUES_AGAINST, GUIDE_ONLY_TESTS,
    GUIDE_TO_DISEASE, IMPLIED_SYMPTOMS,
    NOISY_OCCUPATIONS, RED_FLAGS, SYMPTOM_GROUPS, SYMPTOM_LABELS,
    SYMPTOM_SYNONYMS, TEST_PRIORITY, age_band,
)

#: Longest synonyms first, so "severe ear pain" wins over "ear pain".
_MATCH_ORDER: List[tuple] = sorted(
    ((phrase, canonical)
     for canonical, phrases in SYMPTOM_SYNONYMS.items()
     for phrase in phrases),
    key=lambda pair: -len(pair[0]),
)

_URGENCY_RANK = {"emergency": 0, "urgent": 1, "watch": 2, "routine": 3}

#: The source document's age bands as numeric spans, used for any condition
#: that declares no finer ``age_ranges`` of its own.
_BAND_SPANS: Dict[str, Tuple[int, int]] = {
    key: (lo, hi) for key, _label, lo, hi in AGE_BANDS}

#: Factor for a disease whose defining feature is absent.
_MISSING_DEFINING_FACTOR = 0.35

#: Factor for a possibility whose predicted type of hearing the measured
#: audiogram contradicts. As strong as an absent defining feature: a measured
#: contradiction is at least as much evidence as a symptom not reported.
_AUDIOGRAM_CONFLICT_FACTOR = 0.35

#: WHO (2021) grades a four-frequency average below 20 dB HL as normal
#: hearing; at or above it, an ear has a measured loss.
_NORMAL_PTA_DB = 20


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def _label(symptom: str) -> str:
    return SYMPTOM_LABELS.get(symptom, symptom)


def parse_symptoms(raw: Iterable[str]) -> dict:
    """Canonical symptoms from checkbox keys and free text.

    Returns the matched set and, importantly, the fragments that matched
    nothing — a silent miss in a symptom checker is how a red flag gets lost.
    """
    matched: Dict[str, str] = {}
    leftovers: List[str] = []

    for item in raw:
        if not item:
            continue
        item = str(item).strip()
        if item in SYMPTOM_SYNONYMS:          # already canonical (a checkbox)
            matched.setdefault(item, item)
            continue

        text = f" {_normalise(item)} "
        if not text.strip():
            continue
        residue = text
        hit = False
        for phrase, canonical in _MATCH_ORDER:
            token = f" {_normalise(phrase)} "
            if token in residue:
                matched.setdefault(canonical, phrase)
                residue = residue.replace(token, " ")
                hit = True
        if not hit:
            leftovers.append(item)

    return {
        "symptoms": sorted(matched),
        "evidence": matched,
        "unmatched": leftovers,
    }


# ==========================================================================
# priors: implied symptoms, age, commonness
# ==========================================================================


def _implied(present: set) -> Dict[str, List[str]]:
    """General symptoms entailed by the specific ones reported.

    Only a general symptom that was NOT reported in its own right is implied;
    one the patient also stated plainly is simply reported.
    """
    out: Dict[str, List[str]] = {}
    for general, specifics in IMPLIED_SYMPTOMS.items():
        if general in present:
            continue
        sources = [s for s in specifics if s in present]
        if sources:
            out[general] = sources
    return out


def _display(symptom: str, implied: Dict[str, List[str]]) -> str:
    """Symptom label, marked when it was implied rather than reported."""
    if symptom not in implied:
        return _label(symptom)
    by = ", ".join(_label(s).lower() for s in implied[symptom])
    return f"{_label(symptom)} (implied by {by})"


def _age_ranges(disease: dict) -> List[Tuple[int, int]]:
    """Typical ages: declared ranges, else the source document's bands.

    Contiguous bands are merged, so a condition prone in children and adults
    is one span from 0 to 64 rather than two that meet at 17/18.
    """
    declared = disease.get("age_ranges")
    if declared:
        return [(int(lo), int(hi)) for lo, hi in declared]
    spans = sorted(_BAND_SPANS[b] for b in disease.get("age_bands", [])
                   if b in _BAND_SPANS)
    merged: List[Tuple[int, int]] = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged or [(0, 200)]


def _iso7029_fraction(age: float, typical_from: float) -> float:
    """ISO 7029:2000 median age-related shift at ``age`` as a fraction of the
    shift at ``typical_from``.

    The standard's median is a(freq, sex) x (age - 18)^2 (norms.py), so the
    coefficient cancels: the fraction is the same at every frequency and for
    either sex, and it is 0 at or below the 18-year reference age.
    """
    span = typical_from - ISO7029_REFERENCE_AGE
    if span <= 0:
        return 1.0
    return min(1.0, (max(0.0, age - ISO7029_REFERENCE_AGE) / span) ** 2)


def _age_factor(age: int, disease: dict) -> float:
    """1.0 inside a typical range, tapering linearly to the floor outside it.

    The floor is reached AGE_TAPER_YEARS outside the range. It is lower for a
    condition defined by age, where age is evidence rather than a prior.

    A condition declaring an ``age_prior`` follows that cited curve below its
    range instead: the ISO 7029 median shift (``_iso7029_fraction``), or an
    incidence that doubles every ``years`` years of age.
    """
    floor = AGE_DEFINING_FLOOR if disease.get("age_defining") else AGE_FIT_FLOOR
    ranges = _age_ranges(disease)
    for lo, hi in ranges:
        if lo <= age <= hi:
            return 1.0
    prior = disease.get("age_prior") or {}
    below = [lo for lo, _hi in ranges if age < lo]
    if prior.get("curve") == "iso7029" and below:
        return max(_iso7029_fraction(age, lo) for lo in below)
    if prior.get("curve") == "doubling" and below:
        return max(0.5 ** ((lo - age) / prior["years"]) for lo in below)
    best = floor
    for lo, hi in ranges:
        gap = lo - age if age < lo else age - hi
        best = max(best, 1.0 - (1.0 - floor) * gap / AGE_TAPER_YEARS)
    return best


def _commonness(disease: dict) -> Tuple[Optional[str], float]:
    """Declared commonness tier and its weight on the symptom score.

    A condition carrying a red flag is exempt: it is on the list because it
    must not be missed, and ranking it down for rarity would undo that.
    """
    if disease.get("red_flag"):
        return None, 1.0
    tier = disease.get("commonness")
    return tier, COMMONNESS_WEIGHT.get(tier, 1.0)


def _score_disease(key: str, disease: dict, present: set, age: int,
                   implied: Optional[Dict[str, List[str]]] = None) -> Optional[dict]:
    implied = implied or {}
    weights = disease["symptoms"]
    positive = {s: w for s, w in weights.items() if w > 0}
    possible = sum(positive.values()) or 1

    matched = [s for s in positive if s in present]
    earned = sum(positive[s] for s in matched)
    # Negative weights encode "this symptom argues against": CAPD with a real
    # hearing loss is less likely to be CAPD.
    against = [s for s, w in weights.items() if w < 0 and s in present]
    earned += sum(weights[s] for s in against)

    if earned <= 0:
        return None

    overlap = max(earned, 0) / possible

    # A defining feature that is absent is a reason to demote.
    required = disease.get("requires_any") or []
    missing_defining = bool(required) and not any(r in present for r in required)
    if missing_defining:
        overlap *= _MISSING_DEFINING_FACTOR

    # A reported symptom the condition's definition rules out until a test
    # has excluded it (a hearing loss, for CAPD): as strong as an absent
    # defining feature. The factor is carried so that ``reconcile`` can lift
    # it once the audiogram has done that.
    conflict = disease.get("contradicted_by_report") or {}
    conflicting = [s for s in conflict.get("symptoms", []) if s in present]
    report_factor = _MISSING_DEFINING_FACTOR if conflicting else 1.0
    overlap *= report_factor

    age_factor = _age_factor(age, disease)
    tier, commonness_factor = _commonness(disease)

    # A history the presentation needs in this age group (adult CAPD needs a
    # neurological route). Ranked down without it, never out — and phased in
    # over AGE_TAPER_YEARS from the age it starts at, for the same reason the
    # age prior tapers: the year a patient turns 18 is not the year a
    # developmental disorder stops being likely.
    context_factor, context_note, context_missing = 1.0, "", []
    ctx = disease.get("adult_context")
    if ctx and age >= ctx["from_age"] and not any(
            s in present for s in ctx["requires_any"]):
        years_in = age - ctx["from_age"] + 1
        context_factor = 1.0 - (1.0 - ctx["factor"]) * min(
            1.0, years_in / AGE_TAPER_YEARS)
        context_note = ctx["note"]
        context_missing = [_label(s) for s in ctx["requires_any"]]

    evidence = overlap * commonness_factor * context_factor

    return {
        "key": key,
        "name": disease["name"],
        "category": disease["category"],
        "score": round(evidence * age_factor, 4),
        "symptom_overlap": round(overlap, 4),
        "matched": [{"key": s, "label": _display(s, implied),
                     "weight": positive[s], "implied": s in implied}
                    for s in sorted(matched, key=lambda s: -positive[s])],
        "argues_against": [_display(s, implied) for s in against],
        "missing_key_features": [_label(r) for r in required
                                 if r not in present] + context_missing,
        "missing_defining_feature": missing_defining,
        "age_fit": age_factor >= 1.0,
        "age_factor": round(age_factor, 3),
        "age_note": disease["age_note"],
        "commonness": tier,
        "commonness_factor": commonness_factor,
        "context_factor": context_factor,
        "context_note": context_note,
        # Below 1 when a reported symptom contradicts the definition until
        # tested (``contradicted_by_report``); reconcile divides it out once
        # the audiogram has ruled the symptom out.
        "report_conflict_factor": report_factor,
        "report_conflict_note": conflict.get("note", "") if conflicting else "",
        "tests": disease["tests"],
        "audiology_note": disease["audiology_note"],
        "expected_pattern": disease["expected_pattern"],
        "expected_type": disease.get("expected_type", "any"),
        "red_flag": disease.get("red_flag", ""),
        "kb_source": disease.get("source", "disease reference"),
    }


def _complaint_guides(complaints: Sequence[str], band: str) -> List[dict]:
    """The source document's ranked causes for these complaints at this age."""
    guides = []
    for key in complaints:
        entry = COMPLAINTS.get(key)
        if not entry:
            continue
        rows = entry["by_age"].get(band, [])
        guides.append({
            "complaint": key,
            "name": entry["name"],
            "age_band": band,
            "causes": [{
                "rank": i + 1, "condition": condition, "complaint": complaint,
                "note": note, "red_flag": flag,
            } for i, (condition, complaint, note, flag) in enumerate(rows)],
        })
    return guides


def _infer_complaints(present: set, explicit: Sequence[str]) -> List[str]:
    """Which presenting complaints the reported symptoms amount to."""
    found = [c for c in explicit if c in COMPLAINTS]
    for key, entry in COMPLAINTS.items():
        if key in found:
            continue
        if any(p in present for p in entry["prompts"]):
            found.append(key)
    return found


def _red_flags(present: set, band: str) -> List[dict]:
    hits = []
    for rule in RED_FLAGS:
        if rule["ages"] and band not in rule["ages"]:
            continue
        if not all(s in present for s in rule["all"]):
            continue
        if rule["any"] and not any(s in present for s in rule["any"]):
            continue
        hits.append({k: rule[k] for k in ("id", "level", "title", "detail", "action")})
    hits.sort(key=lambda r: _URGENCY_RANK.get(r["level"], 9))
    return hits


def occupation_prompt(occupation: Optional[str], present: Iterable[str]) -> Optional[dict]:
    """A prompt to take a noise history when the occupation calls for one.

    Never a recorded exposure: the job title says nothing about years, hours
    or protection, so noise-induced loss stays gated on the clinician's
    answer. Nothing is returned once noise exposure has been recorded.
    """
    if not occupation or not str(occupation).strip():
        return None
    if "noise_exposure" in set(present):
        return None
    text = _normalise(str(occupation))
    for sector, patterns in NOISY_OCCUPATIONS.items():
        if any(re.search(p, text) for p in patterns):
            shown = str(occupation).strip()
            return {
                "id": "occupational_noise",
                "occupation": shown,
                "sector": sector,
                "asserts_exposure": False,
                "text": (f"The recorded occupation (“{shown}”) is in a "
                         f"high-noise sector ({sector}), and noise exposure has "
                         "not been recorded. Ask about it — years in the job, "
                         "hours a day, hearing protection — before ranking "
                         "noise-induced hearing loss in or out."),
            }
    return None


#: Guide rank -> how strongly the source document's ordering argues for it.
_GUIDE_WEIGHT = [1.0, 0.85, 0.7, 0.55, 0.4]

#: Floor applied to a guide cause whose described presentation the patient
#: does not match. It is a floor rather than zero because the ranking still
#: carries information: the commonest cause of a complaint stays on the list
#: even when the history is thin.
_GUIDE_FIT_FLOOR = 0.35


#: Forms of a hearing loss whose onset is not acute.
_NOT_ACUTE_LOSSES = {"gradual_hearing_loss", "fluctuating_hearing_loss"}


def _guide_fit(complaint_text: str, present: set, acute: bool = False) -> float:
    """How well the patient matches the presentation the guide describes.

    Each cause in the source guide comes with its own one-line complaint —
    "Persistent ear discharge with hearing loss", "Severe ear pain, especially
    when touching or pulling the ear". Running those through the same synonym
    matcher as the patient's own words is what separates the cause that
    actually fits from the one that merely tops the list.

    The guide's unqualified "hearing loss" is satisfied by any loss present,
    implied or stated — except for an ``acute`` cause (GUIDE_ACUTE_CAUSES),
    where a loss recorded as gradual or fluctuating is not the loss it
    describes. Onset decides, not how the loss was entered, so the chip
    "gradually worsening hearing" and "hearing loss" with onset gradual give
    the same fit.
    """
    expected = set(parse_symptoms([complaint_text])["symptoms"])
    if not expected:
        return 1.0
    have = set(present)
    if acute and "sudden_hearing_loss" not in have and have & _NOT_ACUTE_LOSSES:
        have.discard("hearing_loss")
    return len(expected & have) / len(expected)


def _merge_guide(ranked: List[dict], guides: List[dict], present: set) -> List[dict]:
    """Fold the complaint guide's ranked causes into the differential.

    The two source documents overlap but neither contains the other. The
    disease reference scores how well the symptoms fit; the complaint guide
    says which causes are actually common for this complaint at this age —
    and it names several conditions (chronic suppurative otitis media, otitis
    externa, BPPV) that the disease reference does not cover at all. Dropping
    them because they are in the other document would be an artefact of how
    the material was filed.

    A condition supported by both sources scores higher than either alone,
    and the response reports the two components separately so a clinician can
    see which is doing the work.

    The guide's one-line presentation is matched against everything present,
    implied symptoms included, with onset deciding whether a loss fits an
    acute cause (``_guide_fit``). The exclusions in GUIDE_ARGUES_AGAINST are
    checked against everything present too. A condition both documents name
    keeps its defining feature whichever document ranks it: the guide places
    Meniere's third for vertigo, and that rank says nothing about a patient
    with neither vertigo nor a fluctuating loss.
    """
    by_key = {entry["key"]: entry for entry in ranked}
    best_guide: Dict[str, dict] = {}

    for guide in guides:
        for cause in guide["causes"]:
            name = cause["condition"]
            plain = name.lower().split(" (")[0].strip()
            key = GUIDE_TO_DISEASE.get(plain, f"guide:{plain}")
            prior = _GUIDE_WEIGHT[min(cause["rank"] - 1, len(_GUIDE_WEIGHT) - 1)]
            fit = _guide_fit(cause["complaint"], present,
                             acute=plain in GUIDE_ACUTE_CAUSES)
            weight = prior * (_GUIDE_FIT_FLOOR + (1 - _GUIDE_FIT_FLOOR) * fit)
            if (by_key.get(key) or {}).get("missing_defining_feature"):
                weight *= _MISSING_DEFINING_FACTOR
            exclusion = GUIDE_ARGUES_AGAINST.get(plain) or {}
            against = [s for s in exclusion.get("symptoms", []) if s in present]
            if against:
                # As strong as an absent defining feature: the symptom is one
                # the condition's own definition rules out.
                weight *= _MISSING_DEFINING_FACTOR
            current = best_guide.get(key)
            if current is None or weight > current["guide_score"]:
                best_guide[key] = {
                    "key": key, "name": name, "guide_score": round(weight, 4),
                    "guide_fit": round(fit, 3), "prior": prior,
                    "rank": cause["rank"], "complaint": cause["complaint"],
                    "note": cause["note"], "red_flag": cause["red_flag"],
                    "source_complaint": guide["name"],
                    "argues_against": [_label(s) for s in against],
                    "against_note": exclusion.get("note", "") if against else "",
                }

    merged: List[dict] = []
    for key, entry in by_key.items():
        guide = best_guide.pop(key, None)
        entry = dict(entry)
        entry["guide_score"] = guide["guide_score"] if guide else 0.0
        entry["guide_rank"] = guide["rank"] if guide else None
        entry["guide_fit"] = guide["guide_fit"] if guide else None
        entry["guide_complaint"] = guide["complaint"] if guide else ""
        entry["guide_note"] = guide["note"] if guide else ""
        entry["sources"] = [entry.get("kb_source", "disease reference")] + (
            [f"complaint guide ({guide['source_complaint']}, #{guide['rank']})"]
            if guide else [])
        if guide and guide["argues_against"]:
            entry["argues_against"] = list(entry.get("argues_against", [])) + [
                s for s in guide["argues_against"]
                if s not in entry.get("argues_against", [])]
            entry["against_note"] = guide["against_note"]
        merged.append(entry)

    # Whatever remains appears only in the complaint guide. The guide is
    # already split by age band and ordered by commonness, so its entries
    # carry neither an age taper nor a commonness weight of their own.
    for key, guide in best_guide.items():
        merged.append({
            "key": key, "name": guide["name"], "category": "guide",
            "symptom_overlap": 0.0, "matched": [],
            "argues_against": guide["argues_against"],
            "against_note": guide["against_note"],
            "missing_key_features": [], "missing_defining_feature": False,
            "age_fit": True, "age_factor": 1.0, "age_note": "",
            "commonness": None, "commonness_factor": 1.0,
            "context_factor": 1.0, "context_note": "",
            "tests": list(GUIDE_ONLY_TESTS),
            "audiology_note": guide["note"] or "",
            "expected_pattern": "", "expected_type": "any",
            "red_flag": ("Flagged in the source guide as not to be missed."
                         if guide["red_flag"] else ""),
            "guide_score": guide["guide_score"], "guide_rank": guide["rank"],
            "guide_fit": guide["guide_fit"],
            "guide_complaint": guide["complaint"], "guide_note": guide["note"],
            "sources": [f"complaint guide ({guide['source_complaint']}, "
                        f"#{guide['rank']})"],
        })

    def _combine(symptom: float, guide: float, age_factor: float) -> float:
        # Agreement between two independent sources counts for more than
        # either alone. Clamped rather than rescaled: dividing by the maximum
        # possible bonus would let corroboration lower a score below what one
        # source gave it on its own, which is the opposite of the intent.
        combined = max(symptom, guide) + 0.15 * min(symptom, guide)
        return round(min(combined * age_factor, 1.0), 4)

    for entry in merged:
        # The commonness weight and the adult-context gate act on the
        # disease-reference component only: the guide's rank already encodes
        # how common a cause is for this complaint at this age.
        fit = (entry.get("symptom_overlap", 0.0)
               * entry.get("context_factor", 1.0))
        age_factor = entry.get("age_factor", 1.0)
        entry["score"] = _combine(fit * entry.get("commonness_factor", 1.0),
                                  entry["guide_score"], age_factor)
        # The same evidence before the commonness weight. Commonness is a
        # prior that orders the list; whether the presentation has separated
        # one condition from the rest is a statement about fit, and the
        # summary judges that on this.
        entry["fit_score"] = _combine(fit, entry["guide_score"], age_factor)
        # The score the same evidence earns once the audiogram has ruled out
        # the reported symptom that contradicts the definition (reconcile).
        report_factor = entry.get("report_conflict_factor", 1.0) or 1.0
        if report_factor < 1.0:
            entry["score_without_report_conflict"] = _combine(
                fit / report_factor * entry.get("commonness_factor", 1.0),
                entry["guide_score"], age_factor)

    merged.sort(key=lambda r: (-r["score"], r["name"]))
    return merged


def _canonical_test(name: str) -> str:
    """Fold "Pure-tone audiometry once stable" onto "Pure-tone audiometry".

    The disease reference qualifies the same test differently per condition.
    Without folding, one test splits into several near-duplicate rows and none
    of them accumulates the votes that should put it at the top of the list.
    """
    lowered = name.lower()
    for known in TEST_PRIORITY:
        stem = known.lower()[:18]
        if lowered.startswith(stem):
            return known
    return name


def _test_rank(name: str) -> int:
    canonical = _canonical_test(name)
    return TEST_PRIORITY.index(canonical) if canonical in TEST_PRIORITY \
        else len(TEST_PRIORITY)


def _battery(ranked: List[dict], limit: int = 5) -> List[dict]:
    """Test battery implied by the leading diagnoses.

    Ordered by how many of the leading candidates call for it. Ties are broken
    by the order these tests are actually run in clinic, so the list reads as
    a sequence — otoscopy, then pure tones, then immittance — rather than an
    alphabetical jumble.
    """
    tally: Dict[str, dict] = {}
    for rank, entry in enumerate(ranked[:limit]):
        for test in entry["tests"]:
            head = _canonical_test(test.split(" - ")[0].split(" (")[0].strip())
            row = tally.setdefault(head, {"test": head, "for": [], "votes": 0})
            if entry["name"] not in row["for"]:
                row["for"].append(entry["name"])
            row["votes"] += (limit - rank)
    return sorted(tally.values(),
                  key=lambda r: (-r["votes"], _test_rank(r["test"]), r["test"]))


def assess(
    age: int,
    complaints: Optional[Sequence[str]] = None,
    symptoms: Optional[Sequence[str]] = None,
    side: str = "unspecified",
    duration: str = "unspecified",
    onset: str = "unknown",
    occupation: Optional[str] = "",
) -> dict:
    """Full symptom-led assessment."""
    age = int(age)
    band = age_band(age)
    parsed = parse_symptoms(list(symptoms or []) + list(complaints or []))
    present = set(parsed["symptoms"])
    evidence = dict(parsed["evidence"])

    # Onset is asked for separately on the intake form; fold it in so the
    # sudden-loss red flag fires without the user having to type it twice.
    if onset == "sudden" and "hearing_loss" in present:
        present.add("sudden_hearing_loss")
        evidence.setdefault("sudden_hearing_loss", "hearing loss, onset recorded as sudden")
    if onset == "gradual" and "hearing_loss" in present:
        present.add("gradual_hearing_loss")
        evidence.setdefault("gradual_hearing_loss", "hearing loss, onset recorded as gradual")

    # After the onset fold, so that only the general symptom the patient
    # actually stated decides the onset, and the implication runs on the
    # completed set.
    implied = _implied(present)
    present |= set(implied)

    scored = [r for r in (
        _score_disease(k, d, present, age, implied) for k, d in DISEASES.items()
    ) if r]

    active_complaints = _infer_complaints(present, list(complaints or []))
    guides = _complaint_guides(active_complaints, band["key"])
    ranked = _merge_guide(scored, guides, present)
    flags = _red_flags(present, band["key"])
    prompts = [p for p in (occupation_prompt(occupation, present),) if p]

    urgency = flags[0]["level"] if flags else ("routine" if ranked else "none")
    top = ranked[0] if ranked else None

    if not present:
        summary = ("No symptoms recorded yet. Enter the presenting complaint to "
                   "get a differential and a suggested test battery.")
    elif flags:
        summary = (f"{flags[0]['title']}. {flags[0]['action']}")
    elif top:
        # Separation is judged on fit, before the commonness prior: a rare
        # condition that fits perfectly has still been separated from the
        # rest, and an uncommon leader must not read as "not yet separated"
        # only because it is uncommon. Measured against every other entry,
        # since the prior can rank a better-fitting one below second place.
        lead_fit = top.get("fit_score", top["score"])
        runner_up = max((r.get("fit_score", r["score"]) for r in ranked[1:]),
                        default=0.0)
        confident = lead_fit >= 0.5 and lead_fit - runner_up >= 0.15
        lead = (f"Findings fit {top['name']} most closely"
                if confident else
                f"{top['name']} leads a differential that is not yet separated")
        summary = (f"{lead}. Next test: "
                   f"{_battery(ranked)[0]['test'] if ranked else 'pure-tone audiometry'}.")
    else:
        summary = ("The reported symptoms do not match any condition in the "
                   "reference set. Record more detail, or proceed with a "
                   "standard battery.")

    from_reference = sum(1 for d in DISEASES.values() if not d.get("source"))
    added = [d for d in DISEASES.values() if d.get("source")]

    return {
        "age": age,
        "age_band": band,
        "side": side,
        "duration": duration,
        "onset": onset,
        "occupation": occupation or "",
        "reported": {
            "symptoms": [{"key": s,
                          "label": _display(s, implied),
                          "matched_on": (f"implied by "
                                         f"{', '.join(_label(x).lower() for x in implied[s])}"
                                         if s in implied else evidence.get(s, s)),
                          "implied": s in implied}
                         for s in sorted(present)],
            "unmatched": parsed["unmatched"],
        },
        "complaints": [{"key": c, "name": COMPLAINTS[c]["name"]}
                       for c in active_complaints],
        "red_flags": flags,
        "urgency": urgency,
        "history_prompts": prompts,
        "differential": ranked[:6],
        "all_scored": len(ranked),
        "complaint_guides": guides,
        "recommended_battery": _battery(ranked),
        "summary": summary,
        "sources": [
            "Presenting-complaint guide (otorrhoea, otalgia, vertigo, headache) "
            "ranked by age band.",
            "Disease reference: main symptoms, most prone age group and "
            f"audiological tests, {from_reference} conditions.",
        ] + [f"{d['name']}: {d['source']}." for d in added],
        "disclaimer": (
            "Decision support from a fixed clinical reference set. It ranks "
            "possibilities and suggests which tests separate them; it does not "
            "diagnose, and it only knows the conditions it was given."
        ),
    }


def catalog() -> dict:
    """Everything the intake form needs to render itself."""
    return {
        "age_bands": [{"key": k, "label": label, "range": [lo, hi]}
                      for k, label, lo, hi in AGE_BANDS],
        "complaints": [{"key": k, "name": v["name"]} for k, v in COMPLAINTS.items()],
        "symptom_groups": [
            {"group": group,
             "symptoms": [{"key": s, "label": SYMPTOM_LABELS.get(s, s),
                           "examples": SYMPTOM_SYNONYMS.get(s, [])[:3]}
                          for s in keys]}
            for group, keys in SYMPTOM_GROUPS.items()
        ],
        "diseases": [{"key": k, "name": v["name"], "category": v["category"],
                      "age_note": v["age_note"], "tests": v["tests"],
                      "expected_pattern": v["expected_pattern"],
                      "audiology_note": v["audiology_note"],
                      "source": v.get("source", "disease reference")}
                     for k, v in DISEASES.items()],
    }


# ==========================================================================
# the history against the audiogram
# ==========================================================================


#: Why a provisional type settles nothing about one component of the loss.
_PROVISIONAL_NOTE = ("bone conduction was not tested, was incomplete, or gave no "
                     "response at the vibrator's output limit")


def _ear_parts(ear: dict) -> Tuple[Optional[bool], Optional[bool], bool]:
    """What one ear's type says about its conductive and sensorineural parts.

    Each part is True (measured present), False (measured absent) or None
    (not determined); the third value is whether the type is provisional.
    rules.py types an ear from air conduction alone when bone conduction was
    not tested, or gave no response at the vibrator's limit, and labels it
    "Sensorineural (provisional)" — in its own caveat, "a conductive
    component cannot be excluded". That label settles neither part. A type
    that is provisional because bone conduction was incomplete reports what
    the tested frequencies measured, and leaves open only the part they could
    not exclude.
    """
    lowered = str(ear.get("type") or "").lower()
    provisional = bool(ear.get("provisional")) or "provisional" in lowered
    base = lowered.replace("(provisional)", "").strip()
    if "(provisional)" in lowered or not base or "indeterminate" in base:
        return None, None, True
    if "mixed" in base:
        return True, True, provisional
    if "conductive" in base:
        return True, (None if provisional else False), provisional
    if "sensorineural" in base:
        return (None if provisional else False), True, provisional
    if "normal" in base:
        # rules.hearing_type types an ear within normal limits Normal even
        # with an air-bone gap over 10 dB, and reports the gap separately: a
        # measured conductive finding without a loss, never "none measured".
        if ear.get("significant_air_bone_gap"):
            return True, False, provisional
        return False, False, provisional
    return None, None, True


def _measured_ears(analysis: Optional[dict]) -> List[dict]:
    """Each ear that has a pure-tone average, with what its type determined."""
    rules = (analysis or {}).get("rules") or {}
    ears = []
    for side in ("right", "left"):
        ear = rules.get(side) or {}
        pta = (ear.get("ac_pta") or {}).get("value")
        if pta is None:
            continue
        conductive, sensorineural, provisional = _ear_parts(ear)
        # An air-bone gap behind normal hearing is a finding, not a loss: the
        # ear stays "within normal limits" for every degree and type reading.
        gap_only = "normal" in str(ear.get("type") or "").lower() and conductive is True
        ears.append({
            "side": side, "pta": pta, "type": ear.get("type") or "untyped",
            "conductive": conductive, "sensorineural": sensorineural,
            "mixed": bool(conductive and sensorineural),
            "provisional": provisional,
            "gap_only": gap_only,
            "abg": (ear.get("abg") or {}).get("value"),
            # A provisional ear with a measured average is still impaired:
            # degree is measured by air conduction alone.
            "impaired": pta >= _NORMAL_PTA_DB or (conductive is True and not gap_only),
        })
    return ears


def _describe(ears: List[dict]) -> str:
    return ", ".join(f"{e['side']} {e['type'].lower()} at {e['pta']:g} dB HL"
                     for e in ears)


def _ear_reading(expected_type: str, ear: dict) -> str:
    """How one measured ear bears on the type of hearing a condition predicts.

    ``fits``; ``against`` (the predicted part measured absent, or a loss where
    normal hearing is predicted); ``undetermined`` (the predicted part was not
    determined — a provisional type); or ``normal``: thresholds within normal
    limits, for a condition that predicts a loss, which by type neither fits
    nor contradicts it.
    """
    if expected_type == "normal":
        return "against" if ear["impaired"] else "fits"
    if not ear["impaired"]:
        return "normal"
    if expected_type in ("conductive", "sensorineural"):
        part = ear[expected_type]
        return ("fits" if part is True else
                "against" if part is False else "undetermined")
    # Mixed: either component can be the early picture (Ralston et al., 2019),
    # so a measured part of either kind fits it and none contradicts it.
    if ear["conductive"] is True or ear["sensorineural"] is True:
        return "fits"
    return "undetermined"


def _unexplained(expected_type: str, ears: List[dict],
                 laterality: Optional[str]) -> List[str]:
    """Measured ears that a possibility the audiogram leaves open does not explain.

    An ear whose loss is of the wrong kind needs its own explanation even
    when the other ear fits. A normal ear beside an affected one is expected
    of a one-sided condition and noted for a two-sided one (presbycusis: a
    marked asymmetry is not presbycusis).
    """
    readings = [(e, _ear_reading(expected_type, e)) for e in ears]
    out = [f"the {e['side']} ear's {e['type'].lower()} loss ({e['pta']:g} dB HL) "
           "is not the type it predicts and needs its own explanation"
           for e, r in readings if r == "against"]
    if laterality == "bilateral" and any(r in ("fits", "undetermined")
                                         for _e, r in readings):
        out += [f"the {e['side']} ear is within normal limits ({e['pta']:g} dB "
                "HL), and it usually affects both ears"
                for e, r in readings if r == "normal"]
    return out


def audiogram_contradiction(expected_type: Optional[str],
                            ears: List[dict]) -> Optional[str]:
    """Why the measured ears contradict the type of hearing a condition predicts.

    Only a measured loss of the wrong kind counts. Thresholds within normal
    limits do not contradict a condition that predicts a loss — early noise
    damage, early presbycusis and Eustachian tube dysfunction can all leave
    the four-frequency average normal, and degree is checked elsewhere
    (``linkage.symptoms_vs_audiogram``). Nor does a part of the loss that was
    never determined: without bone conduction, "no conductive component" is
    not a finding. Returns None when nothing conflicts.
    """
    if not ears or expected_type in (None, "", "any"):
        return None
    impaired = [e for e in ears if e["impaired"]]

    if expected_type == "normal":
        # CAPD is defined by normal peripheral hearing. ASHA (2005) allows it
        # to coexist with a peripheral loss, but the complaint can no longer
        # be attributed to central processing until that loss is accounted
        # for — so this ranks it down, and never removes it. Degree needs only
        # air conduction, so a provisional type does not soften this.
        if impaired:
            return ("it predicts normal pure-tone thresholds, and the audiogram "
                    f"measured a loss ({_describe(impaired)})")
        return None

    if not impaired:
        return None
    if expected_type == "conductive":
        if all(e["conductive"] is False for e in impaired):
            return ("it predicts a conductive component, and the measured loss "
                    f"has none ({_describe(impaired)})")
    elif expected_type == "sensorineural":
        if all(e["sensorineural"] is False for e in impaired):
            return ("it predicts a sensorineural loss, and the measured loss is "
                    f"purely conductive ({_describe(impaired)})")
    # "mixed" is never contradicted by type alone: either component can be the
    # early picture — Paget's skull involvement produces sensorineural,
    # conductive and mixed losses (Ralston et al., 2019).
    return None


def _type_status(expected_type: Optional[str], ears: List[dict],
                 laterality: Optional[str] = None) -> Tuple[str, str]:
    """How the measured type of hearing bears on one possibility, and why.

    ``contradicted`` (with the reason). ``compatible`` when an ear measured
    the predicted part of the loss — the note then names any ear it does not
    explain. ``undetermined`` when no ear measured it and a provisional type
    leaves it open. ``within normal limits`` when it predicts a loss and every
    ear is within normal limits: that does not support it, and does not
    contradict it either. ``no prediction`` when it predicts no type of
    hearing. ``laterality`` is the condition's declared side.
    """
    if expected_type in (None, "", "any"):
        return "no prediction", ""
    reason = audiogram_contradiction(expected_type, ears)
    if reason:
        return "contradicted", reason
    if expected_type == "normal":
        return "compatible", ""
    readings = [_ear_reading(expected_type, e) for e in ears]
    if ears and all(r == "normal" for r in readings):
        gaps = [e for e in ears if e.get("gap_only")]
        gap_note = "".join(
            f"; the {e['side']} ear has an air-bone gap"
            + (f" of {e['abg']:g} dB" if isinstance(e.get("abg"), (int, float)) else "")
            + " behind normal hearing — a conductive finding to check with "
              "tympanometry and otoscopy"
            for e in gaps)
        return "within normal limits", (
            f"the thresholds are within normal limits ({_describe(ears)}) and "
            f"it predicts a {expected_type} loss, so the audiogram does not "
            "support it — but it does not rule it out: an early, fluctuating "
            "or frequency-limited loss can leave the four-frequency average "
            "normal" + gap_note)
    unexplained = "; ".join(_unexplained(expected_type, ears, laterality))
    if "fits" in readings or "undetermined" not in readings:
        return "compatible", unexplained
    open_ears = [e for e, r in zip(ears, readings) if r == "undetermined"]
    part = (f"a {expected_type} component"
            if expected_type in ("conductive", "sensorineural")
            else "either component")
    note = (f"the type of loss is provisional ({_describe(open_ears)}) — "
            f"{_PROVISIONAL_NOTE}, so {part} can be neither confirmed nor "
            "excluded")
    return "undetermined", f"{note}; {unexplained}" if unexplained else note


def _laterality_bar(disease: dict, ears: Optional[List[dict]],
                    asymmetry: Optional[dict]) -> str:
    """Why a condition declared to affect both ears cannot be named on this
    audiogram's laterality; empty when it can.

    Presbycusis is the case in point: its own reference note says marked
    asymmetry is not presbycusis and needs investigating, and NICE NG98
    (rec. 1.3.2) routes an asymmetric sensorineural loss for imaging. A
    measured loss in one ear beside a normal one, or an asymmetry the safety
    engine has flagged for the retrocochlear screen, is therefore not
    evidence for a bilateral condition — it is a reason to investigate.
    """
    if disease.get("laterality") != "bilateral" or not ears:
        return ""
    impaired = [e for e in ears if e["impaired"]]
    normal = [e for e in ears if not e["impaired"]]
    if impaired and normal:
        return (f"it usually affects both ears, and the {normal[0]['side']} ear is "
                "within normal limits — a one-sided loss needs investigating "
                "before it is attributed to a bilateral condition")
    if (asymmetry or {}).get("flag"):
        return ("it usually affects both ears alike, and the audiogram shows an "
                "interaural asymmetry flagged for investigation")
    return ""


def _cannot_lead(row: dict, entry: dict, floor: Optional[float],
                 ears: Optional[List[dict]] = None,
                 asymmetry: Optional[dict] = None) -> str:
    """Why an open possibility may not take the place of a contradicted leader.

    Empty when it may. The audiogram removes a leader; it adds no evidence
    for whatever happens to rank next, so the replacement has to be one the
    history itself singles out. Ruled out:

    - a possibility that predicts no type of hearing (the audiogram cannot
      favour it — every complaint-guide cause is one);
    - one whose defining feature was not reported;
    - one for which the patient stated none of its ``distinguishing``
      features — matched only on a loss, tinnitus or difficulty in noise, it
      is any hearing loss, and naming it would rest on the leader's
      contradiction alone. Paget's disease and cholesteatoma without
      discharge are the cases in point. An age-defined condition is singled
      out by age instead, so it is ruled out only outside that age;
    - one declared to affect both ears, on a one-sided loss or an asymmetry
      flagged for the retrocochlear screen (``_laterality_bar``);
    - one the history supports less than the leader it would replace, even
      after that leader's contradiction penalty — it would then rank above
      it only because contradicted possibilities are sorted last.

    A hand-built entry without its ``matched`` list (or, for an age-defined
    condition, its ``age_fit``) has no stated evidence and is never promoted.
    """
    if row["audiogram"] == "contradicted":
        return "the measured type of hearing contradicts it"
    if row["audiogram"] == "no prediction":
        return ("it predicts no particular type of hearing, so the audiogram "
                "cannot favour it")
    if entry.get("missing_defining_feature"):
        return "its defining feature was not reported"
    disease = DISEASES.get(row.get("key") or "") or {}
    if disease.get("age_defining"):
        if entry.get("age_fit") is False:
            return "the patient is outside the age that defines it"
        if entry.get("age_fit") is not True:
            return "the age that defines it is not recorded on the entry"
    else:
        stated = {m.get("key") for m in (entry.get("matched") or [])
                  if isinstance(m, dict) and not m.get("implied")}
        if not stated & set(disease.get("distinguishing") or []):
            return ("nothing the patient reported distinguishes it from a "
                    "hearing loss in general")
    lateral = _laterality_bar(disease, ears, asymmetry)
    if lateral:
        return lateral
    if floor is not None and row["score"] is not None and row["score"] < floor:
        return ("the history supports it less than the possibility it would "
                "replace, even once that one is set aside")
    return ""


def reconcile(assessment: Optional[dict], analysis: Optional[dict]) -> dict:
    """The history's differential re-ranked against the measured audiogram.

    Works on the differential the clinician was shown, not a re-run of the
    history, so "on history alone X led" refers to the list on the screen.
    A possibility whose predicted type of hearing the audiogram contradicts
    is ranked below every possibility the audiogram leaves open, its score is
    reduced by the same factor as a missing defining feature, and the reason
    is carried with it. Nothing is removed.

    The audiogram can also lift a penalty: a possibility ranked down for a
    reported hearing loss its definition rules out until tested (CAPD) gets
    its unpenalised score back when both ears measure within normal limits.

    Three outcomes. ``unchanged``: the history's leader is not contradicted —
    including when the type is provisional and so cannot contradict it — and
    no lifted penalty overtakes it. ``replaced``: it is contradicted and
    another possibility is well enough supported to lead (see
    ``_cannot_lead``), or a possibility whose penalty was lifted now ranks
    above it (``replaced_because`` says which). ``unresolved``: it is
    contradicted and none is — which is said plainly rather than promoting
    whatever ranks next, because "the audiogram leaves it open" is not
    evidence for it.
    """
    differential = [d for d in ((assessment or {}).get("differential") or [])
                    if isinstance(d, dict) and d.get("name")]
    if not differential:
        return {"available": False, "note": "No differential to reconcile."}
    ears = _measured_ears(analysis)
    if not ears:
        return {"available": False,
                "note": ("No measured thresholds yet — the differential rests on "
                         "the history alone.")}

    # A hearing loss the history reported is ruled out only when both ears
    # were measured and neither has a loss: one ear alone may not be the ear
    # the patient meant.
    loss_ruled_out = (len(ears) == 2 and not any(e["impaired"] for e in ears))

    rows = []
    numeric = True
    for index, entry in enumerate(differential):
        expected_type = entry.get("expected_type") or "any"
        laterality = (DISEASES.get(entry.get("key") or "") or {}).get("laterality")
        status, why = _type_status(expected_type, ears, laterality)
        score = entry.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            numeric = False
            score = None
        contradicted = status == "contradicted"
        adjusted = (round(score * (_AUDIOGRAM_CONFLICT_FACTOR if contradicted
                                   else 1.0), 4)
                    if score is not None else None)
        # The reverse case: a possibility the history ranked down for a
        # reported hearing loss that contradicts its definition until tested
        # (``contradicted_by_report`` — CAPD, which predicts normal pure
        # tones). Thresholds within normal limits in both ears rule that loss
        # out, and its score without the penalty stands.
        lifted = entry.get("score_without_report_conflict")
        lift = (loss_ruled_out and status == "compatible" and score is not None
                and isinstance(lifted, (int, float)) and not isinstance(lifted, bool)
                and lifted > score)
        if lift:
            adjusted = round(float(lifted), 4)
            why = ("the hearing loss the history reported was not measured — both "
                   f"ears are within normal limits ({_describe(ears)}), as it "
                   "predicts — so the report no longer counts against it")
        rows.append({
            "key": entry.get("key"),
            "name": entry["name"],
            "category": entry.get("category"),
            "expected_type": expected_type,
            "expected_pattern": entry.get("expected_pattern", ""),
            "history_rank": index + 1,
            "history_score": score,
            "score": adjusted,
            "audiogram": status,
            "reason": why if contradicted else "",
            "type_note": "" if contradicted else why,
            "report_conflict_lifted": lift,
        })

    history = rows[0]
    leader_contradicted = history["audiogram"] == "contradicted"
    floor = history["score"] if (leader_contradicted and numeric) else None
    asymmetry = (((analysis or {}).get("safety") or {}).get("asymmetry")) or {}
    for row, entry in zip(rows, differential):
        if row is history:
            row["can_lead"], row["cannot_lead_because"] = not leader_contradicted, (
                history["reason"] if leader_contradicted else "")
            continue
        if row["report_conflict_lifted"]:
            # The measured normal thresholds are what single it out — for
            # CAPD, no reported symptom can (ASHA, 2005).
            row["can_lead"], row["cannot_lead_because"] = True, ""
            continue
        why_not = _cannot_lead(row, entry, floor, ears, asymmetry)
        row["can_lead"], row["cannot_lead_because"] = not why_not, why_not

    # A contradicted possibility ranks below every possibility the audiogram
    # leaves open, whatever its history score: the factor alone would let a
    # strong enough history keep a contradicted leader on top, which is the
    # summary this function exists to prevent. Within each group the
    # (adjusted) score orders, and without scores the history's order stands.
    rows.sort(key=lambda r: (r["audiogram"] == "contradicted",
                             -r["score"] if numeric else 0,
                             r["history_rank"]))

    if not leader_contradicted:
        # Nothing set the leader aside, but a possibility whose reported-loss
        # penalty the audiogram lifted may now outrank it.
        if numeric and rows[0] is not history and rows[0]["report_conflict_lifted"]:
            outcome, leading = "replaced", rows[0]
        else:
            outcome, leading = "unchanged", history
    else:
        candidates = [r for r in rows if r is not history and r["can_lead"]]
        outcome, leading = (("replaced", candidates[0]) if candidates
                            else ("unresolved", None))
    all_contradicted = all(r["audiogram"] == "contradicted" for r in rows)
    name = history["name"]
    # Why the history's leader no longer leads: its own contradiction, or the
    # lifted penalty that lets another possibility overtake it.
    replaced_because = ""
    if outcome == "replaced":
        replaced_because = (history["reason"] if leader_contradicted else
                            f"{leading['type_note']}, and {leading['name']} now "
                            "ranks first")

    # When the history's leader is set aside and the loss has a conductive
    # component, explanations such as wax, an effusion or a perforation are
    # ones a history often does not reveal, and two quick tests separate
    # them — whether or not another possibility takes the lead (wax is the
    # commoner cause of a conductive loss at any age the history names).
    # Named as tests to run, never as findings.
    conductive = [e for e in ears if e["impaired"] and e["conductive"] is True]
    next_step = (f"the measured loss has a conductive component "
                 f"({_describe(conductive)}), whose causes — wax, a middle-ear "
                 "effusion, a perforation, a fixed ossicular chain — need not "
                 "show in the history: otoscopy and tympanometry first"
                 if outcome in ("unresolved", "replaced") and conductive else "")

    if outcome == "unchanged":
        if history["audiogram"] == "undetermined":
            headline = (f"{name} still leads; the audiogram can neither confirm "
                        f"nor set it aside by type: {history['type_note']}.")
        elif history["audiogram"] == "no prediction":
            headline = (f"{name} still leads; it predicts no particular type of "
                        "hearing, so the audiogram cannot test it by type.")
        elif history["audiogram"] == "within normal limits":
            headline = f"{name} still leads; {history['type_note']}."
        elif history["type_note"]:
            headline = (f"{name} still leads with the audiogram taken into "
                        f"account, though {history['type_note']}.")
        else:
            headline = (f"{name} still leads with the audiogram taken into "
                        "account.")
    elif outcome == "replaced":
        headline = (f"{leading['name']} leads once the audiogram is taken into "
                    f"account. On the history alone {name} led, but "
                    f"{replaced_because}.")
    elif all_contradicted:
        headline = (f"None of the possibilities the history raised fits the "
                    f"measured audiogram; on the history alone {name} led. "
                    "Revisit the history and the thresholds, or look for a "
                    "cause outside the reference set.")
    else:
        headline = (f"On the history alone {name} led, but {history['reason']}. "
                    "None of the other possibilities the history raised is well "
                    "enough supported to take its place. Revisit the history "
                    "and the thresholds, or look for a cause outside the "
                    "reference set.")
    if next_step:
        headline += f" {next_step[0].upper()}{next_step[1:]}."

    return {
        "available": True,
        "outcome": outcome,
        "leading": leading,
        "next_step": next_step,
        "replaced_because": replaced_because,
        "history_leading": {"key": history["key"], "name": name,
                            "audiogram": history["audiogram"],
                            "reason": history["reason"],
                            "type_note": history["type_note"]},
        "changed": outcome == "replaced",
        "unresolved": outcome == "unresolved",
        "all_contradicted": all_contradicted,
        "type_provisional": any(e["provisional"] and e["impaired"] for e in ears),
        "set_aside": [r for r in rows if r["audiogram"] == "contradicted"],
        "differential": rows,
        "ears": [{"side": e["side"], "type": e["type"], "pta": e["pta"],
                  "provisional": e["provisional"]} for e in ears],
        "headline": headline,
        "note": ("Reconciled on the type of hearing only — normal, conductive or "
                 "sensorineural — against the type each possibility predicts, "
                 "and only where bone conduction determined it. A contradicted "
                 "possibility is ranked down, not removed: the conflict may lie "
                 "in the history or the thresholds. Degree, configuration and "
                 "symmetry are compared in the case linkage."),
    }


def correlate(assessment: dict, analysis: Optional[dict]) -> dict:
    """Does the audiogram support the leading symptom-based diagnosis?

    The differential above is built from what the patient said. Once thresholds
    exist, the two can be checked against each other — and a mismatch is a
    finding, not an error to be smoothed over.
    """
    if not analysis:
        return {"available": False,
                "note": "No audiometry yet — run the test battery to confirm."}

    reconciled = reconcile(assessment, analysis)
    top = (assessment.get("differential") or [None])[0]
    if not top:
        return {"available": False, "note": "No differential to correlate.",
                "reconciled": reconciled}

    # The expected type is a declared field on each disease, not a keyword
    # sniffed out of the prose description — prose that reads perfectly to a
    # human ("notch at 3-6 kHz") contains none of the words a matcher needs.
    expected_type = top.get("expected_type", "any")
    if expected_type == "any":
        return {"available": False,
                "note": f"{top['name']} does not predict a specific audiometric "
                        "type, so there is nothing to reconcile.",
                "reconciled": reconciled}

    supports: List[str] = []
    against: List[str] = []
    undetermined: List[str] = []
    within_normal: List[str] = []
    pattern = top.get("expected_pattern", "")
    name = top["name"]
    predicts = f"{name} predicts a {expected_type} picture — {pattern}."
    laterality = (DISEASES.get(top.get("key") or "") or {}).get("laterality")
    ears = _measured_ears(analysis)
    # The verdict comes from the same reading of the ears as the history line
    # on the Results screen, so the two cannot disagree about the same case.
    status, note = _type_status(expected_type, ears, laterality)
    for ear in ears:
        described = (f"{ear['side'].title()} ear is {ear['type']} "
                     f"(PTA {ear['pta']:g} dB HL)")
        reading = _ear_reading(expected_type, ear)
        if reading == "undetermined":
            # Without bone conduction a part of the loss is not determined,
            # and an undetermined part neither fits nor contradicts.
            undetermined.append(
                f"{described}; the type is provisional — {_PROVISIONAL_NOTE} — "
                f"so it can neither confirm nor rule out the {expected_type} "
                f"picture {name} predicts.")
        elif reading == "normal":
            affected = any(o["impaired"] for o in ears if o is not ear)
            if affected and laterality in ("unilateral", "either"):
                # A one-sided condition predicts a normal opposite ear: that
                # ear is the expected half of the picture, not a mismatch.
                supports.append(
                    f"{described}, as expected opposite the affected ear: "
                    f"{name} {'is usually' if laterality == 'unilateral' else 'can be'} "
                    "one-sided.")
            elif affected and laterality == "bilateral":
                against.append(f"{described}; {name} usually affects both "
                               f"ears — {pattern}.")
            else:
                within_normal.append(f"{described}; {predicts}")
        else:
            (supports if reading == "fits" else against).append(
                f"{described}; {predicts}")

    def _sentence(clause: str) -> str:
        return f"{clause[0].upper()}{clause[1:]}." if clause else ""

    if status == "contradicted":
        verdict = ("The audiogram does not fit the leading diagnosis — revisit "
                   "the history or the thresholds.")
        # Say what the same differential offers in its place — or that it
        # offers nothing well supported, rather than naming whatever ranks
        # next.
        if reconciled.get("available"):
            if reconciled["outcome"] == "replaced":
                verdict += (f" Of the other possibilities the history raised, "
                            f"{reconciled['leading']['name']} is not "
                            "contradicted by the measured type of hearing, and "
                            "the history singles it out.")
            elif reconciled["all_contradicted"]:
                verdict += (" None of the possibilities the history raised "
                            "fits the measured type of hearing.")
            elif reconciled["outcome"] == "unresolved":
                verdict += (" None of the other possibilities the history "
                            "raised is well enough supported to take its "
                            "place.")
            if reconciled.get("next_step"):
                verdict += " " + _sentence(reconciled["next_step"])
    elif status == "within normal limits":
        verdict = (f"Thresholds are within normal limits. {name} predicts a "
                   f"{expected_type} loss, so the audiogram does not support it "
                   "— but it does not rule it out: an early, fluctuating or "
                   "frequency-limited loss can leave the four-frequency average "
                   "normal.")
    elif status == "undetermined":
        verdict = ("The type of loss is provisional, so the audiogram can "
                   "neither confirm nor rule out the leading diagnosis — "
                   "complete bone conduction, masked where needed, to settle it.")
        if against:
            verdict += " " + _sentence(
                "; ".join(_unexplained(expected_type, ears, laterality)))
    elif against:
        verdict = ("The audiogram fits the leading diagnosis only in part: "
                   f"{note}.")
    elif supports and undetermined:
        verdict = ("The audiogram is consistent with the leading diagnosis "
                   "where the type of loss was measured; elsewhere the type is "
                   "provisional.")
    elif supports:
        verdict = "The audiogram is consistent with the leading diagnosis."
    else:
        verdict = "Not enough of the audiogram to correlate."

    return {
        "available": True,
        "diagnosis": top["name"],
        "expected_type": expected_type,
        "expected_pattern": pattern,
        "supports": supports,
        "against": against,
        "undetermined": undetermined,
        # Ears within normal limits when the leader predicts a loss and no ear
        # has one: neither support nor a mismatch by type.
        "within_normal_limits": within_normal,
        "audiogram": status,
        "verdict": verdict,
        "reconciled": reconciled,
    }
