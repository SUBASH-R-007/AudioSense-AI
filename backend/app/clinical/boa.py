"""Behavioural Observation Audiometry — what an infant does when sound happens.

BOA is the entry point of paediatric audiometry and the most misread test in
it. An infant under about six months cannot be conditioned, so there is no
raise-your-hand response to shape. Instead the tester presents sound and
watches for unconditioned, reflexive behaviour: an eye blink, a startle, a
change in sucking, a pause in activity.

THE CENTRAL POINT, AND THE ONE MOST OFTEN LOST: **BOA DOES NOT MEASURE
THRESHOLDS.** It measures the level at which a behaviour becomes visible to an
observer, which is far above the level at which the infant can hear. Those are
minimum response levels, and a normal-hearing newborn's MRL to a warble tone is
around 78 dB SPL — some 75 dB above their actual threshold. Recording an MRL as
a threshold produces an audiogram showing a hearing loss in a normal ear.

Three further limits, all of which the module states rather than assumes away:

  HABITUATION. Reflexive responses fade on repetition. The second and third
  presentations at the same level are less likely to produce a response than
  the first, so an apparently rising threshold across a session is usually the
  infant losing interest.

  OBSERVER BIAS. The tester decides whether a movement was a response. Without
  a second observer blind to when the stimulus occurred, agreement is poor.

  IT IS A SCREEN, NOT AN ASSESSMENT. Ear-specific and frequency-specific
  information is not obtainable this way. A BOA result that raises concern is
  followed by ABR or ASSR, not by more BOA.

From about six months, visual reinforcement audiometry conditions a head-turn
and gives genuine thresholds — so BOA has an upper age limit as well as a
lower one, and continuing past it wastes the better test.

Normative minimum response levels after Northern & Downs, *Hearing in
Children*; response repertoire after the same source and standard paediatric
audiology practice.
"""
from __future__ import annotations

from typing import Dict, List, Optional

#: Age above which visual reinforcement audiometry replaces BOA, months.
VRA_FROM_MONTHS = 6

#: Minimum response levels by age. ``warble`` and ``speech`` are dB SPL, the
#: unit these norms are published in. ``startle`` is the level at which a Moro
#: or startle reflex is expected.
#:
#: The trend is the finding: the level falls steeply over the first two years
#: as the infant's *behaviour* matures, not their hearing. A 9-month-old
#: responding at 45 dB and a 3-month-old responding at 70 dB may have
#: identical thresholds.
BOA_NORMS: List[dict] = [
    {"band": "0-6 weeks", "low_months": 0, "high_months": 1.5,
     "warble_db_spl": 78, "speech_db_spl": 40, "startle_db_spl": 65,
     "expected": ["Eye blink (auropalpebral reflex)", "Moro / startle",
                  "Arousal from sleep", "Cessation of activity"],
     "note": "Responses are reflexive and fatigue quickly."},
    {"band": "6 weeks - 4 months", "low_months": 1.5, "high_months": 4,
     "warble_db_spl": 70, "speech_db_spl": 47, "startle_db_spl": 65,
     "expected": ["Eye widening", "Eye shift toward sound", "Cessation of activity",
                  "Rudimentary head turn"],
     "note": "Eye widening and shifting replace the pure startle."},
    {"band": "4-7 months", "low_months": 4, "high_months": 7,
     "warble_db_spl": 51, "speech_db_spl": 21, "startle_db_spl": 65,
     "expected": ["Head turns laterally toward the sound",
                  "Listening attitude", "Eye shift"],
     "note": "A true lateral head turn appears — the point at which VRA becomes "
             "possible and preferable."},
    {"band": "7-9 months", "low_months": 7, "high_months": 9,
     "warble_db_spl": 45, "speech_db_spl": 15, "startle_db_spl": 65,
     "expected": ["Head turns laterally and below", "Direct localisation"],
     "note": "Localisation extends downward."},
    {"band": "9-13 months", "low_months": 9, "high_months": 13,
     "warble_db_spl": 38, "speech_db_spl": 8, "startle_db_spl": 65,
     "expected": ["Direct localisation to the side and below",
                  "Indirect localisation above"],
     "note": "Localisation becomes reliable."},
    {"band": "13-16 months", "low_months": 13, "high_months": 16,
     "warble_db_spl": 32, "speech_db_spl": 5, "startle_db_spl": 65,
     "expected": ["Direct localisation in all planes"],
     "note": "Adult-like localisation behaviour."},
    {"band": "16-21 months", "low_months": 16, "high_months": 21,
     "warble_db_spl": 25, "speech_db_spl": 5, "startle_db_spl": 65,
     "expected": ["Direct localisation in all planes"],
     "note": "Response levels approach adult thresholds."},
    {"band": "21-24 months", "low_months": 21, "high_months": 24,
     "warble_db_spl": 26, "speech_db_spl": 3, "startle_db_spl": 65,
     "expected": ["Direct localisation in all planes"],
     "note": "Play audiometry becomes the better test from about this age."},
]

#: The unconditioned behaviours a tester may record.
BOA_RESPONSES: Dict[str, str] = {
    "eye_blink": "Eye blink (auropalpebral reflex)",
    "startle": "Moro / startle",
    "arousal": "Arousal from sleep",
    "cessation": "Cessation of activity",
    "eye_widening": "Eye widening",
    "eye_shift": "Eye shift toward the sound",
    "head_turn": "Head turn toward the sound",
    "localisation": "Direct localisation",
    "sucking_change": "Change in sucking rate",
    "facial_grimace": "Facial grimace",
    "limb_movement": "Limb movement",
}

#: An infant this many dB above the age-typical MRL warrants objective testing.
CONCERN_MARGIN_DB = 20

CITATIONS = [
    "Northern, J. L., & Downs, M. P. Hearing in Children — minimum response levels",
    "JCIH (2019) — objective testing follows a failed behavioural screen",
]


def age_band(age_months: float) -> Optional[dict]:
    for band in BOA_NORMS:
        if band["low_months"] <= age_months < band["high_months"]:
            return band
    return BOA_NORMS[-1] if age_months >= 24 else None


def analyze_boa(age_months: float,
                observed_level_db_spl: Optional[float] = None,
                responses: Optional[List[str]] = None,
                observers: int = 1,
                presentations: Optional[int] = None,
                ear: str = "sound field") -> dict:
    """One BOA observation against the age-appropriate response level.

    Everything here is reported as a *minimum response level*. Nothing in this
    module returns a threshold, because BOA cannot produce one.
    """
    responses = responses or []
    band = age_band(age_months)
    findings: List[str] = []
    flags: List[str] = []

    if band is None:
        return {"available": False,
                "note": "Age outside the range these norms cover."}

    expected_mrl = band["warble_db_spl"]
    difference = None
    concern = False
    if observed_level_db_spl is not None:
        difference = round(observed_level_db_spl - expected_mrl, 1)
        concern = difference >= CONCERN_MARGIN_DB
        if concern:
            flags.append("mrl_above_age_expectation")
            findings.append(
                f"Responses first seen at {observed_level_db_spl:g} dB SPL against "
                f"an age-typical {expected_mrl:g} dB SPL for {band['band']} — "
                f"{difference:g} dB higher. Refer for objective testing (ABR or "
                "ASSR); do not repeat BOA to confirm it.")
        else:
            findings.append(
                f"Responses at {observed_level_db_spl:g} dB SPL are consistent "
                f"with the {expected_mrl:g} dB SPL typical for {band['band']}.")

    # Whether the behaviours recorded are ones this age actually produces.
    labels = [BOA_RESPONSES.get(r, r) for r in responses]
    age_appropriate = None
    if responses:
        localising = {"head_turn", "localisation"}
        reflexive = {"eye_blink", "startle", "arousal"}
        if age_months < 4 and (localising & set(responses)):
            flags.append("response_beyond_age")
            findings.append(
                "A head turn or localisation was recorded below four months, "
                "which is earlier than that behaviour normally appears. Confirm "
                "it was time-locked to the stimulus rather than spontaneous.")
            age_appropriate = False
        elif age_months >= 7 and set(responses) <= reflexive:
            flags.append("only_reflexive_responses")
            findings.append(
                "Only reflexive responses were seen at an age when localisation "
                "is expected. That may reflect hearing, development, or the "
                "child's state — it is a reason to test objectively, not to "
                "conclude.")
            age_appropriate = False
        else:
            age_appropriate = True

    if observers < 2:
        flags.append("single_observer")
        findings.append(
            "A single observer decided whether each movement was a response. "
            "Without a second observer blind to stimulus timing, agreement is "
            "poor and false positives are common.")

    if presentations is not None and presentations > 3:
        flags.append("habituation_risk")
        findings.append(
            f"{presentations} presentations were made at this level. Reflexive "
            "responses habituate, so later presentations under-respond — an "
            "apparently rising level across a session is usually fatigue rather "
            "than hearing.")

    if age_months >= VRA_FROM_MONTHS:
        flags.append("vra_indicated")
        findings.append(
            f"At {age_months:g} months, visual reinforcement audiometry can "
            "condition a head-turn and yields genuine ear- and "
            "frequency-specific thresholds. Continuing with BOA past six months "
            "gives up the better test.")

    return {
        "available": True,
        "ear": ear,
        "age_months": age_months,
        "band": band["band"],
        "expected_mrl_db_spl": expected_mrl,
        "expected_speech_db_spl": band["speech_db_spl"],
        "observed_level_db_spl": observed_level_db_spl,
        "difference_db": difference,
        "concern": concern,
        "expected_behaviours": band["expected"],
        "observed_behaviours": labels,
        "age_appropriate_responses": age_appropriate,
        "observers": observers,
        "presentations": presentations,
        "flags": flags,
        "findings": findings,
        "is_threshold": False,
        "headline": (
            "Minimum response levels are above the age expectation — refer for "
            "objective testing." if concern else
            "Minimum response levels are consistent with the age band."
            if observed_level_db_spl is not None else
            "No response level recorded yet."),
        "caveat": (
            "These are MINIMUM RESPONSE LEVELS, not thresholds. A normal-hearing "
            "newborn responds to a warble tone near 78 dB SPL — roughly 75 dB "
            "above the level they can actually hear. Plotting these values on an "
            "audiogram would show a hearing loss in a normal ear."),
        "citations": list(CITATIONS),
    }


def boa_reference() -> dict:
    """The norms and the response repertoire, for the intake form."""
    return {
        "bands": BOA_NORMS,
        "responses": [{"key": k, "label": v} for k, v in BOA_RESPONSES.items()],
        "vra_from_months": VRA_FROM_MONTHS,
        "concern_margin_db": CONCERN_MARGIN_DB,
        "limits": [
            "BOA yields minimum response levels, never thresholds.",
            "Reflexive responses habituate on repetition.",
            "A single observer cannot reliably judge whether a movement was a "
            "response — two observers, one blind to stimulus timing.",
            "It is not ear-specific and not frequency-specific.",
            "A concerning result is followed by ABR or ASSR, not by more BOA.",
        ],
        "citations": list(CITATIONS),
    }
