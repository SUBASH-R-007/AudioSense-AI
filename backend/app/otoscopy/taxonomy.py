"""The eight otoscopic patterns, and what each one predicts about the tests.

The classes come from the reference document supplied by the clinical team
("Otoscopic evaluation"), which is also the source of the labelled reference
images in ``data/otoscope_reference/``. Nothing here is invented: each entry
records the appearance the document describes, plus the audiological
consequence that makes the finding actionable rather than merely descriptive.

The ``expected_*`` fields are what makes otoscopy worth running inside this
app. A picture on its own is a picture; a picture that says "this should show
a Type B tympanogram and a conductive gap" can be *checked* against the rest
of the battery, and disagreement flagged.
"""
from __future__ import annotations

from typing import Dict, List

#: Ordered so the UI and the model always agree on class indices.
CLASSES: List[str] = [
    "normal",
    "cerumen_impaction",
    "otitis_media",
    "retraction",
    "perforation_central",
    "perforation_marginal",
    "perforation_attic",
    "tumor",
]

TAXONOMY: Dict[str, dict] = {
    "normal": {
        "name": "Normal tympanic membrane",
        "appearance": (
            "Clear external canal, pearly-grey translucent drum, malleus handle "
            "visible, cone of light present in the antero-inferior quadrant."
        ),
        "severity": "normal",
        "expected_hearing": "Normal, or a loss arising beyond the middle ear.",
        "expected_type": "Sensorineural or normal — not conductive.",
        "expected_tympanogram": "A",
        "expected_gap_db": (0, 10),
        "recommended_tests": [
            "Pure-tone audiometry",
            "Tympanometry (to confirm normal middle-ear pressure)",
            "Otoacoustic emissions if a cochlear cause is suspected",
        ],
        "referral": "No otological referral needed on the basis of the image alone.",
        "red_flags": [],
        "note": (
            "A normal drum does not mean normal hearing. It means any loss "
            "present is unlikely to be conductive, which redirects the workup "
            "to the cochlea and the auditory nerve."
        ),
    },
    "cerumen_impaction": {
        "name": "Cerumen impaction (wax occlusion)",
        "appearance": "Brown-to-black wax filling the canal and obscuring the drum.",
        "severity": "benign",
        "expected_hearing": (
            "Mild conductive loss, typically flat and rarely worse than 40 dB HL. "
            "Reversible."
        ),
        "expected_type": "Conductive",
        "expected_tympanogram": "A or B (a fully occluding plug reduces measured volume)",
        "expected_gap_db": (10, 40),
        "recommended_tests": [
            "Repeat pure-tone audiometry AFTER wax removal",
            "Tympanometry after removal",
        ],
        "referral": (
            "Wax removal (syringing, microsuction or curettage) then re-test. "
            "Do not certify a hearing loss measured through an occluding plug."
        ),
        "red_flags": [],
        "note": (
            "This is the single most common reversible cause of a conductive "
            "loss, and the most common reason an audiogram overstates the "
            "permanent deficit. Removing the wax is the test."
        ),
    },
    "otitis_media": {
        "name": "Acute otitis media / middle-ear effusion",
        "appearance": (
            "Red, bulging or opaque drum; landmarks lost; a fluid level or "
            "bubbles may be visible behind the membrane."
        ),
        "severity": "active",
        "expected_hearing": "Conductive loss, commonly 20-40 dB HL, largest at low frequencies.",
        "expected_type": "Conductive",
        "expected_tympanogram": "B (flat, normal ear-canal volume)",
        "expected_gap_db": (15, 45),
        "recommended_tests": [
            "Tympanometry — a flat trace with normal canal volume confirms fluid",
            "Pure-tone audiometry with masked bone conduction",
            "Repeat audiometry after the infection resolves",
        ],
        "referral": (
            "Medical management now; ENT referral if the effusion persists beyond "
            "three months or hearing loss affects a child's speech development."
        ),
        "red_flags": [
            "Pain with swelling or tenderness behind the ear suggests mastoiditis "
            "— urgent ENT assessment.",
        ],
        "note": (
            "Thresholds taken during an active effusion measure the infection, "
            "not the patient's permanent hearing. Re-test after resolution "
            "before any disability calculation."
        ),
    },
    "retraction": {
        "name": "Retracted tympanic membrane (Eustachian tube dysfunction)",
        "appearance": (
            "Drum drawn inward; malleus handle foreshortened and unusually "
            "prominent; cone of light distorted or absent."
        ),
        "severity": "chronic",
        "expected_hearing": "Normal to mild conductive loss; often fluctuating.",
        "expected_type": "Conductive or normal",
        "expected_tympanogram": "C (negative middle-ear pressure)",
        "expected_gap_db": (0, 25),
        "recommended_tests": [
            "Tympanometry — expect a peak at markedly negative pressure",
            "Eustachian tube function testing",
            "Pure-tone audiometry",
        ],
        "referral": (
            "Treat the underlying nasal or allergic cause; ENT review if a deep "
            "retraction pocket is developing."
        ),
        "red_flags": [
            "A deep attic retraction pocket that cannot be fully seen may harbour "
            "cholesteatoma — ENT review.",
        ],
        "note": (
            "Retraction is the step before an effusion and, if a pocket forms and "
            "traps skin, the step before cholesteatoma. Catching it here is the "
            "cheap intervention."
        ),
    },
    "perforation_central": {
        "name": "Central perforation",
        "appearance": (
            "Defect in the pars tensa surrounded on all sides by remnant drum; "
            "the annulus is intact."
        ),
        "severity": "chronic",
        "expected_hearing": (
            "Conductive loss roughly proportional to the size of the defect, "
            "typically 20-40 dB HL."
        ),
        "expected_type": "Conductive",
        "expected_tympanogram": "B with a LARGE ear-canal volume",
        "expected_gap_db": (15, 45),
        "recommended_tests": [
            "Tympanometry — large equivalent ear-canal volume confirms the defect",
            "Pure-tone audiometry with masked bone conduction",
            "Speech audiometry",
        ],
        "referral": (
            "ENT referral for assessment of tympanoplasty. Keep the ear dry; "
            "avoid water entry and topical aminoglycosides."
        ),
        "red_flags": [],
        "note": (
            "This is the 'safe' perforation. It causes hearing loss and "
            "recurrent discharge but does not erode bone."
        ),
    },
    "perforation_marginal": {
        "name": "Marginal perforation",
        "appearance": (
            "Defect reaching the annulus, so that no remnant drum separates it "
            "from the canal wall."
        ),
        "severity": "unsafe",
        "expected_hearing": "Conductive loss, often 25-50 dB HL.",
        "expected_type": "Conductive or mixed",
        "expected_tympanogram": "B with a LARGE ear-canal volume",
        "expected_gap_db": (20, 50),
        "recommended_tests": [
            "Tympanometry (large canal volume)",
            "Pure-tone audiometry with masked bone conduction",
            "CT temporal bone if cholesteatoma is suspected",
        ],
        "referral": "ENT referral — this is an unsafe perforation.",
        "red_flags": [
            "Marginal perforations allow canal skin to migrate into the middle "
            "ear and are associated with cholesteatoma. Treat as unsafe.",
        ],
        "note": (
            "The distinction from a central perforation is not cosmetic: the "
            "absence of an annular rim is what lets squamous epithelium enter "
            "the middle ear."
        ),
    },
    "perforation_attic": {
        "name": "Attic (pars flaccida) perforation or retraction pocket",
        "appearance": (
            "Defect or crust in the pars flaccida, superior to the short process "
            "of the malleus; often with keratin debris."
        ),
        "severity": "unsafe",
        "expected_hearing": (
            "Variable — may be near normal early, then conductive or mixed as "
            "the ossicles erode."
        ),
        "expected_type": "Conductive, becoming mixed",
        "expected_tympanogram": "B or C depending on the state of the middle ear",
        "expected_gap_db": (0, 60),
        "recommended_tests": [
            "CT temporal bone",
            "Pure-tone audiometry with masked bone conduction",
            "Tympanometry and acoustic reflexes",
        ],
        "referral": "Urgent ENT referral — assume cholesteatoma until excluded.",
        "red_flags": [
            "Attic crusting or a keratin-filled pocket is cholesteatoma until "
            "proven otherwise. It erodes ossicles, can cause facial palsy, "
            "labyrinthine fistula and intracranial sepsis.",
            "Normal hearing does NOT reassure here — early cholesteatoma is "
            "often silent on the audiogram.",
        ],
        "note": (
            "The most dangerous of the three perforation sites and the easiest "
            "to overlook, because the audiogram can be normal while the disease "
            "advances."
        ),
    },
    "tumor": {
        "name": "Mass in the canal or middle ear",
        "appearance": (
            "Soft-tissue mass, polyp or vascular blush behind or replacing the "
            "drum; may bleed on contact."
        ),
        "severity": "urgent",
        "expected_hearing": "Conductive or mixed loss; may be unilateral and progressive.",
        "expected_type": "Conductive or mixed",
        "expected_tympanogram": "B, or a pulsatile trace with a vascular mass",
        "expected_gap_db": (15, 60),
        "recommended_tests": [
            "Imaging (CT and/or MRI temporal bone) before any manipulation",
            "Pure-tone and speech audiometry",
            "Acoustic reflexes",
        ],
        "referral": "Urgent ENT referral. Do not biopsy in clinic — a glomus tumour bleeds.",
        "red_flags": [
            "Pulsatile tinnitus with a red retrotympanic mass suggests a glomus "
            "tumour — image before touching it.",
            "Persistent bloody discharge with a canal mass in an older patient "
            "raises squamous cell carcinoma.",
        ],
        "note": (
            "Rare, but the one class where a delayed diagnosis changes the "
            "outcome most. Any unilateral mass gets imaged."
        ),
    },
}

#: Coarse category per class. Distinguishing a central from a marginal
#: perforation is genuinely hard from a photograph, and on the reference set
#: the model does it barely above chance. Distinguishing "there is a hole"
#: from "the canal is full of wax" is much more reliable, and it is already
#: enough to decide what happens next — so the category is reported alongside
#: the fine label, with its own (higher) measured accuracy.
CATEGORY: Dict[str, str] = {
    "normal": "normal",
    "cerumen_impaction": "canal_obstruction",
    "otitis_media": "inflammation_effusion",
    "retraction": "retraction",
    "perforation_central": "perforation",
    "perforation_marginal": "perforation",
    "perforation_attic": "perforation",
    "tumor": "mass",
}

CATEGORY_LABEL: Dict[str, str] = {
    "normal": "Normal appearance",
    "canal_obstruction": "Canal obstruction",
    "inflammation_effusion": "Inflammation or effusion",
    "retraction": "Retraction",
    "perforation": "Tympanic membrane perforation",
    "mass": "Mass lesion",
}

#: How urgently each pattern needs to be acted on. Coarser still, and the
#: most reliable output of the three.
URGENCY: Dict[str, str] = {
    "normal": "routine",
    "cerumen_impaction": "routine",
    "otitis_media": "treat",
    "retraction": "treat",
    "perforation_central": "refer",
    "perforation_marginal": "urgent",
    "perforation_attic": "urgent",
    "tumor": "urgent",
}

URGENCY_LABEL: Dict[str, str] = {
    "routine": "Routine — no urgent otological action",
    "treat": "Treat and re-test once resolved",
    "refer": "ENT referral",
    "urgent": "Urgent ENT referral",
}

#: Classes for which the audiogram should show an air-bone gap. Used by the
#: cross-check against pure-tone results.
CONDUCTIVE_CLASSES = {
    "cerumen_impaction", "otitis_media", "perforation_central",
    "perforation_marginal", "perforation_attic", "tumor",
}

#: Classes that should never be managed with reassurance alone.
URGENT_CLASSES = {"perforation_attic", "tumor"}


def describe(label: str) -> dict:
    """Clinical record for a predicted class, with the label attached."""
    entry = TAXONOMY.get(label)
    if entry is None:
        return {"label": label, "name": label.replace("_", " ").title()}
    return {"label": label, **entry}
