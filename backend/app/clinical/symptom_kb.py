"""Knowledge base for symptom-led assessment. Data only, no logic.

Two clinical documents supplied by the project's audiology team are encoded
here, unchanged in substance:

1. A presenting-complaint guide — otorrhoea, otalgia, vertigo and headache —
   listing the likely causes for each complaint IN RANK ORDER, separately for
   children, adults and older adults. The ordering is the clinical content:
   the same discharge means acute otitis media in a five-year-old and
   malignant otitis externa in a diabetic of seventy-five.

2. A disease reference listing, for fourteen conditions, the main symptoms,
   the most prone age group, and the audiological tests that establish the
   diagnosis. That last column is what turns this from a symptom checker into
   something useful in an audiology clinic: it says which test to run next.

Everything a clinician sees carries its source, so nothing here is an
unattributable assertion by a piece of software. Weights are the one addition
— the documents rank causes but do not say how strongly each symptom argues
for each disease — and they are declared, not hidden, so they can be argued
with.

References carried by the source documents:
  American Academy of Otolaryngology-Head and Neck Surgery. (n.d.).
  Katz, J., et al. (Eds.). (2015). Handbook of clinical audiology (7th ed.).
  Merck Manual Professional Edition. (n.d.).
  American Speech-Language-Hearing Association. (n.d.). Practice portal.
  Hall, J. W. (2020). New handbook of auditory evoked responses.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# --------------------------------------------------------------------------
# age bands, exactly as the source document splits them
# --------------------------------------------------------------------------
AGE_BANDS: List[Tuple[str, str, int, int]] = [
    ("pediatric", "Pediatric (0-17 years)", 0, 17),
    ("adult", "Adults (18-64 years)", 18, 64),
    ("geriatric", "Geriatric (65 years and older)", 65, 200),
]


def age_band(age: int) -> dict:
    for key, label, lo, hi in AGE_BANDS:
        if lo <= age <= hi:
            return {"key": key, "label": label, "range": [lo, hi]}
    return {"key": "adult", "label": AGE_BANDS[1][1], "range": [18, 64]}


# --------------------------------------------------------------------------
# symptom vocabulary
# --------------------------------------------------------------------------
#: Canonical symptom -> what a patient or a clerk might actually type. Free
#: text is matched against these, because "water is coming from my ear" is how
#: the complaint arrives and "otorrhoea" is how it is recorded.
SYMPTOM_SYNONYMS: Dict[str, List[str]] = {
    "ear_discharge": [
        "discharge", "otorrhea", "otorrhoea", "running ear", "water from ear",
        "water discharge", "water coming from ear", "fluid from ear", "pus",
        "wet ear", "weeping ear", "ear leaking", "liquid from ear",
    ],
    "foul_smelling_discharge": [
        "foul smell", "smelly discharge", "bad smell from ear", "offensive discharge",
        "foul-smelling",
    ],
    "bloody_discharge": ["blood from ear", "bloody ear discharge", "bloody discharge",
                         "bleeding from ear"],
    "ear_pain": ["ear pain", "otalgia", "earache", "ear ache", "pain in ear", "sore ear"],
    "severe_ear_pain": ["severe ear pain", "intense ear pain", "excruciating ear pain",
                        "deep ear pain"],
    # The guide's own wording ("especially when touching or pulling the ear")
    # must match too — these phrases are what separate one ranked cause from
    # the next, and a synonym table that only understands how a patient speaks
    # cannot read the document it is ranking against.
    "pain_on_touching_ear": ["pain when touching ear", "pain pulling ear",
                             "tragal tenderness", "hurts to touch ear",
                             "touching or pulling the ear", "pulling the ear",
                             "touching the ear"],
    "hearing_loss": ["hearing loss", "cannot hear", "can't hear", "hard of hearing",
                     "reduced hearing", "deaf", "poor hearing", "hearing reduced"],
    "sudden_hearing_loss": ["sudden hearing loss", "hearing lost overnight",
                            "lost hearing suddenly", "woke up deaf"],
    "gradual_hearing_loss": ["gradual hearing loss", "slowly worsening hearing",
                             "gradually worsening hearing", "progressive hearing loss"],
    "fluctuating_hearing_loss": ["fluctuating hearing", "hearing comes and goes",
                                 "hearing varies"],
    "muffled_hearing": ["muffled", "dull hearing", "sounds muffled", "blocked hearing"],
    "tinnitus": ["tinnitus", "ringing", "buzzing", "hissing", "noise in ear",
                 "sound in my ear"],
    "pulsatile_tinnitus": ["pulsatile tinnitus", "heartbeat in ear", "whooshing",
                           "pulsing sound", "hear my pulse"],
    "vertigo": ["vertigo", "spinning", "room spinning", "dizzy", "dizziness",
                "giddiness", "whirling"],
    "positional_vertigo": ["dizzy when turning head", "dizzy lying down",
                           "brief dizziness", "vertigo on movement"],
    "imbalance": ["imbalance", "unsteady", "off balance", "balance problem",
                  "falls", "staggering"],
    "aural_fullness": ["fullness", "blocked ear", "pressure in ear", "stuffy ear",
                       "ear feels full", "plugged ear"],
    "popping": ["popping", "clicking in ear", "crackling"],
    "fever": ["fever", "temperature", "febrile", "hot"],
    "headache": ["headache", "head pain", "head ache"],
    "stiff_neck": ["stiff neck", "neck stiffness", "cannot bend neck"],
    "photophobia": ["photophobia", "light hurts", "sensitive to light"],
    "vomiting": ["vomiting", "nausea", "throwing up", "sick to stomach"],
    "drowsiness": ["drowsy", "sleepy", "hard to wake", "lethargic", "unresponsive"],
    "seizures": ["seizure", "fits", "convulsion"],
    "postauricular_swelling": ["swelling behind the ear", "swelling behind ear",
                               "lump behind ear",
                               "tender behind ear", "red behind ear",
                               "ear sticking out"],
    "facial_weakness": ["facial weakness", "facial palsy", "face droop",
                        "cannot close eye", "mouth drooping"],
    "speech_in_noise_difficulty": [
        "difficulty in noise", "cannot hear in noisy places", "struggle in restaurants",
        "hard to follow conversation in crowd", "noisy environment",
    ],
    "asks_repetition": ["asks to repeat", "says pardon", "asking me to repeat",
                        "repeat yourself"],
    "poor_speech_discrimination": ["words unclear", "hears but does not understand",
                                   "speech unclear", "cannot make out words"],
    "difficulty_following_instructions": ["cannot follow instructions",
                                          "does not follow directions",
                                          "poor listening"],
    "delayed_speech": ["speech delay", "not talking", "delayed speech",
                       "not responding to sound", "no response to name"],
    "inconsistent_response_to_sound": ["responds sometimes", "inconsistent response",
                                       "hears sometimes"],
    "pain_on_chewing": ["pain when chewing", "while chewing", "chewing",
                        "opening the mouth", "jaw pain", "pain opening mouth",
                        "tmj", "jaw joint"],
    "toothache": ["toothache", "tooth pain", "dental pain"],
    "noise_exposure": ["loud noise", "factory", "machinery", "gunfire", "workshop",
                       "loud music", "headphones", "construction", "generator"],
    "ototoxic_medication": ["chemotherapy", "cisplatin", "gentamicin", "amikacin",
                            "aminoglycoside", "ototoxic", "tb treatment",
                            "streptomycin"],
    "recent_trauma": ["head injury", "cotton bud injury", "after injury", "injury",
                      "trauma", "slap", "blast", "accident", "hit on ear"],
    "barotrauma": ["flying", "diving", "air travel", "pressure change", "scuba"],
    "straining": ["straining", "heavy lifting", "coughing hard"],
    "ear_blisters": ["blisters", "bullae", "vesicles on eardrum"],
    "foreign_body": ["foreign body", "object in ear", "bead in ear", "insect in ear"],
    "itching": ["itching", "itchy ear", "irritation"],
    "diabetes": ["diabetes", "diabetic", "high sugar"],
    "immunosuppression": ["immunosuppressed", "hiv", "on steroids", "transplant",
                          "low immunity"],
    "swimming": ["swimming", "swimmer", "water in ear", "pool"],
    "hearing_aid_user": ["hearing aid", "hearing aids"],
    "family_history": ["family history", "runs in family", "mother deaf",
                       "father deaf"],
}

#: Grouped for the intake form, so a clinician ticks boxes rather than typing.
SYMPTOM_GROUPS: Dict[str, List[str]] = {
    "Discharge": ["ear_discharge", "foul_smelling_discharge", "bloody_discharge"],
    "Pain": ["ear_pain", "severe_ear_pain", "pain_on_touching_ear",
             "pain_on_chewing", "toothache"],
    "Hearing": ["hearing_loss", "sudden_hearing_loss", "gradual_hearing_loss",
                "fluctuating_hearing_loss", "muffled_hearing", "asks_repetition",
                "speech_in_noise_difficulty", "poor_speech_discrimination",
                "difficulty_following_instructions"],
    "Ear noise": ["tinnitus", "pulsatile_tinnitus"],
    "Balance": ["vertigo", "positional_vertigo", "imbalance"],
    "Pressure": ["aural_fullness", "popping"],
    "Systemic": ["fever", "headache", "stiff_neck", "photophobia", "vomiting",
                 "drowsiness", "seizures", "postauricular_swelling",
                 "facial_weakness"],
    "Children": ["delayed_speech", "inconsistent_response_to_sound", "foreign_body"],
    "History and exposure": ["noise_exposure", "ototoxic_medication", "recent_trauma",
                             "barotrauma", "straining", "swimming", "diabetes",
                             "immunosuppression", "hearing_aid_user", "itching",
                             "ear_blisters", "family_history"],
}

SYMPTOM_LABELS: Dict[str, str] = {
    "ear_discharge": "Discharge from the ear",
    "foul_smelling_discharge": "Foul-smelling discharge",
    "bloody_discharge": "Blood-stained discharge",
    "ear_pain": "Ear pain",
    "severe_ear_pain": "Severe or deep ear pain",
    "pain_on_touching_ear": "Pain on touching or pulling the ear",
    "hearing_loss": "Hearing loss",
    "sudden_hearing_loss": "Sudden hearing loss",
    "gradual_hearing_loss": "Gradually worsening hearing",
    "fluctuating_hearing_loss": "Hearing that fluctuates",
    "muffled_hearing": "Muffled hearing",
    "tinnitus": "Ringing or buzzing (tinnitus)",
    "pulsatile_tinnitus": "Pulsatile tinnitus (hears own heartbeat)",
    "vertigo": "Vertigo (spinning sensation)",
    "positional_vertigo": "Brief vertigo on head movement",
    "imbalance": "Imbalance or unsteadiness",
    "aural_fullness": "Fullness or pressure in the ear",
    "popping": "Popping or clicking",
    "fever": "Fever",
    "headache": "Headache",
    "stiff_neck": "Stiff neck",
    "photophobia": "Sensitivity to light",
    "vomiting": "Nausea or vomiting",
    "drowsiness": "Drowsiness or difficulty waking",
    "seizures": "Seizures",
    "postauricular_swelling": "Swelling or tenderness behind the ear",
    "facial_weakness": "Facial weakness",
    "speech_in_noise_difficulty": "Difficulty understanding speech in noise",
    "asks_repetition": "Frequently asks for repetition",
    "poor_speech_discrimination": "Hears sound but cannot make out words",
    "difficulty_following_instructions": "Difficulty following spoken instructions",
    "delayed_speech": "Delayed speech or no response to sound",
    "inconsistent_response_to_sound": "Inconsistent responses to sound",
    "pain_on_chewing": "Ear pain on chewing or opening the mouth",
    "toothache": "Toothache",
    "noise_exposure": "Loud-noise exposure",
    "ototoxic_medication": "Ototoxic medication",
    "recent_trauma": "Recent head or ear trauma",
    "barotrauma": "Flying, diving or pressure change",
    "straining": "Straining or heavy lifting",
    "ear_blisters": "Blisters on the eardrum",
    "foreign_body": "Foreign body in the ear",
    "itching": "Itching in the ear",
    "diabetes": "Diabetes",
    "immunosuppression": "Immunosuppression",
    "swimming": "Swimming or water exposure",
    "hearing_aid_user": "Hearing aid user",
    "family_history": "Family history of hearing loss",
}

# --------------------------------------------------------------------------
# presenting complaints, ranked by age band (source document 1)
# --------------------------------------------------------------------------
#: Each entry: (condition, the complaint as the document phrases it, red flag)
COMPLAINTS: Dict[str, dict] = {
    "otorrhea": {
        "name": "Otorrhoea (ear discharge)",
        "prompts": ["ear_discharge"],
        "by_age": {
            "pediatric": [
                ("Acute otitis media with tympanic membrane perforation",
                 "Severe ear pain, often with fever.",
                 "the most common cause in children", False),
                ("Otitis externa (swimmer's ear)",
                 "Severe ear pain, especially when touching or pulling the ear.",
                 "", False),
                ("Chronic suppurative otitis media",
                 "Persistent ear discharge with hearing loss.", "", False),
                ("Foreign body in the ear with secondary infection",
                 "Ear discomfort with foul-smelling discharge.", "", False),
                ("Mastoiditis",
                 "Pain and swelling behind the ear with fever.",
                 "less common but important", True),
            ],
            "adult": [
                ("Otitis externa",
                 "Severe ear pain, especially when touching or pulling the ear.",
                 "", False),
                ("Chronic suppurative otitis media",
                 "Persistent ear discharge with hearing loss.", "", False),
                ("Acute otitis media with tympanic membrane perforation",
                 "Severe ear pain, often with fever.", "", False),
                ("Cholesteatoma",
                 "Persistent foul-smelling ear discharge with hearing loss.",
                 "", True),
                ("Traumatic tympanic membrane perforation",
                 "Sudden ear pain with hearing loss after injury.", "", False),
            ],
            "geriatric": [
                ("Otitis externa (especially in hearing aid users)",
                 "Severe ear pain, especially when touching or pulling the ear.",
                 "", False),
                ("Malignant (necrotizing) otitis externa",
                 "Severe deep ear pain with persistent discharge.",
                 "particularly in older adults with diabetes or immunosuppression",
                 True),
                ("Chronic suppurative otitis media",
                 "Persistent ear discharge with hearing loss.", "", False),
                ("Cholesteatoma",
                 "Persistent foul-smelling ear discharge with hearing loss.",
                 "", True),
                ("Squamous cell carcinoma of the external auditory canal",
                 "Persistent bloody ear discharge.",
                 "rare but should be considered with persistent or bloody discharge",
                 True),
            ],
        },
    },
    "otalgia": {
        "name": "Otalgia (ear pain)",
        "prompts": ["ear_pain", "severe_ear_pain"],
        "by_age": {
            "pediatric": [
                ("Acute otitis media", "Severe ear pain, often with fever.",
                 "the most common cause", False),
                ("Otitis externa",
                 "Severe ear pain, especially when touching or pulling the ear.",
                 "", False),
                ("Eustachian tube dysfunction", "Feeling of blocked ear with pain.",
                 "", False),
                ("Foreign body in the ear",
                 "Ear discomfort with foul-smelling discharge.", "", False),
                ("Mastoiditis", "Pain and swelling behind the ear with fever.",
                 "", True),
            ],
            "adult": [
                ("Otitis externa",
                 "Severe ear pain, especially when touching or pulling the ear.",
                 "", False),
                ("Acute otitis media", "Severe ear pain, often with fever.", "", False),
                ("Temporomandibular disorder",
                 "Ear pain while chewing or opening the mouth.",
                 "a common cause of referred ear pain", False),
                ("Dental infection", "Toothache with pain radiating to the ear.",
                 "another frequent source of referred otalgia", False),
                ("Eustachian tube dysfunction", "Feeling of blocked ear with pain.",
                 "", False),
            ],
            "geriatric": [
                ("Otitis externa",
                 "Severe ear pain, especially when touching or pulling the ear.",
                 "", False),
                ("Malignant (necrotizing) otitis externa",
                 "Severe deep ear pain with persistent discharge.",
                 "especially in older adults with diabetes or immunosuppression",
                 True),
                ("Temporomandibular disorder",
                 "Ear pain while chewing or opening the mouth.", "", False),
                ("Head and neck squamous cell carcinoma",
                 "Persistent one-sided ear pain.",
                 "an important consideration in persistent unilateral otalgia "
                 "with a normal ear examination", True),
                ("Dental disease", "Tooth pain felt as ear pain.", "", False),
            ],
        },
    },
    "vertigo": {
        "name": "Vertigo",
        "prompts": ["vertigo", "positional_vertigo", "imbalance"],
        "by_age": {
            "pediatric": [
                ("Vestibular migraine",
                 "Recurrent spinning sensation with headache.",
                 "one of the most common causes in children", False),
                ("Vestibular neuritis", "Sudden severe spinning sensation.", "", False),
                ("Benign paroxysmal vertigo of childhood",
                 "Brief episodes of spinning sensation.", "", False),
                ("Otitis media with labyrinthine involvement",
                 "Ear infection with dizziness.", "", False),
                ("Labyrinthitis", "Vertigo with hearing loss.", "", False),
            ],
            "adult": [
                ("Benign paroxysmal positional vertigo (BPPV)",
                 "Brief dizziness when turning the head.",
                 "the most common cause", False),
                ("Vestibular neuritis", "Sudden severe spinning sensation.", "", False),
                ("Meniere disease", "Recurrent vertigo with ringing in the ear.",
                 "", False),
                ("Vestibular migraine",
                 "Recurrent spinning sensation with headache.", "", False),
                ("Labyrinthitis", "Vertigo with hearing loss.", "", False),
            ],
            "geriatric": [
                ("Benign paroxysmal positional vertigo (BPPV)",
                 "Brief dizziness when turning the head.",
                 "by far the most common", False),
                ("Cerebellar stroke", "Sudden severe vertigo with imbalance.",
                 "an important central cause that must not be missed", True),
                ("Meniere disease", "Recurrent vertigo with ringing in the ear.",
                 "", False),
                ("Vestibular neuritis", "Sudden severe spinning sensation.", "", False),
                ("Medication-induced vertigo",
                 "Dizziness after starting medication.",
                 "for example antihypertensives, sedatives, aminoglycosides", False),
            ],
        },
    },
    "headache": {
        "name": "Headache (otological causes only)",
        "prompts": ["headache"],
        "by_age": {
            "pediatric": [
                ("Acute otitis media", "Severe ear pain, often with fever.", "", False),
                ("Mastoiditis", "Pain and swelling behind the ear with fever.",
                 "", True),
                ("Labyrinthitis", "Vertigo with hearing loss.", "", False),
                ("Chronic suppurative otitis media",
                 "Persistent ear discharge with hearing loss.", "", False),
                ("Otitis externa",
                 "Severe ear pain, especially when touching or pulling the ear.",
                 "", False),
            ],
            "adult": [
                ("Otitis externa",
                 "Severe ear pain, especially when touching or pulling the ear.",
                 "", False),
                ("Labyrinthitis", "Vertigo with hearing loss.", "", False),
                ("Meniere disease", "Recurrent vertigo with ringing in the ear.",
                 "", False),
                ("Cholesteatoma",
                 "Persistent foul-smelling ear discharge with hearing loss.",
                 "", True),
                ("Vestibular schwannoma",
                 "Gradually worsening hearing loss with imbalance.", "", True),
            ],
            "geriatric": [
                ("Malignant (necrotizing) otitis externa",
                 "Severe deep ear pain with persistent discharge.", "", True),
                ("Vestibular schwannoma",
                 "Gradually worsening hearing loss with imbalance.", "", True),
                ("Cholesteatoma",
                 "Persistent foul-smelling ear discharge with hearing loss.",
                 "", True),
                ("Labyrinthitis", "Vertigo with hearing loss.", "", False),
                ("Mastoiditis", "Pain and swelling behind the ear with fever.",
                 "", True),
            ],
        },
    },
}

# --------------------------------------------------------------------------
# disease reference (source document 2)
# --------------------------------------------------------------------------
#: ``symptoms`` maps a canonical symptom to how strongly it argues FOR this
#: disease (0-3). ``age_bands`` is the "most prone age group" column.
#: ``tests`` is reproduced from the "audiological tests" column, in order.
DISEASES: Dict[str, dict] = {
    "bacterial_meningitis": {
        "name": "Bacterial meningitis",
        "category": "emergency",
        "symptoms": {"fever": 3, "headache": 3, "stiff_neck": 3, "vomiting": 2,
                     "photophobia": 2, "drowsiness": 3, "seizures": 3,
                     "hearing_loss": 1, "sudden_hearing_loss": 2},
        "requires_any": ["stiff_neck", "drowsiness", "seizures", "photophobia"],
        "age_bands": ["pediatric", "geriatric"],
        "age_note": "Infants under 1 year highest risk; 1-5 years increased; 65+.",
        "tests": ["Pure-tone audiometry once stable",
                  "Otoacoustic emissions",
                  "Auditory brainstem response (ABR/BERA)"],
        "audiology_note": (
            "Meningitis is the leading acquired cause of profound childhood "
            "deafness, and the cochlea can ossify within weeks. Hearing must be "
            "tested urgently after recovery, not at a routine follow-up."),
        "expected_pta": (65, 120),
        "laterality": "bilateral",
        "expected_type": "sensorineural",
        "expected_pattern": "Bilateral severe-to-profound sensorineural loss",
        "red_flag": "Medical emergency — treat first, test hearing after recovery.",
    },
    "sensory_presbycusis": {
        "name": "Sensory presbycusis (age-related hearing loss)",
        "category": "chronic",
        "symptoms": {"gradual_hearing_loss": 3, "hearing_loss": 2,
                     "speech_in_noise_difficulty": 3, "asks_repetition": 2,
                     "tinnitus": 2, "poor_speech_discrimination": 1},
        "requires_any": [],
        "age_bands": ["geriatric"],
        "age_note": "65 years and older.",
        "tests": ["Pure-tone audiometry",
                  "Speech audiometry (SRT and word recognition)",
                  "Otoacoustic emissions",
                  "Auditory brainstem response if retrocochlear pathology is suspected",
                  "Immittance audiometry with acoustic reflexes",
                  "High-frequency audiometry"],
        "audiology_note": (
            "Symmetrical and gradual. Marked asymmetry is not presbycusis and "
            "needs investigating."),
        "expected_pta": (20, 65),
        "laterality": "bilateral",
        "expected_type": "sensorineural",
        "expected_pattern": "Bilateral symmetrical high-frequency sensorineural loss",
        "red_flag": "",
    },
    "capd": {
        "name": "Central auditory processing disorder (CAPD)",
        "category": "central",
        "symptoms": {"speech_in_noise_difficulty": 3, "asks_repetition": 2,
                     "difficulty_following_instructions": 3,
                     "poor_speech_discrimination": 3, "hearing_loss": -1},
        "requires_any": [],
        "age_bands": ["pediatric", "adult"],
        "age_note": "Most often diagnosed in school-aged children (7-17); in "
                    "adults after brain injury, stroke or neurological disorder.",
        "tests": ["Dichotic listening tests",
                  "Temporal processing tests (gap detection, frequency pattern)",
                  "Speech-in-noise tests",
                  "Auditory brainstem response (ABR/BERA)",
                  "Otoacoustic emissions and pure-tone audiometry to rule out "
                  "peripheral hearing loss"],
        "audiology_note": (
            "The audiogram is normal by definition. A normal audiogram is "
            "therefore not a reason to stop testing when the complaint is "
            "understanding rather than hearing."),
        "expected_pta": (0, 20),
        "laterality": "bilateral",
        "expected_type": "normal",
        "expected_pattern": "Normal pure-tone thresholds with disproportionate "
                            "difficulty in noise",
        "red_flag": "",
    },
    "ansd": {
        "name": "Auditory neuropathy spectrum disorder (ANSD)",
        "category": "neural",
        "symptoms": {"poor_speech_discrimination": 3,
                     "inconsistent_response_to_sound": 3,
                     "speech_in_noise_difficulty": 2, "delayed_speech": 3,
                     "hearing_loss": 1},
        "requires_any": [],
        "age_bands": ["pediatric", "adult"],
        "age_note": "Commonly identified in newborns and infants (0-5); less "
                    "common in adults, where it follows neurological disease.",
        "tests": ["Auditory brainstem response (ABR/BERA) - typically absent or abnormal",
                  "Otoacoustic emissions - often present initially",
                  "Cochlear microphonic testing",
                  "Pure-tone audiometry for older or cooperative patients",
                  "Speech perception testing",
                  "Immittance audiometry with acoustic reflexes"],
        "audiology_note": (
            "Emissions present with absent reflexes and speech far worse than "
            "the thresholds predict. Conventional amplification often "
            "disappoints — establish the diagnosis before fitting."),
        "expected_pta": (0, 120),
        "laterality": "either",
        "expected_type": "any",
        "expected_pattern": "Present OAEs, absent or grossly abnormal ABR",
        "red_flag": "",
    },
    "perilymphatic_fistula": {
        "name": "Perilymphatic fistula",
        "category": "acute",
        "symptoms": {"vertigo": 3, "hearing_loss": 2, "tinnitus": 2,
                     "aural_fullness": 2, "recent_trauma": 3, "barotrauma": 3,
                     "straining": 3, "sudden_hearing_loss": 2},
        "requires_any": ["recent_trauma", "barotrauma", "straining", "vertigo"],
        "age_bands": ["pediatric", "adult", "geriatric"],
        "age_note": "Any age; most often after trauma, barotrauma or a sudden "
                    "pressure change.",
        "tests": ["Pure-tone audiometry",
                  "Speech audiometry",
                  "Tympanometry",
                  "Vestibular evoked myogenic potentials (VEMP)",
                  "Electrocochleography (ECochG)",
                  "Fistula test"],
        "audiology_note": (
            "The link to straining or pressure change is the diagnosis. Ask "
            "about it explicitly — patients rarely volunteer it."),
        "expected_pta": (20, 80),
        "laterality": "unilateral",
        "expected_type": "sensorineural",
        "expected_pattern": "Fluctuating sensorineural loss with vestibular symptoms",
        "red_flag": "Sudden sensorineural loss after trauma is time-critical — "
                    "refer the same day.",
    },
    "ototoxicity": {
        "name": "Ototoxicity",
        "category": "acquired",
        "symptoms": {"ototoxic_medication": 3, "hearing_loss": 2, "tinnitus": 3,
                     "speech_in_noise_difficulty": 1, "vertigo": 1,
                     "imbalance": 2, "gradual_hearing_loss": 1},
        "requires_any": ["ototoxic_medication"],
        "age_bands": ["pediatric", "adult", "geriatric"],
        "age_note": "Any age; higher risk in children on chemotherapy or certain "
                    "antibiotics, and in older adults on multiple medications.",
        "tests": ["Pure-tone audiometry to monitor sensitivity",
                  "High-frequency audiometry to detect early change",
                  "Otoacoustic emissions for outer hair cell damage",
                  "Auditory brainstem response",
                  "Speech audiometry",
                  "Tympanometry to rule out middle ear involvement",
                  "Vestibular function tests if balance symptoms are present"],
        "audiology_note": (
            "Monitoring is the whole point: high-frequency audiometry and OAEs "
            "change before the conversational frequencies do, which is the "
            "window in which the drug regimen can still be altered."),
        "expected_pta": (20, 80),
        "laterality": "bilateral",
        "expected_type": "sensorineural",
        "expected_pattern": "Bilateral symmetrical high-frequency sensorineural loss, "
                            "progressing downward",
        "red_flag": "",
    },
    "menieres": {
        "name": "Meniere's disease",
        "category": "chronic",
        "symptoms": {"vertigo": 3, "fluctuating_hearing_loss": 3, "tinnitus": 3,
                     "aural_fullness": 3, "hearing_loss": 1},
        "requires_any": ["vertigo", "fluctuating_hearing_loss"],
        "age_bands": ["adult", "geriatric"],
        "age_note": "Most commonly 40-60 years; less common but possible in 65+.",
        "tests": ["Pure-tone audiometry (fluctuating sensorineural loss)",
                  "Speech audiometry",
                  "Tympanometry",
                  "Electrocochleography (ECochG) for endolymphatic hydrops",
                  "Otoacoustic emissions",
                  "Vestibular evoked myogenic potentials (VEMP)",
                  "Videonystagmography / electronystagmography"],
        "audiology_note": (
            "The classic tetrad is vertigo, fluctuating hearing loss, tinnitus "
            "and aural fullness, usually in one ear. A single audiogram cannot "
            "establish it — serial testing during and between attacks can."),
        "expected_pta": (20, 65),
        "laterality": "unilateral",
        "expected_type": "sensorineural",
        "expected_pattern": "Unilateral fluctuating low-frequency sensorineural loss",
        "red_flag": "",
    },
    "nihl": {
        "name": "Noise-induced hearing loss",
        "category": "preventable",
        "symptoms": {"noise_exposure": 3, "gradual_hearing_loss": 2,
                     "speech_in_noise_difficulty": 3, "tinnitus": 3,
                     "muffled_hearing": 2, "hearing_loss": 1},
        "requires_any": ["noise_exposure"],
        "age_bands": ["adult", "pediatric", "geriatric"],
        "age_note": "Most often working-age adults through occupational or "
                    "recreational exposure; also children through loud music "
                    "and gaming devices.",
        "tests": ["Pure-tone audiometry (3-6 kHz notch)",
                  "Speech audiometry",
                  "Otoacoustic emissions for outer hair cell damage",
                  "High-frequency audiometry",
                  "Auditory brainstem response",
                  "Tympanometry to rule out middle ear involvement"],
        "audiology_note": (
            "The only entirely preventable cause on this list. Absent emissions "
            "with a still-normal audiogram means damage has started and the "
            "remaining hearing can still be protected."),
        "expected_pta": (0, 50),
        "laterality": "bilateral",
        "expected_type": "sensorineural",
        "expected_pattern": "Bilateral notch at 3-6 kHz with recovery at 8 kHz",
        "red_flag": "",
    },
    "glomus_tumor": {
        "name": "Glomus tumour (paraganglioma of the middle ear)",
        "category": "neoplasm",
        "symptoms": {"pulsatile_tinnitus": 3, "hearing_loss": 2,
                     "aural_fullness": 2, "imbalance": 1, "vertigo": 1,
                     "bloody_discharge": 2},
        "requires_any": ["pulsatile_tinnitus"],
        "age_bands": ["adult", "geriatric"],
        "age_note": "Most commonly 40-70 years; occurrence rises with age.",
        "tests": ["Pure-tone audiometry (conductive or mixed loss)",
                  "Speech audiometry",
                  "Tympanometry (may show a pulsatile mass effect)",
                  "Acoustic reflex testing",
                  "Otoacoustic emissions",
                  "Auditory brainstem response if needed",
                  "Vestibular tests if balance symptoms are present"],
        "audiology_note": (
            "Pulsatile tinnitus with a red retrotympanic mass is a glomus "
            "tumour until imaging says otherwise. Do not biopsy it in clinic."),
        "expected_pta": (20, 60),
        "laterality": "unilateral",
        "expected_type": "conductive",
        "expected_pattern": "Unilateral conductive or mixed loss",
        "red_flag": "Pulsatile tinnitus needs imaging, not reassurance.",
    },
    "etd": {
        "name": "Eustachian tube dysfunction",
        "category": "common",
        "symptoms": {"aural_fullness": 3, "muffled_hearing": 3, "ear_pain": 2,
                     "popping": 3, "hearing_loss": 1, "barotrauma": 2},
        "requires_any": [],
        "age_bands": ["pediatric", "adult", "geriatric"],
        "age_note": "Most common in children, whose tubes are shorter and more "
                    "horizontal; in adults with allergies, infection or pressure change.",
        "tests": ["Pure-tone audiometry",
                  "Tympanometry for middle-ear pressure and tube function",
                  "Acoustic reflex testing",
                  "Speech audiometry",
                  "Otoacoustic emissions to rule out inner ear involvement",
                  "Eustachian tube function tests"],
        "audiology_note": (
            "Expect a Type C tympanogram. This is the step before an effusion "
            "and, if a retraction pocket forms, before cholesteatoma."),
        "expected_pta": (0, 35),
        "laterality": "either",
        "expected_type": "conductive",
        "expected_pattern": "Normal to mild conductive loss; Type C tympanogram",
        "red_flag": "",
    },
    "cholesteatoma": {
        "name": "Cholesteatoma",
        "category": "unsafe",
        "symptoms": {"foul_smelling_discharge": 3, "ear_discharge": 2,
                     "hearing_loss": 2, "aural_fullness": 1, "ear_pain": 1,
                     "tinnitus": 1, "facial_weakness": 2, "vertigo": 1},
        "requires_any": ["ear_discharge", "foul_smelling_discharge", "hearing_loss"],
        "age_bands": ["pediatric", "adult", "geriatric"],
        "age_note": "Common in children through Eustachian tube dysfunction and "
                    "recurrent infection; in adults through chronic ear disease.",
        "tests": ["Pure-tone audiometry (conductive or mixed loss)",
                  "Speech audiometry",
                  "Tympanometry for membrane mobility",
                  "Acoustic reflex testing",
                  "Otoacoustic emissions",
                  "Auditory brainstem response if neural involvement is suspected",
                  "CT temporal bone (imaging, not an audiological test)"],
        "audiology_note": (
            "Foul-smelling discharge with hearing loss is cholesteatoma until "
            "excluded. It erodes bone; hearing loss is the least of it."),
        "expected_pta": (20, 60),
        "laterality": "unilateral",
        "expected_type": "conductive",
        "expected_pattern": "Progressive conductive then mixed loss, usually unilateral",
        "red_flag": "Erodes ossicles and can cause facial palsy, labyrinthine "
                    "fistula and intracranial sepsis. Refer.",
    },
    "mastoiditis": {
        "name": "Mastoiditis",
        "category": "emergency",
        "symptoms": {"postauricular_swelling": 3, "fever": 3, "ear_pain": 3,
                     "ear_discharge": 2, "hearing_loss": 2, "headache": 1},
        # Fever accompanies most ear infections; swelling behind the ear is
        # what makes this mastoiditis rather than any of them.
        "requires_any": ["postauricular_swelling"],
        "age_bands": ["pediatric", "adult", "geriatric"],
        "age_note": "Most common in children, especially under 2 years, after "
                    "frequent middle-ear infection.",
        "tests": ["Pure-tone audiometry",
                  "Speech audiometry",
                  "Tympanometry",
                  "Acoustic reflex testing",
                  "Otoacoustic emissions",
                  "Auditory brainstem response if pathway involvement is suspected",
                  "CT temporal bone (imaging, not an audiological test)"],
        "audiology_note": (
            "Do not delay treatment for audiometry. Test hearing once the "
            "infection is controlled."),
        "expected_pta": (20, 55),
        "laterality": "unilateral",
        "expected_type": "conductive",
        "expected_pattern": "Conductive or mixed loss on the affected side",
        "red_flag": "Swelling behind the ear with fever is a surgical emergency.",
    },
    "bullous_myringitis": {
        "name": "Bullous myringitis",
        "category": "acute",
        "symptoms": {"severe_ear_pain": 3, "ear_pain": 2, "hearing_loss": 2,
                     "ear_blisters": 3, "ear_discharge": 1, "tinnitus": 1},
        # Blisters on the drum are what make this bullous myringitis rather
        # than any other painful ear. Without them it should not outrank
        # conditions that explain the whole picture.
        "requires_any": ["ear_blisters"],
        "age_bands": ["pediatric", "adult", "geriatric"],
        "age_note": "Most common in children after frequent middle-ear infection.",
        "tests": ["Pure-tone audiometry",
                  "Speech audiometry",
                  "Tympanometry",
                  "Acoustic reflex testing",
                  "Otoacoustic emissions if required",
                  "Otoscopy / video otoscopy to visualise the bullae"],
        "audiology_note": (
            "Pain out of proportion to the findings, with blisters on the drum. "
            "This is the one condition on the list where otoscopy alone is "
            "close to diagnostic."),
        "expected_pta": (20, 45),
        "laterality": "unilateral",
        "expected_type": "conductive",
        "expected_pattern": "Mild conductive loss on the affected side",
        "red_flag": "",
    },
    "pagets": {
        "name": "Paget's disease of bone (otic involvement)",
        "category": "chronic",
        "symptoms": {"gradual_hearing_loss": 3, "hearing_loss": 2, "tinnitus": 2,
                     "vertigo": 1, "imbalance": 2, "facial_weakness": 2},
        "requires_any": [],
        "age_bands": ["adult", "geriatric"],
        "age_note": "Risk rises through 40-64 years; most common in 65+.",
        "tests": ["Pure-tone audiometry (sensorineural or mixed loss)",
                  "Speech audiometry",
                  "Tympanometry",
                  "Acoustic reflex testing",
                  "Otoacoustic emissions",
                  "Auditory brainstem response",
                  "Vestibular tests if balance symptoms are present"],
        "audiology_note": (
            "Rare, and easily filed as presbycusis. The mixed component and "
            "the systemic bone disease are what separate them."),
        "expected_pta": (35, 80),
        "laterality": "bilateral",
        "expected_type": "mixed",
        "expected_pattern": "Progressive mixed loss, often with a low-frequency "
                            "conductive component",
        "red_flag": "",
    },
}

# --------------------------------------------------------------------------
# joining the two documents
# --------------------------------------------------------------------------
#: The complaint guide and the disease reference name some of the same
#: conditions in slightly different words. Mapping them lets a condition be
#: supported by both sources at once — and lets the engine say so.
GUIDE_TO_DISEASE: Dict[str, str] = {
    "cholesteatoma": "cholesteatoma",
    "mastoiditis": "mastoiditis",
    "meniere disease": "menieres",
    "eustachian tube dysfunction": "etd",
}

#: Conditions that appear only in the complaint guide. The guide gives their
#: rank and presenting complaint but not a test list, so a sensible default
#: battery is attached — every one of them is assessed the same way.
GUIDE_ONLY_TESTS: List[str] = [
    "Otoscopy / video otoscopy",
    "Pure-tone audiometry",
    "Tympanometry",
    "Speech audiometry",
]

#: Order in which tests are actually run in an audiology clinic. Used only to
#: break ties, so the recommended battery reads as a sequence rather than an
#: alphabetical list.
TEST_PRIORITY: List[str] = [
    "Otoscopy / video otoscopy",
    "Pure-tone audiometry",
    "High-frequency audiometry",
    "Speech audiometry",
    "Tympanometry",
    "Acoustic reflex testing",
    "Immittance audiometry with acoustic reflexes",
    "Otoacoustic emissions",
    "Auditory brainstem response (ABR/BERA)",
    "Speech-in-noise tests",
    "Dichotic listening tests",
    "Temporal processing tests",
    "Electrocochleography (ECochG)",
    "Vestibular evoked myogenic potentials (VEMP)",
    "Videonystagmography / electronystagmography",
    "Vestibular function tests",
    "Fistula test",
    "Eustachian tube function tests",
    "Cochlear microphonic testing",
    "CT temporal bone",
]


# --------------------------------------------------------------------------
# what the ear LOOKS like, tied to what the patient SAYS
# --------------------------------------------------------------------------
#: For each otoscopic pattern: the symptoms it should produce, the symptoms it
#: cannot account for, and the conditions it points at by name.
#:
#: This is what makes an image worth taking. A photograph on its own is a
#: photograph; a photograph that predicts "this patient should be reporting
#: discharge and hearing loss" can be checked against what they actually said,
#: and a mismatch is a finding rather than a rounding error.
OTOSCOPY_LINKS: Dict[str, dict] = {
    "normal": {
        "expects": [],
        # Hearing loss is deliberately absent from this list: a normal drum is
        # exactly what a sensorineural loss looks like. Pain and fever are on
        # it, because although both can be referred from the jaw or teeth,
        # that is a finding to raise rather than to pass over.
        "unexplained": ["ear_discharge", "foul_smelling_discharge", "bloody_discharge",
                        "severe_ear_pain", "ear_pain", "fever",
                        "postauricular_swelling"],
        "conditions": [],
        "note": ("A normal drum does not explain discharge, pain, fever or "
                 "swelling behind the ear. Re-examine the canal, which the "
                 "view may not have cleared, and consider referred otalgia "
                 "from the jaw joint or the teeth."),
    },
    "cerumen_impaction": {
        "expects": ["muffled_hearing", "aural_fullness", "hearing_loss", "itching"],
        "unexplained": ["foul_smelling_discharge", "vertigo", "facial_weakness",
                        "postauricular_swelling"],
        "conditions": ["Cerumen impaction"],
        "note": ("Wax explains a blocked, muffled ear. It does not explain "
                 "vertigo, facial weakness or offensive discharge — those need "
                 "another cause, and the drum must be seen after removal."),
    },
    "otitis_media": {
        "expects": ["ear_pain", "severe_ear_pain", "fever", "hearing_loss",
                    "muffled_hearing", "aural_fullness", "ear_discharge"],
        "unexplained": ["pulsatile_tinnitus", "bloody_discharge"],
        "conditions": ["Acute otitis media",
                       "Acute otitis media with tympanic membrane perforation",
                       "mastoiditis", "etd"],
        "note": ("Pain with fever and a red bulging drum is the classic "
                 "picture. Add swelling behind the ear and it is mastoiditis "
                 "until proven otherwise."),
    },
    "retraction": {
        "expects": ["aural_fullness", "popping", "muffled_hearing", "barotrauma",
                    "hearing_loss", "ear_pain"],
        "unexplained": ["ear_discharge", "fever", "bloody_discharge"],
        "conditions": ["etd", "Eustachian tube dysfunction"],
        "note": ("Retraction is Eustachian tube dysfunction made visible. It "
                 "precedes effusion and, if a pocket deepens, cholesteatoma."),
    },
    "perforation_central": {
        "expects": ["ear_discharge", "hearing_loss", "recent_trauma",
                    "muffled_hearing", "tinnitus"],
        "unexplained": ["foul_smelling_discharge", "facial_weakness", "vertigo"],
        "conditions": ["Chronic suppurative otitis media",
                       "Traumatic tympanic membrane perforation"],
        "note": ("The safe perforation: discharge and hearing loss, but no bone "
                 "erosion. Offensive discharge would argue for cholesteatoma "
                 "instead."),
    },
    "perforation_marginal": {
        "expects": ["ear_discharge", "foul_smelling_discharge", "hearing_loss"],
        "unexplained": [],
        "conditions": ["cholesteatoma", "Chronic suppurative otitis media"],
        "note": ("No annular rim means canal skin can migrate into the middle "
                 "ear. Treat as unsafe whatever the symptoms are."),
    },
    "perforation_attic": {
        "expects": ["foul_smelling_discharge", "ear_discharge", "hearing_loss",
                    "facial_weakness", "vertigo"],
        "unexplained": [],
        "conditions": ["cholesteatoma"],
        "note": ("Attic disease can be entirely silent — normal hearing and no "
                 "discharge do NOT reassure here, which is exactly why it gets "
                 "missed."),
    },
    "tumor": {
        "expects": ["pulsatile_tinnitus", "hearing_loss", "aural_fullness",
                    "bloody_discharge", "imbalance"],
        "unexplained": [],
        "conditions": ["glomus_tumor",
                       "Squamous cell carcinoma of the external auditory canal"],
        "note": ("Pulsatile tinnitus with a retrotympanic mass is a glomus "
                 "tumour until imaging says otherwise. Do not biopsy in clinic."),
    },
}

# --------------------------------------------------------------------------
# what the ear looks like, tied to every disease
# --------------------------------------------------------------------------
#: Otoscopic pattern -> how strongly it argues for each disease (0-3), the
#: diseases it argues against, and the named conditions that sit outside the
#: fourteen-disease reference.
#:
#: This is the link that works with nothing else recorded. A photograph alone
#: produces a ranked differential here, before any history is taken and before
#: a single threshold is measured — which is the order a clinic actually works
#: in, since the scope goes in the ear before the patient is in the booth.
OTOSCOPY_DISEASE_LINKS: Dict[str, dict] = {
    "normal": {
        "supports": {"sensory_presbycusis": 2, "nihl": 2, "menieres": 2,
                     "ototoxicity": 2, "capd": 2, "ansd": 2,
                     "bacterial_meningitis": 1, "pagets": 1},
        "excludes": ["cholesteatoma", "mastoiditis", "bullous_myringitis"],
        "other": [],
        "reasoning": ("An intact, normal-looking drum makes a middle-ear cause "
                      "unlikely, which is what promotes every cochlear and "
                      "neural diagnosis on the list."),
    },
    "cerumen_impaction": {
        "supports": {"etd": 1},
        "excludes": [],
        "other": ["Cerumen impaction", "Otitis externa"],
        "reasoning": ("Wax explains a conductive loss by itself and hides "
                      "everything behind it. Nothing else can be excluded until "
                      "the canal is cleared and the drum seen."),
    },
    "otitis_media": {
        "supports": {"mastoiditis": 3, "etd": 3, "bullous_myringitis": 2,
                     "cholesteatoma": 1},
        "excludes": ["sensory_presbycusis", "capd"],
        "other": ["Acute otitis media", "Otitis media with effusion",
                  "Acute otitis media with tympanic membrane perforation"],
        "reasoning": ("A red or bulging drum is active middle-ear disease. "
                      "Mastoiditis is the complication to exclude; Eustachian "
                      "tube dysfunction is the usual precursor."),
    },
    "retraction": {
        "supports": {"etd": 3, "cholesteatoma": 2},
        "excludes": ["capd"],
        "other": ["Otitis media with effusion", "Retraction pocket",
                  "Adhesive otitis media"],
        "reasoning": ("Retraction is Eustachian tube dysfunction made visible, "
                      "and a deepening pocket is how cholesteatoma begins."),
    },
    "perforation_central": {
        "supports": {"cholesteatoma": 1, "etd": 2, "mastoiditis": 1},
        "excludes": ["capd"],
        "other": ["Chronic suppurative otitis media",
                  "Traumatic tympanic membrane perforation"],
        "reasoning": ("The safe perforation: discharge and hearing loss without "
                      "bone erosion. Cholesteatoma stays on the list but ranks "
                      "below the tubotympanic causes."),
    },
    "perforation_marginal": {
        "supports": {"cholesteatoma": 3, "mastoiditis": 2, "etd": 1},
        "excludes": ["capd"],
        "other": ["Chronic suppurative otitis media, atticoantral type"],
        "reasoning": ("No annular rim means canal skin can migrate inward. "
                      "Unsafe whatever the symptoms are."),
    },
    "perforation_attic": {
        "supports": {"cholesteatoma": 3, "mastoiditis": 2, "pagets": 0},
        "excludes": ["capd", "sensory_presbycusis"],
        "other": ["Attic retraction pocket", "Keratosis obturans"],
        "reasoning": ("Attic disease is cholesteatoma until imaging says "
                      "otherwise, and it erodes ossicles while the audiogram "
                      "can still read normal."),
    },
    "tumor": {
        "supports": {"glomus_tumor": 3, "cholesteatoma": 1},
        "excludes": ["capd"],
        "other": ["Squamous cell carcinoma of the external auditory canal",
                  "Middle-ear polyp", "Vascular anomaly"],
        "reasoning": ("Any unilateral mass behind or replacing the drum is "
                      "imaged before it is touched — a glomus tumour bleeds."),
    },
}


# --------------------------------------------------------------------------
# what the middle ear MEASURES, tied to the diseases
# --------------------------------------------------------------------------
#: All eight tympanogram types from the immittance reference, each with the
#: conditions it supports and the ones it argues against. The "argues against"
#: column is the half usually left out, and it is often the more useful one: a
#: Type A tympanogram does not diagnose anything, but it removes most of the
#: conductive differential in one step.
TYMPANOGRAM_LINKS: Dict[str, dict] = {
    "A": {
        "label": "Type A — normal middle ear",
        "supports": ["sensory_presbycusis", "nihl", "menieres", "ototoxicity",
                     "capd", "ansd", "bacterial_meningitis"],
        "argues_against": ["etd", "cholesteatoma", "mastoiditis",
                           "bullous_myringitis"],
        "also_consider": ["Otosclerosis (a stiff ear can still read Type A early)"],
        "meaning": ("Normal pressure and mobility. Any loss present is unlikely "
                    "to be middle-ear, which redirects the workup to the cochlea "
                    "and the nerve."),
    },
    "As": {
        "label": "Type As — shallow / stiff",
        "supports": ["pagets", "cholesteatoma"],
        "argues_against": ["etd"],
        "also_consider": ["Otosclerosis (stapes fixation)", "Tympanosclerosis",
                          "Ossicular fixation"],
        "meaning": ("Reduced mobility with normal pressure. With a conductive "
                    "loss and absent reflexes this is the classic stapedial "
                    "fixation picture; otic Paget's disease produces the same "
                    "stiffening."),
    },
    "Ad": {
        "label": "Type Ad — deep / hypercompliant",
        "supports": ["perilymphatic_fistula"],
        "argues_against": ["etd", "mastoiditis"],
        "also_consider": ["Ossicular discontinuity", "Healed / monomeric membrane",
                          "Post-traumatic ossicular disruption"],
        "meaning": ("An unusually mobile system: a broken ossicular chain, or a "
                    "membrane thinned by previous perforation. Trauma is the "
                    "commonest history."),
    },
    "Add": {
        "label": "Type Add — extremely deep peak, off the instrument scale",
        "supports": ["perilymphatic_fistula"],
        "argues_against": ["etd", "mastoiditis", "capd"],
        "also_consider": ["Ossicular discontinuity",
                          "Post-traumatic ossicular chain disruption"],
        "meaning": ("Admittance beyond what the instrument can plot. Where Ad is "
                    "merely deep, Add is the disconnected ossicular chain — the "
                    "middle ear has nothing left to load the drum."),
    },
    "B": {
        "label": "Type B — flat, no measurable peak",
        "supports": ["mastoiditis", "bullous_myringitis", "cholesteatoma", "etd"],
        "argues_against": ["capd", "sensory_presbycusis"],
        "also_consider": ["Otitis media with effusion (normal canal volume)",
                          "Tympanic membrane perforation (large canal volume)",
                          "Patent ventilation tube (large canal volume)",
                          "Impacted cerumen or a blocked probe (small canal volume)",
                          "Chronic suppurative otitis media"],
        "meaning": ("No mobility at any pressure. The ear-canal volume splits "
                    "the differential three ways: normal volume is fluid behind "
                    "an intact drum, large volume means the probe is measuring "
                    "past it, and small volume is wax or a blocked probe — an "
                    "artefact rather than middle-ear disease."),
    },
    "C": {
        "label": "Type C — negative middle-ear pressure",
        "supports": ["etd", "cholesteatoma"],
        "argues_against": ["capd"],
        "also_consider": ["Resolving or developing otitis media with effusion",
                          "Retraction pocket", "Recent upper respiratory infection"],
        "meaning": ("The Eustachian tube is not ventilating. This is the step "
                    "before an effusion and, if a retraction pocket forms and "
                    "traps skin, the step before cholesteatoma."),
    },
    "D": {
        "label": "Type D — narrow notched peak",
        "supports": [],
        "argues_against": ["etd", "mastoiditis"],
        "also_consider": ["Hypermobile tympanic membrane",
                          "Scarred or monomeric membrane",
                          "Healed previous perforation"],
        "meaning": ("A notch on an otherwise normal-height peak. The membrane "
                    "itself is abnormally mobile — usually thinned or scarred by "
                    "a perforation that has since healed."),
    },
    "E": {
        "label": "Type E — wide notched peak",
        "supports": ["perilymphatic_fistula"],
        "argues_against": ["etd", "mastoiditis", "capd"],
        "also_consider": ["Ossicular disruption",
                          "Post-traumatic ossicular chain disruption"],
        "meaning": ("A broad notch with high admittance. Where Type D is a "
                    "floppy drum, Type E is a broken ossicular chain."),
    },
}


# --------------------------------------------------------------------------
# what each disease does to the AUDIOGRAM
# --------------------------------------------------------------------------
#: A characteristic audiogram per disease: air conduction at the six standard
#: frequencies, bone conduction where a gap is expected, and the shape in words.
#:
#: These are textbook configurations, not patient data, and they exist so the
#: audiogram can be matched against the disease list **on its own** — no
#: history required. Comparing a measured curve against each of these gives a
#: ranked differential from thresholds alone, and plotting the two together
#: shows a clinician immediately where the patient departs from the classic
#: picture.
DISEASE_AUDIOGRAM: Dict[str, dict] = {
    "bacterial_meningitis": {
        "shape": "Bilateral severe-to-profound, flat or slightly sloping",
        "ac": {250: 70, 500: 75, 1000: 80, 2000: 85, 4000: 90, 8000: 95},
        "bc": {250: 70, 500: 75, 1000: 80, 2000: 85, 4000: 90},
        "note": "Often profound and bilateral; the cochlea can ossify within weeks.",
    },
    "sensory_presbycusis": {
        "shape": "Bilateral symmetrical high-frequency sloping sensorineural",
        "ac": {250: 15, 500: 20, 1000: 25, 2000: 35, 4000: 50, 8000: 65},
        "bc": {250: 15, 500: 20, 1000: 25, 2000: 35, 4000: 50},
        "note": "Gradual and symmetrical. Marked asymmetry is not presbycusis.",
    },
    "capd": {
        "shape": "Normal pure tones at every frequency",
        "ac": {250: 10, 500: 10, 1000: 10, 2000: 10, 4000: 10, 8000: 15},
        "bc": {250: 10, 500: 10, 1000: 10, 2000: 10, 4000: 10},
        "note": "Normal by definition — the deficit is in processing, not detection.",
    },
    "ansd": {
        "shape": "Variable, often mild-to-moderate and flat or rising",
        "ac": {250: 40, 500: 40, 1000: 35, 2000: 35, 4000: 40, 8000: 45},
        "bc": {250: 40, 500: 40, 1000: 35, 2000: 35, 4000: 40},
        "note": ("Thresholds are the least informative part: emissions present "
                 "with absent ABR is the diagnosis, not the audiogram shape."),
    },
    "perilymphatic_fistula": {
        "shape": "Unilateral fluctuating sensorineural, often worse at high frequencies",
        "ac": {250: 30, 500: 35, 1000: 40, 2000: 45, 4000: 50, 8000: 55},
        "bc": {250: 30, 500: 35, 1000: 40, 2000: 45, 4000: 50},
        "note": "Fluctuates with pressure change; serial audiograms show more than one.",
    },
    "ototoxicity": {
        "shape": "Bilateral high-frequency sensorineural, progressing downward",
        "ac": {250: 10, 500: 10, 1000: 15, 2000: 30, 4000: 55, 8000: 75},
        "bc": {250: 10, 500: 10, 1000: 15, 2000: 30, 4000: 55},
        "note": ("The highest frequencies go first, which is why monitoring uses "
                 "high-frequency audiometry rather than the conversational range."),
    },
    "menieres": {
        "shape": "Unilateral low-frequency rising sensorineural (early)",
        "ac": {250: 45, 500: 40, 1000: 35, 2000: 25, 4000: 25, 8000: 30},
        "bc": {250: 45, 500: 40, 1000: 35, 2000: 25, 4000: 25},
        "note": ("The rising low-frequency shape is the classic early picture and "
                 "it fluctuates; later it flattens."),
    },
    "nihl": {
        "shape": "Bilateral notch at 3-6 kHz with recovery at 8 kHz",
        "ac": {250: 10, 500: 10, 1000: 15, 2000: 20, 4000: 50, 8000: 30},
        "bc": {250: 10, 500: 10, 1000: 15, 2000: 20, 4000: 50},
        "note": ("The recovery at 8 kHz is what makes it a notch rather than a "
                 "slope, and it is the single most recognisable audiogram shape."),
    },
    "glomus_tumor": {
        "shape": "Unilateral conductive or mixed loss",
        "ac": {250: 40, 500: 40, 1000: 40, 2000: 45, 4000: 45, 8000: 50},
        "bc": {250: 15, 500: 15, 1000: 15, 2000: 20, 4000: 20},
        "note": "Unilateral by nature; pulsatile tinnitus is the accompanying clue.",
    },
    "etd": {
        "shape": "Mild conductive loss, worst at low frequencies",
        "ac": {250: 30, 500: 30, 1000: 25, 2000: 20, 4000: 20, 8000: 25},
        "bc": {250: 5, 500: 5, 1000: 5, 2000: 5, 4000: 5},
        "note": "Often fluctuates with the state of the tube; rarely beyond 35 dB.",
    },
    "cholesteatoma": {
        "shape": "Progressive conductive, becoming mixed as ossicles erode",
        "ac": {250: 45, 500: 45, 1000: 50, 2000: 50, 4000: 55, 8000: 60},
        "bc": {250: 10, 500: 10, 1000: 15, 2000: 25, 4000: 30},
        "note": ("The bone line deteriorating over time is the sign that disease "
                 "has reached the inner ear."),
    },
    "mastoiditis": {
        "shape": "Unilateral conductive loss",
        "ac": {250: 40, 500: 40, 1000: 40, 2000: 35, 4000: 35, 8000: 40},
        "bc": {250: 5, 500: 5, 1000: 5, 2000: 10, 4000: 10},
        "note": "Test once the infection is controlled; do not delay treatment for it.",
    },
    "bullous_myringitis": {
        "shape": "Mild conductive loss on the affected side",
        "ac": {250: 30, 500: 30, 1000: 25, 2000: 25, 4000: 25, 8000: 30},
        "bc": {250: 5, 500: 5, 1000: 5, 2000: 5, 4000: 5},
        "note": "Resolves with the bullae; re-test rather than certifying this.",
    },
    "pagets": {
        "shape": "Mixed: low-frequency conductive component with high-frequency sensorineural",
        "ac": {250: 45, 500: 45, 1000: 50, 2000: 55, 4000: 60, 8000: 70},
        "bc": {250: 25, 500: 25, 1000: 35, 2000: 45, 4000: 55},
        "note": ("Easily filed as presbycusis; the conductive component and the "
                 "systemic bone disease are what separate them."),
    },
}

#: Reflex findings that change the differential regardless of the trace shape.
REFLEX_LINKS: Dict[str, dict] = {
    "absent_conductive": {
        "when": "reflexes absent with a conductive loss",
        "supports": ["cholesteatoma"],
        "also_consider": ["Otosclerosis", "Ossicular fixation or discontinuity"],
        "meaning": "Any middle-ear block large enough abolishes the reflex.",
    },
    "absent_with_emissions": {
        "when": "reflexes absent while emissions are present",
        "supports": ["ansd", "pagets"],
        "also_consider": ["Vestibular schwannoma", "Brainstem lesion"],
        "meaning": ("The cochlea works but the reflex arc does not — the lesion "
                    "lies beyond the cochlea."),
    },
    "present_with_severe_loss": {
        "when": "reflexes present despite a severe loss",
        "supports": [],
        "also_consider": ["Non-organic (exaggerated) hearing loss",
                          "Cochlear recruitment"],
        "meaning": ("Reflexes are normally absent once the loss exceeds about "
                    "60 dB HL. Their presence suggests the thresholds overstate "
                    "the true loss."),
    },
}


# --------------------------------------------------------------------------
# red flags — patterns that change the urgency, not just the differential
# --------------------------------------------------------------------------
#: (id, required symptoms (all), any-of symptoms, age bands or None, entry)
RED_FLAGS: List[dict] = [
    {
        "id": "meningitis",
        "all": ["fever"],
        "any": ["stiff_neck", "photophobia", "drowsiness", "seizures"],
        "ages": None,
        "level": "emergency",
        "title": "Possible bacterial meningitis",
        "detail": "Fever with neck stiffness, photophobia, drowsiness or seizures "
                  "is meningitis until proven otherwise.",
        "action": "Emergency medical assessment now. Audiology follows recovery — "
                  "and must not be forgotten, because the cochlea can ossify "
                  "within weeks.",
    },
    {
        "id": "cerebellar_stroke",
        "all": ["vertigo"],
        "any": ["imbalance"],
        "ages": ["geriatric"],
        "level": "emergency",
        "title": "Central cause of vertigo must be excluded",
        "detail": "Sudden severe vertigo with imbalance in an older adult may be "
                  "cerebellar stroke — the source guide names it as the central "
                  "cause that must not be missed.",
        "action": "Urgent neurological assessment before any vestibular workup.",
    },
    {
        "id": "sudden_snhl",
        "all": ["sudden_hearing_loss"],
        "any": [],
        "ages": None,
        "level": "emergency",
        "title": "Sudden sensorineural hearing loss is time-critical",
        "detail": "Treatment benefit falls sharply after the first few days.",
        "action": "Same-day ENT assessment. Do not book a routine appointment.",
    },
    {
        "id": "mastoiditis",
        "all": ["postauricular_swelling"],
        "any": ["fever", "ear_pain", "ear_discharge"],
        "ages": None,
        "level": "emergency",
        "title": "Possible mastoiditis",
        "detail": "Swelling, redness or tenderness behind the ear with fever or "
                  "discharge is a surgical emergency.",
        "action": "Immediate ENT referral. Do not delay for audiometry.",
    },
    {
        "id": "malignant_otitis_externa",
        "all": ["severe_ear_pain"],
        "any": ["diabetes", "immunosuppression"],
        "ages": ["geriatric", "adult"],
        "level": "urgent",
        "title": "Possible malignant (necrotizing) otitis externa",
        "detail": "Severe deep ear pain with discharge in a diabetic or "
                  "immunosuppressed patient is a skull-base infection, not "
                  "simple otitis externa.",
        "action": "Urgent ENT referral with imaging and inflammatory markers.",
    },
    {
        "id": "cholesteatoma",
        "all": ["foul_smelling_discharge"],
        "any": [],
        "ages": None,
        "level": "urgent",
        "title": "Foul-smelling discharge suggests cholesteatoma",
        "detail": "Persistent offensive discharge with hearing loss is "
                  "cholesteatoma until excluded.",
        "action": "ENT referral for examination under microscope and CT.",
    },
    {
        "id": "facial_palsy",
        "all": ["facial_weakness"],
        "any": ["ear_discharge", "ear_pain", "hearing_loss"],
        "ages": None,
        "level": "emergency",
        "title": "Facial weakness with ear disease",
        "detail": "Facial nerve involvement means the disease has left the "
                  "middle-ear cleft.",
        "action": "Emergency ENT referral.",
    },
    {
        "id": "pulsatile_tinnitus",
        "all": ["pulsatile_tinnitus"],
        "any": [],
        "ages": None,
        "level": "urgent",
        "title": "Pulsatile tinnitus needs imaging",
        "detail": "A vascular or neoplastic cause — glomus tumour, dural fistula, "
                  "stenosis — must be excluded.",
        "action": "ENT referral with dedicated imaging. Do not biopsy a "
                  "retrotympanic mass in clinic.",
    },
    {
        "id": "bloody_discharge_elderly",
        "all": ["bloody_discharge"],
        "any": [],
        "ages": ["geriatric"],
        "level": "urgent",
        "title": "Persistent bloody discharge in an older adult",
        "detail": "The source guide lists squamous cell carcinoma of the external "
                  "auditory canal as rare but to be considered here.",
        "action": "ENT referral for examination and biopsy.",
    },
    {
        "id": "unilateral_otalgia_normal_exam",
        "all": ["ear_pain"],
        "any": ["toothache", "pain_on_chewing"],
        "ages": ["geriatric"],
        "level": "watch",
        "title": "Referred otalgia with a normal ear",
        "detail": "Persistent one-sided ear pain with a normal examination raises "
                  "head and neck malignancy in this age group; dental and "
                  "temporomandibular causes are commoner and are checked first.",
        "action": "Examine the mouth, teeth and jaw joint. If the ear is normal "
                  "and the pain persists, refer.",
    },
    {
        "id": "asymmetric_progressive",
        "all": ["gradual_hearing_loss"],
        "any": ["imbalance", "tinnitus"],
        "ages": None,
        "level": "watch",
        "title": "Consider vestibular schwannoma if the loss is asymmetric",
        "detail": "Gradually worsening hearing with imbalance is the presentation "
                  "the source guide gives for vestibular schwannoma.",
        "action": "Compare the two ears. Asymmetry beyond 15 dB or a word-score "
                  "gap warrants MRI.",
    },
]
