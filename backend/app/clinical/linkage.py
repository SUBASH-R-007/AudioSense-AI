"""Cross-linking the four assessments: history, image, immittance, audiogram.

Each module in this app answers a different question, and each one can be
wrong on its own. The history says what the patient notices; the image says
what the ear looks like; tympanometry says whether the middle ear moves; the
audiogram says how much is lost and where. None of them is the diagnosis.

The diagnosis is in whether they AGREE — and when they do not, in naming the
specific disagreement rather than averaging it away. That is what this module
does. Every link is bidirectional and every claim is traceable to a rule
stated in ``symptom_kb``:

    otoscopy  <-> symptoms    the appearance predicts what the patient reports
    symptoms  <-> audiogram   the differential predicts a type, degree and side
    immittance <-> diseases   each Jerger type supports some, excludes others
    PTA       <-> symptoms    a reported loss should show up in the thresholds

A deliberate asymmetry runs through all of it: **a confirmation is weaker
evidence than a contradiction.** Two tests agreeing may only mean they share
an assumption. Two tests that cannot both be true means one of them is wrong,
and that is always worth a clinician's attention. So conflicts sort first,
carry an action, and are never hidden behind a reassuring headline.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from app.clinical.symptom_kb import (
    DISEASE_AUDIOGRAM, DISEASES, OTOSCOPY_DISEASE_LINKS, OTOSCOPY_LINKS,
    REFLEX_LINKS, SYMPTOM_LABELS, TYMPANOGRAM_LINKS,
)

#: Frequencies compared when matching an audiogram against a disease's
#: characteristic shape.
MATCH_FREQS = [250, 500, 1000, 2000, 4000, 8000]

#: WHO 2021 grade boundaries, reused so linkage speaks the same language as
#: the rules engine rather than inventing a second vocabulary.
WHO_BANDS = [
    (0, 20, "normal"), (20, 35, "mild"), (35, 50, "moderate"),
    (50, 65, "moderately severe"), (65, 80, "severe"), (80, 999, "profound"),
]


def _grade(pta: Optional[float]) -> Optional[str]:
    if pta is None:
        return None
    for lo, hi, name in WHO_BANDS:
        if lo <= pta < hi:
            return name
    return "profound"


def _disease_name(key: str) -> str:
    entry = DISEASES.get(key)
    return entry["name"] if entry else key


def _label(symptom: str) -> str:
    return SYMPTOM_LABELS.get(symptom, symptom.replace("_", " "))


def _finding(kind: str, title: str, detail: str, action: str = "",
             weight: float = 1.0) -> dict:
    return {"kind": kind, "title": title, "detail": detail,
            "action": action, "weight": weight}


# ==========================================================================
# 1. otoscopy  <->  symptoms
# ==========================================================================
def otoscopy_vs_symptoms(otoscopy: Optional[dict],
                         assessment: Optional[dict]) -> dict:
    """Does what the ear looks like match what the patient reports?

    The image classifier is weak on its own — that is stated plainly wherever
    it is shown. This check does not depend on it being right. It asks a
    different question: given that this is what the drum appears to be, are
    the patient's symptoms the ones it would produce? Agreement raises
    confidence in a label the classifier could not earn alone; disagreement
    says one of the two is wrong, which is worth knowing either way.
    """
    if not otoscopy or not assessment:
        return {"available": False,
                "note": ("Needs both an otoscope image and a symptom history. "
                         "Record whichever is missing to enable the check.")}

    label = (otoscopy.get("prediction") or {}).get("label")
    link = OTOSCOPY_LINKS.get(label)
    if not link:
        return {"available": False, "note": "No linkage rule for this pattern."}

    present = {s["key"] for s in (assessment.get("reported") or {}).get("symptoms", [])}
    expects = [s for s in link["expects"] if s in present]
    missing = [s for s in link["expects"] if s not in present]
    unexplained = [s for s in link["unexplained"] if s in present]

    findings: List[dict] = []

    if expects:
        findings.append(_finding(
            "agreement",
            f"History matches the otoscopic appearance",
            f"{otoscopy['prediction']['name']} typically presents with "
            f"{', '.join(_label(s).lower() for s in link['expects'])}. "
            f"This patient reports {', '.join(_label(s).lower() for s in expects)}.",
            weight=len(expects) / max(len(link["expects"]), 1),
        ))

    if unexplained:
        findings.append(_finding(
            "conflict",
            "Symptoms the appearance does not explain",
            f"{', '.join(_label(s) for s in unexplained)} "
            f"{'is' if len(unexplained) == 1 else 'are'} reported, but "
            f"{otoscopy['prediction']['name'].lower()} does not account for "
            f"{'it' if len(unexplained) == 1 else 'them'}. {link['note']}",
            action="Re-examine the ear and the canal; consider a second pathology.",
            weight=1.0,
        ))

    # Does the symptom differential independently name a condition this
    # appearance points at? That is two methods reaching the same answer from
    # different evidence, which is the strongest signal available here.
    ranked = assessment.get("differential") or []
    named = {c.lower() for c in link["conditions"]}
    hits = [d for d in ranked[:6]
            if d["key"] in link["conditions"] or d["name"].lower() in named]
    if hits:
        top = hits[0]
        findings.append(_finding(
            "agreement",
            "Image and history point at the same condition",
            f"The symptom differential ranks {top['name']} at "
            f"{round(top['score'] * 100)}, and the otoscopic appearance "
            f"({otoscopy['prediction']['name']}) independently points there.",
            weight=1.2,
        ))
    elif ranked and link["conditions"]:
        findings.append(_finding(
            "conflict",
            "Image and history point elsewhere",
            f"The appearance suggests {', '.join(link['conditions'][:2])}, but "
            f"the history leads towards {ranked[0]['name']}.",
            action="Neither is established. Run the battery both agree on before "
                   "committing to either.",
            weight=0.8,
        ))

    # A normal drum has no symptoms of its own to match, so without an
    # explicit statement it would report "insufficient" — which reads as
    # "nothing to say" when in fact it has just excluded the entire
    # middle-ear differential.
    if label == "normal" and not unexplained:
        findings.append(_finding(
            "agreement",
            "Normal appearance is consistent with the history",
            "Nothing in the reported symptoms requires a middle-ear cause, and "
            "the drum looks normal. A loss present here is unlikely to be "
            "conductive, which redirects the workup to the cochlea and the nerve.",
            weight=0.7,
        ))

    # Silent-but-dangerous: the one place where absence of symptoms must not
    # be allowed to reassure.
    if label in ("perforation_attic", "tumor") and not expects:
        findings.append(_finding(
            "conflict",
            "Dangerous appearance with no supporting symptoms",
            f"{otoscopy['prediction']['name']} is present on the image while the "
            "history is unremarkable. Early attic disease and small middle-ear "
            "masses are frequently silent — the absence of symptoms is not "
            "reassurance here.",
            action="Refer on the examination, not the history.",
            weight=1.5,
        ))

    return _summarise(findings, extra={
        "available": True,
        "otoscopy_label": label,
        "otoscopy_name": otoscopy["prediction"]["name"],
        "expected_symptoms": [{"key": s, "label": _label(s), "present": s in present}
                              for s in link["expects"]],
        "missing_symptoms": [_label(s) for s in missing],
        "unexplained_symptoms": [_label(s) for s in unexplained],
        "note": link["note"],
    })


# ==========================================================================
# 1b. otoscopy  ->  diseases, with nothing else recorded
# ==========================================================================
def otoscopy_vs_diseases(otoscopy: Optional[dict]) -> dict:
    """A ranked differential from the image alone.

    Deliberately independent of the history. A scope goes in the ear before
    the patient is in the booth, and the appearance already narrows the
    differential — requiring a symptom history first would make the image
    useless at the moment it is actually taken.

    Uncertainty in the classifier is carried through rather than discarded:
    the ranked class probabilities weight the disease scores, so a picture the
    model cannot separate produces a differential that is correspondingly
    spread out instead of a confident answer built on a coin flip.
    """
    if not otoscopy:
        return {"available": False, "note": "No otoscope image recorded."}

    ranked_patterns = otoscopy.get("ranked") or []
    if not ranked_patterns:
        label = (otoscopy.get("prediction") or {}).get("label")
        if not label:
            return {"available": False, "note": "No otoscopic pattern to work from."}
        ranked_patterns = [{"label": label, "probability": 1.0}]

    scores: Dict[str, float] = {}
    excluded: Dict[str, float] = {}
    other: List[str] = []
    reasoning: List[str] = []

    for entry in ranked_patterns:
        weight = float(entry.get("probability", 0.0))
        if weight < 0.02:
            continue
        link = OTOSCOPY_DISEASE_LINKS.get(entry["label"])
        if not link:
            continue
        for key, strength in link["supports"].items():
            scores[key] = scores.get(key, 0.0) + weight * strength
        for key in link["excludes"]:
            excluded[key] = excluded.get(key, 0.0) + weight
        if weight >= 0.25:
            other.extend(c for c in link["other"] if c not in other)
            if link["reasoning"] not in reasoning:
                reasoning.append(link["reasoning"])

    # A disease the leading appearance argues against is removed from the
    # ranking rather than quietly out-scored, and reported separately.
    for key, weight in excluded.items():
        if weight >= 0.5:
            scores.pop(key, None)

    top = max(scores.values()) if scores else 0.0
    differential = sorted(
        ({"key": k, "name": _disease_name(k),
          "score": round(v / top, 3) if top else 0.0,
          "raw": round(v, 3)} for k, v in scores.items()),
        key=lambda d: (-d["score"], d["name"]),
    )
    # A pattern the classifier gave 3% to still drags its whole disease list in
    # at 3% of the weight. Those are not candidates, they are arithmetic, and
    # printing them makes the differential look longer than it is.
    differential = [d for d in differential if d["score"] >= 0.05]

    # A normal drum supports every cochlear and neural cause equally, so the
    # leaders tie. Presenting a tie as a ranking would imply a discrimination
    # the image cannot make.
    tied = [d["name"] for d in differential
            if differential and d["score"] >= differential[0]["score"] - 1e-6]
    separated = len(tied) == 1 and (
        len(differential) == 1
        or differential[0]["score"] - differential[1]["score"] >= 0.15)

    leading = (otoscopy.get("prediction") or {}).get("label")
    if leading == "normal":
        headline = ("A normal drum excludes the middle-ear causes; it cannot "
                    "rank the cochlear and neural ones against each other.")
    elif separated:
        headline = f"The appearance points to {differential[0]['name']}."
    elif len(tied) > 1:
        headline = ("The appearance does not discriminate between "
                    + ", ".join(tied[:3]) + ".")
    elif differential:
        headline = (f"{differential[0]['name']} leads, but the appearance does "
                    "not separate it clearly.")
    else:
        headline = "No disease in the reference set is linked to this appearance."

    return {
        "available": True,
        "from": "otoscopy",
        "pattern": otoscopy["prediction"]["name"],
        "certainty": otoscopy["prediction"].get("certainty"),
        "differential": differential,
        "separated": separated,
        "tied": tied if len(tied) > 1 else [],
        "headline": headline,
        "argues_against": [{"key": k, "name": _disease_name(k)}
                           for k in sorted(excluded) if excluded[k] >= 0.5],
        "other_conditions": other,
        "reasoning": reasoning,
        "note": ("Ranked from the image alone, weighted by the classifier's own "
                 "uncertainty. It needs no history and no audiogram — and it "
                 "inherits the classifier's accuracy, so read it as a prompt "
                 "list rather than a conclusion."),
    }


# ==========================================================================
# 1c. audiogram  ->  diseases, with nothing else recorded
# ==========================================================================
def _ac_numeric(analysis: dict, side: str) -> Dict[int, float]:
    raw = ((analysis.get("thresholds") or {}).get(side) or {}).get("ac") or {}
    out: Dict[int, float] = {}
    for freq, value in raw.items():
        if value is None:
            continue
        out[int(freq)] = 120.0 if value == "NR" else float(value)
    return out


def _shape_similarity(measured: Dict[int, float],
                      reference: Dict[int, float]) -> Optional[float]:
    """How closely two audiograms agree in SHAPE, ignoring overall level.

    Both curves are centred on their own mean before comparing, so a 4 kHz
    notch matches a 4 kHz notch whether the patient's is 20 dB deep or 50.
    Level is scored separately against the disease's expected PTA range —
    keeping the two apart is what lets the result say *which* of them is wrong.
    """
    shared = [f for f in MATCH_FREQS if f in measured and f in reference]
    if len(shared) < 4:
        return None
    m_mean = sum(measured[f] for f in shared) / len(shared)
    r_mean = sum(reference[f] for f in shared) / len(shared)
    deviation = sum(abs((measured[f] - m_mean) - (reference[f] - r_mean))
                    for f in shared) / len(shared)
    # 25 dB of mean shape error is treated as no resemblance at all.
    return max(0.0, 1.0 - deviation / 25.0)


def audiogram_vs_diseases(analysis: Optional[dict], side: str = "right") -> dict:
    """A ranked differential from the thresholds alone.

    Three independent components, reported separately because they fail
    separately: the **shape** of the curve, the **degree** against the range
    each disease produces, and the **type** from the air-bone gap. A disease
    can match the shape perfectly and be excluded by the type, and a clinician
    needs to see which of the three disagreed.
    """
    if not analysis:
        return {"available": False, "note": "No audiogram recorded."}

    measured = _ac_numeric(analysis, side)
    if len(measured) < 4:
        return {"available": False,
                "note": f"Too few {side}-ear thresholds to match a pattern."}

    rules_ear = (analysis.get("rules") or {}).get(side) or {}
    pta = (rules_ear.get("ac_pta") or {}).get("value")
    ear_type = (rules_ear.get("type") or "").lower()
    conductive = "conductive" in ear_type
    mixed = "mixed" in ear_type

    rules = analysis.get("rules") or {}
    ptas = [(rules.get(s) or {}).get("ac_pta", {}).get("value")
            for s in ("right", "left")]
    ptas = [p for p in ptas if p is not None]
    asymmetry = round(max(ptas) - min(ptas), 1) if len(ptas) == 2 else None

    rows: List[dict] = []
    for key, disease in DISEASES.items():
        reference = DISEASE_AUDIOGRAM.get(key)
        if not reference:
            continue
        shape = _shape_similarity(measured, reference["ac"])
        if shape is None:
            continue

        lo, hi = disease["expected_pta"]
        if pta is None:
            level = 0.5
        elif lo <= pta <= hi:
            level = 1.0
        else:
            over = pta - hi if pta > hi else lo - pta
            level = max(0.0, 1.0 - over / 30.0)

        expected_type = disease.get("expected_type", "any")
        if expected_type == "any":
            type_fit = 0.6
        elif expected_type == "conductive":
            type_fit = 1.0 if (conductive or mixed) else 0.15
        elif expected_type == "mixed":
            type_fit = 1.0 if mixed else (0.5 if conductive else 0.15)
        elif expected_type == "sensorineural":
            type_fit = 0.15 if (conductive or mixed) else 1.0
        else:  # normal
            type_fit = 1.0 if (pta is not None and pta < 20) else 0.15

        laterality = disease.get("laterality", "either")
        if asymmetry is None or laterality == "either":
            side_fit = 0.75
        elif laterality == "unilateral":
            side_fit = 1.0 if asymmetry >= 15 else 0.4
        else:
            side_fit = 1.0 if asymmetry < 15 else 0.4

        score = 0.40 * shape + 0.25 * level + 0.25 * type_fit + 0.10 * side_fit
        rows.append({
            "key": key,
            "name": disease["name"],
            "score": round(score, 3),
            "shape_match": round(shape, 3),
            "level_match": round(level, 3),
            "type_match": round(type_fit, 3),
            "laterality_match": round(side_fit, 3),
            "expected_shape": reference["shape"],
            "expected_type": expected_type,
            "expected_pta": [lo, hi],
            "note": reference["note"],
            "reference_ac": reference["ac"],
            "reference_bc": reference["bc"],
        })

    rows.sort(key=lambda r: (-r["score"], r["name"]))
    best = rows[0] if rows else None
    separated = bool(best and (len(rows) == 1
                               or best["score"] - rows[1]["score"] >= 0.08))

    # A normal audiogram is not a disease that happens to look normal. Two
    # conditions in the reference set present with normal pure tones, and
    # pattern-matching would otherwise rank one of them first and read as a
    # diagnosis of a patient whose hearing is fine.
    normal_audiogram = pta is not None and pta < 20 and not (conductive or mixed)
    if normal_audiogram:
        headline = (f"The {side} ear is within normal limits ({pta:g} dB HL) — no "
                    "loss pattern to match. The conditions below are the ones "
                    "that present WITH a normal audiogram; they are not ranked "
                    "against a loss.")
    elif best:
        headline = (f"The {side} audiogram most closely matches {best['name']}"
                    + ("." if separated
                       else ", but the leading candidates are not separated."))
    else:
        headline = "No characteristic pattern matched."

    return {
        "available": True,
        "from": "audiogram",
        "ear": side,
        "measured_ac": measured,
        "pta": pta,
        "ear_type": rules_ear.get("type"),
        "asymmetry_db": asymmetry,
        "normal_audiogram": normal_audiogram,
        "differential": rows[:6],
        "headline": headline,
        "separated": separated and not normal_audiogram,
        "note": ("Matched against textbook configurations by shape, degree, type "
                 "and symmetry, each scored separately. Shape is compared with "
                 "the overall level removed, so a notch matches a notch whatever "
                 "its depth. This is a pattern resemblance, not a diagnosis."),
    }


# ==========================================================================
# 2 + 4. symptoms / PTA  <->  audiogram
# ==========================================================================
def symptoms_vs_audiogram(assessment: Optional[dict],
                          analysis: Optional[dict]) -> dict:
    """Check the leading differential against type, degree and symmetry.

    Three separate comparisons, because a diagnosis predicts three separate
    things about an audiogram and they fail independently. Presbycusis with a
    conductive gap is wrong about the type; presbycusis at 90 dB is wrong about
    the degree; presbycusis in one ear only is wrong about the symmetry — and
    each of those points somewhere different.
    """
    if not assessment or not analysis:
        return {"available": False,
                "note": "Needs both a symptom history and an audiogram."}

    # Only the disease reference predicts an audiometric pattern; the complaint
    # guide ranks causes but says nothing about thresholds. So the correlation
    # runs against the highest-ranked entry that HAS a prediction — and reports
    # its rank, because silently correlating against the third item while the
    # page shows a different leader would be quietly misleading.
    full = assessment.get("differential") or []
    ranked = [(i, d) for i, d in enumerate(full) if d.get("key") in DISEASES]
    if not ranked:
        return {"available": False,
                "note": ("The leading possibilities all come from the complaint "
                         "guide, which does not predict an audiometric pattern. "
                         "Nothing to reconcile.")}

    index, top = ranked[0]
    disease = DISEASES[top["key"]]
    rank_note = ""
    if index > 0:
        rank_note = (f"Correlated against {top['name']} (ranked #{index + 1}); "
                     f"{full[0]['name']} leads the differential but comes from "
                     "the complaint guide, which predicts no audiometric pattern.")
    rules = analysis.get("rules") or {}
    findings: List[dict] = []

    ptas = {}
    types = {}
    for side in ("right", "left"):
        ear = rules.get(side) or {}
        ptas[side] = (ear.get("ac_pta") or {}).get("value")
        types[side] = ear.get("type", "")

    measured = [v for v in ptas.values() if v is not None]
    if not measured:
        return {"available": False, "note": "No pure-tone average available."}

    best = min(measured)
    worst = max(measured)
    asymmetry = round(worst - best, 1)

    # --- type ------------------------------------------------------------
    expected_type = disease.get("expected_type", "any")
    if expected_type != "any":
        for side in ("right", "left"):
            if ptas[side] is None:
                continue
            lowered = types[side].lower()
            conductive = "conductive" in lowered
            mixed = "mixed" in lowered
            if expected_type == "conductive":
                fits = conductive or mixed
            elif expected_type == "mixed":
                fits = mixed
            elif expected_type == "sensorineural":
                fits = "sensorineural" in lowered or (
                    not conductive and not mixed and ptas[side] >= 20)
            else:
                fits = ptas[side] < 20
            findings.append(_finding(
                "agreement" if fits else "conflict",
                f"{side.title()} ear type "
                f"{'matches' if fits else 'does not match'} {top['name']}",
                f"{top['name']} predicts a {expected_type} picture "
                f"({disease['expected_pattern']}); the {side} ear is "
                f"{types[side] or 'untyped'} at {ptas[side]:g} dB HL.",
                action="" if fits else
                       "Re-check masked bone conduction, or revisit the history.",
            ))

    # --- degree (the PTA link) -------------------------------------------
    # Three outcomes, not two. Audiometric thresholds carry a few decibels of
    # test-retest variation, so a value just past the edge of a range is not a
    # contradiction — but it is not "inside the range" either, and saying so
    # would be a false statement about a number printed next to it.
    lo, hi = disease.get("expected_pta", (0, 120))
    grade = _grade(best)
    TOLERANCE_DB = 5
    if best < lo - TOLERANCE_DB:
        findings.append(_finding(
            "conflict",
            f"Thresholds are better than {top['name']} would produce",
            f"The better ear averages {best:g} dB HL ({grade}), while "
            f"{top['name']} typically produces {lo}-{hi} dB HL. Either the "
            "condition is early, or it is not the explanation for this "
            "patient's complaint.",
            action="Consider causes that leave pure tones normal — central "
                   "processing, neural dys-synchrony, or a non-auditory cause.",
        ))
    elif best > hi + TOLERANCE_DB:
        findings.append(_finding(
            "conflict",
            f"Thresholds are worse than {top['name']} would produce",
            f"The better ear averages {best:g} dB HL ({grade}), beyond the "
            f"{lo}-{hi} dB HL this condition usually causes. A second, "
            "additive pathology may be present.",
            action="Look for a coexisting cause rather than attributing all of "
                   "the loss to one diagnosis.",
        ))
    elif lo <= best <= hi:
        findings.append(_finding(
            "agreement",
            f"Degree of loss fits {top['name']}",
            f"Better-ear average {best:g} dB HL ({grade}) sits inside the "
            f"{lo}-{hi} dB HL range this condition typically produces.",
        ))
    else:
        over = best > hi
        findings.append(_finding(
            "agreement",
            f"Degree of loss is borderline for {top['name']}",
            f"Better-ear average {best:g} dB HL ({grade}) is just "
            f"{'above' if over else 'below'} the {lo}-{hi} dB HL range this "
            f"condition typically produces — within test-retest variation, so "
            "not a contradiction, but not a comfortable fit either.",
            weight=0.6,
        ))

    # --- symmetry ---------------------------------------------------------
    laterality = disease.get("laterality", "either")
    if laterality != "either" and len(measured) == 2:
        one_sided = asymmetry >= 15
        if laterality == "unilateral" and not one_sided:
            findings.append(_finding(
                "conflict",
                f"{top['name']} is usually one-sided",
                f"The two ears differ by only {asymmetry:g} dB. A symmetrical "
                "loss argues against this diagnosis.",
                action="Revisit the differential for a bilateral cause.",
            ))
        elif laterality == "bilateral" and one_sided:
            findings.append(_finding(
                "conflict",
                f"{top['name']} is usually symmetrical",
                f"The ears differ by {asymmetry:g} dB. Marked asymmetry needs "
                "its own explanation and is not presbycusis or noise injury.",
                action="Consider retrocochlear pathology; MRI if the asymmetry "
                       "persists on repeat testing.",
            ))
        else:
            findings.append(_finding(
                "agreement",
                f"Symmetry fits {top['name']}",
                f"{'One-sided' if one_sided else 'Symmetrical'} "
                f"({asymmetry:g} dB between ears), as expected for a "
                f"{laterality} condition.",
            ))

    # --- what the patient said versus what was measured -------------------
    present = {s["key"] for s in (assessment.get("reported") or {}).get("symptoms", [])}
    reports_loss = bool(present & {"hearing_loss", "gradual_hearing_loss",
                                   "sudden_hearing_loss", "muffled_hearing",
                                   "fluctuating_hearing_loss"})
    if reports_loss and best < 20 and worst < 20:
        findings.append(_finding(
            "conflict",
            "Hearing loss reported but thresholds are normal",
            f"Both ears average under 20 dB HL, yet the patient reports "
            "difficulty. Pure tones do not measure everything that matters.",
            action="Test speech in noise and consider central auditory "
                   "processing or auditory neuropathy before reassuring.",
            weight=1.3,
        ))
    if not reports_loss and best >= 35:
        findings.append(_finding(
            "conflict",
            "Significant loss not reported by the patient",
            f"The better ear averages {best:g} dB HL, which is a "
            f"{_grade(best)} loss, but hearing difficulty was not among the "
            "reported symptoms.",
            action="Gradual loss is often unnoticed. Counsel on the measured "
                   "result rather than the reported one.",
            weight=1.1,
        ))
    if "speech_in_noise_difficulty" in present and best < 25:
        findings.append(_finding(
            "agreement",
            "Difficulty in noise with near-normal thresholds",
            "This is the presentation the audiogram is least able to explain, "
            "and the reason speech-in-noise testing exists.",
        ))

    return _summarise(findings, extra={
        "available": True,
        "diagnosis": top["name"],
        "diagnosis_rank": index + 1,
        "rank_note": rank_note,
        "expected_type": expected_type,
        "expected_pta": [lo, hi],
        "expected_laterality": laterality,
        "measured": {"better_ear_pta": best, "worse_ear_pta": worst,
                     "asymmetry_db": asymmetry, "grade": grade,
                     "right": ptas["right"], "left": ptas["left"]},
    })


# ==========================================================================
# 3. immittance  <->  diseases
# ==========================================================================
def immittance_vs_diseases(analysis: Optional[dict],
                           assessment: Optional[dict] = None,
                           side: str = "right") -> dict:
    """Which diseases each tympanogram type supports, and which it removes.

    Covers all five Jerger types. The "argues against" half is the one usually
    left out and often the more useful: a Type A tympanogram diagnoses nothing
    on its own, but it takes most of the conductive differential off the table
    in a single measurement.
    """
    if not analysis:
        return {"available": False, "note": "No test battery recorded."}

    immittance = ((analysis.get("immittance") or {}).get(side)) or {}
    tymp = immittance.get("tympanogram")
    if not tymp:
        return {"available": False,
                "note": f"No tympanogram recorded for the {side} ear."}

    jerger = tymp["type"]
    link = TYMPANOGRAM_LINKS.get(jerger)
    if not link:
        return {"available": False, "note": f"No linkage rule for Type {jerger}."}

    supports = [{"key": k, "name": _disease_name(k)} for k in link["supports"]]
    against = [{"key": k, "name": _disease_name(k)} for k in link["argues_against"]]

    # Type B splits in two on ear-canal volume, and the split changes the
    # differential completely — perforation versus fluid behind an intact drum.
    also = list(link["also_consider"])
    if jerger == "B":
        large = tymp.get("ecv_flag") == "large"
        also = [c for c in also
                if ("large canal volume" in c) == large
                or "canal volume" not in c]
        also.insert(0, "Perforation or patent ventilation tube — the probe is "
                       "seeing past the drum" if large
                    else "Middle-ear effusion behind an intact drum")

    findings: List[dict] = []
    ranked = {d["key"]: d for d in (assessment or {}).get("differential", [])
              if d.get("key")}

    for entry in supports:
        if entry["key"] in ranked:
            findings.append(_finding(
                "agreement",
                f"{link['label']} supports {entry['name']}",
                f"{link['meaning']} {entry['name']} is already on the "
                f"differential from the history.",
                weight=1.2,
            ))
    for entry in against:
        if entry["key"] in ranked:
            findings.append(_finding(
                "conflict",
                f"{link['label']} argues against {entry['name']}",
                f"{entry['name']} ranks on the symptom differential, but "
                f"{link['label'].lower()} is not the trace it produces.",
                action=f"Either the trace or the history is misleading — "
                       f"re-check the probe seal before dropping {entry['name']}.",
            ))

    # Reflexes add a second, independent axis.
    reflexes = immittance.get("reflexes") or {}
    oae = (analysis.get("oae") or {}).get(side) or {}
    rules_ear = (analysis.get("rules") or {}).get(side) or {}
    pta = (rules_ear.get("ac_pta") or {}).get("value")
    conductive = "conductive" in (rules_ear.get("type") or "").lower() or \
                 "mixed" in (rules_ear.get("type") or "").lower()

    reflex_notes: List[dict] = []
    if reflexes:
        pattern = reflexes.get("pattern")
        if pattern == "absent" and conductive:
            reflex_notes.append(REFLEX_LINKS["absent_conductive"])
        if pattern == "absent" and oae.get("present_freqs"):
            reflex_notes.append(REFLEX_LINKS["absent_with_emissions"])
        if pattern == "present" and pta is not None and pta > 60:
            reflex_notes.append(REFLEX_LINKS["present_with_severe_loss"])

    return _summarise(findings, extra={
        "available": True,
        "ear": side,
        "type": jerger,
        "label": link["label"],
        "meaning": link["meaning"],
        "interpretation": tymp["interpretation"],
        "supports": supports,
        "argues_against": against,
        "also_consider": also,
        "reflex_findings": [{
            "when": r["when"],
            "meaning": r["meaning"],
            "supports": [_disease_name(k) for k in r["supports"]],
            "also_consider": r["also_consider"],
        } for r in reflex_notes],
        "all_types": [{"type": t, "label": v["label"], "meaning": v["meaning"]}
                      for t, v in TYMPANOGRAM_LINKS.items()],
    })


# ==========================================================================
# assembly
# ==========================================================================
def _summarise(findings: List[dict], extra: Optional[dict] = None) -> dict:
    """Conflicts first, then agreements — never the reverse.

    Sorting agreements to the top would let a page of green ticks bury the one
    line that says two measurements cannot both be true.
    """
    conflicts = [f for f in findings if f["kind"] == "conflict"]
    agreements = [f for f in findings if f["kind"] == "agreement"]
    conflicts.sort(key=lambda f: -f["weight"])
    agreements.sort(key=lambda f: -f["weight"])

    if conflicts:
        verdict = "conflicting"
        headline = (f"{len(conflicts)} finding"
                    f"{'s' if len(conflicts) > 1 else ''} do not agree.")
    elif agreements:
        verdict = "consistent"
        headline = (f"{len(agreements)} independent "
                    f"{'checks' if len(agreements) > 1 else 'check'} agree.")
    else:
        verdict = "insufficient"
        headline = "Not enough overlap between these tests to cross-check."

    return {
        **(extra or {}),
        "conflicts": conflicts,
        "agreements": agreements,
        "verdict": verdict,
        "headline": headline,
    }


def otoscopy_vs_audiogram(otoscopy: Optional[dict], analysis: Optional[dict],
                          side: str) -> dict:
    """What the drum looks like against what the battery measured.

    Delegates to the otoscopy module, which already owns the rule that each
    appearance predicts a particular air-bone gap and tympanogram type. It is
    surfaced here so the dashboard shows it alongside the other links rather
    than only on the page where the image was uploaded.
    """
    if not otoscopy or not analysis:
        return {"available": False,
                "note": "Needs both an otoscope image and an audiogram."}

    # Imported inside the function: the otoscopy package pulls in OpenCV and
    # scikit-learn, and nothing else in this module needs them.
    from app.otoscopy.model import concordance

    result = concordance(otoscopy, analysis, side)
    if not result.get("available"):
        return {"available": False, "note": result.get("note", "")}

    findings = [
        _finding("agreement", a["title"], a["detail"])
        for a in result["agreements"]
    ] + [
        _finding("conflict", c["title"], c["detail"], c.get("action", ""))
        for c in result["conflicts"]
    ]
    return _summarise(findings, extra={"available": True, "ear": side})


def link_case(analysis: Optional[dict] = None,
              assessment: Optional[dict] = None,
              otoscopy: Optional[dict] = None,
              side: str = "right") -> dict:
    """Every available cross-check for one case, plus a single headline."""
    links = {
        "otoscopy_symptoms": otoscopy_vs_symptoms(otoscopy, assessment),
        "otoscopy_audiogram": otoscopy_vs_audiogram(otoscopy, analysis, side),
        "symptoms_audiogram": symptoms_vs_audiogram(assessment, analysis),
        "immittance_diseases": immittance_vs_diseases(analysis, assessment, side),
    }

    # Standalone differentials. Each needs exactly one input, so they are the
    # part of this module that works on a case where nothing else was recorded.
    standalone = {
        "from_otoscopy": otoscopy_vs_diseases(otoscopy),
        "from_audiogram": audiogram_vs_diseases(analysis, side),
    }

    active = [v for v in links.values() if v.get("available")]
    conflicts = [c for v in active for c in v.get("conflicts", [])]
    agreements = [a for v in active for a in v.get("agreements", [])]
    conflicts.sort(key=lambda f: -f["weight"])

    available = [k for k, v in links.items() if v.get("available")]
    missing = _missing_inputs(analysis, assessment, otoscopy)
    agreed = _standalone_agreement(standalone)

    if conflicts:
        headline = conflicts[0]["title"] + "."
    elif agreements:
        headline = (f"{len(agreements)} independent check"
                    f"{'s' if len(agreements) != 1 else ''} across "
                    f"{len(active)} linked modalit"
                    f"{'ies' if len(active) != 1 else 'y'} agree.")
    elif agreed:
        headline = (f"The image and the audiogram independently rank "
                    f"{agreed[0]['name']} first.")
    elif any(v.get("available") for v in standalone.values()):
        source = ("the image" if standalone["from_otoscopy"].get("available")
                  else "the audiogram")
        headline = f"A differential is available from {source} alone."
    else:
        headline = ("Record any one of a history, an image or an audiogram to "
                    "start narrowing the differential.")

    return {
        "links": links,
        "standalone": standalone,
        "standalone_agreement": agreed,
        "links_available": available,
        "missing_inputs": missing,
        "conflict_count": len(conflicts),
        "agreement_count": len(agreements),
        "top_conflicts": conflicts[:4],
        "verdict": ("conflicting" if conflicts else
                    "consistent" if agreements else "insufficient"),
        "headline": headline,
        "note": ("Cross-checks compare what each test predicts about the others. "
                 "A disagreement means one of the two is wrong — it does not say "
                 "which."),
    }


def _standalone_agreement(standalone: Dict[str, dict]) -> List[dict]:
    """Diseases that the image and the audiogram both rank highly, alone.

    Two independent modalities converging without either being told what the
    other found is the strongest signal available on a case with no history —
    and it costs nothing to compute, since both differentials already exist.
    """
    oto = standalone["from_otoscopy"]
    aud = standalone["from_audiogram"]
    if not (oto.get("available") and aud.get("available")):
        return []

    oto_rank = {d["key"]: d for d in oto["differential"][:5]}
    out = []
    for i, entry in enumerate(aud["differential"][:5]):
        if entry["key"] in oto_rank:
            out.append({
                "key": entry["key"],
                "name": entry["name"],
                "audiogram_score": entry["score"],
                "audiogram_rank": i + 1,
                "otoscopy_score": oto_rank[entry["key"]]["score"],
            })
    out.sort(key=lambda d: -(d["audiogram_score"] + d["otoscopy_score"]))
    return out


def _missing_inputs(analysis, assessment, otoscopy) -> List[str]:
    missing = []
    if not assessment:
        missing.append("add a symptom history to link the complaint to the tests")
    if not otoscopy:
        missing.append("add an otoscope image to check the appearance against it")
    if not analysis:
        missing.append("run an audiogram to link thresholds to the history")
    elif not ((analysis.get("immittance") or {}).get("right")
              or (analysis.get("immittance") or {}).get("left")):
        missing.append("add tympanometry to link the middle ear to the diseases")
    return missing
