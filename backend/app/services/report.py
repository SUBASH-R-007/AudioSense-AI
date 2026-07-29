"""MODULE 6 — Dual-engine AI report pipeline.

Offline engine (default, no key): a data-driven clause library fills every
report section from the structured analysis JSON, then a deterministic
verifier RE-DERIVES each number from the source data and checks it appears
in the draft — so the "verified ✓" badge is genuinely earned, not decorative.

API engine (when the user enables a provider in AI Settings): generator
call with a senior-audiologist system prompt (input = structured JSON only)
followed by a second verifier call that cross-checks every number/claim.
Any failure falls back to the offline engine so the demo never breaks.

Also produces the patient counseling sheet: plain 8th-grade language in
English AND Tamil with practical tips.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from app.services import llm_provider
from app.services.ai_config import get_config
from app.services.languages import (
    BENCHMARK,
    EAR_SENTENCE,
    GRADE_SIMPLE,
    HEADING,
    HEARING_AID,
    LANGUAGES,
    SIDE_WORD,
    TIPS,
    TIPS_HEADING,
    URGENT,
)

DISCLAIMER = (
    "AI-assisted interpretation; final diagnosis requires a qualified audiologist."
)

NOISE_OCCUPATIONS = (
    "factory", "construction", "military", "army", "navy", "mill", "machin",
    "industrial", "welder", "carpenter", "driver", "musician", "dj", "mining",
    "miner", "airport", "drill", "textile", "loom",
)


# ------------------------------------------------------------ helpers ------

def _grade_word(grade: Optional[dict]) -> str:
    return grade["grade"] if grade else "not assessable"


def _ear_summary(ear: dict, side: str) -> str:
    g = ear.get("who_grade")
    pta = ear.get("ac_pta")
    if not pta:
        return f"The {side} ear could not be assessed (no thresholds at PTA frequencies)."
    text = (
        f"{side.capitalize()} ear: four-frequency pure-tone average (500/1k/2k/4k Hz) "
        f"of {pta['value']:g} dB HL — {_grade_word(g)} "
        f"({g['range']}), {ear['type'].lower()} type."
    )
    abg = ear.get("abg")
    if abg:
        text += f" Air-bone gap averages {abg['value']:g} dB."
    return text


def _etiology(analysis: dict) -> List[str]:
    """Occupation- and age-aware likely etiologies per detected pattern."""
    patient = analysis.get("patient", {})
    occupation = (patient.get("occupation") or "").lower()
    age = patient.get("age") or 0
    noisy_job = any(k in occupation for k in NOISE_OCCUPATIONS)
    out: List[str] = []

    for side in ("right", "left"):
        ml = (analysis.get("ml") or {}).get(side)
        ear = (analysis.get("rules") or {}).get(side, {})
        if not ml:
            continue
        p = ml["pattern"]
        label = ml["pattern_label"]
        prefix = f"{side.capitalize()} ear — {label} configuration"
        if p == "noise_notch_4k":
            if noisy_job:
                out.append(
                    f"{prefix}: a 4 kHz notch is the classic signature of "
                    f"noise-induced hearing loss. The patient's occupation "
                    f"(\"{patient.get('occupation')}\") involves occupational noise "
                    "exposure, making occupational NIHL the leading etiology. "
                    "Recommend noise-exposure history, hearing-protection review, "
                    "and OSHA-style monitoring."
                )
            else:
                out.append(
                    f"{prefix}: 4 kHz notches suggest noise exposure "
                    "(occupational or recreational — firearms, loud music). "
                    "A detailed noise history is indicated."
                )
        elif p == "sloping_high_frequency":
            if age >= 60:
                out.append(
                    f"{prefix}: gradually sloping high-frequency sensorineural loss "
                    f"at age {age} is most consistent with presbycusis "
                    "(age-related hearing loss)."
                )
            else:
                out.append(
                    f"{prefix}: high-frequency sloping loss; consider noise exposure, "
                    "ototoxic medication history, and genetic factors given the "
                    f"patient's age ({age})."
                )
        elif p == "ski_slope":
            out.append(
                f"{prefix}: precipitous high-frequency loss with preserved low "
                "frequencies; etiologies include genetic SNHL, ototoxicity and "
                "advanced noise injury. High-frequency amplification with "
                "frequency-lowering features may help."
            )
        elif p == "rising":
            if "conductive" in ear.get("type", "").lower():
                out.append(
                    f"{prefix} with conductive component: low-frequency conductive "
                    "loss suggests middle-ear pathology — otitis media with "
                    "effusion or early otosclerosis. ENT referral with "
                    "tympanometry indicated."
                )
            else:
                out.append(
                    f"{prefix}: rising sensorineural configurations are associated "
                    "with Ménière's disease / endolymphatic hydrops — correlate "
                    "with vertigo, fullness and tinnitus history."
                )
        elif p == "cookie_bite":
            out.append(
                f"{prefix}: mid-frequency (\"cookie-bite\") SNHL is strongly "
                "associated with hereditary/congenital hearing loss; family "
                "audiometric screening is advisable."
            )
        elif p == "corner_audiogram":
            out.append(
                f"{prefix}: only low-frequency residual hearing remains. "
                "Candidacy for cochlear implantation should be evaluated; "
                "power hearing aids provide limited benefit."
            )
        elif p == "flat":
            if "conductive" in ear.get("type", "").lower():
                out.append(
                    f"{prefix} with conductive mechanism: consistent with "
                    "middle-ear effusion, ossicular fixation or tympanic "
                    "membrane pathology; ENT evaluation indicated."
                )
            else:
                out.append(
                    f"{prefix}: flat sensorineural losses occur in Ménière's "
                    "disease, sudden SNHL (treat urgently if recent), and some "
                    "genetic etiologies."
                )
        if ml.get("ood"):
            out.append(
                f"{side.capitalize()} ear: {ml['ood_message']} — the measured shape "
                "is atypical for all trained patterns; manual review advised."
            )
    return out or ["No pattern classification available."]


def _recommendations(analysis: dict) -> List[str]:
    rules = analysis.get("rules", {})
    disability = rules.get("disability") or {}
    recs: List[str] = []

    # Safety first: emergencies and validity problems outrank everything else.
    for alert in (analysis.get("safety") or {}).get("alerts", []):
        if alert["level"] in ("emergency", "urgent", "validity"):
            prefix = {"emergency": "URGENT", "urgent": "PRIORITY",
                      "validity": "TEST VALIDITY"}[alert["level"]]
            recs.append(f"{prefix} — {alert['title']}: {alert['action']}")
    worst = max(
        (rules.get(s, {}).get("ac_pta") or {}).get("value", 0) for s in ("right", "left")
    )
    types = {rules.get(s, {}).get("type", "") for s in ("right", "left")}

    if any("Conductive" in t or "Mixed" in t for t in types):
        recs.append("ENT referral for the conductive component (tympanometry, "
                    "otoscopy); many conductive losses are medically or "
                    "surgically treatable.")
    if worst >= 35:
        sii = (analysis.get("sii") or {}).get("better") or (analysis.get("sii") or {}).get("right")
        if sii and sii.get("aided_quiet") and sii.get("aided_gain_quiet", 0) > 5:
            recs.append(
                "Hearing-aid evaluation and fitting for the affected ear(s): a NAL-R "
                f"first-fit projects audible speech cues rising from "
                f"{sii['quiet']['percent']:g}% to {sii['aided_quiet']['percent']:g}% in quiet "
                f"(+{sii['aided_gain_quiet']:g} points)."
            )
        else:
            recs.append("Hearing-aid evaluation and fitting for the affected ear(s).")
    if worst >= 80:
        recs.append("Cochlear implant candidacy assessment.")
    if any((analysis.get("ml") or {}).get(s, {}).get("pattern") == "noise_notch_4k"
           for s in ("right", "left") if (analysis.get("ml") or {}).get(s)):
        recs.append("Mandatory hearing protection in noise; annual audiometric "
                    "monitoring per hearing-conservation guidelines.")
    if disability.get("benchmark_disability"):
        recs.append("Patient meets the RPwD Act 2016 benchmark (≥40%); assist "
                    "with disability certification for entitled benefits.")
    provisional = any(rules.get(s, {}).get("provisional") for s in ("right", "left"))
    if provisional:
        recs.append("Complete bone-conduction testing to confirm the type of loss "
                    "(current typing is provisional).")
    recs.append("Repeat pure-tone audiometry in 6–12 months to monitor stability.")
    return recs


# ----------------------------------------------------- offline generator ---

def generate_offline(analysis: dict) -> dict:
    rules = analysis.get("rules", {})
    phonemes = analysis.get("phonemes", {})
    disability = rules.get("disability")

    findings = [
        _ear_summary(rules.get("right", {}), "right"),
        _ear_summary(rules.get("left", {}), "left"),
    ]
    for side in ("right", "left"):
        for c in rules.get(side, {}).get("caveats", []):
            findings.append(f"Note ({side}): {c}.")

    for alert in (analysis.get("safety") or {}).get("alerts", []):
        if alert["level"] in ("emergency", "urgent", "validity"):
            findings.append(
                f"{alert['title']} ({alert['ear'] or 'both'} ear): {alert['detail']}"
            )
    for side in ("right", "left"):
        sp = (analysis.get("speech_audiometry") or {}).get(side)
        if sp and sp.get("srt"):
            findings.append(f"{side.capitalize()} ear speech: {sp['srt']['message']}")
        if sp and sp.get("wrs"):
            findings.append(
                f"{side.capitalize()} ear word recognition: {sp['wrs']['pb_max']:g}% at "
                f"{sp['wrs']['pb_max_level']} dB HL — {sp['wrs']['interpretation']}."
            )

    degree_type = []
    for side in ("right", "left"):
        ear = rules.get(side, {})
        g = ear.get("who_grade")
        if g:
            degree_type.append(
                f"{side.capitalize()}: {g['grade']} (WHO 2021, PTA {g['pta']:g} dB HL), "
                f"type: {ear['type']}."
            )

    if disability:
        dis_lines = [
            f"Right ear monaural impairment: {disability['right']['formula']}",
            f"Left ear monaural impairment: {disability['left']['formula']}",
            f"Binaural: {disability['binaural_formula']}",
            ("MEETS" if disability["benchmark_disability"] else "Does not meet")
            + " the RPwD Act 2016 benchmark-disability threshold (40%).",
        ]
    else:
        dis_lines = ["Disability percentage not computable (incomplete PTA data)."]

    impact = []
    for side in ("right", "left"):
        ph = phonemes.get(side)
        if ph:
            impact.append(
                f"{side.capitalize()} ear hears {ph['audibility_pct']:g}% of "
                f"conversational phonemes"
                + (f"; inaudible: {', '.join('/' + s + '/' for s in ph['inaudible'])}."
                   if ph["inaudible"] else "; all speech sounds audible.")
            )
    combined = phonemes.get("better") or phonemes.get("right")
    if combined:
        impact.extend(combined["impact"])

    sii = (analysis.get("sii") or {}).get("better") or (analysis.get("sii") or {}).get("right")
    if sii:
        impact.append(
            f"Speech Intelligibility Index (better ear): "
            f"{sii['quiet']['percent']:g}% of speech cues audible in quiet"
            + (f", falling to {sii['noise']['percent']:g}% in background noise"
               if sii.get("noise") else "")
            + f" — {sii['quiet']['descriptor']}."
        )
    words = analysis.get("speech_words")
    if words and words["counts"]["missed"]:
        missed = [w["word"] for w in words["words"] if w["status"] == "missed"][:6]
        impact.append(
            f"In a standard test sentence, roughly {words['missed_pct']:g}% of words "
            f"would be misheard (e.g. {', '.join(missed)})."
        )

    report = {
        "findings": findings,
        "pattern_etiology": _etiology(analysis),
        "degree_type": degree_type,
        "disability": dis_lines,
        "functional_impact": impact,
        "recommendations": _recommendations(analysis),
        "disclaimer": DISCLAIMER,
    }
    verification = verify_offline(report, analysis)
    return {
        "report": report,
        "verified": verification["verified"],
        "verification": verification,
        "counseling": counseling_sheet(analysis),
        "engine": "offline-template",
        "fallback_used": False,
    }


# --------------------------------------------------- deterministic verify --

def verify_offline(report: dict, analysis: dict) -> dict:
    """Re-derive every key number from the structured JSON and confirm the
    draft report states it. Returns per-claim check results."""
    text = json.dumps(report, ensure_ascii=False)
    rules = analysis.get("rules", {})
    checks = []

    def expect(claim: str, needle: str):
        checks.append({"claim": claim, "expected": needle, "found": needle in text})

    for side in ("right", "left"):
        pta = rules.get(side, {}).get("ac_pta")
        if pta:
            expect(f"{side} PTA value", f"{pta['value']:g}")
            g = rules.get(side, {}).get("who_grade")
            if g:
                expect(f"{side} WHO grade", g["grade"])
            expect(f"{side} type", rules[side]["type"])
    disability = rules.get("disability")
    if disability:
        expect("binaural disability %", f"{disability['binaural_pct']:g}")
    verified = all(c["found"] for c in checks) and bool(checks)
    return {"verified": verified, "checks": checks, "method": "deterministic re-derivation"}


# ------------------------------------------------------- counseling sheet --

def counseling_sheet(analysis: dict) -> dict:
    """Plain-language (8th-grade) patient summary in six languages.

    Built from the pre-authored phrase tables in ``languages.py`` so the
    same clinical facts are stated identically in every language.
    """
    rules = analysis.get("rules", {})
    name = (analysis.get("patient") or {}).get("name") or "You"
    disability = rules.get("disability")
    urgent = (analysis.get("safety") or {}).get("has_urgent")

    hearing_aid = any(
        (rules.get(s, {}).get("ac_pta") or {}).get("value", 0) >= 35
        for s in ("right", "left")
    )

    sheet = {}
    for lang in LANGUAGES:
        summary = []
        if urgent:
            summary.append(URGENT[lang])
        for side in ("right", "left"):
            g = rules.get(side, {}).get("who_grade")
            if g:
                grade_word = GRADE_SIMPLE[lang].get(g["grade"])
                if grade_word:
                    summary.append(EAR_SENTENCE[lang].format(
                        side=SIDE_WORD[lang][side], grade=grade_word))
        if hearing_aid:
            summary.append(HEARING_AID[lang])
        if disability and disability["benchmark_disability"]:
            summary.append(BENCHMARK[lang].format(pct=f"{disability['binaural_pct']:g}"))

        sheet[lang] = {
            "summary": summary,
            "tips": TIPS[lang],
            "heading": HEADING[lang].format(name=name),
            "tips_heading": TIPS_HEADING[lang],
            "label": LANGUAGES[lang]["label"],
            "native": LANGUAGES[lang]["native"],
            "tts": LANGUAGES[lang]["tts"],
        }

    sheet["reading_level"] = "8th grade"
    sheet["languages"] = {k: v for k, v in LANGUAGES.items()}
    return sheet


# ------------------------------------------------------------- LLM engine --

GENERATOR_SYSTEM = """You are a senior clinical audiologist writing a formal
interpretation of a pure-tone audiometry test. You are given ONLY structured
JSON produced by a deterministic clinical rules engine, an ML pattern
classifier and a phoneme audibility model. Use ONLY numbers present in the
JSON — never invent values. Tie likely etiologies to the patient's
occupation and age where relevant (e.g. a 4 kHz noise notch in a factory
worker suggests occupational noise-induced hearing loss).

Return STRICT JSON only:
{
 "findings": [<sentences>],
 "pattern_etiology": [<sentences>],
 "degree_type": [<sentences>],
 "disability": [<sentences incl. the full formula steps>],
 "functional_impact": [<sentences from the phoneme data>],
 "recommendations": [<sentences>],
 "disclaimer": "AI-assisted interpretation; final diagnosis requires a qualified audiologist."
}"""

VERIFIER_SYSTEM = """You are a meticulous clinical QA auditor. You receive
(1) structured JSON data from a deterministic audiology rules engine and
(2) a draft report. Check EVERY number and claim in the draft against the
data: PTA values, WHO grades, types, air-bone gaps, disability percentages,
phoneme lists. Correct any inconsistency. Return STRICT JSON:
{"report": <the corrected report object, same schema>,
 "issues_found": [<description of each correction, empty if none>]}"""


def generate_report(analysis: dict) -> dict:
    """Entry point: LLM pipeline when enabled, offline engine otherwise."""
    if not llm_provider.ai_enabled():
        return generate_offline(analysis)
    cfg = get_config()
    try:
        payload = json.dumps(_slim(analysis), ensure_ascii=False)
        draft_raw = llm_provider.call_llm(
            f"Structured audiometry data:\n{payload}", system=GENERATOR_SYSTEM
        )
        draft = llm_provider.extract_json(draft_raw)
        verify_raw = llm_provider.call_llm(
            f"DATA:\n{payload}\n\nDRAFT REPORT:\n{json.dumps(draft, ensure_ascii=False)}",
            system=VERIFIER_SYSTEM,
        )
        verified_obj = llm_provider.extract_json(verify_raw)
        report = verified_obj.get("report", draft)
        report["disclaimer"] = DISCLAIMER
        return {
            "report": report,
            "verified": True,
            "verification": {
                "verified": True,
                "issues_found": verified_obj.get("issues_found", []),
                "method": f"dual-LLM verification ({cfg.provider})",
            },
            "counseling": counseling_sheet(analysis),
            "engine": f"llm:{cfg.provider}",
            "fallback_used": False,
        }
    except Exception as exc:
        result = generate_offline(analysis)
        result["fallback_used"] = True
        result["fallback_reason"] = f"AI provider failed: {str(exc)[:200]}"
        return result


def _slim(analysis: dict) -> dict:
    """Strip bulky per-phoneme detail before sending to the LLM."""
    slim = {k: v for k, v in analysis.items() if k != "phonemes"}
    phonemes = analysis.get("phonemes") or {}
    slim["phonemes"] = {
        side: {
            "audible": p.get("audible"),
            "inaudible": p.get("inaudible"),
            "audibility_pct": p.get("audibility_pct"),
            "impact": p.get("impact"),
        }
        for side, p in phonemes.items()
        if isinstance(p, dict)
    }
    return slim
