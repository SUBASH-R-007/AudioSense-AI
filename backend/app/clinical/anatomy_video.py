"""Which anatomy animation explains THIS patient's hearing loss.

A patient does not picture a 40 dB air-bone gap. They picture their ear. This
module picks the one short animation — eardrum, through the middle ear, to the
cochlea — that shows where their own sound is being lost, and supplies the two
or three plain sentences a clinician says while it plays.

WHAT IT IS AND IS NOT. Every clip is a generic illustration of a mechanism. It
is NOT a scan, a recording, or a rendering of this patient's own ear, and the
response says so on every single selection (``illustration_only``). A patient
who believes they have watched footage of their own eardrum has been misled by
the tool that was supposed to inform them, so the disclaimer travels in the
payload rather than being a caption the interface may forget to render.

HOW THE CHOICE IS MADE. Mechanism beats grade. A conductive loss on the
audiogram says sound is not reaching the cochlea; it cannot say why, and "why"
is the whole point of a picture. So the tympanogram and the otoscopy image are
read first — they name the mechanism — and the audiogram type is the fallback
when neither is available:

  1. Ear-canal volume splits a flat (Type B) trace three ways, and the three
     mean completely different things: large volume is a hole in the drum,
     small volume is the probe against wax, normal volume is fluid behind an
     intact drum. Getting this wrong shows a patient a perforation they do not
     have.
  2. Otoscopy, but only when the image was filed under THIS ear. The stored
     result carries its own ``side``; a right-ear photograph must never drive
     the left ear's animation.
  3. Stiffness and laxity: Type As is a chain that will not move; Type Ad/Add
     and a wide notch (Type E) are a chain that moves too freely or is
     disconnected; a narrow notch (Type D) is a lax or scarred drum.
  4. Failing all of that, the audiogram type alone.

A mixed loss keeps its middle-ear animation and raises ``plus_sensorineural``,
because the middle-ear part is the part a picture can show and the cochlear
part still has to be said out loud.

Boundaries and vocabulary follow the modules that own them: Jerger typing and
the ear-canal-volume split from ``tympanometry.py``, the eight otoscopy
patterns from ``otoscopy/taxonomy.py``, and the ear types from ``rules.py``.
Nothing here re-derives a clinical decision another module already makes.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: Stated on every selection. The clips are generic anatomy, not this patient.
ILLUSTRATION_NOTE = (
    "This is a general animation of how the ear works, not a picture or scan "
    "of your own ear. It is here to show where the sound is being lost."
)

#: Where each clip must start and end, so the set feels like one journey.
JOURNEY = "Ear canal and eardrum, through the middle-ear bones, into the cochlea."

#: The catalogue. ``file`` and ``poster`` are resolved by the frontend against
#: its own public asset directory; nothing here touches the filesystem, so a
#: clip that has not been generated yet is a rendering concern rather than a
#: server error.
VIDEOS: Dict[str, dict] = {
    "normal": {
        "title": "Normal sound pathway",
        "patient_title": "How hearing works when nothing is blocking it",
        "shows": "Sound entering the canal, vibrating the eardrum, carried by "
                 "the three bones into the cochlea, where hair cells fire.",
        "plain": "Your ears are moving sound the way they should. Sound waves "
                 "shake the eardrum, three tiny bones carry that movement "
                 "inward, and the hearing organ turns it into signals your "
                 "brain understands.",
        "mechanism": "No loss demonstrated at the frequencies tested.",
    },
    "wax_occlusion": {
        "title": "Wax occluding the canal",
        "patient_title": "Wax is blocking sound before it reaches the eardrum",
        "shows": "Sound stopped by a plug of wax in the canal; the eardrum and "
                 "everything past it healthy and still.",
        "plain": "The ear itself is working. Wax is sitting in the canal and "
                 "stopping sound before it ever reaches the eardrum. This is "
                 "the most easily fixed cause of hearing loss there is — the "
                 "hearing usually returns once the wax is removed.",
        "mechanism": "Sound is blocked in the outer ear, before the eardrum.",
    },
    "effusion": {
        "title": "Fluid behind an intact eardrum",
        "patient_title": "There is fluid behind your eardrum",
        "shows": "The middle-ear space filling with fluid; the eardrum and "
                 "bones becoming sluggish and barely moving.",
        "plain": "The space behind your eardrum, which should be full of air, "
                 "has fluid in it. The eardrum cannot move freely through "
                 "fluid, so sound is muffled — like hearing underwater. The "
                 "eardrum itself is not torn.",
        "mechanism": "Sound is absorbed by fluid in the middle-ear space.",
    },
    "perforation": {
        "title": "Perforated eardrum",
        "patient_title": "There is a hole in your eardrum",
        "shows": "A hole in the eardrum; sound passing through it instead of "
                 "driving the bones.",
        "plain": "There is a hole in your eardrum. A drum with a hole in it "
                 "cannot catch sound properly, so some of the sound passes "
                 "straight through instead of being carried inward. Keep "
                 "water out of this ear until it has been reviewed.",
        "mechanism": "Sound escapes through the drum instead of driving the "
                     "ossicular chain.",
    },
    "retraction": {
        "title": "Retracted eardrum (Eustachian tube not opening)",
        "patient_title": "Your eardrum is being pulled inward",
        "shows": "The pressure-equalising tube staying shut, the middle-ear "
                 "air being absorbed, and the eardrum drawing inward.",
        "plain": "The small tube that lets air into the space behind your "
                 "eardrum is not opening properly. Air gets absorbed, a "
                 "vacuum forms, and the eardrum is pulled inward and stiffens "
                 "— so it cannot pass sound on as easily.",
        "mechanism": "Negative middle-ear pressure stiffens the drum.",
    },
    "ossicular_fixation": {
        "title": "Stiff ossicular chain",
        "patient_title": "One of the hearing bones has become stiff",
        "shows": "The stapes held at the oval window by extra bone; the chain "
                 "vibrating far less than it should.",
        "plain": "Three tiny bones carry sound across your middle ear. One of "
                 "them has become stiff and no longer rocks freely, so less "
                 "of the sound gets through to the hearing organ. The eardrum "
                 "itself looks normal.",
        "mechanism": "A fixed ossicular chain cannot transmit vibration.",
    },
    "ossicular_discontinuity": {
        "title": "Interrupted ossicular chain",
        "patient_title": "The chain of hearing bones is not joined up",
        "shows": "The link between the bones separated; the eardrum moving "
                 "freely but the movement not reaching the cochlea.",
        "plain": "The three small bones behind your eardrum normally work as "
                 "one connected chain. That connection is not intact, so the "
                 "eardrum moves easily but the movement is not carried "
                 "through to the hearing organ.",
        "mechanism": "A broken chain moves freely but transmits nothing.",
    },
    "flaccid_drum": {
        "title": "Lax or scarred eardrum",
        "patient_title": "Your eardrum is floppier than it should be",
        "shows": "A thinned, over-mobile drum flapping without driving the "
                 "bones firmly.",
        "plain": "Your eardrum is more slack than usual, often where it has "
                 "healed after an old infection or perforation. It moves very "
                 "easily but does not pass that movement on firmly, so some "
                 "sound is lost.",
        "mechanism": "An over-compliant drum couples poorly to the ossicles.",
    },
    "conductive_unspecified": {
        "title": "Sound blocked somewhere before the cochlea",
        "patient_title": "Something is blocking sound on its way in",
        "shows": "The outer and middle ear highlighted as the point of loss, "
                 "with the cochlea shown working normally.",
        "plain": "Your hearing organ is responding normally, but something "
                 "between the outside and it is stopping sound getting "
                 "through. The test shows that clearly — the next test tells "
                 "us exactly where.",
        "mechanism": "A conductive block is present; the mechanism is not yet "
                     "identified.",
    },
    "sensorineural": {
        "title": "Cochlear hair-cell damage",
        "patient_title": "The hearing organ itself is damaged",
        "shows": "Sound travelling normally to the cochlea; the hair cells at "
                 "the high-frequency end flattened and not firing.",
        "plain": "Sound is reaching the hearing organ perfectly well. Inside "
                 "it are tiny hair cells that turn movement into nerve "
                 "signals, and some of yours are damaged — the ones for high "
                 "sounds first. That is why speech can be loud enough and "
                 "still unclear. These cells do not grow back, so the aim is "
                 "to protect the ones you have and amplify what is left.",
        "mechanism": "Loss is at the cochlea, past the conducting mechanism.",
    },
    "mixed": {
        "title": "Both a block and cochlear damage",
        "patient_title": "There are two problems at once",
        "shows": "A middle-ear block and flattened cochlear hair cells "
                 "highlighted one after the other.",
        "plain": "Two things are happening in the same ear. Something is "
                 "blocking sound on the way in, and the hearing organ itself "
                 "is also damaged. The blockage is often treatable; the "
                 "inner-ear part usually is not, so we deal with them "
                 "separately.",
        "mechanism": "Conductive and sensorineural components together.",
    },
}

#: Jerger type -> mechanism, for the types that name one on their own. Type B
#: is deliberately absent: it means nothing without the ear-canal volume,
#: which splits it three ways.
_TYMP_MECHANISM: Dict[str, str] = {
    "C": "retraction",
    "As": "ossicular_fixation",
    "Ad": "ossicular_discontinuity",
    "Add": "ossicular_discontinuity",
    "E": "ossicular_discontinuity",
    "D": "flaccid_drum",
}

#: Otoscopy pattern -> mechanism. ``normal`` and ``tumor`` are absent on
#: purpose: a normal drum names no mechanism, and a mass is a referral, not an
#: animation to reassure somebody with.
_OTOSCOPY_MECHANISM: Dict[str, str] = {
    "cerumen_impaction": "wax_occlusion",
    "otitis_media": "effusion",
    "retraction": "retraction",
    "perforation_central": "perforation",
    "perforation_marginal": "perforation",
    "perforation_attic": "perforation",
}

#: Ear-canal volume flag -> what a flat trace means at that volume.
_TYPE_B_BY_VOLUME: Dict[str, str] = {
    "large": "perforation",
    "small": "wax_occlusion",
    "normal": "effusion",
}

SIDES = ("right", "left")


def _clean_type(value) -> Optional[str]:
    """Ear type with the provisional suffix stripped, or None."""
    if not isinstance(value, str):
        return None
    return value.replace(" (provisional)", "").strip() or None


def _tympanogram(analysis: dict, side: str) -> dict:
    imm = (analysis.get("immittance") or {}).get(side) or {}
    return imm.get("tympanogram") or {}


def _otoscopy_label(otoscopy: Optional[dict], side: str) -> Optional[str]:
    """The otoscopy pattern for THIS ear, or None.

    The stored result carries the side it was filed under. An image of the
    other ear must not choose this ear's animation, so a mismatch — or an
    untagged result — counts as no information rather than as a finding.
    """
    if not isinstance(otoscopy, dict):
        return None
    if otoscopy.get("side") != side:
        return None
    label = (otoscopy.get("prediction") or {}).get("label")
    return label if isinstance(label, str) and label else None


def _mechanism(analysis: dict, side: str,
               otoscopy: Optional[dict]) -> Tuple[Optional[str], List[str]]:
    """The named middle-ear mechanism for this ear, with what named it."""
    because: List[str] = []
    tymp = _tympanogram(analysis, side)
    ttype = tymp.get("type")
    volume = tymp.get("ecv_flag")
    oto = _otoscopy_label(otoscopy, side)

    # A flat trace is read through the ear-canal volume, never on its own.
    if ttype == "B":
        key = _TYPE_B_BY_VOLUME.get(volume or "normal", "effusion")
        because.append(
            f"Type B tympanogram with a {volume or 'normal'} ear-canal volume")
        if oto and oto in _OTOSCOPY_MECHANISM:
            because.append(f"otoscopy of this ear: {oto.replace('_', ' ')}")
        return key, because

    if ttype in _TYMP_MECHANISM:
        because.append(f"Type {ttype} tympanogram")
        return _TYMP_MECHANISM[ttype], because

    if oto in _OTOSCOPY_MECHANISM:
        because.append(f"otoscopy of this ear: {oto.replace('_', ' ')}")
        return _OTOSCOPY_MECHANISM[oto], because

    return None, because


def select(analysis: Optional[dict], side: str = "right",
           otoscopy: Optional[dict] = None) -> dict:
    """Choose the animation that explains this ear, and say why.

    Returns ``available: False`` rather than guessing when the ear was not
    tested — an animation shown for an untested ear is a claim about a
    measurement nobody made.
    """
    if side not in SIDES:
        side = "right"
    a = analysis if isinstance(analysis, dict) else {}
    rules = (a.get("rules") or {}).get(side) or {}
    ear_type = _clean_type(rules.get("type"))

    if ear_type in (None, "Indeterminate"):
        return {
            "available": False,
            "side": side,
            "reason": ("No thresholds were recorded for this ear at the "
                       "frequencies the interpretation rests on, so there is "
                       "nothing yet to illustrate."),
            "illustration_only": True,
            "note": ILLUSTRATION_NOTE,
        }

    mech, because = _mechanism(a, side, otoscopy)

    if ear_type in ("Conductive", "Mixed") and mech:
        key = mech
    elif ear_type == "Conductive":
        key = "conductive_unspecified"
        because.append("conductive loss on the audiogram, mechanism not yet identified")
    elif ear_type == "Mixed":
        key = "mixed"
        because.append("mixed loss on the audiogram, mechanism not yet identified")
    elif ear_type == "Sensorineural":
        key = "sensorineural"
        because.append("sensorineural loss on the audiogram")
    elif ear_type == "Normal":
        # A normal-hearing ear can still carry a middle-ear finding worth
        # showing — a retracted drum with thresholds still inside normal
        # limits is exactly the case worth explaining before it progresses.
        key = mech or "normal"
        if not mech:
            because.append("thresholds within normal limits")
    else:
        key = mech or "conductive_unspecified"

    entry = VIDEOS[key]
    return {
        "available": True,
        "side": side,
        "key": key,
        "file": f"{key}.mp4",
        "poster": f"{key}.jpg",
        "ear_type": ear_type,
        "journey": JOURNEY,
        # A mixed loss keeps the middle-ear picture; the cochlear half of the
        # story cannot be drawn on the same clip and has to be said.
        "plus_sensorineural": bool(ear_type == "Mixed" and key != "mixed"),
        "because": because,
        "illustration_only": True,
        "note": ILLUSTRATION_NOTE,
        **entry,
    }


def catalogue() -> List[dict]:
    """Every clip, so the interface can state what the set covers."""
    return [{"key": k, "file": f"{k}.mp4", "poster": f"{k}.jpg", **v}
            for k, v in VIDEOS.items()]
