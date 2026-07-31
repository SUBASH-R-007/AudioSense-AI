"""Core endpoints: health, demo cases, full analysis."""
from __future__ import annotations

from fastapi import APIRouter, Body

from app.clinical import rules
from app.clinical.consistency import battery_review, reconcile_ear
from app.clinical.immittance import analyze_immittance
from app.clinical.oae import analyze_oae
from app.clinical.prescription import prescribe, verify_fitting
from app.clinical.safety import safety_review, sort_alerts
from app.clinical.speech_audiometry import analyze_speech
from app.ml import classifier
from app.models.schemas import EarData, TestRecord, ear_to_numeric
from app.services.demo_cases import DEMO_CASES, PROGRESSION_PAIR
from app.services.phonemes import phoneme_audibility
from app.services.sii import sii_bundle, word_intelligibility

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok", "model_trained": classifier.model_available()}


@router.get("/demo-cases")
def demo_cases():
    return {"cases": DEMO_CASES, "progression_pair": PROGRESSION_PAIR}


@router.post("/analyze")
def analyze(record: TestRecord):
    """Full pipeline: rules engine + ML pattern + phoneme audibility."""
    rules_result = rules.analyze_test(
        record.right.ac, record.right.bc, record.left.ac, record.left.bc
    )

    ml_result, ml_warning = {"right": None, "left": None}, None
    try:
        ml_result = {
            "right": classifier.classify_ear(record.right.ac, record.right.bc),
            "left": classifier.classify_ear(record.left.ac, record.left.bc),
        }
    except FileNotFoundError as exc:
        ml_warning = str(exc)

    phonemes = {
        "right": phoneme_audibility(record.right.ac) if record.right.ac else None,
        "left": phoneme_audibility(record.left.ac) if record.left.ac else None,
    }
    # Combined functional impact follows the better ear (binaural listening).
    r_pta = (rules_result["right"].get("ac_pta") or {}).get("value")
    l_pta = (rules_result["left"].get("ac_pta") or {}).get("value")
    better_ear = None
    if r_pta is not None and l_pta is not None:
        better_ear = "right" if r_pta <= l_pta else "left"
        phonemes["better"] = phonemes[better_ear]
        phonemes["better_ear"] = better_ear

    sii = {
        "right": sii_bundle(record.right.ac) if record.right.ac else None,
        "left": sii_bundle(record.left.ac) if record.left.ac else None,
    }
    prescription = {
        "right": prescribe(record.right.ac) if record.right.ac else None,
        "left": prescribe(record.left.ac) if record.left.ac else None,
    }
    if better_ear:
        sii["better_ear"] = better_ear
        sii["better"] = sii[better_ear]

    speech_ear = better_ear or ("right" if record.right.ac else "left")
    speech_ac = getattr(record, speech_ear).ac

    safety = safety_review(record.right, record.left, record.patient.onset)
    speech = {
        "right": analyze_speech(record.right, r_pta),
        "left": analyze_speech(record.left, l_pta),
    }

    # --- the rest of the test battery, and whether it agrees --------------
    immittance = {
        "right": analyze_immittance(record.right, r_pta),
        "left": analyze_immittance(record.left, l_pta),
    }
    oae = {
        "right": analyze_oae(record.right, ear_to_numeric(record.right.ac)),
        "left": analyze_oae(record.left, ear_to_numeric(record.left.ac)),
    }
    battery = battery_review({
        side: reconcile_ear(
            side, rules_result[side], immittance[side], oae[side], speech[side],
            ear_to_numeric(getattr(record, side).ac),
        )
        for side in ("right", "left")
    })
    for side in ("right", "left"):
        ear_review = battery[side]
        for c in ear_review["contradictions"]:
            safety["alerts"].append({
                "level": "validity",
                "title": c["title"], "ear": side, "detail": c["detail"],
                "action": c.get("action", "Review the full test battery."),
            })
            safety["validity_warning"] = True
        for conf in ear_review["confirmations"]:
            if conf.get("priority"):
                safety["alerts"].append({
                    "level": "urgent",
                    "title": conf["title"], "ear": side, "detail": conf["detail"],
                    "action": "Enforce hearing protection now and re-screen in 6 months "
                              "— this damage is still preventable.",
                })
                safety["has_urgent"] = True

    fitting = {
        "right": verify_fitting(record.right.ac, record.right.aided),
        "left": verify_fitting(record.left.ac, record.left.aided),
    }
    for side in ("right", "left"):
        s = speech[side]
        if not s:
            continue
        if s["srt"] and s["srt"]["non_organic_suspected"]:
            safety["alerts"].append({
                "level": "validity",
                "title": "Possible non-organic (functional) hearing loss",
                "ear": side, "detail": s["srt"]["message"],
                "action": "Repeat pure-tone audiometry with re-instruction; do not "
                          "certify disability on the current thresholds.",
            })
            safety["validity_warning"] = True
        if s["retrocochlear_suspicion"]:
            safety["alerts"].append({
                "level": "urgent",
                "title": "Speech findings suggest retrocochlear pathology",
                "ear": side, "detail": " ".join(s["wrs"]["notes"]),
                "action": "Refer for ENT / neuro-otology assessment with imaging.",
            })
            safety["has_urgent"] = True
    sort_alerts(safety["alerts"])

    return {
        "patient": record.patient.model_dump(),
        "thresholds": {
            "right": {"ac": record.right.ac, "bc": record.right.bc},
            "left": {"ac": record.left.ac, "bc": record.left.bc},
        },
        "rules": rules_result,
        "ml": ml_result,
        "ml_warning": ml_warning,
        "phonemes": phonemes,
        "sii": sii,
        "prescription": prescription,
        "speech_words": word_intelligibility(speech_ac) if speech_ac else None,
        "safety": safety,
        "speech_audiometry": speech,
        "immittance": immittance,
        "oae": oae,
        "battery": battery,
        "fitting": fitting,
    }


@router.post("/prescription")
def prescription_endpoint(ear: EarData = Body(...)):
    """NAL-R gains for arbitrary thresholds — drives the aided simulator."""
    bundle = prescribe(ear.ac)
    bundle["words"] = word_intelligibility(ear.ac)
    return bundle


@router.post("/speech-words")
def speech_words(payload: dict = Body(...)):
    """Word-level audibility for arbitrary text — live conversation captions.

    Uses the same engine as the report, so what a judge sees struck out on
    screen matches what the clinical document says.
    """
    ac = {int(k): v for k, v in (payload.get("ac") or {}).items()}
    text = (payload.get("text") or "").strip()
    if not ac or not text:
        return {"words": [], "counts": {"clear": 0, "degraded": 0, "missed": 0},
                "missed_pct": 0.0, "text": text}
    return word_intelligibility(ac, text)
