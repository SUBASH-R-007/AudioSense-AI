# AudioSense AI — Jury Pitch

*Problem Statement 8 — AI-Based Pure Tone Audiometry Diagnosis Predictor*

---

## The 30-second version

> India has roughly one audiologist for every 500,000 people. A screening
> camp produces two hundred audiograms in a day, and they all look alike in
> the folder — including the one that needed a doctor this week.
>
> AudioSense AI interprets a pure-tone audiogram in **670 milliseconds**:
> pattern, degree, type, statutory disability percentage, and a full clinical
> report. Then it does the thing that actually removes the delay — it
> **orders the queue by who needs a clinician first**, and tells you which
> drafts are safe to release without one. On our sample batch, **75% were.**
>
> And it catches what the audiogram alone cannot: a 26-year-old welder with a
> **completely normal audiogram** whose cochlea is already dying.
>
> It runs with **no API key, no internet, and no cloud** — on a laptop, in a
> village camp.

---

## Open with the save (first 60 seconds of any demo)

Load the **🔬 Pre-clinical Noise Damage** case.

Every threshold is within normal limits. A conventional screening — and every
competing tool — says *"normal hearing, no action"* and sends this welder back
to the shipyard.

AudioSense opens with:

> **"Hearing thresholds are still normal, but the cochlea is already being
> damaged — this loss is still preventable."**
>
> Tympanogram Type A — the middle ear is normal, so it is not what silenced
> the emissions.
> Otoacoustic emissions absent at 4 kHz and 8 kHz.
> **Next step: enforce hearing protection now and re-screen in 6 months.**

*"Outer hair cells die before thresholds move. This is the only window in
which the hearing can still be saved — and it is invisible on the audiogram."*

Then load **🚨 Sudden Asymmetric Loss**. Five alerts, in priority order:
possible sudden sensorineural hearing loss (**an emergency — steroids work,
but the window is days**), an asymmetric sensorineural loss warranting MRI,
speech findings suggesting retrocochlear pathology, asymmetric word
recognition, and a validity warning that speech masking was indicated but
not recorded.

*"Most tools would have called this 'moderate sensorineural loss' and booked
a hearing-aid fitting."*

---

## Why this wins on the problem statement

The brief lists five features. All five are built and tested. But the brief
*justifies itself* on time, volume and consistency — and that is where the
work went.

| The brief says | We answer with | Measured |
|---|---|---|
| "time-consuming" | Full interpretation per audiogram | **670 ms — 89 per minute** |
| "high-patient-volume" | Triage worklist by clinical priority | 8 cases in 5.4 s → 2 flagged, **75% auto-releasable** |
| "audiologist availability" | Explicit review-vs-release routing, with reasons | Conservative by design |
| "more consistent" | Guideline conformance across the whole input space | **261 + 323 + 625** checks, **50×** identical output |
| Accuracy | Validation harness, run so far only on 12 cases our team wrote | ML pattern **11/12 (95% CI 65–99%)**; rules 12/12, a consistency check — **not yet measured on clinical data** |

---

## The four things that make this different

### 1. We deleted our own best number

Our classifier scores **99.9%** on hold-out data. We removed it from the
README as a headline claim.

That figure is hold-out accuracy on *synthetic* data. It proves the model
learned its own generator. It is not clinical accuracy, and presenting it as
such would not survive this room.

What replaced it is a **validation harness** that scores the system against
expert-labelled audiograms using accuracy *and Cohen's kappa*, listing every
disagreement.

It has not yet been run on a clinic's labelled audiograms. The bundled set is
**12 cases our own team wrote**, so it shows the harness works; it does not
measure clinical accuracy:

- **Pattern classification: 11 of 12 (91.7%, κ = 0.90) — 95% CI 65–99%.**
  Two of the twelve are normal audiograms decided by a rule before the model
  runs, so the model itself named 9 of 10 loss configurations. Two labels
  were corrected to "normal" to match their own grade and type columns;
  against the original labels the same build scores 9 of 12.
- **Degree, type, disability: 12 of 12, 0.00% disability error.** Expected,
  because those labels were computed from the same published tables.

The rules are **deterministic implementations of WHO 2021 and the RPwD
Gazette ready reckoner (S.O. 76(E), 2018)**, so they are proven by
conformance sweeps, not by agreement on twelve cases. The ML needs real
empirical validation, and twelve cases cannot give it: with an interval that
wide, the honest headline is "not yet measured".

*We would rather show you the number we can defend than the one that sounds
better.*

### 2. You can hear the diagnosis

Press one button and the audiogram becomes a live audio filter.

**Normal → this patient → with a hearing aid.** Measured 4 kHz energy:
**116 → 30.5 → 97.4**. The loss stops being a number.

Then switch the aid to **"cheap amplifier"** — the roadside device sold across
India. It raises everything equally: low frequencies jump to **139.7** while
speech clarity does not return. *That is the argument for proper fitting, made
audible in four seconds.*

Add restaurant babble on an SNR slider. Play the **smoke alarm** — for this
patient, it is gone.

### 3. Three measures the audiogram cannot give

An audiogram says how loud a tone must be before you detect it. It says almost
nothing about the three complaints people actually arrive with.

**"I can't tell where sounds come from."** Our spatial test renders sound in
3D with HRTF, each ear through its own loss. With normal ears the interaural
difference **flips sign** with direction — **+69.7** from the right,
**−73.7** from the left. That flip *is* how you localize. With this patient's
dead left ear it stays positive from both sides: **+130.9** and **+56.3**. The
cue is destroyed. *This is why he steps into traffic.*

**"I can't follow speech in a crowd."** An adaptive digit-triplet test — the
instrument behind national screening programmes. Because only the *ratio* of
speech to noise matters, it stays valid on uncalibrated laptop audio where
tone screening does not. It flags the patient with a clean audiogram — every
threshold from 0.25 to 8 kHz below 20 dB HL in both ears — who still
struggles in noise. Its normal / insufficient / poor cut-offs (−7.0 / −4.5 dB
SNR) are provisional: published cut-offs belong to each test version, and
none has been validated for this browser test. A track with fewer than six
reversals is flagged as low-reliability.

**"There's a ringing that never stops."** Pitch and loudness matching, then a
notched masker generated live — a **92-unit dip** carved at exactly the
matched pitch while neighbouring bands are preserved.

### 4. Built for the clinic that actually exists

- **No API key. No internet. No cloud.** Reports come from a deterministic
  template engine; photo digitisation uses OpenCV. Six LLM providers can be
  enabled from the UI for richer narrative — and **any** failure falls back
  automatically. *The demo cannot die because the network did.*
- **Paper in, worklist out.** Photograph a folder of audiograms — 2 digitised,
  interpreted and triaged in 0.79 s. Our digitizer recovered **all 22
  thresholds exactly** against ground truth.
- **Six languages** — English, Tamil, Hindi, Telugu, Kannada, Malayalam — read
  aloud, or handed over as a **QR the patient scans onto their own phone**.
- **Installable PWA** that works offline in a village camp.
- **Statutory output**: RPwD Act 2016 disability from the Gazette ready
  reckoner (S.O. 76(E), 2018), with every step shown and a *not certifiable*
  flag whenever one of the four frequencies is missing, because a percentage
  that decides entitlement should never be a black box.

---

## Technical credibility, briefly

- **2,046 automated tests**, including boundary values (PTA exactly
  20/35/50/65/80/95, ABG exactly 10, the RPwD ready reckoner's 59→60 dB
  step) and full input-space conformance sweeps
- **Calibrated** RandomForest with **IsolationForest** out-of-distribution
  flagging — the model can say *"atypical, priority human review"*
- **Counterfactual explanations**: *"If 4 kHz were 10 dB better, this would
  classify as flat"* — plus the 12 nearest reference cases
- **A deep ensemble, benchmarked honestly**: 100.00% accuracy vs the forest's
  99.88% — but the forest has the **better log loss (0.0071 vs 0.0104)**. The
  forest stays primary, because calibration matters more than a 0.12-point
  accuracy gap that is close to noise. *We shipped the comparison, not just
  the winner.*
- **Bayesian screening** with a 95% credible interval on every threshold, and
  silent catch trials that flag a patient responding to nothing
- **Clinician correction loop** — every disagreement is logged for retraining

---

## The 3-minute demo running order

| Time | Action | The line |
|---|---|---|
| 0:00 | 🩺 Signs & Symptoms — same complaint, two ages | *"Water from the ear at 34 is chronic otitis media. At 72 with diabetes it's a skull-base infection. The age is the diagnosis."* |
| 0:25 | 🔬 Pre-clinical case | *"Normal audiogram, normal middle ear, emissions gone at 4 and 8 kHz. Every other tool sends him back to work."* |
| 0:50 | 🚨 Sudden asymmetric | *"This one is an emergency, and it sorts above everything else."* |
| 1:05 | Snap a paper audiogram | *"Paper to interpretation, offline, human confirms before anything is issued."* |
| 1:20 | 👁 Otoscopy — normal drum on a conductive case | *"Four links, and two of them go amber. The picture argues with the history AND with the measurement. A conflict is worth a look whichever side is wrong — an agreement would only back a pattern match we have not validated."* |
| 1:40 | 📉 Immittance — early effusion | *"Normal peak height. Width 199 daPa against a ceiling of 114. Three numbers call this normal; the curve's width flags it."* |
| 1:55 | 🎧 Simulator | Normal → patient → aided → cheap amplifier → smoke alarm |
| 2:20 | 🧭 Listening Lab | *"With his ears, everything sounds like it's on the right."* |
| 2:40 | Batch + Validate | *"89 a minute. 75% auto-releasable. And here's the harness on twelve cases we wrote — 11 of 12, with an interval from 65 to 99%. That proves the harness, not the model: the real number comes from a clinic's labelled audiograms, and it will not be 99.9%."* |
| 2:55 | Close | *"Deterministic clinical core. Calibrated AI that admits doubt. Empathy you can hear."* |

---

## What we are honest about

We will say this before you have to ask:

1. **The ML is validated on synthetic data.** Real expert-labelled audiograms
   are needed before quoting clinical accuracy. The harness is built and
   waiting.
2. **The otoscopy classifier is trained on 62 views cut from 22 photographs,
   and it shows.** With every view of the test photograph held out of
   training, it names the exact pattern **27% of the time** (17 of 62, 95% CI
   15–42%) — about twice chance (12.5%), nowhere near diagnostic. So the
   screen leads with a **ranked differential and the three closest labelled
   reference views**, not a label, and prints the measured accuracy in the
   interface itself. On photographs it has not seen it does not identify
   retraction, marginal perforation or masses at all, and almost never attic
   disease — and we say so on the page. The training pipeline takes the public
   Kaggle otoscope dataset with one command and no code change; we could not
   redistribute it here, so we shipped the model that the data we *do* have
   honestly supports.
   **The audiogram cross-check** compares what the matched pattern predicts
   against what was measured. It uses the classifier's label, so a conflict
   is informative either way, but an agreement only corroborates a pattern
   match that is not validated.
3. **Symptom assessment ranks; it does not diagnose.** It knows fifteen
   conditions (the fourteen in the supplied reference documents plus sudden
   sensorineural hearing loss from the AAO-HNS 2019 guideline) and four
   presenting complaints, and nothing else. Free text is matched by synonym table — words
   it does not recognise are shown back rather than silently dropped.
4. **Browser screening is a screening**, not a diagnostic audiogram —
   consumer headphones are not ISO 389 calibrated.
5. **The 5-year forecast is a counselling aid**, not a validated prognosis.
6. **SII measures audibility, not comprehension.**
7. **Nothing here replaces an audiologist.** Every report carries:
   *"AI-assisted interpretation; final diagnosis requires a qualified
   audiologist."*

Every one of these limits is stated **inside the application**, not just in a
document — because a medical tool that oversells is more dangerous than one
that admits what it cannot know.

---

## Why we deserve the prize

Most entries will show you a model that classifies audiograms.

We built a **clinical instrument**: a deterministic core that provably
conforms to the WHO 2021 grades and the 2018 Gazette disability table (still
to be checked against the 2024 guidelines that superseded it), an AI layer that knows when to defer to a
human, a queue that puts the emergency first, a validation harness that
reports our real accuracy rather than our flattering one — and a demonstration
that lets a jury **hear**, in four seconds, what a factory worker has lost.

And it catches the damage **before the audiogram does**, which is the only
point at which the hearing can still be saved.

---

### One sentence, if you remember nothing else

> **AudioSense AI turns a folder of paper audiograms into a triaged clinical
> worklist in seconds, tells you which cases a human must see, proves its own
> numbers against the guidelines — and finds the damage while it is still
> preventable.**

---

*Repository:* `github.com/SUBASH-R-007/AudioSense-AI`
*Full technical detail:* [`WALKTHROUGH.md`](WALKTHROUGH.md)
*Run it:* [`README.md`](README.md) — two commands, no API key
