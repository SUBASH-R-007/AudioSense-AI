"""Tympanometry and acoustic reflexes — the middle-ear half of the battery.

Pure-tone audiometry says *how much* hearing is lost. Immittance says
*where the problem is*, independently of the patient's voluntary response,
which is why it is the standard cross-check on a conductive finding.

Tympanogram types (Jerger classification, 1970):
  A   normal peak pressure and compliance
  As  shallow ("stiff") — otosclerosis, tympanosclerosis
  Ad  deep ("flaccid") — ossicular discontinuity, monomeric membrane
  B   flat, no peak — middle-ear effusion or perforation
      (distinguished by ear-canal volume: large volume = perforation/patent
       grommet, normal volume = effusion)
  C   peak at markedly negative pressure — Eustachian tube dysfunction

Acoustic reflex thresholds normally appear 70-100 dB above the pure-tone
threshold. Their presence or absence, ipsilateral versus contralateral,
localises the lesion along the reflex arc.
"""
from __future__ import annotations

from typing import Dict, List, Optional

#: Normal static admittance (compliance), millimhos.
COMPLIANCE_NORMAL = (0.3, 1.6)
#: Normal tympanometric peak pressure, daPa.
PRESSURE_NORMAL = (-100, 50)
#: Normal equivalent ear-canal volume, cm3 (adult).
ECV_NORMAL = (0.6, 2.0)
#: Acoustic reflex thresholds are normally 70-100 dB SL above threshold.
REFLEX_SL_NORMAL = (70, 100)


def classify_tympanogram(
    peak_pressure: Optional[float],
    compliance: Optional[float],
    ecv: Optional[float] = None,
) -> Optional[dict]:
    """Assign a Jerger type from peak pressure, compliance and canal volume."""
    if peak_pressure is None and compliance is None:
        return None

    # A flat trace has no measurable peak; compliance collapses.
    flat = compliance is not None and compliance < 0.2
    if flat or peak_pressure is None:
        perforation = ecv is not None and ecv > ECV_NORMAL[1]
        return {
            "type": "B",
            "label": "Type B — flat, no compliance peak",
            "interpretation": (
                "Large ear-canal volume: tympanic membrane perforation or a patent "
                "ventilation tube."
                if perforation else
                "Normal ear-canal volume: middle-ear effusion (fluid) is the usual cause."
            ),
            "suggests_conductive": True,
            "ecv_flag": "large" if perforation else "normal",
        }

    if compliance is not None and compliance > COMPLIANCE_NORMAL[1]:
        return {
            "type": "Ad",
            "label": "Type Ad — deep / hypercompliant",
            "interpretation": "Ossicular discontinuity or a flaccid (monomeric) "
                              "tympanic membrane.",
            "suggests_conductive": True,
            "ecv_flag": "normal",
        }
    if compliance is not None and compliance < COMPLIANCE_NORMAL[0]:
        return {
            "type": "As",
            "label": "Type As — shallow / stiff",
            "interpretation": "Reduced middle-ear mobility: otosclerosis, "
                              "tympanosclerosis or middle-ear stiffening.",
            "suggests_conductive": True,
            "ecv_flag": "normal",
        }
    if peak_pressure < PRESSURE_NORMAL[0]:
        return {
            "type": "C",
            "label": "Type C — negative middle-ear pressure",
            "interpretation": "Eustachian tube dysfunction; often precedes or "
                              "follows an effusion.",
            "suggests_conductive": peak_pressure < -200,
            "ecv_flag": "normal",
        }
    return {
        "type": "A",
        "label": "Type A — normal",
        "interpretation": "Normal middle-ear pressure and mobility.",
        "suggests_conductive": False,
        "ecv_flag": "normal",
    }


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


def analyze_immittance(ear, pta: Optional[float] = None) -> Optional[dict]:
    """Full immittance review for one ear (EarData)."""
    tymp = classify_tympanogram(ear.tymp_pressure, ear.tymp_compliance, ear.tymp_ecv)
    reflexes = analyze_reflexes(ear.reflexes or {}, pta)
    if tymp is None and reflexes is None:
        return None
    return {"tympanogram": tymp, "reflexes": reflexes}
