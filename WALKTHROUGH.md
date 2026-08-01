# AudioSense AI — Complete Walkthrough

A full explanation of what this project is, how every part works, why each
design decision was made, and what has actually been measured.

**Scale:** ~12,300 lines of backend Python across 64 modules, ~8,700 lines of
frontend across 34 files, **561 automated tests**, 11 application pages,
25 test files.

---

## Table of contents

1. [The problem](#1-the-problem)
2. [What the system does end to end](#2-what-the-system-does-end-to-end)
3. [Architecture](#3-architecture)
4. [The clinical rules engine](#4-the-clinical-rules-engine)
5. [The safety layer](#5-the-safety-layer)
6. [The cross-modal test battery](#6-the-cross-modal-test-battery)
   - [6a. Tympanometry as an instrument](#6a-tympanometry-as-an-instrument)
   - [6b. The DP-gram](#6b-the-dp-gram)
   - [6c. Otoscopy — the picture, checked against the measurement](#6c-otoscopy--the-picture-checked-against-the-measurement)
   - [6d. Signs and symptoms](#6d-signs-and-symptoms)
   - [6e. Linkage — everything cross-checks everything](#6e-linkage--everything-cross-checks-everything)
   - [6f. A differential from any single input](#6f-a-differential-from-any-single-input)
7. [Machine learning](#7-machine-learning)
8. [Snap-to-Digitize](#8-snap-to-digitize-photo--audiogram)
9. [Functional impact: phonemes, SII, hearing age](#9-functional-impact)
10. [The Hearing Loss Simulator](#10-the-hearing-loss-simulator)
11. [The Listening Lab](#11-the-listening-lab)
12. [In-browser screening](#12-in-browser-screening)
13. [Reports and the AI layer](#13-reports-and-the-ai-layer)
14. [Triage and throughput](#14-triage-and-throughput)
15. [Validation and honesty](#15-validation-and-honesty)
16. [Clinic workflow](#16-clinic-workflow)
17. [Frontend design](#17-frontend-design)
18. [Testing strategy](#18-testing-strategy)
19. [How to run it](#19-how-to-run-it)
20. [Known limits](#20-known-limits)

---

## 1. The problem

Interpreting a pure-tone audiogram requires clinical expertise. Someone must
classify the pattern, determine degree and type, calculate a disability
percentage under statute, and write a report. It is slow, it depends on an
audiologist being available, and in high-volume settings the delay pushes back
diagnosis, hearing-aid fitting and rehabilitation.

India has roughly one audiologist per 500,000 people. A screening camp
generates hundreds of audiograms in a day. The bottleneck is not any single
interpretation — it is that two hundred of them arrive at once, all looking
alike in a folder, and the one that needed a doctor *this week* sits behind a
hundred routine screens.

That framing drove the whole design: **interpret accurately, then order the
queue, then prove the interpretation is trustworthy.**

---

## 2. What the system does end to end

```
Paper audiogram photo ──┐
Manual threshold entry ─┼──▶ Analysis ──▶ Verdict ──▶ Report ──▶ Referral / PDF / QR handout
In-browser screening ───┘        │
                                 ├──▶ Triage priority + auto-release decision
                                 ├──▶ Hearing simulation (hear the diagnosis)
                                 └──▶ Listening Lab (localization, speech-in-noise, tinnitus)
```

One `POST /api/analyze` returns, in about 670 ms:

- Pure-tone averages, WHO 2021 degree, conductive/sensorineural/mixed type
- RPwD Act 2016 disability percentage with every intermediate step
- ML pattern classification with calibrated confidence and OOD flagging
- Counterfactual explanations and nearest reference cases
- Phoneme audibility, Speech Intelligibility Index, hearing age
- Red-flag safety alerts, cross-modal battery reconciliation
- NAL-R hearing-aid prescription and aided-benefit projection
- Triage priority and an auto-release-vs-review decision
- A one-sentence verdict with the next action

---

## 3. Architecture

```
backend/  FastAPI + scikit-learn + OpenCV + reportlab
  app/clinical/   pure functions implementing published guidelines
  app/ml/         dataset generation, training, inference, deep ensemble
  app/services/   reports, vision, records, PDF, LLM providers, validation
  app/routers/    HTTP surface
frontend/ React 18 + Vite + Tailwind v4 + Recharts
  src/audio/      Web Audio engines (simulator, tones, spatial, tinnitus)
  src/pages/      eight pages
  src/components/ chart, cochlea map, verdict banner, tour, settings
```

**The central architectural decision: the deterministic clinical core is
strictly separated from the machine learning.**

Degree, type and disability are pure functions with guideline-cited
docstrings. They are not model outputs and cannot drift. The ML classifier
sits alongside them, handles only pattern recognition, and is permitted to
say "I don't know."

This separation is why validation splits cleanly: the rules are validated by
*conformance* (they either implement the guideline or they don't), the model
by *statistics*.

---

## 4. The clinical rules engine

`backend/app/clinical/rules.py` (227 lines)

### Pure-tone average
Mean of air-conduction thresholds at 500, 1000, 2000 and 4000 Hz, per the WHO
World Report on Hearing (2021). Untested frequencies are excluded and flagged;
"No Response" counts as 120 dB HL and is flagged wherever it propagates.

### Degree — WHO 2021
| Grade | PTA (dB HL) |
|---|---|
| Normal | < 20 |
| Mild | 20 – <35 |
| Moderate | 35 – <50 |
| Moderately severe | 50 – <65 |
| Severe | 65 – <80 |
| Profound | ≥ 80 |

Lower bound inclusive: exactly 20.0 grades as Mild. Pinned by tests.

### Type — air-bone gap
ABG = mean(AC − BC) over the four PTA frequencies.

- **Conductive:** ABG > 10 dB and BC PTA ≤ 20
- **Sensorineural:** ABG ≤ 10 dB and AC PTA > 20
- **Mixed:** ABG > 10 dB and BC PTA > 20
- **Normal:** otherwise

An ABG of *exactly* 10 dB is not significant — it must exceed 10. Pinned.

**Missing bone conduction is handled explicitly rather than guessed.** If BC
was not tested, the ear is classified from AC alone and flagged
`provisional` with the message *"type provisional — BC not tested."*

### Disability — India RPwD Act 2016
Per the Gazette notification of 4 January 2018:

```
monaural %  = 1.5 × (PTA − 25), clamped to [0, 100]
binaural %  = (5 × better-ear % + worse-ear %) / 6
benchmark   = ≥ 40%
```

Every intermediate value is returned as a formatted string so the UI can show
the working — a disability percentage that decides entitlement should never be
a black box.

---

## 5. The safety layer

`backend/app/clinical/safety.py` (250 lines)

Some audiograms are not a fitting problem but a medical emergency. Missing
those is the costliest mistake the system could make, so they outrank
everything else on the page.

**Sudden SNHL** — ≥30 dB across ≥3 contiguous frequencies within 72 hours.
Corticosteroids are effective but the window is days. With a prior audiogram
the drop is measured directly; without one the check uses reported onset and
returns a *conditional* flag stating exactly what would make it an emergency.

**Asymmetric loss** — ≥20 dB at one frequency or ≥15 dB at two. Warrants MRI
to exclude a vestibular schwannoma.

**Masking / shadow curve** — when the test-ear AC exceeds the *opposite* ear's
BC by the interaural attenuation of the transducer (40 dB for supra-aural
earphones), sound crosses the skull and the other cochlea may be responding.
A warning is raised only when masking was indicated *and* not recorded.

**Non-organic loss** — SRT substantially better than the pure-tone average
means the tones are exaggerated. This matters directly for disability
certification.

**Rollover** — word recognition that *falls* as level rises (rollover index
> 0.45) points to retrocochlear pathology.

Alerts sort strictly by urgency: emergency → urgent → validity → info. An
early bug where an informational prompt displaced the clinical next step was
found and fixed.

---

## 6. The cross-modal test battery

`immittance.py`, `oae.py`, `consistency.py`

Any single test misleads. Pure tones need a cooperative patient; tympanometry
says nothing about the cochlea; emissions say nothing about the nerve.
Diagnosis comes from whether the tests **agree**.

**Tympanometry** — Jerger types A / As / Ad / B / C, with Type B split by
ear-canal volume (normal volume = effusion, large = perforation).

**Acoustic reflexes** — present / absent / partial, ipsi and contra.

**Otoacoustic emissions** — present when the emission exceeds the noise floor
by ≥6 dB.

The consistency engine reconciles all of it and names the pattern:

| Pattern | Evidence |
|---|---|
| Effusion confirmed | conductive loss + Type B tympanogram |
| Otosclerosis | conductive + Type As + absent reflexes |
| **Pre-clinical NIHL** | **absent OAEs with normal thresholds** |
| Auditory neuropathy | OAEs present + reflexes absent + poor speech |
| Non-organic | objective tests better than the audiogram allows |

**The pre-clinical case is the most valuable thing this project does.** Outer
hair cells die before thresholds move. Absent emissions with a normal
audiogram is cochlear damage that has not yet reached the audiogram — the
point at which the remaining hearing can still be saved. The bundled
🔬 demo case is a 26-year-old welder with a completely normal audiogram whom
every conventional screening would send back to the shipyard.

### 6a. Tympanometry as an instrument

`tympanometry.py`, `/api/tympanometry/analyze`

The classification follows the immittance reference supplied by the clinical
team (Gelfand, *Essentials of Audiology*, 4th ed., pp. 187–192), which is more
complete than the five-type Jerger scheme in two ways that change answers.

### Eight types, not five

| Type | Peak pressure | Static admittance (adult) | Shape | Disorders |
|---|---|---|---|---|
| A | +50 to −100 daPa | 0.37–1.66 mmho | Normal peak | Normal function |
| As | +50 to −100 | < 0.37 | Shallow peak | Otosclerosis, tympanosclerosis, stiff drum |
| Ad | +50 to −100 | > 1.66 | Deep peak | Flaccid drum, ossicular discontinuity |
| **Add** | +50 to −100 | Off-scale | Extremely deep peak | Ossicular discontinuity |
| B | No measurable peak | ~0–0.2 | Flat | Effusion, cholesteatoma, cerumen, perforation |
| C | < −100 | 0.37–1.66 | Negative pressure | Eustachian tube dysfunction |
| **D** | +50 to −100 | usually 0.37–1.66 | Narrow notched peak | Hypermobile / scarred drum |
| **E** | +50 to −100 | usually > 1.66 | Wide notched peak | Ossicular disruption |

Children carry their own bands: admittance 0.35–1.25 mmho, canal volume
0.3–1.0 ml against 0.6–2.0 in adults. The same 0.36 mmho peak is Type As in an
adult and Type A in a child, and 1.40 is Type A in an adult and Type Ad in a
child — so the age is an input, not an assumption.

A **notch outranks depth**: Types D and E are notched by definition while Ad
and Add are not, so the notch is tested first. Classifying a notched trace as
plain Ad loses the distinction between a scarred drum and a disconnected
ossicular chain, which are not the same referral. Notch detection requires the
dip between two maxima to be at least 12% of the peak height, so sampling
ripple is not mistaken for one.

### Type B splits three ways, not two

| Canal volume | Meaning |
|---|---|
| Normal | Middle-ear effusion behind an intact drum |
| Large | Perforation or a patent ventilation tube |
| **Small** | **Cerumen occluding the canal, or a probe against the canal wall** |

The third is the one that matters and the one a two-way split silently gets
wrong: a small-volume flat trace is an **instrument artefact**, and reporting
it as middle-ear disease sends a patient down the wrong path when the fix is
to clear the canal and repeat.

### Two shape measures, both reported

The **tympanic gradient** is a dimensionless ratio:

    GR = (Ytm − Y±50) ÷ Ytm

where Ytm is the compensated peak admittance and Y±50 the mean 50 daPa either
side of it. A sharp peak falls away quickly and scores high; a broad, rounded
peak scores low. Normal is > 0.2, matching the reference table. The
**tympanometric width** in daPa is the same shape property in the other
convention (51–114 adults, 60–150 children), and both are shown so the result
reads against either.

### Where the criteria genuinely disagree, it says so

The reference gives Type B as "absent / ~0–0.2 mmho" and Type As as "< 0.37",
so the two bands touch at 0.2 and the table alone cannot settle a value sitting
on it. The comparison is strict — a peak of exactly 0.2 exists, however
shallow, so it types as As — and anything between 0.15 and 0.25 carries an
explicit *borderline* note telling the clinician to repeat the sweep. Inventing
a confident answer at a boundary the source does not resolve would be the
wrong kind of certainty.

### The curves are generated, not traced

The source document illustrates each type with a screenshot, but those come
from several places and disagree on axes, scales and even units — some plot
mm H₂O rather than daPa. So the app derives one curve per type from the
numeric criteria instead, giving one consistent set on one pair of axes, each
traceable to the row that produced it.

Every generated curve is fed back through the classifier as a test: **all eight
re-classify as their own type**, so the picture and the label cannot drift
apart.

Two refusals remain: a 226 Hz probe below six months of age, where it can read
normal over a middle ear full of fluid, and a peak sitting at the edge of the
sweep, which means the sweep was too short rather than that this is a Type C.
Summary-only entry still draws a curve, labelled `modelled` rather than
`measured`.

### 6b. The DP-gram

`dpoae.py`, `/api/oae/analyze`

Emission and noise floor at each f2 frequency, with a **stated protocol**:
newborn (3 of 3), general screening (2 of 3), occupational (3 of 3 weighted to
3–6 kHz), or a full diagnostic gram. A "refer" means nothing without the rule
that produced it, so the rule travels with the result.

Three judgements that a naive pass/fail gets wrong:

1. **Absent above the ceiling is uninformative.** Emissions disappear once the
   loss exceeds ~50 dB HL. Counting an absent emission at a 70 dB threshold as
   evidence of hair-cell damage double-counts the audiogram. Those frequencies
   are marked `uninformative`, not `refer`.
2. **A high noise floor invalidates, it does not fail.** A 3 dB SNR in a quiet
   booth and in a screaming infant are different measurements. Above 10 dB SPL
   of noise the frequency is `invalid` and the overall result is `incomplete`.
3. **A missing protocol frequency is incomplete, not a pass.** Two of three
   present with the third never recorded is not a pass.

Each dropout maps to a **cochlear place** via the tonotopic arrangement, so the
result reads as "the basal turn, where noise damage starts" rather than a list
of numbers. A notch — absent emissions with recovery both above and below — is
named ahead of the coarser basal pattern, because a 4 kHz dropout with 8 kHz
intact is the noise signature specifically.

---

## 6c. Otoscopy — the picture, checked against the measurement

`app/otoscopy/`, `/api/otoscopy/analyze`

Eight patterns from the clinical reference document supplied by the audiology
team, extracted panel by panel from its figures into **62 labelled views**:
normal, cerumen impaction, otitis media, retraction, and central / marginal /
attic perforation, plus mass lesions.

### Why hand-built features rather than a network

62 images across 8 classes. A convolutional network would memorise them.
Features that encode what a clinician actually looks at generalise from tens
of examples instead of tens of thousands — and every one can be shown to the
user as a number they can disagree with: erythema, cone of light, wax
fraction, dark-defect size *and where it sits*. Position is most of the
diagnosis here; the same defect is central in the pars tensa, marginal at the
annulus, or attic superiorly.

A bug worth recording: the first version thresholded the illuminated region
and used those pixels as the mask, which **punched a hole wherever the view
was dark — exactly where a perforation is**. The fix takes the outline of the
lit region and fills it. Perforations were being masked out before the
perforation detector ran.

### What it honestly achieves

Validated **leave-one-source-image-out**, so no augmented sibling of a test
image is ever in its own training fold:

| Measure | Result | Chance |
|---|---|---|
| Exact pattern, top-1 | ~44% | 12.5% |
| Correct answer in top 3 | ~73% | 37.5% |
| Urgency band | ~55% | 25% |

Several times chance; nowhere near diagnostic. Retraction, with four reference
views, is not learned at all. **So the interface does not present a label.** It
presents a ranked differential, the three closest labelled reference images
side by side with the capture, and the measured accuracy printed in the page
itself. Feed it one of its own reference views and it says so, rather than
letting a 100% bar look like performance.

Random forests, extra trees and an RBF SVM were all measured under the same
protocol; PCA into logistic regression beat them and is what ships.

### The part that does not depend on the classifier

Each pattern in the taxonomy records what it **predicts**: the expected
air-bone gap, the expected tympanogram type, the tests that follow, the
referral. Comparing those against the measured battery produces a checkable
result either way:

- Image read as otitis media, measured gap 32.5 dB, Type B trace →
  **two independent confirmations**.
- Image read as normal on the same case → *"conductive loss with a
  normal-looking drum"* and *"tympanogram does not match the appearance"*.

That conflict is informative whichever of the two is wrong, and it is the
thing a clinician cannot get from the picture or the audiogram alone.

Attic disease and mass lesions raise a referral **regardless of the
audiogram**, because early cholesteatoma is frequently silent on pure tones.

### Upgrading with the public dataset

`scripts/fetch_otoscope_dataset.py` puts the Kaggle otoscope dataset in place
(API or a manual download), mapping its folder names onto this taxonomy and
**reporting any folder it will not map rather than guessing**. Then
`python -m scripts.train_otoscopy` retrains. Same features, same API, same
screens; only the model card changes. The dataset is not committed here — it
is not ours to redistribute, and it requires an authenticated account.

---

## 6d. Signs and symptoms

`symptom_kb.py`, `symptoms.py`, `/api/symptoms/analyze`

Two supplied clinical documents, encoded unchanged in substance:

1. A **presenting-complaint guide** — otorrhoea, otalgia, vertigo, headache —
   listing likely causes **in rank order, separately for children, adults and
   older adults**. The ordering *is* the clinical content.
2. A **14-disease reference** giving main symptoms, most prone age group, and
   the audiological tests that establish each diagnosis. That last column is
   what makes this useful in an audiology clinic: it says which test to run
   next.

### Free text is matched, not parsed

No language model, and none needed. Patients and clerks use a small, highly
repetitive vocabulary; a synonym table covers it deterministically, offline,
in microseconds. "Water discharge from ears" resolves to `ear_discharge`.
Longer phrases win over their substrings, so "severe deep ear pain" is not
filed as ordinary ear pain. **Anything unmatched is reported back on screen** —
a symptom checker that silently drops a word is how a red flag goes missing.

### Combining two sources that disagree

The disease reference scores symptom overlap; the complaint guide gives a rank
prior. Neither alone is right. The guide's top entry for adult otorrhoea is
otitis externa — but its described presentation is *pain on touching the ear*,
and this patient has persistent discharge with hearing loss. So the guide's
prior is **modulated by how well the patient matches each cause's own
one-line complaint**, run through the same matcher. Chronic suppurative otitis
media, rank 2, correctly leads.

Agreement between the two sources scores higher than either alone, and the
response reports both components so a clinician can see which did the work.

Other deliberate behaviours:

- **Absence is evidence.** A disease whose defining feature is missing is
  demoted, not merely un-promoted. Meniere's without vertigo or fluctuation is
  a different diagnosis. Bullous myringitis requires bullae — ordinary ear pain
  must not summon it.
- **Some symptoms argue against.** A real hearing loss lowers CAPD, which is
  defined by normal thresholds.
- **Red flags do not compete with the differential.** They are evaluated
  separately and reported above it, because "this might be meningitis" is not a
  fourth-place possibility. Eleven rules, several age-restricted: cerebellar
  stroke fires for vertigo with imbalance only in the geriatric band, exactly
  as the source guide frames it.
- **The battery is ordered by discrimination**, then by the sequence tests are
  actually run in clinic — so it reads as a plan, not an alphabetical list.

Once thresholds exist, the correlation checks the leading diagnosis against
them using a **declared** expected type per disease, not keywords sniffed out
of prose. Free text that reads perfectly to a human ("notch at 3–6 kHz")
contains none of the words a matcher would need.

---

## 6e. Linkage — everything cross-checks everything

`linkage.py`, `/api/linkage`

Each module answers a different question and each can be wrong alone. The
history says what the patient notices; the image says what the ear looks like;
tympanometry says whether the middle ear moves; the audiogram says how much is
lost and where. The diagnosis is in whether they agree — and when they do not,
in naming the specific disagreement rather than averaging it away.

Four links, all bidirectional, all traceable to a rule in `symptom_kb`:

| Link | What it checks |
|---|---|
| Otoscopy ↔ symptoms | the appearance predicts symptoms; are they reported? |
| Otoscopy ↔ audiogram | the appearance predicts a gap and a trace; were they measured? |
| Symptoms ↔ audiogram | the differential predicts a **type, a PTA range and a side** |
| Immittance ↔ diseases | each of the **five** Jerger types supports some and excludes others |

**A confirmation is weaker evidence than a contradiction.** Two tests agreeing
may only mean they share an assumption; two that cannot both be true means one
is wrong, and that always deserves attention. So conflicts sort first, carry an
action, and drive the headline. A page of green ticks that buries the one line
saying two measurements disagree is worse than no panel at all.

### Otoscopy ↔ symptoms

This is the link that redeems a weak classifier. Each pattern declares the
symptoms it should produce and the symptoms it cannot account for. Otitis
media on the image plus pain and fever in the history is two independent
methods reaching the same answer from different evidence — worth more than
either alone. A normal drum with fever and discharge is a conflict.

Two asymmetries are deliberate. Hearing loss is **not** listed as unexplained
by a normal drum, because a normal drum is exactly what a sensorineural loss
looks like. And attic disease or a mass with *no* supporting symptoms raises a
conflict rather than passing quietly, because early cholesteatoma is frequently
silent — absence of symptoms must not be allowed to reassure.

### Symptoms ↔ audiogram, including the PTA

A diagnosis predicts three separate things about an audiogram, and they fail
independently: presbycusis with a conductive gap is wrong about the **type**,
presbycusis at 90 dB is wrong about the **degree**, presbycusis in one ear is
wrong about the **symmetry** — and each points somewhere different. So each is
checked and reported separately, against an `expected_type`, `expected_pta` and
`laterality` declared per disease.

Degree comparison uses a ±5 dB test-retest tolerance and has **three**
outcomes, not two. A value a few decibels past the edge of a range is not a
contradiction, but describing it as "inside the range" would be a false
statement about a number printed next to it, so it reports *borderline*.

Two further checks compare what the patient said against what was measured:
a reported loss with normal thresholds (the presentation pure tones are least
able to explain — test speech in noise before reassuring), and a significant
measured loss the patient never mentioned (gradual loss is often unnoticed;
counsel on the measurement, not the report).

When the leading possibility comes from the complaint guide, which predicts no
audiometric pattern, correlation falls to the highest-ranked entry that does —
and **says so**, with its rank, rather than appearing to reason about a
diagnosis the page never showed as the leader.

### Immittance ↔ diseases, all five types

Every Jerger type, each with the diseases it supports and the ones it argues
against. The second column is the one usually left out and often the more
useful: a Type A trace diagnoses nothing on its own, but it removes most of the
conductive differential in a single measurement. Type B splits on ear-canal
volume, and the split changes the differential completely — perforation versus
fluid behind an intact drum. Reflex patterns add a second axis: absent with a
conductive loss, absent while emissions are present, or present despite a
severe loss each carry their own differential.

---

## 6f. A differential from any single input

`linkage.otoscopy_vs_diseases`, `linkage.audiogram_vs_diseases`

The cross-checks in 6e all need two things recorded. That is the wrong
requirement at the moment each finding is actually made: a scope goes in the
ear before the patient is in the booth, and an audiogram often arrives with no
history attached at all. So both of these produce a ranked differential from
**one** input, with nothing else on file.

### From the image alone

Every otoscopic pattern is mapped to the diseases it argues for, with a
strength, plus the ones it argues against and the named conditions outside the
fourteen-disease reference. The classifier's **own uncertainty is carried
through**: the ranked class probabilities weight the disease scores, so a
picture the model cannot separate produces a correspondingly spread
differential instead of a confident answer built on a coin flip.

Two behaviours are deliberate:

- **A tie is not a ranking.** A normal drum supports every cochlear and neural
  cause equally, so the leaders tie. It says *"a normal drum excludes the
  middle-ear causes; it cannot rank the cochlear and neural ones against each
  other"* rather than printing an order it did not earn.
- **Convergent evidence is allowed to be confident.** Three uncertain patterns
  that all imply Eustachian tube dysfunction do make it likely, even when the
  image cannot say which of the three it is. Spread in the *pattern* does not
  have to mean spread in the *disease*.

Candidates scoring below 5% of the leader are dropped — a pattern the model
gave 3% to drags its whole disease list in at 3% of the weight, and those are
arithmetic rather than possibilities.

### From the audiogram alone

Each disease carries a **characteristic audiogram** — air and bone conduction
at the standard frequencies — and the measured curve is matched against all
fourteen on four independent axes:

| Axis | What it compares |
|---|---|
| Shape | the curve with its overall level removed |
| Degree | the PTA against the range this disease produces |
| Type | conductive / sensorineural / mixed / normal |
| Symmetry | one-sided against bilateral |

All four are reported separately, because they fail separately: a disease can
match the shape perfectly and be excluded by the type, and the clinician needs
to see which one disagreed. Removing the level before comparing shape is what
lets a 4 kHz notch match a 4 kHz notch whether the patient's is 20 dB deep or
50 — the level is then judged on its own axis.

**A normal audiogram is not a disease that happens to look normal.** Two
conditions in the reference set present with normal pure tones, so plain
pattern-matching would rank one of them first and read as a diagnosis of a
patient whose hearing is fine. The response detects this and says the ear is
within normal limits, offering those conditions as *the ones that present with
a normal audiogram* rather than as a ranked answer.

Finally, when both standalone differentials exist, the diseases they **both**
rank highly are surfaced — two modalities converging without either being told
what the other found, which is the strongest signal available on a case with
no history.

---

## 7. Machine learning

### Dataset
`generate_dataset.py` synthesises 12,000 labelled single-ear audiograms
across seven configurations — flat, sloping high-frequency, ski-slope,
rising, 4 kHz noise notch, cookie-bite, corner — with ±5 dB jitter and 5 dB
quantisation to mimic real measurement.

### Features (19 per ear)
Six raw AC thresholds, five adjacent-frequency slopes, low- and high-frequency
averages, 4 kHz notch depth (4k − mean(2k, 8k)), and five per-frequency
air-bone gaps.

### Primary model
`RandomForestClassifier(300)` wrapped in `CalibratedClassifierCV` (sigmoid,
5-fold) so `predict_proba` values are trustworthy confidences.

### Out-of-distribution detection
An `IsolationForest` fitted on the training features. A case is flagged
*"atypical — priority human review"* when max calibrated probability < 0.6
**or** the isolation score falls below the 1st percentile of training scores.

### Explainability — three complementary mechanisms

1. **Per-frequency importance.** Global RF feature importance scaled by how
   far this input deviates from the training mean, attributed to the
   frequencies each feature describes. Drives the teal glow on the chart.
2. **Counterfactuals.** The smallest single-frequency change that flips the
   classification: *"If 4 kHz were 10 dB better, this would classify as
   flat."* All probes are batched into one prediction. When nothing within
   ±50 dB changes the answer it says so — the pattern is unambiguous.
3. **Case retrieval.** The 12 nearest reference audiograms and how many carry
   the same label.

### Deep ensemble
`deep.py` trains five MLPs (96→48, ReLU, early stopping). Their *disagreement*
separates aleatoric from epistemic uncertainty — "this is hard" from "I have
never seen this" — which a single calibrated model cannot express.

**Benchmarked honestly:**

| | Accuracy | Log loss |
|---|---|---|
| Deep ensemble (5) | 100.00% | 0.0104 |
| RandomForest | 99.88% | **0.0071** |

The ensemble is marginally more accurate; **the forest is better calibrated**.
On a hold-out this saturated, 0.12 points is a handful of cases and close to
noise, while the calibration gap decides whether a stated confidence can be
trusted. The forest therefore remains primary — cheaper, deterministic,
directly interpretable — and the ensemble is retained for its uncertainty
decomposition. Live at `GET /api/model/comparison`.

### Clinician feedback loop
Any disagreement with the classifier is logged with its thresholds to
`feedback.jsonl` for the next training run, with agreement statistics exposed.

---

## 8. Snap-to-Digitize (photo → audiogram)

`backend/app/services/vision.py` (212 lines)

Works offline with no API key:

1. **Grid detection** — morphological extraction of long horizontal and
   vertical lines, clustered into gridline positions, giving the
   pixel → (frequency, dB) mapping.
2. **Symbol detection** — HSV colour masks isolate red (right) and blue
   (left); connected components near a frequency column are AC symbols,
   components offset beside a column are BC brackets.
3. **Snapping** — values snap to the 5 dB grid, with per-value confidence
   from snap distance.

Extracted values land in the **editable** entry grid with confidence badges.
Nothing goes straight into a diagnosis.

**Verified:** on the bundled sample photo it recovered **all 22 thresholds
exactly** against known ground truth (`tests/test_digitize.py`).

If a vision-capable LLM provider is enabled, that path runs instead — and
OpenCV remains the automatic fallback.

---

## 9. Functional impact

### Phoneme audibility (`phonemes.py`)
The classic "speech banana" — approximate frequency/intensity positions of 23
English phonemes — compared against the patient's thresholds by
log-frequency interpolation. Produces audible / borderline / inaudible lists
and rule-generated impact statements: *"will miss plurals and word endings;
difficulty with female and children's voices."*

### Speech Intelligibility Index (`sii.py`)
Band-importance-weighted audibility simplified from ANSI S3.5-1997, using the
ANSI octave-band importance function and the same speech-banana boundaries
drawn on the chart — so the number and the picture can never disagree.
Reported in quiet, in noise, and aided.

Reported as **the share of speech cues that are audible** — its actual
definition — never as a predicted word score. Audibility is necessary but not
sufficient for understanding.

### Word-level captions
Grapheme-to-phoneme approximation marks each word of a sentence clear /
degraded / missed. A word is only "missed" when most of its **consonant** cues
are gone — an earlier version that struck out "the" for losing /th/ reported
55% of words missed for a mild notch, which was overstated and was retuned.

### Hearing age — ISO 7029 (`norms.py`)
Median age-related threshold shift is a quadratic in age:
`H(age, f, sex) = a(f, sex) × (age − 18)²`. Inverting it gives the most
intuitive line the system produces:

> *"These ears are performing like a typical 55-year-old's — about 29 years
> older than the patient."*

For the 26-year-old welder that single sentence carries the entire prevention
argument.

**A deliberate correction:** the percentile spread floor is set to **9 dB**,
wider than the standard's own. Audiometry carries ±5 dB test-retest, and ISO
7029 describes *otologically screened* populations. With a tighter spread, a
clinically normal 15 dB threshold reported as "bottom 1%", which is alarming
and wrong. A regression test now fails if that ever recurs.

---

## 10. The Hearing Loss Simulator

`frontend/src/audio/simulatorGraph.js` (407 lines)

The audiogram becomes a live audio filter.

```
source ─ input ─┬─ dry ─────────────────────────────────────────────┐
                └─ aid filters ─ compressor ─ makeup ─ loss filters ─ shaper ─ wet ─┴─ master ─ analyser ─ out
```

**Three states**, crossfaded click-free:
- **Normal** — dry reference
- **This patient** — one BiquadFilter per audiometric band attenuating by
  (threshold − 20 dB)
- **With hearing aid** — NAL-R insertion gain, then wide-dynamic-range
  compression *with makeup gain*, then the same loss

**Measured proof** (4 kHz band energy, noise-notch patient):

| Normal | Patient | Aided |
|---|---|---|
| 116 | 30.5 | 97.4 |

**Prescription vs cheap amplifier.** A roadside amplifier raises everything
equally. Measured on the affected ear: the flat amplifier pushes low
frequencies to **139.7** against NAL-R's **109.7**, while mid-frequency
speech energy is no better. That is the argument for proper fitting, made
audible.

A real bug was found here: the compressor initially had no makeup gain, so
the "hearing aid" *attenuated*. Real aids apply makeup gain; now it tracks
`compressor.reduction` and gives it back.

**Also on this page:** restaurant babble on an SNR slider with live SII,
five synthesised everyday sounds (smoke alarm at 3.1 kHz, birdsong, reversing
truck, doorbell, telephone), true binaural mode with head shadow, and live
speech-recognition captions striking out missed words as you speak.

---

## 11. The Listening Lab

Three measures the audiogram cannot give, grouped on one page.

### 🧭 Spatial hearing
HRTF-rendered noise bursts placed around the listener; each ear then passes
through its own loss. Click where you heard it; scored as RMS error in degrees
against a 10° normative bound.

**Measured interaural level difference:**

| | Sound from right | Sound from left |
|---|---|---|
| Normal ears | **+69.7** | **−73.7** |
| Asymmetric patient | **+130.9** | **+56.3** |

With normal ears the difference **flips sign** with direction — that sign flip
*is* the localization cue. With a dead left ear it stays positive from both
sides. The cue is destroyed, so everything sounds like it is on the good side.
That is why such a patient turns the wrong way into traffic.

Enters immersive WebXR when a headset is present; degrades to a 2D compass
otherwise.

### 🍽 Digits-in-noise
The adaptive digit-triplet test behind national telephone screening
programmes. One-up/one-down converges on the SNR giving 50% correct.

**Only the speech-to-noise ratio matters**, so it stays valid on uncalibrated
laptop audio where pure-tone screening does not.

Verified against simulated listeners at four true thresholds: **mean error
under 0.6 dB in about 11 trials**.

It flags the dissociation that matters — normal thresholds with poor speech in
noise, which a booth audiogram cannot show.

### 🔔 Tinnitus
Pitch and loudness matching, minimum masking level, residual inhibition, then
a notched masker generated live: a half-octave band removed at the matched
pitch.

**Measured:** the notch carves a **92-unit dip** at the matched pitch while
neighbouring bands are preserved, against a flat plain masker.

Interpretation notes whether the matched pitch falls inside the region of
hearing loss (it usually does), and makes the counselling point that tinnitus
loudness is characteristically only a few dB above threshold — distress
correlates with intrusiveness, not level.

---

## 12. In-browser screening

`toneAudiometer.js`, `bayesianThreshold.js`

Two procedures, both with silent catch trials that flag a patient responding
to nothing.

**Modified Hughson-Westlake** — down 10 dB after a response, up 5 dB after
none; threshold at the lowest level heard on 2 of 3 ascending presentations.
Verified to converge exactly to truth at 0/10/25/40/55/70 dB in 7–11
presentations, and to return "NR" beyond the ceiling.

**Bayesian (QUEST/ZEST family)** — maintains a posterior over threshold,
presents the most informative next level, stops when the 95% credible interval
narrows to 10 dB. Every threshold arrives **with an error bar**.

**Benchmarked over 300 simulated listeners with realistic response noise:**

| | Presentations | Mean abs error | Bias | Errors > 10 dB |
|---|---|---|---|---|
| Bayesian | 9.6 | 2.7 dB | −0.2 dB | 1.3% |
| Staircase | 11.6 | 3.3 dB | +1.2 dB | 0.3% |

An earlier draft claimed it "halves the presentations". That was wrong; the
copy now states the measured numbers *including* the downside — the Bayesian
procedure produces more occasional large misses. Its real advantage is
calibrated uncertainty, not raw speed.

Calibration anchors 40 dB HL to the user's headphones; ISO 389-1 RETSPL
offsets correct for 0 dB HL being a different sound pressure at every
frequency. Labelled a screening, never a diagnostic audiogram.

**End-to-end verified:** driving the full UI with a simulated listener across
99 presentations recovered the intended audiogram **exactly** on both ears,
and the dashboard correctly flagged "type provisional — BC not tested".

---

## 13. Reports and the AI layer

### Offline engine (default, no API key)
A clause library keyed on pattern, degree, type and occupation fills every
section — Findings, Pattern & Likely Etiologies, Degree/Type, Disability,
Functional Impact, Recommendations, plus the fixed disclaimer. A noise notch
in a factory worker produces an occupational-NIHL etiology paragraph naming
the occupation.

A **deterministic verifier** then re-derives every number from the structured
JSON and confirms it appears in the draft. The "verified ✓" badge is earned,
not decorative.

### API engine (optional)
Six providers — Gemini, OpenAI, Anthropic, Groq, OpenRouter, Ollama — behind
one interface. Generator call with a senior-audiologist system prompt
(structured JSON only, never raw thresholds), then a second verifier call that
cross-checks every number.

**Any failure falls back to the offline engine automatically**, with the
reason surfaced. Verified live: with a quota-exhausted OpenAI key the system
produced a full verified report in six languages in 740 ms.

### Counselling in six languages
English, Tamil, Hindi, Telugu, Kannada, Malayalam — pre-authored phrase
tables, not runtime machine translation, so wording is stable and reviewable.
Read aloud via the Web Speech API, with an honest message when no voice for
that language is installed.

### Outputs
- **PDF report** — chart image, all sections, counselling, QR verification
  hash, signature line
- **ENT referral letter** — carries the exact red-flag criteria met
- **Patient QR handout** — the counselling sheet on the patient's own phone,
  works on a clinic LAN with no internet

---

## 14. Triage and throughput

`backend/app/clinical/triage.py`

| Priority | Trigger | SLA |
|---|---|---|
| **Critical** | sudden SNHL and other emergencies | same day |
| **Urgent** | asymmetry, retrocochlear findings | within 1 week |
| **Review** | OOD, low confidence, provisional type, battery conflict, benchmark disability | routine clinic |
| **Routine** | unambiguous and confident | auto-releasable |

Batch results return **ordered by clinical priority, not upload order**, worst
hearing first within a band.

**Measured on the 8-patient sample:** 5.37 s total, ~670 ms per case,
**89 cases per minute**, 2 flagged for review, **6 of 8 drafts (75%)
auto-releasable**.

**A deliberate judgement call:** normal audiograms no longer route to review
for pattern uncertainty. The classifier is trained only on losses, so normal
hearing is genuinely out-of-distribution — but nobody classifies the shape of
a normal audiogram, and in a camp normals are the bulk of the queue.
Everything else atypical still routes to a human.

---

## 15. Validation and honesty

This section is the one most worth reading.

### The 99.9% figure was removed as a headline
The classifier scores 99.88% hold-out accuracy on synthetic data. That number
proves only that the model learned its own generator. It is **not** clinical
accuracy, and the README no longer presents it as such.

### What replaced it
`POST /api/validate` accepts expert-labelled audiograms and reports agreement
the way a clinical validation study would — accuracy **and Cohen's kappa**,
with confusion matrices and every disagreement listed.

On the bundled 12-case labelled set:

| Measure | Agreement | Kappa |
|---|---|---|
| Degree (rules) | **100%** | **1.00** |
| Type (rules) | **100%** | **1.00** |
| Disability (rules) | 0.00% mean error | — |
| **Pattern (ML)** | **83.3%** | **0.795** ("substantial") |

That split is the strongest part of the answer. The rules score perfectly not
because a model is good but because they are deterministic implementations of
published guidelines — provable by conformance. Only the pattern classifier
needs empirical validation, and it honestly scores *substantial*, not perfect.

**Stated limitation:** those 12 cases were authored for this project, not
drawn from clinical practice. The harness demonstrates the method and
validates the rules; the ML figure must be re-measured on real
expert-labelled audiograms before being quoted anywhere.

### Conformance instead of statistics, where possible
`tests/test_conformance.py` sweeps the entire input space against the
guideline re-derived independently inside the test:

- **261** WHO grade checks from −10 to 120 dB in 0.5 dB steps
- **323** AC/BC combinations covering every physically real pair
- **625** disability combinations across both ears
- **50×** repeated runs proving byte-identical output, plus insertion-order
  independence

That is what "consistent diagnostic decision-making" means concretely.

---

## 16. Clinic workflow

- **SQLite patient records** — multi-visit history with trend lines, so
  hearing conservation stops being a two-point comparison
- **Camp dashboard** — prevalence by age band, noise-notch rate, benchmark
  disability counts. On the sample: *"38% of this cohort shows a 4 kHz noise
  notch."*
- **Bulk paper ingestion** — a folder of photographed audiograms becomes a
  triaged worklist (2 photos digitised, interpreted and ranked in 0.79 s)
- **Noise-dose calculator** — OSHA (90 dBA, 5 dB exchange) and NIOSH (85 dBA,
  3 dB exchange) with NRR derating as (NRR − 7)/2
- **Population atlas** — PCA projection of the training set with the patient
  plotted, making the OOD flag visual
- **5-year forecast** — continued exposure vs effective protection, with an
  uncertainty band and a preventable-loss figure in dB

---

## 17. Frontend design

Eleven pages, ordered the way a consultation runs: Signs & Symptoms, Otoscopy,
New Test, Screening, Immittance & OAE, Dashboard, Simulator, Listening Lab,
Progression, Batch, Records.

**The dashboard leads with the answer.** A verdict banner states the diagnosis
in one sentence, the three or four figures that carry the decision, and the
single next step. Everything below is explicitly the supporting evidence.

**The audiogram chart** uses correct clinical notation — red O / [ for the
right ear, blue X / ] for the left, log-frequency x-axis, inverted y-axis,
shaded normal band, No-Response arrows — plus a teal glow on the frequencies
that drove the AI classification and auto-placed plain-language callouts
("noise notch").

**Accessibility.** A hearing-health tool that fails accessibility fails on its
own terms: skip link, visible focus rings, ARIA labelling, a screen-reader
data table carrying the same thresholds as the chart, `prefers-reduced-motion`
support, print stylesheet, responsive drawer layout with no horizontal
overflow at 375 px, and an error boundary so one render failure cannot blank
the app mid-demo.

**A guided tour** spotlights each part of the interface across four routes so
the software explains itself.

**Installable PWA** with a service worker caching the app shell and audio, so
entry, simulation and screening keep working with no connectivity.

---

## 18. Testing strategy

**561 tests across 25 files.**

| Kind | What it proves |
|---|---|
| Boundary tests | PTA exactly 20/35/50/65/80, ABG exactly 10, RPwD clamps |
| Conformance sweeps | the guideline holds across the entire input space |
| Reproducibility | identical input → byte-identical output, 50× |
| Safety logic | every red flag fires and sorts correctly |
| Ground-truth regression | the digitizer against known sample photos |
| Provider routing | each LLM backend hits its own endpoint (no network calls) |
| Full API cycle | analyze → report → PDF → verify round-trip |
| Curve round-trips | a synthesised tympanogram reads back as the numbers that made it |
| Knowledge-base integrity | every red-flag rule and disease weight names a symptom that exists |
| Image determinism | the same otoscope image gives byte-identical features every run |
| Path traversal | reference images cannot be used to read outside their directory |

Three of the new tests exist because they caught real defects while being
written: the otoscopy field-of-view mask was excluding dark regions inside the
view (masking out perforations before detecting them), `cv2.kmeans` seeding
made feature extraction non-deterministic, and a noise notch in the DP-gram
was being reported as a generic basal loss because the branches were ordered
wrongly.
| Anti-alarm guards | normal thresholds never report as "bottom 1%" |

Several bugs were caught by these rather than by inspection: a 429-quota
fallback path, an informational alert displacing clinical advice, pattern
labels lowercased into "4 khz", and a test that silently depended on the
developer's environment variables.

---

## 19. How to run it

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m app.ml.generate_dataset
.venv\Scripts\python -m app.ml.train
.venv\Scripts\python -m app.ml.deep
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

```bash
# Frontend
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. No API key needed.

```bash
cd backend
.venv\Scripts\python -m pytest -q
```

---

## 20. Known limits

Stated plainly, because a medical tool that oversells is worse than one that
admits what it cannot do:

1. **The ML is validated on synthetic data.** Real expert-labelled audiograms
   are needed before any accuracy figure is quoted clinically.
2. **The browser screening is a screening.** Consumer headphones are not
   calibrated to ISO 389; absolute dB HL values are approximate.
3. **The 5-year forecast is a counselling aid**, not a validated prognosis —
   it is linear extrapolation from two measurements.
4. **SII measures audibility, not comprehension.** Sensorineural distortion
   reduces understanding further.
5. **ISO 7029 percentiles are indicative.** They use a normal approximation to
   the standard's spread, and the standard describes otologically screened
   populations.
6. **Tinnitus matching is subjective** and repeat matches vary.
7. **The digitizer assumes** a reasonably clean, roughly axis-aligned chart
   with conventional colours.
8. **The otoscopy classifier is trained on 62 images.** Leave-one-source-image-out
   it identifies the exact pattern well under half the time — several times
   chance, far from diagnostic — and it does not detect retraction at all,
   having only four reference views of it. The interface therefore shows a
   ranked differential with the closest labelled reference images, and prints
   the measured accuracy on the page. A photograph also cannot exclude disease
   behind wax, blood or a partly visible membrane. The training pipeline
   accepts the public Kaggle otoscope dataset with one command and no code
   change; that dataset is not redistributable and so is not committed here.
9. **Symptom assessment ranks, it does not diagnose**, and it knows only the
   fourteen diseases and four presenting complaints in the supplied reference
   documents. The weights attached to each symptom are ours, not the
   documents' — they are declared in `symptom_kb.py` so they can be argued
   with rather than hidden.
10. **A modelled tympanogram curve is a drawing of the entered numbers**, not a
    recorded sweep, and is labelled as such in the response and on screen.
11. **Nothing here replaces an audiologist.** Every report carries: *"AI-assisted
    interpretation; final diagnosis requires a qualified audiologist."*
