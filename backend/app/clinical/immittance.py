"""Acoustic reflexes, and the battery-level view of the middle ear.

Pure-tone audiometry says *how much* hearing is lost. Immittance says *where
the problem is*, independently of the patient's voluntary response, which is
why it is the standard cross-check on a conductive finding.

Tympanogram typing itself lives in ``tympanometry.py``, which implements the
full eight-type classification from the clinical reference. This module keeps
the reflex analysis and the per-ear bundle used by the analysis pipeline.

Acoustic reflex thresholds normally appear 70-100 dB above the pure-tone
threshold. Their presence or absence, ipsilateral versus contralateral,
localises the lesion along the reflex arc.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.clinical.tympanometry import _untyped_reason, classify

#: Acoustic reflex thresholds are normally 70-100 dB SL above threshold.
REFLEX_SL_NORMAL = (70, 100)

#: Age (years) below which the battery cannot trust its tympanogram. JCIH
#: (2019, p.14) recommends the 1000 Hz probe "up to age 9 months", because a
#: 226 Hz probe in the compliant infant ear can trace a normal-looking peak
#: over a middle ear full of fluid; reflexes in newborns and infants under 9
#: months are likewise measured with a 1000 Hz probe. The battery records no
#: probe tone and PatientInfo.age is whole years, so age 0 spans birth to 11
#: months and cannot be split at 9 — every age-0 result is treated as
#: possibly 226 Hz in an infant.
INFANT_PROBE_AGE_YEARS = 1.0

INFANT_PROBE_CAVEAT = (
    "Patient is under 12 months and the probe tone was not recorded. Under about "
    "9 months a 226 Hz probe can show a normal-looking trace over a middle ear full "
    "of fluid (JCIH 2019), so this type is provisional — confirm with a 1000 Hz "
    "probe tympanogram before relying on it."
)

INFANT_PROBE_UNTYPED = (
    "Patient is under 12 months and the probe tone was not recorded, so the "
    "tympanogram was not typed: a 226 Hz probe can show a normal-looking trace "
    "over a middle ear full of fluid in a young infant (JCIH 2019). Record a "
    "1000 Hz probe tympanogram."
)

#: Reflexes recorded without a tympanogram still carry the probe-tone problem.
#: In newborns a 226 Hz probe records the reflex less often, and at higher
#: levels, than a 1000 Hz probe (Jacob-Corteletti et al. 2015, CoDAS), so an
#: "absent" here may be the probe rather than the ear.
INFANT_REFLEX_CAVEAT = (
    "Patient is under 12 months and the probe tone was not recorded. Infant "
    "acoustic reflexes are measured with a 1000 Hz probe (JCIH 2019); a 226 Hz "
    "probe misses reflexes that are present in many young infants, so these "
    "reflex results are provisional — repeat with a 1000 Hz probe before relying "
    "on them."
)


def infant_probe_caveat(age_years: Optional[float]) -> Optional[str]:
    """The probe-tone caveat for an infant, or None when it does not apply."""
    if age_years is None or age_years >= INFANT_PROBE_AGE_YEARS:
        return None
    return INFANT_PROBE_CAVEAT


def classify_tympanogram(
    peak_pressure: Optional[float],
    compliance: Optional[float],
    ecv: Optional[float] = None,
    age_years: Optional[float] = None,
) -> Optional[dict]:
    """Type a tympanogram from its summary values.

    Delegates to ``tympanometry.classify`` so there is exactly one place that
    decides what a tympanogram is. This used to hold a second, five-type copy
    of the rules, which meant the battery on the dashboard and the instrument
    page could disagree about the same ear.
    """
    return classify(peak_pressure, compliance, ecv, age_years=age_years)


def analyze_reflexes(
    reflexes: Dict[str, Optional[float]],
    pta: Optional[float] = None,
) -> Optional[dict]:
    """Interpret ipsi/contra acoustic reflex thresholds for one ear.

    ``reflexes``: {"ipsi": dB HL or None, "contra": dB HL or None}, where
    None means "absent at maximum output" rather than "not tested" — the
    caller passes an empty dict when the test was not done.
    """
    if not reflexes:
        return None
    ipsi, contra = reflexes.get("ipsi"), reflexes.get("contra")
    present = {"ipsi": ipsi is not None, "contra": contra is not None}

    sensation_level = None
    elevated = False
    if ipsi is not None and pta is not None:
        sensation_level = round(ipsi - pta, 1)
        elevated = sensation_level > REFLEX_SL_NORMAL[1]

    if not present["ipsi"] and not present["contra"]:
        pattern = "absent"
        note = ("Reflexes absent bilaterally in this ear — consistent with a "
                "conductive block, severe cochlear loss, or a retrocochlear/"
                "neural lesion depending on the rest of the battery.")
    elif present["ipsi"] and present["contra"]:
        pattern = "present"
        note = ("Reflexes present — the middle ear transmits sound and the "
                "reflex arc is intact.")
    else:
        pattern = "partial"
        note = ("Reflexes present on one side only — asymmetric findings warrant "
                "a full reflex pattern (ipsi and contra, both ears) to localise "
                "the lesion.")

    return {
        "ipsi": ipsi, "contra": contra, "present": present, "pattern": pattern,
        "sensation_level": sensation_level, "elevated": elevated,
        "note": note,
        "normal_sl_range": REFLEX_SL_NORMAL,
    }


def analyze_immittance(ear, pta: Optional[float] = None,
                       age_years: Optional[float] = None) -> Optional[dict]:
    """Full immittance review for one ear (EarData).

    ``age_years`` selects the normative band. Omitting it fell back to the
    adult band, so a child's tympanogram analysed through the battery was
    typed against adult norms while the standalone tympanometry page — which
    does send the age — typed the same numbers differently. The child bands
    are narrower (compliance 0.35–1.25 vs 0.37–1.66, ECV 0.3–1.0 vs 0.6–2.0),
    and the divergence changes both the Jerger type and the Type B ECV split,
    which is the difference between an effusion behind an intact drum and a
    perforation.

    Under a year of age the type is marked provisional with the probe-tone
    caveat (see ``INFANT_PROBE_AGE_YEARS``). The standalone tympanometry page
    knows the probe tone and does this itself; the battery does not, so it
    must assume the worst rather than report "normal middle-ear function"
    from a probe that cannot show an infant's effusion.
    """
    tymp = classify_tympanogram(ear.tymp_pressure, ear.tymp_compliance,
                                ear.tymp_ecv, age_years=age_years)
    reflexes = analyze_reflexes(ear.reflexes or {}, pta)
    caveat = infant_probe_caveat(age_years)
    if caveat and reflexes:
        reflexes = {**reflexes, "provisional": True,
                    "note": f"{reflexes['note']} Provisional: reflexes in infants "
                            "under 9 months are measured with a 1000 Hz probe "
                            "(JCIH 2019)."}
    entered = ear.tymp_pressure is not None or ear.tymp_compliance is not None
    if caveat and entered and tymp is None:
        # The classifier may refuse an infant trace outright rather than type
        # it. The values were still entered, so the reader is told why no type
        # came back instead of seeing the tympanogram silently disappear.
        return {"tympanogram": None, "tympanogram_untyped": True,
                "reflexes": reflexes, "infant_warning": INFANT_PROBE_UNTYPED,
                "not_typed": INFANT_PROBE_UNTYPED}
    if entered and tymp is None:
        # Values entered but not enough to type (a static admittance with no
        # peak pressure, or the reverse): say why, in the instrument page's
        # words, rather than dropping the entered admittance without a trace.
        return {"tympanogram": None, "tympanogram_untyped": True,
                "reflexes": reflexes, "infant_warning": None,
                "not_typed": _untyped_reason("jerger", {}, ear.tymp_pressure,
                                             ear.tymp_compliance)}
    if tymp is None and reflexes is None:
        return None
    if caveat and tymp:
        tymp = {
            **tymp,
            "provisional": True,
            "infant_warning": tymp.get("infant_warning") or caveat,
            "interpretation": f"Provisional (infant, probe tone not recorded). "
                              f"{tymp['interpretation']}",
        }
    # Reflexes alone still need the caveat surfaced, not only tucked into
    # their note: they feed the battery's neural-pathway inferences.
    warning = None
    if caveat:
        warning = caveat if tymp else INFANT_REFLEX_CAVEAT if reflexes else None
    return {"tympanogram": tymp, "tympanogram_untyped": False,
            "reflexes": reflexes, "infant_warning": warning}
