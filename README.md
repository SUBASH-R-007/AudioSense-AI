# 🎧 AudioSense AI

**AI-powered Pure Tone Audiometry interpretation platform** — clinically rigorous, offline-first, built to demo.

Enter (or photograph!) an audiogram → get WHO-2021 grading, conductive/sensorineural typing, India RPwD Act 2016 disability percentage, an ML pattern classification with calibrated confidence + out-of-distribution flagging, a phoneme-level functional impact map, a verified clinical report with a Tamil+English patient counseling sheet — and then **hear the world through the patient's ears** with the Web Audio hearing loss simulator.

📖 **[WALKTHROUGH.md](WALKTHROUGH.md)** — complete explanation of every part of the project
🚀 **[DEPLOYMENT.md](DEPLOYMENT.md)** — deploy to Vercel + any Docker host (deployment adds CORS; local development needs an account too — see Run it)
🎤 **[PITCH.md](PITCH.md)** — the jury presentation, with a timed 3-minute demo running order

## 🎯 Against the problem statement

The brief asks for automatic analysis, pattern classification, degree and type prediction, disability estimation and an AI-generated report — because interpretation is *time-consuming*, *expertise-dependent*, and delays diagnosis in *high-volume settings*. All five features are built; these are the numbers behind the justification:

| Claim in the brief | What this system does | Measured |
|---|---|---|
| "time-consuming" | Full interpretation per audiogram | **~670 ms**, 89 cases/minute on a laptop |
| "high-patient-volume" | Triage worklist ordered by clinical priority, not upload order | 8-case batch → 2 flagged for review, **75% of drafts auto-releasable** |
| "dependent on audiologist availability" | Explicit auto-release vs review routing, with reasons | Conservative by design: anything atypical, provisional or entitlement-bearing routes to a human |
| "more consistent" | Guideline conformance swept across the entire input space + reproducibility proof | 261 WHO grade checks, 323 AC/BC type combinations, 625 disability combinations, 50× identical-output runs |
| Accuracy | Validation harness (agreement + Cohen's κ) for expert-labelled audiograms | **Not yet measured on clinical data.** On the 12 bundled cases, written by the project team: ML pattern **11/12 (91.7%, 95% CI 65–99%)**; rules agree on all 12 — a consistency check, since those labels were computed from the same published tables |

**On the 99.9% figure.** That is hold-out accuracy on synthetic data and means only that the model learned its own generator — it is not clinical accuracy and this README will not present it as such. The number worth quoting will come from `/api/validate` run on real expert-labelled audiograms, and no such set has been run yet. `samples/validation_labelled.csv` shows the format, but its 12 cases were written by the project team, so they exercise the harness rather than measure the model: the pattern classifier agrees on 11 of 12 (κ=0.90; Wilson 95% CI 65–99%), and two of those 12 are normal audiograms that a rule gate decides before the classifier runs, so the model itself named 9 of 10 loss configurations. Cases 04 and 08 were relabelled `normal` because their own grade and type columns say normal hearing; against the original labels the same build scores 9 of 12. Degree, type and disability are deterministic implementations of published guidelines, validated by conformance rather than by statistics — their 100% (κ=1.0) and 0.00% disability error on the same cases only confirm that the rules reproduce labels computed from the same tables.

## ✨ Signature features

| | |
|---|---|
| 🔬 **Checks between the tests, not just within them** | Five correlations no single module could make, because each half was computed in a different file: **emissions against evoked potentials** (present OAEs behind an abnormal ABR is the auditory neuropathy pattern — a working cochlea and a bad nerve), **an objective response against a volunteered threshold** (a normal ABR at 30 dB nHL cannot sit under a 75 dB behavioural average; that is the classic non-organic picture), **the otoscope against the emissions** (wax or a perforation blocks an emission on its way out, so absent emissions behind one say nothing about the cochlea — behind a drum confirmed normal they say a great deal), **the forks against the tympanogram** (a negative Rinne with a Type A trace is a disagreement to resolve, and otosclerosis or a third window is what it points at), and **an infant's response level against a measured threshold** (a minimum response level cannot be *better* than a threshold — that pair is impossible, not borderline). Each names the two tests behind it and what to do about it, and a cross-test contradiction can make the whole workup "conflicted" |
| 🔗 **Everything cross-checks everything** | Four links, live on every screen: the **image against the history** (an otitis media picture and a patient reporting pain and fever confirm each other; a normal drum with fever does not), the **image against the audiogram**, the **history against type, degree, symmetry and PTA**, and the **tympanogram against the disease list**. Conflicts always sort above agreements, because two tests that cannot both be true is the finding — a page of green ticks that buries it is worse than no panel at all |
| 🩺 **Signs & symptoms triage** | "Water keeps coming out of my ear." Free text or checklist → ranked differential, **red flags that outrank it**, and the test battery that separates the possibilities — from two clinical reference documents, matched deterministically with no network call. Age changes the answer: the same discharge is acute otitis media in a child and **necrotizing otitis externa** in a diabetic of seventy-five |
| 👁 **Otoscopy pattern matching — per ear, and you overrule it** | **Each ear is examined and recorded separately**, so a perforated left drum beside a normal right one is two findings rather than one overwriting the other. And at 27% top-1 on unseen photographs the person holding the scope is right about three times in four when they disagree — so **"Not what you see?" sets the pattern by hand, and that reading is authoritative**: the expected hearing and tympanogram, the disease differential and every cross-check re-derive from it, and the correction is kept as the expert label this model has almost none of. A tympanic-membrane photo against a **62-view labelled atlas** across eight patterns, returning a ranked differential, the three closest reference images side by side, and the measurements behind the call. Then the cross-check: what the matched pattern *predicts* — a large canal volume, a Type B trace, a 20–45 dB gap — checked against what was actually measured. A conflict is worth a look whichever side is wrong; an agreement only corroborates a pattern match that is not validated |
| ⌨️ **Enter what you actually have** | Every instrument takes the measurement **or just the outcome**. A newborn screener prints PASS; a camp tablet prints REFER; a referral letter says "Type B, left" and nothing else — so tympanometry takes a type on its own, emissions take a pass/refer on its own, and reflexes distinguish *absent* from *not tested*. What an outcome **cannot** support is printed with it: no cochlear place, no pre-clinical damage finding, no frequency-by-frequency comparison, because each of those needs the per-frequency levels. **"Enter values" is the default everywhere** — the worked examples used to be, which meant a page opened showing fabricated numbers beside a real patient's name |
| 🎛 **Test the frequencies you tested** | The DP-gram frequency set is the clinic's, not ours: add 5 kHz to chase a notch, drop to 3/4/6 kHz for occupational monitoring, and the decision is scored against **the set actually measured** rather than a published protocol's list. Every added frequency still gets a real cochlear place, from the Greenwood map rather than a lookup table. A named protocol's pass count stays fixed, because that count *is* the criterion |
| 📉 **Tympanometry, all eight types** | The full classification from the immittance reference — A, As, Ad, **Add**, B, C, **D**, **E** — not the five-type scheme. A notched peak is a scarred drum (D) or a broken ossicular chain (E), which the five-type version files as "deep" and loses. Type B splits **three** ways on canal volume, and the third is the one that matters: small volume is wax or a blocked probe, an artefact otherwise reported as middle-ear disease. Every type ships a **generated curve**, and each curve re-classifies as itself |
| ⌨️ **Four numbers in, the right curve out** | Clinical tympanometers print ECV, PP, SC and GRAD and never export the sweep — so all four can be typed in and the curve is **reconstructed from them**. The gradient is inverted properly (`GR = 1 − exp(−50²/2σ²)` solved for σ, converted to FWHM) rather than drawn to look plausible, so the curve's *measured* gradient reads back as the number entered. Tests round-trip it through the classifier to prove it |
| 🔗 **Diseases from any single input** | A ranked differential from the **image alone**, or the **audiogram alone**, with no history required — a scope goes in the ear before the patient is in the booth. The audiogram is matched against a characteristic curve per disease on four separate axes (shape, degree, type, symmetry), all four shown, because a disease can match the shape perfectly and be excluded by the type |
| 🎚 **Masking, decided per frequency** | Both air-conduction rules — AC(TE)−AC(NTE) ≥ IA **and** AC(TE)−BC(NTE) ≥ IA — because the second catches the case the first misses: a conductive loss in the *non-test* ear lowers the bar the crossed signal has to clear. Bone conduction masks at a 15 dB gap, with no interaural attenuation to rely on. The **transducer is a clinical choice, not a logistical one**: supra-aural 40 dB, insert 50–60 dB, and it changes the answer. Where the noise needed exceeds the level at which it crosses back, the app reports a **masking dilemma** rather than a threshold |
| 🎵 **Tuning forks that bracket the gap** | Rinne, Weber, Bing, ABC/Schwabach and Gelle — and the quantitative fact most tools miss: **the frequency at which the Rinne reverses sizes the air-bone gap.** Reversal at 256 Hz alone means roughly 15–30 dB, at 256 and 512 means 30–45, at all three means 45 or more. **2048 and 4096 Hz have no valid crossover value, so the app refuses to infer a gap from them** rather than extrapolating the series. The killer result is the **false-negative Rinne**: a dead ear whose bone-conducted sound crosses the skull reads as conductive, and the tell is a Weber lateralising the wrong way — that combination gets a red banner and *no diagnosis*. All twelve Rinne × Weber cells are covered by exactly one rule, proven by test. And where the audiogram disagrees, **the audiogram wins**: a fork-derived conductive finding in an ear with no measured gap is retracted, with the predicted band and the measured gap drawn on one axis |
| 🗣 **SDT, SRT and WRS with their real uncertainty** | All three speech measurements, cross-checked against each other and the tones. **A word score is a sample, not a measurement**: every score carries its exact binomial confidence interval, so 88% and 76% on a 25-word list are correctly reported as *not different*. SDT must track the best pure-tone threshold and sit 5–10 dB better than the SRT — a gap of 0–4 or 11–15 dB is reported as atypical, a larger one is flagged, and a detection threshold poorer than reception is impossible and says so. A score taken nearer than 30 dB above the SRT is flagged rather than interpreted, because it measures the presentation level, not the patient |
| 🧠 **ABR, MLR and LLR — the pathway, not one point on it** | Three recordings of the same ascending pathway at increasing heights: brainstem (0–10 ms), thalamocortical (10–80 ms), cortex (50–350 ms). **Their value is comparative** — a normal ABR under an abnormal MLR puts the lesion above the brainstem, and neither recording says that alone. Every absolute latency is judged against the norms **for the intensity actually used**, interpolated between table rows, because Wave V sits near 5.4 ms at 90 dB nHL and near 7.5 ms at 20 dB, so an absolute latency without its intensity is uninterpretable — delayed beyond 3 SD, borderline at 2–3 SD (ACNS Guideline 9C), with a 0.15 ms allowance for a man's later waves. Interpeak intervals lead, judged against adult limits (I–III 2.5, III–V 2.4, I–V 4.5 ms), since a conductive loss delays everything equally and leaves I–V intact while a retrocochlear lesion stretches it. Plus a Wave V threshold in dB nHL with a typical nHL-to-eHL correction, the 0.9 ms insert delay, interaural asymmetry between runs at the same level (Selters & Brackmann-corrected when both 4 kHz thresholds are known), a cochlear microphonic that signals auditory neuropathy only when Wave V is absent, and **P1 latency as a cortical-maturation biomarker** judged against the Sharma, Dorman & Spahr (2002) curve for the child's age |
| 👶 **BOA that refuses to become an audiogram** | Behavioural observation across eight age bands — and the one thing everyone gets wrong is built into the design: **these are minimum response levels, not thresholds.** A normal-hearing newborn responds to a warble tone near 78 dB — far above what they can actually hear; recording that as a threshold draws a hearing loss on a normal ear. (The levels are labelled dB SPL, but whether the Northern & Downs norms are dB SPL or dB HL is unverified, and every BOA result says so.) The panel sits under the pure-tone form and **never offers to transfer a value into the threshold grid**. The curve falls from 78 to 26 dB because the *behaviour* matures, not the hearing — and the caption says so. Habituation, single-observer bias and the VRA hand-off at 6 months are all flagged rather than assumed away |
| 🌀 **DP-gram with a stated protocol** | Emission and noise floor per frequency, pass/refer against newborn, screening, occupational or diagnostic criteria, and the **cochlear place** each dropout maps to. Absent emissions above 50 dB HL are marked *uninformative*, not counted as damage — that would be double-counting the audiogram |
| 🧭 **Spatial hearing test** | HRTF-rendered sound placed around the listener, each ear through its own loss. With normal ears the interaural difference **flips sign** with direction; with asymmetric loss it stays positive whichever side the sound came from — the cue is gone, which is why the patient turns the wrong way. Measured, not asserted |
| 🍽 **Digits-in-noise** | The adaptive digit-triplet test behind national screening programmes. Only the speech-to-noise *ratio* matters, so it works on uncalibrated equipment — and it flags the patient with a clean audiogram (every threshold from 0.25 to 8 kHz below 20 dB HL in both ears, Liberman et al. 2016) who still cannot follow a conversation. The −7.0 / −4.5 dB SNR cut-offs are **provisional** — not validated for this browser test — and a track with fewer than 6 reversals is flagged low-reliability |
| 🔔 **Tinnitus matching + notched therapy** | Match pitch and loudness, then generate a notched masker that carves a half-octave hole at exactly that pitch while leaving its neighbours intact |
| 🎯 **The answer, first** | The dashboard opens with one plain sentence, the figures that carry the decision, and the single next step — everything below it is the evidence |
| 🧭 **Guided tour** | "Show me around" spotlights each part of the interface and says why it exists, so the software explains itself |
| 🚦 **Triage worklist** | A batch comes back ordered by who needs a clinician first, each case carrying an explicit *review required* or *auto-releasable* decision with its reasons — the actual bottleneck in a high-volume clinic |
| 📷 **Bulk paper ingestion** | Drop a folder of photographed audiograms and get a triaged worklist; the department's paper backlog becomes a queue |
| 🔬 **Cross-modal test battery** | Tympanometry, acoustic reflexes and otoacoustic emissions reconciled against the audiogram — the engine reports whether the tests **agree**, and names the pattern when they don't (effusion confirmed, otosclerosis, auditory neuropathy, non-organic). It also notes results the middle ear explains and emissions too noisy to judge; a note becomes a validity alert, able to set the next step, only when it leaves the screening question open in an ear the audiogram grades normal, or when word recognition is poor beyond what the middle ear explains |
| ⏳ **Damage before the audiogram moves** | Absent emissions with normal thresholds behind a normal middle ear (Type A tympanogram, no air-bone gap) = **pre-clinical cochlear damage**; without that confirmation the app asks for tympanometry first, because a middle-ear disorder abolishes emissions too. This is the difference between screening for injury already done and injury still preventable |
| 📐 **Bayesian screening** | A QUEST/ZEST posterior over threshold: every result carries a **95% credible interval**, plus silent catch trials that flag a patient responding to nothing |
| 🎤 **Live conversation mode** | Speak, and your own sentence appears struck through where this patient loses it — powered by the same word-audibility engine as the report |
| 🎧 **True binaural simulation** | Each ear processed with its own audiogram in stereo, with head shadow — asymmetric loss is heard as *lateralised*, not just quieter |
| 🚨 **Red-flag referral engine** | Detects **sudden SNHL** (steroids are time-critical) and **asymmetric sensorineural loss**, in air or bone conduction (MRI to exclude vestibular schwannoma; a conductive asymmetry is referred to ENT/otology instead), and refuses to bury them — emergencies sort above everything else on the page |
| 🔍 **Test-validity checks** | Flags when **masking was indicated but not done** (a shadow curve from the opposite ear), and when the **SRT disagrees with the pure tones** — the classic sign of non-organic hearing loss |
| 🗣 **Speech audiometry** | SRT/PTA agreement, word-recognition banding, and the **rollover index** for retrocochlear screening — gated on a drop the word lists can actually resolve. The index is a *ratio*, so over a low PB max a difference of a few words clears the 0.45 criterion on its own: 6 words correct falling to 3 on a 25-word list scores 0.50, and that used to become an urgent referral for imaging. It is now reported as a **possible rollover to repeat**, not a referral, and each score is tested on **its own list length** instead of borrowing the other's precision. PB max and the index sit behind a click, with what they mean attached |
| 🔊 **Hearing Loss Simulator** | The audiogram becomes a live BiquadFilter cascade — a three-way toggle between **normal hearing → this patient → with a hearing aid** on bundled speech, uploaded audio, or the **live microphone** |
| 🍽 **Restaurant noise + everyday sounds** | An SNR slider adds competing babble with the SII moving live, and synthesized real-world sounds (smoke alarm, birdsong, reversing truck, doorbell, phone) show what else disappears |
| 💸 **Prescription vs cheap amplifier** | Hear NAL-R shaped gain against the flat roadside amplifier that just makes everything louder — the argument for proper fitting, audible |
| 🦻 **Hearing-aid preview** | A NAL-R prescription (Byrne & Dillon 1986) plus output compression, applied in real time — judges *hear* the intervention work, not just the deficit |
| 💬 **Live speech captions** | The test sentence is shown with the words this patient would mishear **struck through**, restored the moment the aid is switched on |
| 🎧 **In-browser screening** | A calibrated-anchor, modified Hughson-Westlake staircase (down 10 / up 5) that measures your own audiogram in ~90 seconds and feeds it into the full pipeline |
| 📷 **Snap-to-Digitize — the ear is a symbol, not a colour** | Photo of a paper audiogram → OpenCV grid detection, then every mark **identified by its shape** across the full standard set (O, X, △, □, <, >, [, ]), which gives the ear, the conduction *and* whether masking was used. That is what makes a **black-and-white chart readable at all** — a photocopy, a fax, a greyscale scan or a one-pen chart returned "no red/blue symbols detected" when the ear was decided by hue. Colour is still used where it exists, as corroboration and to separate two symbols drawn at the same point. On the bundled samples: **22/22 and 21/22 thresholds exact** in colour (was 16 and 15), and 12–16 of 22 in greyscale with **no wrong value in any case** — it reads what it is sure of and names what it left for you |
| 📄 **Scan a whole report** | Not just a chart: a **full A4 report page** — letterhead, patient details, the audiogram somewhere in the middle, the printed results underneath. The audiogram is **located on the page** and digitized; the printed fields are read where OCR or a vision provider is available, and otherwise shown as **crops of the page beside the boxes they fill**, so nothing is ever guessed from the image |
| 🍌 **Phoneme map + SII** | The speech banana on the audiogram, plus a band-importance-weighted **Speech Intelligibility Index** in quiet, in noise, and aided |
| 🐚 **Cochlear damage map** | Greenwood frequency-place mapping shows *where on the basilar membrane* the loss sits — the 4 kHz notch as a glowing lesion at the basal turn |
| 📈 **5-year forecast** | Projects continued exposure vs effective hearing protection, with an uncertainty band and preventable-loss figure in dB |
| 🧠 **Deep ensemble, honestly benchmarked** | Five networks whose disagreement separates "this is hard" from "I have never seen this". Run head-to-head with the forest: the ensemble is marginally more accurate, the **forest is better calibrated**, and the forest stays primary — the comparison is in the app at `/api/model/comparison` |
| 🧠 **ML pattern classifier** | RandomForest, calibrated probabilities, 7 clinical configurations, per-frequency explanation glow on the chart, IsolationForest OOD → "atypical — priority human review". Rules around it: an ear with a four-frequency average below 20 dB HL and no threshold above 25 dB HL gets *Within normal limits* before the model is consulted; fewer than 5 of 6 frequencies, or no 4 kHz, gets *Not classified — insufficient frequencies*; an isolated outlier threshold or no response everywhere also flags *atypical*. Each ear carries a `reliable` flag — confidence ≥ 80%, all six frequencies measured, no atypical or outlier flag, and, when the four-frequency average is normal, raised thresholds that actually form the shape named |
| 🤔 **Counterfactuals + case retrieval** | "If 4 kHz were 10 dB better, this would classify as flat" — plus the 12 nearest reference audiograms and how many agree |
| ✍️ **Clinician correction loop** | Disagree with the AI and the override is logged with its thresholds for the next training run — human-in-the-loop MLOps, not a black box |
| ✅ **Verified reports** | Dual-engine pipeline (offline template engine or any LLM provider) with a verifier pass that re-checks every number — "verified ✓" is earned, not decorative |
| 📑 **Two documents, two readers** | The PDF is the **clinical** report: countersigned, filed, sent to the referring doctor. The counselling sheet is plain language for the patient to take home, and it has **its own QR**. They used to print in one file, which served neither — a clinician filing two pages of counselling, and a patient handed their summary wrapped in air-bone gaps. The QR on the PDF now opens **the clinical report**, readable on a phone with every number intact |
| 🌏 **Six languages + QR handout** | Counseling in English, Tamil, Hindi, Telugu, Kannada and Malayalam — read aloud, or scanned as a QR that opens the sheet on the patient's own phone |
| 📊 **Camp dashboard** | Batch a whole factory shift and get prevalence by age band, noise-notch rate and benchmark-disability counts — "25% of this cohort shows a 4 kHz noise notch with hearing loss at 4 kHz" on the sample, counted by the Coles et al. (2000) notch rule with 4 kHz above 25 dB HL, not by the ML label |
| 📴 **Installable PWA** | Service-worker cached app shell and audio, so entry, simulation and screening keep working in a village camp with no connectivity |
| 🗂 **Longitudinal records** | SQLite patient history with multi-visit trend lines, so hearing conservation stops being a two-point comparison |
| 📮 **One-click ENT referral** | A referral letter carrying the exact red-flag criteria met, the audiogram findings and the battery result |
| 📢 **Noise-dose calculator** | OSHA and NIOSH dose from real task exposures, with NRR derating — grounding the forecast in exposure rather than trend alone |
| 🗺 **Population atlas** | PCA projection of all 12,000 training audiograms with the patient plotted, making the out-of-distribution flag visual |
| 🔌 **Offline ↔ API toggle** | Fully functional with **zero API keys**. Optional providers: Gemini (free tier), OpenAI, Anthropic, Groq, OpenRouter, Ollama — with automatic fallback to offline if a call fails |

## 🏗 Architecture

```mermaid
flowchart LR
    subgraph Frontend [React + Vite + Tailwind + Recharts]
        SY[Signs & Symptoms<br/>complaint → differential] --> OT
        OT[Otoscopy<br/>image vs reference atlas] --> DB
        SCR[Screening Test<br/>Hughson-Westlake tones] --> DB
        NT[New Test / Digitize] --> DB[Results Dashboard<br/>audiogram · SII · cochlea map]
        IMM[Immittance & OAE<br/>tympanogram curve · DP-gram] --> DB
        AEP[Evoked Potentials<br/>ABR · MLR · LLR] --> DB
        TF[Tuning forks<br/>Rinne · Weber · Bing] --> NT
        DB --> SIM[Hearing Simulator<br/>normal → patient → aided<br/>+ live captions]
        DB --> TTS[Counseling read aloud<br/>EN / Tamil]
        PROG[Progression + 5y forecast] & BATCH[Batch CSV]
        SET[AI Settings<br/>Offline / API toggle]
    end

    subgraph Backend [FastAPI]
        SYM[/api/symptoms/] --> KB[Complaint guide by age band<br/>+ 15-condition reference:<br/>14 supplied + SSNHL, AAO-HNS 2019<br/>+ red-flag rules]
        OTO[/api/otoscopy/] --> OTOM[Illumination-normalised features<br/>+ PCA/logistic over 8 patterns<br/>+ nearest-reference retrieval]
        OTOM --> XCHK[Concordance: what the picture<br/>predicts vs what was measured]
        TYM[/api/tympanometry/] --> CURVE[Peak · gradient · canal volume<br/>8 types · age-banded norms<br/>· curve from ECV/PP/SC/GRAD]
        OAE[/api/oae/] --> DPG[DP-gram · protocol pass/refer<br/>· cochlear place]
        EP[/api/aep/] --> EPN[Latency vs norms for the intensity used<br/>· interpeaks · Wave V threshold<br/>· MLR patterns · P1 maturation]
        EPN --> LVL[Where along the pathway<br/>brainstem / thalamus / cortex]
        BOAAPI[/api/boa/] --> MRL[Minimum response levels by age<br/>· never a threshold]
        TFA[/api/tuning-fork/] --> TFG[Crossover ladder brackets the gap<br/>· Rinne x Weber grid<br/>· false-negative Rinne]
        TFG --> BAT
        AN[/api/analyze/] --> RULES[Clinical Rules Engine<br/>WHO 2021 · ABG typing<br/>· RPwD Gazette ready reckoner]
        AN --> ML[RandomForest + calibration<br/>+ IsolationForest OOD<br/>+ per-frequency explanation]
        AN --> PHON[Phoneme audibility · SII<br/>quiet / noise / aided]
        AN --> BAT[Cross-modal battery review]
        RX[/api/prescription/] --> NAL[NAL-R gains<br/>+ word-level audibility]
        DIG[/api/digitize/] --> CV[OpenCV grid + symbol SHAPE recognition<br/>O X triangle square &lt; &gt; [ ]<br/>works on black-and-white charts]
        RPT[/api/digitize/report/] --> PAGE[Locate the chart on a report page<br/>+ printed fields, or crops to confirm]
        REP[/api/report/] --> ENGINE{AI mode?}
        ENGINE -- offline --> TPL[Template engine<br/>+ deterministic verifier]
        ENGINE -- api --> LLM[Gemini / OpenAI / Claude / Groq /<br/>OpenRouter / Ollama<br/>generator → verifier]
        PROGAPI[/api/progression/] --> OSHA[OSHA STS + ASHA criteria<br/>+ exposed vs protected forecast]
        PDF[/api/pdf/] --> RL[reportlab + QR verification hash]
        CURVE & DPG --> BAT
        LVL --> BAT
    end

    Frontend -- REST --> Backend
    LLM -. any failure .-> TPL
```

## 🚀 Run it (Windows-friendly)

Prereqs: Python 3.11+, Node 18+.

**1. Backend** (first run: ~2 min for deps + ~1 min training)

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m app.ml.generate_dataset
.venv\Scripts\python -m app.ml.train
.venv\Scripts\python -m app.ml.deep
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

**1b. Create an account** — the instance ships **locked**

The app holds patient records, so it fails closed: with no accounts configured
every `/api` request is refused with a 503 and the frontend shows a sign-in
screen nobody can get past. Mint one before the first run:

```bash
cd backend
.venv\Scripts\python -m scripts.make_user clinician
```

Paste the two values it prints into `backend/.env` (gitignored; the app reads it
at startup):

```
AUDIOSENSE_USERS=clinician:pbkdf2_sha256$600000$...$...
AUDIOSENSE_SECRET=<the long random value the script printed>
```

Restart uvicorn. Full details — sessions, revocation, the public allowlist — are
in [DEPLOYMENT.md](DEPLOYMENT.md#access-control--do-this-before-the-first-deploy).

**2. Frontend** (second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** and sign in with the account you just created. No
API key needed — everything works offline. To enable LLM narratives, click the
**AI Engine** panel (bottom-left gear) and paste a free Gemini key from
[aistudio.google.com](https://aistudio.google.com).

**Tests** (2,245 tests across 48 files, all passing at the last full run: guideline conformance swept across the whole input space, reproducibility, red-flag and masking logic, speech audiometry with its binomial intervals, ABR normative-table integrity, BOA age banding, tuning-fork grid completeness, tympanogram curve round-trips, triage routing, validation metrics, progression, phonemes, SII, NAL-R prescription, forecast, counterfactuals, camp statistics, six-language counseling, digitizer-vs-ground-truth, full API cycle):

```bash
cd backend
.venv\Scripts\python -m pytest -q
```

Training artifacts land in `backend/data/`: `confusion_matrix.png` + `accuracy_report.txt` (99.9% hold-out accuracy on 12,000 synthetic audiograms).

## 🎬 3-minute demo script

**0:00 — The hook.** "One in five people has hearing loss; audiologists are scarce. AudioSense takes a patient from the sentence they walk in with to a signed clinical interpretation." Open **Signs & Symptoms**, click *Water discharge from the ear*, press **Assess**: chronic suppurative otitis media leads, cholesteatoma sits below it, and the battery is ordered otoscopy → pure tones → tympanometry. Now change the age to 72 and add *diabetes* — the page turns amber for **necrotizing otitis externa**, a skull-base infection. "Same complaint. Different disease. The age is the diagnosis."

**0:10 — The one nobody else catches.** Load **🔬 Pre-clinical Noise Damage**. The verdict banner answers before you read anything else: *"Hearing thresholds are still normal, but the cochlea is already being damaged — this loss is still preventable."* The audiogram is completely normal; the tympanogram is Type A, so the middle ear is not what silenced the emissions; emissions are absent at 4 and 8 kHz. "Every conventional screening in the country would send this welder back to the shipyard."

**0:25 — The save.** Load the **🚨 Sudden Asymmetric Loss** demo case. The dashboard opens with a pulsing red banner: *possible sudden sensorineural hearing loss — steroids are time-critical*, plus an asymmetry flag recommending MRI and a rollover finding suggesting retrocochlear pathology. Say it plainly: "most audiogram tools would have called this 'moderate sensorineural loss' and booked a hearing-aid fitting."

**0:35 — Snap-to-Digitize.** Drag `samples/audiogram_photo_1.png` onto the drop zone. Watch the paper chart become editable thresholds with confidence badges — point out the *human-in-the-loop* banner (OpenCV, fully offline). Click **Analyze →**.

**0:50 — Look in the ear.** With the conductive case loaded, open **Otoscopy** and click an *otitis media* reference view. Two things on screen: the differential with its **measured accuracy stated in the banner** — "we tell you that on photographs it has not seen it names the exact pattern about a quarter of the time, because it does" (17 of 62 views, 27%, 95% CI 15–42%, against 12.5% chance) — and beside it the three closest labelled reference images for the clinician to judge.

Then scroll to **Case linkage — 4 of 4 links active**. The image says otitis media; the history the patient gave independently ranks acute otitis media; the 32.5 dB gap matches; the Type B trace matches. Now click a *normal* reference view instead and watch it turn amber: **⚠ symptoms the appearance does not explain** and **⚠ conductive loss with a normal-looking drum**. "The image link uses the classifier's label, so an agreement only corroborates a pattern match we have not validated — but a conflict is worth a look whichever side is wrong. It is four findings arguing with each other, and a clinician cannot get that from any one of them alone."

**1:10 — The curve, not the number.** Open **Immittance & OAE** and pick *Early effusion (broad peak)*. Peak height is normal, compliance is normal — and the **tympanometric width is 199 daPa against a ceiling of 114**, flagged. "Three numbers on a printout call this a Type A. The width of the curve flags a possible early effusion." Switch to *Perforation*: canal volume 2.8 cm³, flagged as a hole. Below, the DP-gram on *Pre-clinical noise damage* — emissions gone from 3 kHz up, mapped to the **basal turn of the cochlea**.

**1:00 — Dashboard.** The audiogram renders with correct clinical notation; the **teal glow at 4 kHz** shows what drove the AI's "Noise notch" call. Open **Why this classification?** — *"if 4000 Hz were 30 dB better, this would classify as flat"*, and 12 of 12 nearest reference cases agree. Walk the cards: WHO degree, type via air-bone gap, **RPwD disability % with the full formula expanded**, the cochlea map showing the lesion at the basal turn. Report carries the **verified ✓** badge.

**1:40 — Toggle Phonemes.** The speech banana appears; /s/, /f/, /th/ glow red — "he'll miss plurals and children's voices."

**1:55 — The showstopper.** Click **🎧 Hear as this patient**. Play on *Normal*, flip to *This Patient* — the 4 kHz world vanishes and captions strike out the words he loses. Hit **With Hearing Aid**: struck words return; on the dashboard the right ear's SII goes 65% → 81% aided. Then switch the aid to **Cheap amplifier** — everything gets louder, clarity doesn't come back. Turn on **Restaurant noise** and drag the SNR slider to 0 dB: this is the complaint every patient actually has. Finally tap **🚨 Smoke alarm** — for this patient, it is gone.

**2:25 — Prevention.** Progression page: OSHA STS flagged after 3 years of noise exposure — on the labelled 2k/4k proxy, since the sample has no 3000 Hz threshold; the 5-year projection shows *Moderate if exposure continues* vs *Mild with protection* — **15.6 dB of preventable hearing** in the right ear, and a projected disability of 15% against 1% now (a projection, never certifiable).

**2:25 — The Listening Lab.** Hand a judge headphones and open **Spatial hearing**. On *normal ears* they place the noise burst easily. Switch to *this patient's ears* — with the asymmetric case the sound now seems to come from the good side no matter where it actually is, and their localization error triples. "This is why he steps into traffic." Then **Speech in noise** — the digit test that flags a clean audiogram with real difficulty in noise (its cut-offs are provisional until calibrated for this browser test) — and **Tinnitus**, matched and then notched live.

**2:40 — Scale + reach.** Batch page: 8-patient CSV clears in **5 seconds — 89 audiograms a minute** — and comes back as a *worklist*: two flagged for an audiologist, six drafts auto-releasable. Then **🔬 Validate vs expert labels** with the labelled sample: ML pattern 11 of 12 (95% CI 65–99%), rules 12 of 12 — "these twelve cases were written by our team, so this proves the harness works, not that the model is accurate; the number to quote comes when a clinic's own labelled audiograms go through it, and it will not be 99.9%." Camp view adds *"25% of this cohort shows a 4 kHz noise notch with hearing loss at 4 kHz (Coles et al. 2000 criteria)"*. Counseling in six languages, read aloud, or handed over as a **QR the patient scans onto their own phone**. The **Screening Test** page measures a judge's own hearing live into the same pipeline. Installable and offline-capable; add any LLM key for narrative reports, with automatic fallback so the demo can't die.

**2:55 — Close.** "Deterministic clinical core, calibrated ML with an honesty flag, and empathy you can hear. AudioSense AI."

## 📁 Repo map

```
backend/
  app/clinical/    rules.py (WHO/ABG/RPwD, cited docstrings) · progression.py (OSHA/ASHA)
                   safety.py (red flags + masking validity) · speech_audiometry.py (SRT/WRS/rollover)
                   triage.py (priority + auto-release routing)
                   norms.py (ISO 7029:2000 age norms — computed, not shown
                             on the Results page)
                   listening_lab.py (localization · speech-in-noise · tinnitus)
                   immittance.py (tympanograms + reflexes) · oae.py (emissions)
                   masking.py (two AC rules · BC gap · transducers · plateau
                               · masking dilemma)
                   speech_audiometry.py (SDT · SRT · WRS · binomial intervals
                                        · rollover · ear comparison)
                   tympanometry.py (8 types · gradient · notch detection · age norms
                                    · generated reference curves · probe-tone guard)
                   dpoae.py (DP-gram · protocols · cochlear place)
                   aep.py (ABR normative table by intensity · z-scores · interpeaks
                           · insert delay · Wave V threshold · asymmetry · cochlear
                           microphonic · MLR patterns · LLR + P1 maturation
                           · where-along-the-pathway battery)
                   tuning_fork.py (Rinne crossover ladder · gap bracketing
                                   · Weber x Rinne grid, 12 cells, 5 precedence
                                   layers · false-negative Rinne · Bing/ABC/
                                   Schwabach/Gelle · audiogram cross-check)
                   boa.py (8 age bands of minimum response levels · response
                           repertoire · habituation and observer-bias flags
                           · never a threshold)
                   symptom_kb.py (complaint guide by age · 15 conditions (14
                                  supplied + SSNHL from AAO-HNS 2019) · red flags
                                  · otoscopy↔disease, 8 tympanogram↔disease rules
                                  · a characteristic audiogram per disease)
                   symptoms.py (synonym matching · ranked differential · battery)
                   linkage.py (image↔history↔audiogram↔immittance reconciliation)
                   consistency.py (cross-modal reconciliation) · noise_dose.py (OSHA/NIOSH)
                   correlation.py (checks BETWEEN modalities no one module
                                   could make: emissions↔AEP, AEP↔behavioural,
                                   otoscopy↔emissions, forks↔tympanogram,
                                   BOA↔thresholds)
                   prescription.py (NAL-R + aided verification) · forecast.py (5-year projection)
  app/otoscopy/    taxonomy.py (8 patterns + audiological consequence)
                   features.py (field of view · colour · cone of light · polar layout)
                   model.py (training · leave-one-source-photograph-out validation
                             · retrieval · concordance)
  app/ml/          generate_dataset.py · features.py · train.py
                   classifier.py (calibration · OOD · counterfactuals · case retrieval)
  app/services/    phonemes.py · sii.py (SII + word audibility)
                   vision.py (grid + symbol-SHAPE recognition, colour as
                              corroboration; reads black-and-white charts)
                   symbols.py (the 8 clinical symbols from their geometry)
                   report_scan.py (locate the chart on a whole report page,
                                   read or crop the printed fields)
                   report.py (template+LLM, verifier) · languages.py (6 languages)
                   records.py (SQLite visits) · referral.py (ENT letter)
                   validation.py (expert-label agreement, Cohen's kappa)
                   llm_provider.py (6 providers) · ai_config.py · pdf.py (QR hash)
                   auth.py (PBKDF2 accounts · signed session tokens · allowlist)
  app/routers/     analyze · prescription · speech-words · digitize (+ /report,
                   a whole scanned page) · report · report-view (what the PDF's
                   QR opens) · progression
                   batch · pdf · settings · feedback · handout (QR) · clinic (records,
                   noise-dose, referral, atlas) · otoscopy · symptoms · instruments
                   (tympanometry + oae) · linkage · speech · masking
                   aep (ABR/MLR/LLR/battery + BOA) · tuning-fork · diagnosis
                   auth (login + the default-closed middleware every route sits behind)
  data/            otoscope_reference/ (62 labelled views, 8 patterns, ~1.3 MB)
                   otoscopy_model.joblib + model card
  tests/           2,245 pytest tests incl. boundary values (PTA 20/35/50/65/80/95,
                   ABG 10, the RPwD ready reckoner's 59→60 dB step)
  scripts/         make_user.py (mints an account hash for AUDIOSENSE_USERS)
                   make_samples.py (regenerates the demo photos + ground truth)
                   extract_otoscope_reference.py (docx → labelled atlas)
                   train_otoscopy.py · fetch_otoscope_dataset.py
samples/           2 audiogram photos + ground_truth.json + batch_sample.csv
frontend/
  src/pages/       Login (the gate) · Patient (step 1 — demographics, age, onset)
                   Symptoms · Otoscopy · NewTest · Screening · Immittance
                   EvokedPotentials · Dashboard · Simulator · ListeningLab
                   Progression · Batch · Records
  src/components/  ... SpeechAudiometry (P-I function with binomial whiskers)
                   MaskingPanel (per-frequency grid · plateau · dilemma)
                   BOAPanel (developmental MRL curve, under the pure-tone form)
                   TuningForkPanel (crossover ladder · implied gap band drawn
                                    against the measured gap)
  src/components/  AudiogramChart (clinical symbols, glow, banana) · CochleaMap (Greenwood)
                   ThresholdGrid · AISettingsPanel
  src/audio/       simulatorGraph.js (loss + aid + compression + babble + binaural)
                   soundscapes.js (synthesized everyday sounds) · toneAudiometer.js
                   bayesianThreshold.js (QUEST/ZEST + catch trials)
  src/lib/         api.js · store.jsx · flow.js (the seven-step consultation order)
                   speech.js (6-language TTS) · conversation.js
                   svgCapture.js
  public/          audio/speech_sample.wav · sw.js (offline) · manifest.webmanifest
```

## ⚕️ Clinical grounding

- **PTA & degree**: 4-frequency average (500/1k/2k/4k), WHO World Report on Hearing (2021) grades, including its top grade: *complete or total* at 95 dB HL or more (profound is 80 to < 95).
- **Type**: air-bone gap > 10 dB significant; Conductive/Sensorineural/Mixed per standard audiological criteria. An AC PTA ≥ 20 dB HL is a loss (WHO Mild); normal air conduction with a gap > 10 dB is typed Normal, and the gap is reported in `air_bone_gap_note`. Bone-conduction no-response frequencies are excluded from the gap and make the type provisional; missing BC → *"type provisional — BC not tested."*
- **Disability**: Gazette of India S.O. 76(E), 4 Jan 2018, paras 20.2.2–20.2.3. PTA of 500/1k/2k/4k Hz per ear, with a no-response taken as 95 dB (a measured threshold above 95 is not capped). Monaural % from the Gazette ready reckoner: 0–25 dB → 0%, 26–33 → 1%, 34–59 → PTA − 32, 60 → 40%, 61–94 → 40 + 1.71 per dB, ≥ 95 → 100%, entered at the PTA rounded to the nearest whole dB (halves up). Binaural (5 × better + poorer) / 6. Benchmark ≥ 40%, reached exactly when the better ear is 60 dB or more. Flagged *not certifiable* when any of the four frequencies is untested. S.O. 1338(E) (12 Mar 2024) supersedes S.O. 76(E); secondary sources describe the same method, but its primary text could not be retrieved, so the method is unconfirmed against the 2024 guidelines.
- **Progression**: OSHA 1910.95(g)(10) standard threshold shift on 2/3/4 kHz when 3000 Hz is supplied (`thresholds_3000` on `/api/progression`), otherwise on a labelled partial-average proxy that states the 3000 Hz shift that would change the result. OSHA 300 Log recordability follows 29 CFR 1904.10(a): an STS plus a current hearing level of 25 dB HL or more; it is settled only when the frequencies tested decide it, otherwise *met on proxy* or *undetermined*, with the 3000 Hz value needed. ASHA (1994) ototoxicity criteria.
- **Red flags**: sudden SNHL = a sensorineural loss of ≥30 dB at ≥3 consecutive frequencies within 72 h (AAO-HNSF; Chandrasekhar et al. 2019), read from bone conduction beneath any air-bone gap so a sudden loss on a mixed ear counts. It is measured against a prior audiogram where one exists; otherwise against the opposite ear's sensorineural thresholds (from 0 dB HL, and labelled as such, where the opposite ear was not tested), or a sensorineural PTA ≥30 dB HL qualifies — and without a prior audiogram the flag is conditional on reported onset. Asymmetry: ≥20 dB at one frequency from 0.5–4 kHz or ≥15 dB at two frequencies, in air **or** bone conduction (BAA 2023; NICE NG98), with the poorer ear outside normal limits (> 20 dB HL). MRI is recommended only for a sensorineural or undetermined asymmetry; a conductive asymmetry is referred to ENT/otology.
- **Masking**: air conduction masks when AC(test) − AC(non-test) ≥ IA **or** AC(test) − BC(non-test) ≥ IA, evaluated per frequency; interaural attenuation 40 dB supra-aural, 50–60 dB insert (50 applied), 45 dB circumaural. BSA (2018) Rule 1 uses 40 dB for supra- *or* circum-aural earphones and 55 dB for inserts, so the circumaural setting masks less often than BSA would, and the insert setting more often. Bone conduction masks at an air-bone gap ≥ 15 dB (BC crosses the skull essentially unattenuated); BSA Rule 2 masks from 10 dB, and 15 is a documented clinical-team choice, matched to the > 10 dB significance rule for typing. The minimum effective masking for air conduction is AC(TE) − IA + the non-test ear's air-bone gap + a 10 dB safety factor (after Lidén et al. 1959 and Studebaker 1964; Martin's safety factor) — the gap taken as AC(NTE) when the non-test BC is unknown — and never below AC(NTE) + 10. The bone-conduction floor is AC(NTE) plus the occlusion effect, BSA 2018 §8.8's starting level, with no safety factor. The maximum before the noise crosses back is also computed; when the minimum exceeds it the result is reported as a **masking dilemma** rather than a threshold. On supra-aural earphones a very sensitive test-ear bone threshold can be unmaskable at 250 Hz (30 dB occlusion against a minimum-IA ceiling); inserts remove this. A validity warning is raised only when masking was indicated *and* not recorded.
- **Speech audiometry**: SDT tracks the best threshold in the speech range and sits 5–10 dB better than the SRT (Chaiklin 1959; ASHA 1988); a gap of 0–4 or 11–15 dB is reported as atypical, and only a larger one, or an SDT poorer than the SRT, is flagged. The SRT agrees when it is within ±10 dB of the 500/1000/2000 Hz average or of Fletcher's best-two average (ASHA 1988; Fletcher 1950); non-organic loss is suspected only when it is more than 10 dB better than both. In a steep configuration (a step over 20 dB between neighbouring octaves) where the SRT is within 10 dB of the best single threshold, or when any of 500/1000/2000 Hz is untested, the check is reported as indeterminate. The four-frequency mean is shown for reference only. Word scores carry an exact Clopper–Pearson binomial interval and differences are tested rather than eyeballed (Thornton & Raffin 1978), and are banded after Goetzinger (1978): 90/78/66/54%; PB max is expected 30 dB or more above the SRT; the retrocochlear indicator needs BOTH halves — a rollover index > 0.45 (exactly 0.45 is borderline, not rollover; 0.35–0.45 carries an NU-6 word-list caveat after Meyer & Mishler 1985) AND a fall the word lists can resolve. The index is a ratio, so over a low PB max a difference of a few words clears the criterion on its own (6 correct falling to 3 on a 25-word list is 0.50); an index that clears it on an unresolvable drop is reported as a possible rollover to repeat with full lists, not as a referral. Each score is tested against its own list length rather than the other's, since the two ears and the two levels are often scored on different lists. Speech interaural attenuation 45 dB for the shadow-response check.
- **Immittance**: eight tympanogram types (A/As/Ad/Add/B/C/D/E) per the supplied immittance reference (Gelfand, *Essentials of Audiology*, 4th ed., pp. 187–192). Ear-canal volume 0.3–1.0 ml in children and 0.6–2.0 ml in adults; peak pressure +50 to −100 daPa; static admittance 0.35–1.25 mmho in children and 0.37–1.66 in adults; tympanic gradient > 0.2, reported as a heuristic from the reference table (no normative source found) that never changes the type — tympanometric width is the validated shape criterion (51–114 daPa adults, Margolis & Heller 1987; 60–150 children, ASHA 1997). Peak height is compensated admittance (peak minus the +200 daPa tail), and Add is decided on it, so a flat trace with a large raw admittance (a perforation at 4–5 ml) is Type B large volume, not Add. Type B splits three ways on canal volume — normal is effusion, large is perforation or a patent grommet, small is cerumen or a blocked probe. A 226 Hz probe is refused below 6 months of age, where it can read normal over a middle ear full of fluid. A 1000 Hz trace is read from recorded points by the Baldwin (2006) / BSA (2024) §11.2 baseline method: it passes only with at least 0.60 mmho from the −400 daPa tail to the main peak (Margolis et al. 2003); a flat or trough-shaped trace, or no identifiable peak, refers; above 4.3 mmho (the 95th percentile) it is not reported as normal; a sweep short of +200 to −400 daPa, or with missing points, is never more than provisional; and ear-canal volume, width and gradient are not reported at 1000 Hz, so an infant trace never yields a cerumen, perforation or otosclerosis verdict. The test battery (`/api/analyze`) records no probe tone and only whole-year ages, so every patient under 12 months gets the infant probe-tone caveat there: the tympanogram is provisional or untyped, reflexes are provisional, and a validity alert asks for a 1000 Hz probe (JCIH 2019).
- **OAE**: DPOAE counted present when ≥6 dB above the noise floor and at least −5 dB SPL, with the noise floor at or below −5 dB SPL (BSA 2023). A noisier frequency is inconclusive — never pass, refer or damage — and a repeat leads the next step only where an emission was expected (threshold ≤ 20 dB HL or none recorded, in an ear the audiogram grades normal); elsewhere it is reported as information. Absent emissions with normal thresholds are pre-clinical outer-hair-cell damage only behind a confirmed normal middle ear (Type A, no air-bone gap); without a tympanogram they are a possible finding to confirm with tympanometry, and behind an abnormal middle ear they are explained by it. Absent emissions where the threshold already exceeds ~50 dB HL are marked *uninformative* rather than counted as damage.
- **Tuning forks**: the Rinne reversal crossover by fork — 256 Hz at an air-bone gap of about 15 dB, 512 Hz at 20–30, 1024 Hz at 45–50 — reported as bands with medium confidence, because sources disagree and the empirical 512 Hz transition sits below the textbook figure. No crossover exists for 2048 or 4096 Hz and none is extrapolated. The Bing and Gelle are restricted to 256 and 512 Hz, where the occlusion effect is large; from 1 kHz upward "no change" is the normal finding and is marked uninterpretable rather than negative (occlusion-effect frequency dependence after Dean & Martin 2000: 9 dB at 250 Hz, 7 at 500, 0 at 1000). Bone conduction crosses the skull essentially unattenuated, which is the mechanism of the false-negative Rinne. Method and placement follow StatPearls *Rinne Test* (NBK431071), *Weber Test* (NBK526135) and *Bone Conduction Evaluation* (NBK578177). **No sensitivity or specificity figure is quoted**, because none could be verified.
- **Evoked potentials**: ABR absolute latencies compared against the supplied reference's normative table (Table 2-3, normal-hearing females 20–30) for the **stimulus intensity actually used**, interpolated between rows and reported in standard deviations: delayed beyond 3 SD, borderline at 2–3 SD (ACNS Guideline 9C), with a 0.15 ms allowance on a man's later waves; the stored means and SDs are verified to regenerate the reference's own published range table. Under 3 years no adult limit decides the result — a value beyond it is indeterminate. Interpeak I–III, III–V and I–V lead the interpretation, since a conductive loss shifts all waves equally and leaves the intervals intact; they are judged against adult upper limits of 2.5 / 2.4 / 4.5 ms (Chiappa 1979; Misra & Kalita 2008), with an I–V above the adult 95% limit (women 4.34, men 4.46 ms; Lightfoot 1992 / BSA 2019) reported as borderline. A delayed absolute latency is read as peripheral only when Wave I is itself late and I–V is normal; with Wave I on time, retrocochlear pathology cannot be excluded. Insert-earphone delay 0.9 ms applied explicitly. Interaural Wave V difference significant at 0.4 ms uncorrected; when both 4 kHz thresholds are known it is Selters & Brackmann-corrected and significant above 0.37 ms (borderline 0.2–0.37 ms); it is computed only between runs at the same level, and refused when the click is less than 10 dB above an ear's 4 kHz threshold (BSA 2019 §7.6). A cochlear microphonic with no Wave V is the auditory-neuropathy pattern; beside a normal ABR it is a normal pre-neural potential and is not flagged. Wave V is tracked down the intensity series for an *electrophysiological* threshold, reported in dB nHL with de Jager's typical nHL-to-eHL correction (tone burst 20/15/10/10 dB; click 0–5 dB as a range), which approximates the behavioural one and is not a substitute for it. MLR Na–Pa–Nb–Pb and LLR P1–N1–P2–N2 against normative windows (Hall 2007; Katz et al.; Musiek & Baran; Atcherson & Stoody 2012); P1 is judged against the Sharma, Dorman & Spahr (2002) normal-hearing fit (155.6 − 32.746 ln age ms, 95% limits ±32 ms) from 0.1 to 20 years, and the adult N1/P2/N2 windows and the N1-absent flag are not applied under 12 years. The LLR is state-dependent and the app says so.
- **Behavioural observation audiometry**: minimum response levels by age band after Northern & Downs, *Hearing in Children* — 78 dB warble at birth falling to 26 dB, with the speech MRL alongside. The levels are labelled dB SPL, but whether those norms are dB SPL or dB HL (re audiometric zero) is unverified — they are often quoted as dB HL — and every BOA result carries that caveat. **Never reported as a threshold**: MRLs run tens of decibels above true threshold, are neither ear- nor frequency-specific, and habituate within a session. Visual reinforcement audiometry replaces BOA from 6 months, and concern routes to ABR/ASSR rather than to more BOA.
- **Symptom differential**: two supplied clinical documents — a presenting-complaint guide ranked by age band (otorrhoea, otalgia, vertigo, headache) and a 14-disease reference giving symptoms, prone age group and the audiological tests that establish each diagnosis — plus one condition, sudden sensorineural hearing loss, encoded from the AAO-HNS Clinical Practice Guideline (Chandrasekhar et al. 2019) and marked with that source. Ranking also applies, all declared in `symptom_kb.py`: per-condition age ranges; a commonness weight, never applied to red-flag conditions; an adult-CAPD neurological-history gate that phases in from 18; one exclusion on a guide cause (vestibular neuritis with a sudden loss, Bárány Society 2022); onset-aware matching for the two acute guide causes; and, per condition, declared distinguishing features that decide whether it may replace a leader the audiogram contradicts. Free text is matched by synonym table, not inferred; unmatched words are reported back. Every ranked entry names which source put it there.
- **Snap-to-Digitize**: each mark is identified by its SHAPE across the standard symbol set (ASHA; BSA pure-tone audiometry) — O and △ for right air unmasked and masked, X and □ for left, < and [ for right bone, > and ] for left — which gives the ear, the conduction and the masking without relying on the chart being printed in colour. The bone-conduction set has a geometric regularity the classifier uses: every right-ear mark opens to the right and every left-ear mark to the left, so the opening direction gives the ear and the presence of a vertical spine gives masked versus unmasked. A mark whose features do not clearly separate one symbol is reported as unidentified rather than filed under whichever scored a hair higher. Two physiological guards reject misreadings rather than reporting them: a bone threshold more than 15 dB poorer than air at the same frequency is dropped (a negative air-bone gap beyond test-retest is a misread mark, not a finding), and a marginal shape in the bottom 10 dB of the chart is dropped because that strip is where a chart prints its legend — which often spells the symbol set out literally.
- **Otoscopy**: eight patterns from the supplied reference document, with each pattern's *expected* air-bone gap and tympanogram recorded so the image can be checked against the measured battery. The classifier is validated holding out every view cut from the same source picture (62 views from 22 photographs): 27% top-1 (17/62, 95% CI 15–42% by source photograph) against 12.5% chance — above chance with a wide interval, far below diagnostic — and attic perforation, marginal perforation, masses and retraction are essentially never identified on photographs it has not seen. The figures are shown in the app, alongside what it cannot do; a view-level figure of ~44% is kept only as the labelled *optimistic* comparison.
- **Cross-modal linkage**: each otoscopic pattern declares the symptoms it should produce and the ones it cannot account for; each disease declares its expected audiometric type, PTA range and laterality; each of the five Jerger types declares the diseases it supports and the ones it excludes. Every cross-check quotes the rule that produced it. Degree comparison uses a ±5 dB test-retest tolerance and reports *borderline* rather than claiming a value outside the range is inside it.
- **Bayesian screening**: QUEST/ZEST posterior with a logistic psychometric function (4.5 dB slope, 2% guess, 3% lapse), stopping on a 10 dB credible interval, and reporting the lowest 5-dB step at or above the posterior median (ASHA 2005), or NR when the 90 dB tone goes unanswered. Benchmarked against the staircase over 1,000 simulated listeners (12,000 thresholds; 4 dB spread, 3% lapses, 2% false alarms), each scored against the listener's clinical threshold — the lowest 5-dB step heard at least half the time (ASHA 2005): 9.3 vs 10.6 presentations, 1.8 vs 2.2 dB mean absolute error, bias +0.0 vs +0.3 dB, and 0.16% vs 0.03% of thresholds off by more than 10 dB. The gain is calibrated uncertainty, not raw speed.
- **Noise dose**: OSHA 29 CFR 1910.95 (90 dBA, 5 dB exchange) and NIOSH 1998 (85 dBA, 3 dB exchange); protector attenuation derated as (NRR − 7) / 2. The OSHA PEL dose counts only sound at or above 90 dBA and is exceeded only above 100%; the action-level dose counts sound from 80 dBA, and a hearing conservation programme is required from 50%; NIOSH counts sound from 80 dBA. Doses are shown rounded up to 0.1% and judged on the figure shown. The "OSHA dose" field (`osha_dose_pct`) is the action-level dose; `osha_pel_dose_pct` is the PEL dose.
- **Prescription**: NAL-R insertion gain (Byrne & Dillon 1986), applied at every tested band of an ear in which any threshold reaches 20 dB HL (WHO 2021 mild loss); negative targets are set to zero and gains are capped at 45 dB. An ear with every threshold below 20 dB HL is not fitted, and an ear with a loss but no 500/1000/2000 Hz threshold is reported as not prescribable rather than given zero gain. Aided verification tolerances ±10 dB against target.
- **SII**: band-importance-weighted audibility simplified from ANSI S3.5-1997; reported as *share of speech cues audible*, never as a predicted word score.
- **Screening**: modified Hughson-Westlake (ASHA 2005) with ISO 389-1 RETSPL frequency corrections and a user calibration anchor — labelled a screening, not a diagnostic audiogram.
- **Forecast**: linear extrapolation vs an ISO 7029-style age-only scenario, shown with an uncertainty band and an explicit "not a validated prognosis" caveat.
- **"No Response"** computes as 120 dB HL and is flagged in every result it touches, with two exceptions: the RPwD disability, where the Gazette fixes it at 95 dB, and the air-bone gap, where a bone-conduction NR makes the gap indeterminate and that frequency is excluded.

Every one of these is presented with its limits stated in the UI, because a hackathon
demo that overclaims on a medical number is worse than one that admits what it can't know.

> AI-assisted interpretation; final diagnosis requires a qualified audiologist.
