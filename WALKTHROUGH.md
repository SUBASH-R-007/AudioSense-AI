# AudioSense AI — Complete Walkthrough

A full explanation of what this project is, how every part works, why each
design decision was made, and what has actually been measured.

**Scale:** ~7,300 lines of backend Python across 45 modules, ~5,700 lines of
frontend across 30 files, **316 automated tests**, 8 application pages,
19 test files.

---

## Table of contents

1. [The problem](#1-the-problem)
2. [What the system does end to end](#2-what-the-system-does-end-to-end)
3. [Architecture](#3-architecture)
4. [The clinical rules engine](#4-the-clinical-rules-engine)
5. [The safety layer](#5-the-safety-layer)
6. [The cross-modal test battery](#6-the-cross-modal-test-battery)
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

Eight pages: New Test, Screening, Dashboard, Simulator, Listening Lab,
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

**316 tests across 19 files.**

| Kind | What it proves |
|---|---|
| Boundary tests | PTA exactly 20/35/50/65/80, ABG exactly 10, RPwD clamps |
| Conformance sweeps | the guideline holds across the entire input space |
| Reproducibility | identical input → byte-identical output, 50× |
| Safety logic | every red flag fires and sorts correctly |
| Ground-truth regression | the digitizer against known sample photos |
| Provider routing | each LLM backend hits its own endpoint (no network calls) |
| Full API cycle | analyze → report → PDF → verify round-trip |
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
8. **Nothing here replaces an audiologist.** Every report carries: *"AI-assisted
   interpretation; final diagnosis requires a qualified audiologist."*
