"""The one-sentence answer.

Everything else this system produces is evidence. This module produces the
conclusion — what is wrong with this patient, and what should happen next —
so that it can sit above the evidence rather than have to be assembled from
a dozen cards.

Three parts, in the order a clinician actually wants them:
  HEADLINE   the diagnosis in one plain sentence
  NUMBERS    the three figures that carry the decision
  ACTION     the single most important next step
"""
from __future__ import annotations

from typing import List, Optional

from app.clinical.safety import NORMAL_LIMIT_DB
from app.models.schemas import ear_to_numeric

SEVERITY_ORDER = [
    "Complete or total hearing loss",
    "Profound hearing loss", "Severe hearing loss", "Moderately severe hearing loss",
    "Moderate hearing loss", "Mild hearing loss", "Normal hearing",
]

#: WHO World Report on Hearing (2021), grades table: "unilateral" hearing
#: loss is a better ear below 20 dB HL with the worse ear at 35 dB HL or
#: more (four-frequency averages). A worse ear between 20 and 35 dB HL beside
#: a normal ear is a one-sided loss, but not WHO "unilateral hearing loss".
WHO_UNILATERAL_BETTER_BELOW = 20
WHO_UNILATERAL_WORSE_FROM = 35

#: A configuration is stated in the headline only when the classifier is at
#: least this confident and no reliability flag says otherwise; below it the
#: shape stays in the evidence cards, where its confidence is shown.
PATTERN_HEADLINE_CONFIDENCE = 0.8


def _worse_grade(rules: dict) -> Optional[str]:
    # `or {}` rather than a `{}` default: an ear with no PTA-frequency
    # thresholds is emitted as an explicit "who_grade": None (rules.py:262),
    # not as a missing key, so the default never fires and a single-ear test
    # would crash here on None.get.
    grades = [
        ((rules.get(side) or {}).get("who_grade") or {}).get("grade")
        for side in ("right", "left")
    ]
    grades = [g for g in grades if g]
    if not grades:
        return None
    return min(grades, key=lambda g: SEVERITY_ORDER.index(g)
               if g in SEVERITY_ORDER else 99)


# ------------------------------------------------------------- headline


def _freq_text(freqs: List[int]) -> str:
    """[4000] -> '4000 Hz'; [2000, 4000, 8000] -> '2000, 4000 and 8000 Hz'."""
    names = [f"{f:g}" for f in freqs]
    if len(names) == 1:
        return f"{names[0]} Hz"
    return f"{', '.join(names[:-1])} and {names[-1]} Hz"


def _raised_freqs(analysis: dict, side: str) -> List[int]:
    """Tested air-conduction frequencies outside normal limits.

    The WHO grade averages 500–4000 Hz, so an ear can grade "normal" with a
    loss at one frequency — a 4 kHz notch, or 8 kHz, which the average never
    sees. Each threshold is held to the same per-frequency limit the safety
    layer uses (safety.NORMAL_LIMIT_DB; BSA 2018 "mild" starts at 21 dB HL).
    """
    ac = (((analysis.get("thresholds") or {}).get(side) or {}).get("ac") or {})
    numeric = ear_to_numeric({int(f): v for f, v in ac.items()})
    return sorted(f for f, v in numeric.items()
                  if v is not None and v > NORMAL_LIMIT_DB)


def _provisional_reason(ear: dict) -> str:
    """Why the rules engine left this ear's type provisional, in its terms."""
    bc_nr = ear.get("bc_nr_freqs") or []
    if ear.get("abg") is None:
        if bc_nr:
            # Tested, but no response within the vibrator's output: the
            # air-bone gap is indeterminate, which is not the same as never
            # measured.
            return "no bone-conduction response within the vibrator's limit"
        return "bone conduction not measured"
    parts = []
    if (ear.get("bc_pta") or {}).get("missing_freqs"):
        parts.append("bone conduction incomplete")
    if bc_nr:
        parts.append("no bone-conduction response within the vibrator's limit "
                     f"at {_freq_text(bc_nr)}")
    # Bone conduction complete and answered everywhere: the gap is short of
    # frequencies because air conduction is.
    return ", ".join(parts) or "air-bone gap incomplete"


def _ear_summary(rules: dict, side: str, analysis: Optional[dict] = None) -> dict:
    """What the headline needs to know about one ear."""
    ear = rules.get(side) or {}
    grade = (ear.get("who_grade") or {}).get("grade")
    raw_type = ear.get("type") or ""
    type_word = raw_type.replace("(provisional)", "").strip().lower()
    if type_word in ("", "normal", "indeterminate"):
        # Neither names a kind of loss; the grade carries the sentence, and
        # "normal hearing loss" would say nothing.
        type_word = None
    provisional = bool(ear.get("provisional")) or "(provisional)" in raw_type
    # rules.hearing_type types an ear within normal limits Normal even with an
    # air-bone gap over 10 dB, and reports the gap as a finding of its own
    # (air_bone_gap_note): the headline must not read as plain normal hearing.
    gap = None
    if raw_type.strip() == "Normal" and ear.get("significant_air_bone_gap"):
        gap = (ear.get("abg") or {}).get("value")
        gap = gap if isinstance(gap, (int, float)) else True
    return {
        "side": side,
        "grade": grade,
        "pta": (ear.get("ac_pta") or {}).get("value"),
        "type": type_word,
        "provisional": provisional and type_word is not None,
        "provisional_reason": _provisional_reason(ear),
        # Only an ear graded normal needs its individual thresholds named.
        "raised": (_raised_freqs(analysis or {}, side)
                   if grade == "Normal hearing" else []),
        "gap": gap,
    }


def _gap_words(e: dict) -> str:
    """'an air-bone gap of 20 dB in the right ear' for a Normal ear with one."""
    size = f" of {e['gap']:g} dB" if isinstance(e["gap"], (int, float)) \
        and not isinstance(e["gap"], bool) else ""
    return f"an air-bone gap{size} in the {e['side']} ear"


def _gap_sentence(ears: List[dict]) -> str:
    """' There is an air-bone gap of … — check the middle ear …' or ''."""
    gaps = [e for e in ears if e.get("gap")]
    if not gaps:
        return ""
    where = " and ".join(_gap_words(e) for e in gaps)
    return (f" There is {where} behind normal hearing — a conductive finding to "
            "check with tympanometry and otoscopy, after re-checking bone-vibrator "
            "placement and masking.")


def _degree(grade: str) -> str:
    """'Moderately severe hearing loss' -> 'moderately severe'."""
    return grade.lower().replace(" hearing loss", "").strip()


def _loss(e: dict) -> str:
    """'moderate sensorineural hearing loss' for one ear."""
    words = [_degree(e["grade"])] + ([e["type"]] if e["type"] else [])
    return " ".join(words) + " hearing loss"


def _ear_words(e: dict) -> str:
    """'moderate conductive' for one ear inside a two-ear sentence."""
    return " ".join([_degree(e["grade"])] + ([e["type"]] if e["type"] else []))


def _provisional_text(ears: List[dict]) -> str:
    """'type provisional — <why>' wherever the headline names a type, or ''."""
    prov = [e for e in ears if e["provisional"]]
    if not prov:
        return ""
    typed = [e for e in ears if e["type"]]
    if len(prov) == len(typed) and len({e["provisional_reason"] for e in prov}) == 1:
        return f"type provisional — {prov[0]['provisional_reason']}"
    return "type provisional — " + "; ".join(
        f"{e['provisional_reason']} in the {e['side']} ear" for e in prov)


def _provisional_note(ears: List[dict]) -> str:
    """Say the type is provisional wherever the headline names one."""
    text = _provisional_text(ears)
    return f" ({text})" if text else ""


def _normal_but_raised(e: dict) -> str:
    """', but outside normal limits at 8000 Hz' for an ear graded normal."""
    if not e["raised"]:
        return ""
    return f", but outside normal limits at {_freq_text(e['raised'])}"


def _reliable_pattern(ml: dict, side: str) -> Optional[str]:
    """The ear's configuration label, or None when it should not headline.

    The classifier is trained only on configurations of hearing loss, so a
    "normal" (or absent) pattern names no configuration, and a label the
    classifier itself is unsure of is evidence, not a conclusion. An explicit
    ``reliable`` flag from the classifier decides; without one, calibrated
    confidence must reach PATTERN_HEADLINE_CONFIDENCE with no
    out-of-distribution flag.
    """
    m = ml.get(side) or {}
    pattern = m.get("pattern")
    if not pattern or pattern == "normal":
        return None
    reliable = m.get("reliable")
    if reliable is None:
        confidence = m.get("confidence")
        reliable = (confidence is not None
                    and confidence >= PATTERN_HEADLINE_CONFIDENCE
                    and not m.get("ood"))
    if not reliable:
        return None
    label = m.get("pattern_label") or pattern
    # Decapitalize the first letter only — lowercasing the whole label would
    # turn "4 kHz" into "4 khz".
    return label[0].lower() + label[1:]


def _configuration(ml: dict, ears: List[dict]) -> str:
    """', flat configuration' for the ears with a loss, worse ear first."""
    labels = {e["side"]: _reliable_pattern(ml, e["side"]) for e in ears}
    present = [(side, label) for side, label in labels.items() if label]
    if not present:
        return ""
    if len(ears) == 1 or (len(present) == 2 and present[0][1] == present[1][1]):
        return f", {present[0][1]} configuration"
    return ", " + " and ".join(f"{label} configuration in the {side} ear"
                               for side, label in present)


def _ungraded(analysis: dict, side: str) -> str:
    """Why the other ear has no grade — never call this 'unilateral'."""
    ac = (((analysis.get("thresholds") or {}).get(side) or {}).get("ac") or {})
    if any(v is not None for v in ac.values()):
        return f"the {side} ear was not tested at 500–4000 Hz"
    return f"the {side} ear was not tested"


def _describe_hearing(analysis: dict, rules: dict, ml: dict):
    """(headline, tone) from the grades and types of both ears."""
    ears = {s: _ear_summary(rules, s, analysis) for s in ("right", "left")}
    graded = [ears[s] for s in ("right", "left") if ears[s]["grade"]]
    if not graded:
        return "Insufficient data to reach a conclusion.", "unknown"

    if len(graded) == 1:
        # One ear graded: a single-ear test cannot show a unilateral loss,
        # only a finding in the ear that was tested.
        e = graded[0]
        other = "left" if e["side"] == "right" else "right"
        missing = _ungraded(analysis, other)
        if e["grade"] == "Normal hearing":
            if e["raised"]:
                return (f"Hearing in the {e['side']} ear is within normal limits "
                        f"on the four-frequency average{_normal_but_raised(e)}; "
                        f"{missing}.{_gap_sentence([e])}"), "loss"
            if e["gap"]:
                return (f"Hearing in the {e['side']} ear is within normal limits; "
                        f"{missing}.{_gap_sentence([e])}"), "loss"
            return (f"Hearing in the {e['side']} ear is within normal limits; "
                    f"{missing}."), "normal"
        text = (f"{_loss(e)}{_provisional_note([e])} in the {e['side']} ear"
                f"{_configuration(ml, [e])}; {missing}.")
        return text[0].upper() + text[1:], "loss"

    right, left = ears["right"], ears["left"]
    if right["grade"] == left["grade"] == "Normal hearing":
        raised = [e for e in (right, left) if e["raised"]]
        gap_text = _gap_sentence([right, left])
        if not raised:
            if gap_text:
                return ("Hearing is within normal limits in both ears." + gap_text,
                        "loss")
            return "Hearing is within normal limits in both ears.", "normal"
        # A normal average must not read as normal hearing when a threshold
        # the average does not see is outside normal limits — the referral
        # below the headline may be about exactly that frequency.
        if len(raised) == 2 and right["raised"] == left["raised"]:
            where = f"at {_freq_text(right['raised'])} in both ears"
        else:
            where = " and ".join(f"at {_freq_text(e['raised'])} in the "
                                 f"{e['side']} ear" for e in raised)
        return ("The four-frequency average is within normal limits in both "
                f"ears, but hearing is outside normal limits {where}."
                + gap_text), "loss"

    worse, better = ((left, right) if (left["pta"] or 0) > (right["pta"] or 0)
                     else (right, left))
    if better["grade"] == "Normal hearing":
        better_text = (f"the {better['side']} ear is within normal limits"
                       + (f" on the four-frequency average{_normal_but_raised(better)}"
                          if better["raised"] else "")
                       + (f", with {_gap_words(better)}" if better["gap"] else ""))
        if (better["pta"] is not None and worse["pta"] is not None
                and better["pta"] < WHO_UNILATERAL_BETTER_BELOW
                and worse["pta"] >= WHO_UNILATERAL_WORSE_FROM):
            prov = _provisional_text([worse])
            text = (f"Unilateral {_loss(worse)} ({worse['side']} ear"
                    f"{'; ' + prov if prov else ''}){_configuration(ml, [worse])}"
                    + (f"; {better_text}" if better["raised"] or better["gap"]
                       else "") + ".")
        else:
            text = (f"{_loss(worse)}{_provisional_note([worse])} in the "
                    f"{worse['side']} ear{_configuration(ml, [worse])}; "
                    f"{better_text}.")
        return text[0].upper() + text[1:], "loss"

    # Loss in both ears.
    pair = [worse, better]
    note = _provisional_note(pair)
    config = _configuration(ml, pair)
    if worse["grade"] == better["grade"]:
        if worse["type"] == better["type"]:
            text = f"Bilateral {_loss(worse)}{note}{config}."
        else:
            text = (f"Bilateral {_degree(worse['grade'])} hearing loss: "
                    f"{worse['type'] or 'type undetermined'} in the {worse['side']} "
                    f"ear, {better['type'] or 'type undetermined'} in the "
                    f"{better['side']} ear{note}{config}.")
    elif worse["type"] == better["type"] and worse["type"]:
        text = (f"Asymmetric {worse['type']} hearing loss: "
                f"{_degree(worse['grade'])} in the {worse['side']} ear, "
                f"{_degree(better['grade'])} in the {better['side']} ear"
                f"{note}{config}.")
    else:
        text = (f"Asymmetric hearing loss: {_ear_words(worse)} in the "
                f"{worse['side']} ear, {_ear_words(better)} in the "
                f"{better['side']} ear{note}{config}.")
    return text, "loss"


def build_verdict(analysis: dict) -> dict:
    """Assemble the leading conclusion from the full analysis."""
    rules = analysis.get("rules") or {}
    ml = analysis.get("ml") or {}
    safety = analysis.get("safety") or {}
    triage = analysis.get("triage") or {}
    battery = analysis.get("battery") or {}
    sii = (analysis.get("sii") or {}).get("better") or (analysis.get("sii") or {}).get("right")

    grade = _worse_grade(rules)

    # ---------------- headline ------------------------------------------
    if safety.get("has_emergency"):
        emergency = next(a for a in safety["alerts"] if a["level"] == "emergency")
        headline = f"{emergency['title']} — treat as an emergency."
        tone = "emergency"
    elif "preclinical_nihl" in (battery.get("patterns") or []):
        # The pattern is per frequency (an absent emission where that
        # threshold is still normal); "thresholds are still normal" is true of
        # the patient only when no ear grades a loss (WHO 2021: PTA < 20).
        if grade in (None, "Normal hearing"):
            headline = ("Hearing thresholds are still normal, but the cochlea is "
                        "already being damaged — this loss is still preventable.")
        else:
            described, _tone = _describe_hearing(analysis, rules, ml)
            headline = (described + " Emissions are also absent where thresholds "
                        "are still normal — cochlear damage is ahead of the "
                        "audiogram there.")
        tone = "warning"
    else:
        headline, tone = _describe_hearing(analysis, rules, ml)

    # ---------------- the numbers that carry the decision ---------------
    numbers: List[dict] = []
    for side in ("right", "left"):
        pta = ((rules.get(side) or {}).get("ac_pta") or {}).get("value")
        if pta is not None:
            numbers.append({
                "label": f"{side.capitalize()} ear PTA",
                "value": f"{pta:g}",
                "unit": "dB HL",
                "hint": ((rules.get(side) or {}).get("who_grade") or {}).get("grade"),
            })
    disability = rules.get("disability")
    if disability and disability.get("binaural_pct") is not None:
        benchmark = bool(disability.get("benchmark_disability"))
        # A figure the rules engine marks not certifiable (a missing key is
        # read as certifiable) must not read like a certificate value.
        certifiable = disability.get("certifiable", True) is not False
        if certifiable:
            hint = ("meets the 40% benchmark" if benchmark
                    else "below the 40% benchmark")
        else:
            hint = ("provisional, not certifiable from this test — "
                    + ("would meet the 40% benchmark" if benchmark
                       else "below the 40% benchmark"))
        numbers.append({
            "label": ("Disability (RPwD 2016)" if certifiable
                      else "Disability (RPwD 2016, provisional)"),
            "value": f"{disability['binaural_pct']:g}",
            "unit": "%",
            "hint": hint,
            "emphasis": benchmark and certifiable,
            "certifiable": certifiable,
            "note": None if certifiable else disability.get("certification_note"),
        })
    # The ISO 7029 "hearing age" comparison is not part of the verdict: the
    # age-comparison feature was withdrawn from the Results page at NIEPMD's
    # request. analysis["norms"] is still computed for other consumers.
    if sii:
        numbers.append({
            "label": "Speech cues audible",
            "value": f"{sii['quiet']['percent']:g}",
            "unit": "%",
            "hint": f"{sii['noise']['percent']:g}% in noise" if sii.get("noise") else None,
        })

    # ---------------- the single next action ----------------------------
    # Only genuine alerts displace the clinical next step. An informational
    # prompt such as "onset not recorded" is worth showing, but it is not
    # what the clinician should do about this patient's hearing.
    actionable = [a for a in safety.get("alerts", [])
                  if a["level"] in ("emergency", "urgent", "validity")]
    if actionable:
        top = actionable[0]
        action = top.get("action") or top["title"]
        action_level = top["level"]
    elif grade and grade != "Normal hearing":
        worst_pta = max(
            (((rules.get(s) or {}).get("ac_pta") or {}).get("value") or 0)
            for s in ("right", "left")
        )
        # A conductive component is a medical question before it is an
        # amplification one: the BAA Onward Referral Guidance (2023) sends
        # conductive hearing loss to ENT, and middle-ear disease is often
        # treatable. Only a type the rules engine determined routes here.
        # An air-bone gap behind normal hearing in the other ear is a
        # conductive component too (rules.hearing_type reports it apart from
        # the type).
        conductive = [s for s in ("right", "left")
                      if (rules.get(s) or {}).get("type") in ("Conductive", "Mixed")
                      or ((rules.get(s) or {}).get("type") == "Normal"
                          and (rules.get(s) or {}).get("significant_air_bone_gap"))]
        ent = ""
        if conductive:
            where = (f"the {conductive[0]} ear" if len(conductive) == 1
                     else "both ears")
            ent = (f"Refer for ENT / otology assessment of the conductive "
                   f"component in {where} (otoscopy, tympanometry) — it is often "
                   "medically or surgically treatable")
        if worst_pta >= 80:
            action = ("Refer for cochlear implant candidacy assessment."
                      if not ent else f"{ent}; cochlear implant candidacy "
                      "assessment for the loss that remains.")
        elif ent:
            action = (f"{ent}; hearing-aid evaluation if the loss persists."
                      if worst_pta >= 35 else f"{ent}.")
        elif worst_pta >= 35:
            action = "Refer for hearing-aid evaluation and fitting."
        else:
            action = ("Counsel on hearing protection and repeat audiometry in "
                      "6–12 months.")
        action_level = "routine"
    elif "preclinical_nihl" in (battery.get("patterns") or []):
        action = ("Enforce hearing protection now and re-screen in 6 months — the "
                  "damage is not yet in the audiogram.")
        action_level = "urgent"
    elif any(_ear_summary(rules, s)["gap"] for s in ("right", "left")):
        # Normal hearing with a significant air-bone gap: a middle-ear cause
        # or a test artefact, and either needs checking before "no action".
        gap_sides = [s for s in ("right", "left") if _ear_summary(rules, s)["gap"]]
        where = (f"the {gap_sides[0]} ear" if len(gap_sides) == 1 else "both ears")
        action = (f"Check the air-bone gap in {where}: re-test bone conduction with "
                  "the vibrator re-seated and masking, then tympanometry and "
                  "otoscopy for a middle-ear cause.")
        action_level = "routine"
    elif any(_raised_freqs(analysis, s) for s in ("right", "left")):
        # Graded normal on the average, with a threshold outside normal
        # limits: not "no action".
        action = ("Repeat audiometry in 6–12 months to follow the frequencies "
                  "outside normal limits, and counsel on hearing protection.")
        action_level = "routine"
    else:
        action = "No action required beyond routine re-screening."
        action_level = "routine"

    return {
        "headline": headline,
        "tone": tone,
        "numbers": numbers[:4],
        "action": action,
        "action_level": action_level,
        "review_required": triage.get("review_required", True),
        "confidence_note": (
            "Interpretation is unambiguous and confident."
            if triage.get("auto_releasable")
            else "Flagged for audiologist review — see the reasons below."
        ),
        "disclaimer": ("AI-assisted interpretation; final diagnosis requires a "
                       "qualified audiologist."),
    }
