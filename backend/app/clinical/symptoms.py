"""Symptom-led assessment: what the patient says, before any test is run.

A woman walks in and says water keeps coming out of her ear. That sentence
already narrows the differential, already determines which tests are worth
running, and — if she is seventy and diabetic — already carries a red flag
that outranks everything the audiogram will say. This module turns the
complaint into a ranked differential, a recommended test battery, and an
urgency level, using only the two clinical documents encoded in
``symptom_kb``.

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

RED FLAGS DO NOT COMPETE WITH THE DIFFERENTIAL. They are evaluated
separately and reported above it, because "this might be meningitis" is not
a fourth-place possibility.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence

from app.clinical.symptom_kb import (
    AGE_BANDS, COMPLAINTS, DISEASES, GUIDE_ONLY_TESTS, GUIDE_TO_DISEASE,
    RED_FLAGS, SYMPTOM_GROUPS, SYMPTOM_LABELS, SYMPTOM_SYNONYMS, TEST_PRIORITY,
    age_band,
)

#: Longest synonyms first, so "severe ear pain" wins over "ear pain".
_MATCH_ORDER: List[tuple] = sorted(
    ((phrase, canonical)
     for canonical, phrases in SYMPTOM_SYNONYMS.items()
     for phrase in phrases),
    key=lambda pair: -len(pair[0]),
)

_URGENCY_RANK = {"emergency": 0, "urgent": 1, "watch": 2, "routine": 3}


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


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


def _score_disease(key: str, disease: dict, present: set, band: str) -> Optional[dict]:
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
        overlap *= 0.35

    age_fit = band in disease["age_bands"]
    score = overlap * (1.0 if age_fit else 0.6)

    return {
        "key": key,
        "name": disease["name"],
        "category": disease["category"],
        "score": round(score, 4),
        "symptom_overlap": round(overlap, 4),
        "matched": [{"key": s, "label": SYMPTOM_LABELS.get(s, s),
                     "weight": positive[s]} for s in sorted(matched, key=lambda s: -positive[s])],
        "argues_against": [SYMPTOM_LABELS.get(s, s) for s in against],
        "missing_key_features": [SYMPTOM_LABELS.get(r, r) for r in required
                                 if r not in present],
        "missing_defining_feature": missing_defining,
        "age_fit": age_fit,
        "age_note": disease["age_note"],
        "tests": disease["tests"],
        "audiology_note": disease["audiology_note"],
        "expected_pattern": disease["expected_pattern"],
        "expected_type": disease.get("expected_type", "any"),
        "red_flag": disease.get("red_flag", ""),
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


#: Guide rank -> how strongly the source document's ordering argues for it.
_GUIDE_WEIGHT = [1.0, 0.85, 0.7, 0.55, 0.4]

#: Floor applied to a guide cause whose described presentation the patient
#: does not match. It is a floor rather than zero because the ranking still
#: carries information: the commonest cause of a complaint stays on the list
#: even when the history is thin.
_GUIDE_FIT_FLOOR = 0.35


def _guide_fit(complaint_text: str, present: set) -> float:
    """How well the patient matches the presentation the guide describes.

    Each cause in the source guide comes with its own one-line complaint —
    "Persistent ear discharge with hearing loss", "Severe ear pain, especially
    when touching or pulling the ear". Running those through the same synonym
    matcher as the patient's own words is what separates the cause that
    actually fits from the one that merely tops the list.
    """
    expected = set(parse_symptoms([complaint_text])["symptoms"])
    if not expected:
        return 1.0
    return len(expected & present) / len(expected)


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
    """
    by_key = {entry["key"]: entry for entry in ranked}
    best_guide: Dict[str, dict] = {}

    for guide in guides:
        for cause in guide["causes"]:
            name = cause["condition"]
            plain = name.lower().split(" (")[0].strip()
            key = GUIDE_TO_DISEASE.get(plain, f"guide:{plain}")
            prior = _GUIDE_WEIGHT[min(cause["rank"] - 1, len(_GUIDE_WEIGHT) - 1)]
            fit = _guide_fit(cause["complaint"], present)
            weight = prior * (_GUIDE_FIT_FLOOR + (1 - _GUIDE_FIT_FLOOR) * fit)
            current = best_guide.get(key)
            if current is None or weight > current["guide_score"]:
                best_guide[key] = {
                    "key": key, "name": name, "guide_score": round(weight, 4),
                    "guide_fit": round(fit, 3), "prior": prior,
                    "rank": cause["rank"], "complaint": cause["complaint"],
                    "note": cause["note"], "red_flag": cause["red_flag"],
                    "source_complaint": guide["name"],
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
        entry["sources"] = ["disease reference"] + (
            [f"complaint guide ({guide['source_complaint']}, #{guide['rank']})"]
            if guide else [])
        merged.append(entry)

    # Whatever remains appears only in the complaint guide.
    for key, guide in best_guide.items():
        merged.append({
            "key": key, "name": guide["name"], "category": "guide",
            "symptom_overlap": 0.0, "matched": [], "argues_against": [],
            "missing_key_features": [], "missing_defining_feature": False,
            "age_fit": True, "age_note": "",
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

    for entry in merged:
        symptom = entry.get("symptom_overlap", 0.0)
        # Agreement between two independent sources counts for more than
        # either alone. Clamped rather than rescaled: dividing by the maximum
        # possible bonus would let corroboration lower a score below what one
        # source gave it on its own, which is the opposite of the intent.
        combined = max(symptom, entry["guide_score"]) + \
            0.15 * min(symptom, entry["guide_score"])
        if not entry.get("age_fit", True):
            combined *= 0.6
        entry["score"] = round(min(combined, 1.0), 4)

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
) -> dict:
    """Full symptom-led assessment."""
    band = age_band(int(age))
    parsed = parse_symptoms(list(symptoms or []) + list(complaints or []))
    present = set(parsed["symptoms"])

    # Onset is asked for separately on the intake form; fold it in so the
    # sudden-loss red flag fires without the user having to type it twice.
    if onset == "sudden" and "hearing_loss" in present:
        present.add("sudden_hearing_loss")
    if onset == "gradual" and "hearing_loss" in present:
        present.add("gradual_hearing_loss")

    scored = [r for r in (
        _score_disease(k, d, present, band["key"]) for k, d in DISEASES.items()
    ) if r]

    active_complaints = _infer_complaints(present, list(complaints or []))
    guides = _complaint_guides(active_complaints, band["key"])
    ranked = _merge_guide(scored, guides, present)
    flags = _red_flags(present, band["key"])

    urgency = flags[0]["level"] if flags else ("routine" if ranked else "none")
    top = ranked[0] if ranked else None

    if not present:
        summary = ("No symptoms recorded yet. Enter the presenting complaint to "
                   "get a differential and a suggested test battery.")
    elif flags:
        summary = (f"{flags[0]['title']}. {flags[0]['action']}")
    elif top:
        confident = top["score"] >= 0.5 and (
            len(ranked) == 1 or top["score"] - ranked[1]["score"] >= 0.15)
        lead = (f"Findings fit {top['name']} most closely"
                if confident else
                f"{top['name']} leads a differential that is not yet separated")
        summary = (f"{lead}. Next test: "
                   f"{_battery(ranked)[0]['test'] if ranked else 'pure-tone audiometry'}.")
    else:
        summary = ("The reported symptoms do not match any condition in the "
                   "reference set. Record more detail, or proceed with a "
                   "standard battery.")

    return {
        "age": int(age),
        "age_band": band,
        "side": side,
        "duration": duration,
        "onset": onset,
        "reported": {
            "symptoms": [{"key": s, "label": SYMPTOM_LABELS.get(s, s),
                          "matched_on": parsed["evidence"].get(s, s)}
                         for s in sorted(present)],
            "unmatched": parsed["unmatched"],
        },
        "complaints": [{"key": c, "name": COMPLAINTS[c]["name"]}
                       for c in active_complaints],
        "red_flags": flags,
        "urgency": urgency,
        "differential": ranked[:6],
        "all_scored": len(ranked),
        "complaint_guides": guides,
        "recommended_battery": _battery(ranked),
        "summary": summary,
        "sources": [
            "Presenting-complaint guide (otorrhoea, otalgia, vertigo, headache) "
            "ranked by age band.",
            "Disease reference: main symptoms, most prone age group and "
            "audiological tests, 14 conditions.",
        ],
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
                      "audiology_note": v["audiology_note"]}
                     for k, v in DISEASES.items()],
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

    top = (assessment.get("differential") or [None])[0]
    if not top:
        return {"available": False, "note": "No differential to correlate."}

    # The expected type is a declared field on each disease, not a keyword
    # sniffed out of the prose description — prose that reads perfectly to a
    # human ("notch at 3-6 kHz") contains none of the words a matcher needs.
    expected_type = top.get("expected_type", "any")
    if expected_type == "any":
        return {"available": False,
                "note": f"{top['name']} does not predict a specific audiometric "
                        "type, so there is nothing to reconcile."}

    supports: List[str] = []
    against: List[str] = []
    rules = analysis.get("rules") or {}
    for side in ("right", "left"):
        ear = rules.get(side) or {}
        pta = (ear.get("ac_pta") or {}).get("value")
        if pta is None:
            continue
        ear_type = ear.get("type", "")
        lowered = ear_type.lower()
        conductive = "conductive" in lowered
        mixed = "mixed" in lowered
        sensorineural = "sensorineural" in lowered

        if expected_type == "conductive":
            fits = conductive or mixed
        elif expected_type == "mixed":
            fits = mixed
        elif expected_type == "sensorineural":
            fits = sensorineural or (not conductive and not mixed and pta >= 20)
        else:  # normal
            fits = pta < 20

        line = (f"{side.title()} ear is {ear_type or 'untyped'} "
                f"(PTA {pta:g} dB HL); {top['name']} predicts a "
                f"{expected_type} picture — {top['expected_pattern']}.")
        (supports if fits else against).append(line)

    return {
        "available": True,
        "diagnosis": top["name"],
        "expected_type": expected_type,
        "expected_pattern": top["expected_pattern"],
        "supports": supports,
        "against": against,
        "verdict": ("The audiogram is consistent with the leading diagnosis."
                    if supports and not against else
                    "The audiogram does not fit the leading diagnosis — revisit "
                    "the history or the thresholds." if against else
                    "Not enough of the audiogram to correlate."),
    }
