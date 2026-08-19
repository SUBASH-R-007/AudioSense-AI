// The guided tour — the whole product, in the order a consultation runs.
//
// This exists because the app is now thirteen screens and a clinician should
// not have to guess which one comes next, or discover the tuning-fork bracket
// by opening a collapsed section nobody mentioned. The tour walks the actual
// flow: who the patient is, what they complain of, what the ear looks like,
// what the measurements say, what the battery concludes, and what is still
// missing.
//
// Three things it does that a list of tooltips would not.
//
//   IT LOADS A CASE FIRST. Half the app renders nothing without an analysis —
//   the dashboard, the cochlea map, the linkage panel. A tour that spotlights
//   empty boxes teaches nothing, so it seeds a demo case before it starts and
//   says that it has.
//
//   IT SURVIVES A MISSING TARGET. Panels appear conditionally: red flags only
//   when there are red flags, masking only when masking was indicated. A step
//   whose anchor is absent is skipped rather than left pointing at nothing.
//
//   IT ADMITS THE LIMITS. The last chapter is the honest one — synthetic
//   training data, a 22-photograph otoscopy atlas, screening thresholds that
//   are not diagnostic. A tour that only sells is a brochure.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, apiUrl } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

/** Chapters, in flow order. `at` is the route; `on` is the anchor to spotlight. */
const STEPS = [
  // ---------------------------------------------------------------- the shell
  {
    chapter: 'Getting around', at: '/patient', on: '[data-tour="flow-nav"]',
    title: 'The consultation, in order',
    body: 'Seven numbered steps, run top to bottom. A tick means recorded, a dash '
        + 'means deliberately skipped, and the bar counts how much of the battery '
        + 'is settled. You never have to remember what comes next.',
  },
  {
    chapter: 'Getting around', at: '/patient', on: '[data-tour="tools-nav"]',
    title: 'Tools sit apart',
    body: 'These belong to the clinic rather than to one patient — the simulator, '
        + 'the batch worklist, the records browser. Keeping them out of the '
        + 'numbered flow is what makes the flow readable.',
  },
  {
    chapter: 'Getting around', at: '/patient', on: '[data-tour="patient-form"]',
    title: 'Step 1 — who the patient is',
    body: 'Entered once and carried everywhere. The age is not paperwork: it picks '
        + 'the normative band a tympanogram is judged against, and under six '
        + 'months it reorders the whole battery, because there is no conditioned '
        + 'response to shape yet.',
  },

  {
    chapter: 'Getting around', at: '/patient', on: '[data-tour="ai-engine"]',
    title: 'It works with no API key',
    body: 'Every clinical judgement here is deterministic and offline — the AI '
        + 'engine only writes the narrative. Add a provider key and it will use '
        + 'one, falling back automatically if the call fails, so a demo cannot '
        + 'die because a network did.',
  },
  {
    chapter: 'Getting around', at: '/patient', on: '[data-tour="backend-status"]',
    title: 'You find out here, not later',
    body: 'The backend is polled continuously. If it goes down, or the model is '
        + 'not loaded, this says so — rather than letting you discover it '
        + 'halfway through entering a patient.',
  },

  // --------------------------------------------------------------- the history
  {
    chapter: 'Intake', at: '/symptoms', on: '[data-tour="symptom-intake"]',
    title: 'What the patient actually said',
    body: 'Free text or a checklist. "Water keeps coming out of my ear" is matched '
        + 'against a synonym table rather than guessed at, and anything it could '
        + 'not place is reported back rather than quietly dropped.',
  },
  {
    chapter: 'Intake', at: '/symptoms', on: '[data-tour="differential"]',
    title: 'Age changes the answer',
    body: 'The same discharge is acute otitis media in a child and necrotizing '
        + 'otitis externa in a diabetic of seventy. Every entry names which '
        + 'source put it there and which features are missing.',
  },
  {
    chapter: 'Intake', at: '/symptoms', on: '[data-tour="red-flags"]',
    title: 'Emergencies outrank the ranking',
    body: 'Sudden sensorineural loss is a steroid emergency with a window of days. '
        + 'Findings like that are pulled out above the differential, never left '
        + 'to be noticed partway down a list.',
  },
  {
    chapter: 'Intake', at: '/symptoms', on: '[data-tour="battery-order"]',
    title: 'Which test to do next',
    body: 'Ordered so the first test separates the most candidates — the point of '
        + 'a differential is to know what would collapse it.',
  },
  {
    chapter: 'Intake', at: '/symptoms', on: '[data-tour="step-nav"]',
    title: 'Most of this is skippable',
    body: 'No otoscope on site? Say so once. A skip records the reason, and — this '
        + 'is the part that matters — it changes nothing about the '
        + 'interpretation. "Not performed" and "performed and normal" stay '
        + 'different facts.',
  },
  {
    chapter: 'Intake', at: '/otoscopy', on: '[data-tour="otoscopy-upload"]',
    title: 'Look in the ear',
    body: 'A tympanic-membrane photo against a labelled reference atlas, returning '
        + 'a ranked differential and the three closest reference views side by '
        + 'side for you to judge.',
  },
  {
    chapter: 'Intake', at: '/otoscopy', on: '[data-tour="otoscopy-result"]',
    title: 'What the picture predicts',
    body: 'The part that does not depend on the classifier being right: what this '
        + 'appearance should produce — a large canal volume, a Type B trace, a '
        + '20–45 dB gap — checked against what was actually measured.',
  },
  {
    chapter: 'Intake', at: '/otoscopy', on: '[data-tour="otoscopy-limits"]',
    title: 'And what it cannot do',
    body: 'The measured accuracy is printed on the page, not buried in a footnote. '
        + 'The atlas is 62 crops from 22 source photographs, so the classifier is '
        + 'well above chance and well below diagnostic. The durable value is the '
        + 'retrieval, not the label.',
  },

  // ------------------------------------------------------------- the measuring
  {
    chapter: 'Measuring', at: '/new-test', on: '[data-tour="demo-cases"]',
    title: 'Start from a real case',
    body: 'Seven bundled cases, each a complete record. The tour has loaded one so '
        + 'the screens ahead have something in them.',
  },
  {
    chapter: 'Measuring', at: '/new-test', on: '[data-tour="threshold-grid"]',
    title: 'Three ways in',
    body: 'Type thresholds straight into the grid, photograph a paper audiogram, '
        + 'or measure them here in the browser. A clinic with no audiometer still '
        + 'completes this step.',
  },
  {
    chapter: 'Measuring', at: '/new-test', on: '[data-tour="digitize"]',
    title: 'Paper in, data out',
    body: 'OpenCV finds the grid and the symbols and hands back editable values, '
        + 'each with its own confidence badge. Human-in-the-loop by design — the '
        + 'grid is what gets analysed, not the photograph.',
  },
  {
    chapter: 'Measuring', at: '/new-test', on: '[data-tour="screening-launch"]',
    title: 'Or measure it here',
    body: 'A calibrated-anchor staircase, or a Bayesian estimator that stops when '
        + 'the credible interval is tight enough. The values land in the grid '
        + 'marked as screening — uncalibrated headphones, air conduction only, '
        + 'and the interface says so and keeps saying so.',
  },
  {
    chapter: 'Measuring', at: '/new-test', on: '[data-tour="tuning-fork"]',
    title: 'Forks size the gap',
    body: 'The frequency at which the Rinne reverses brackets the air-bone gap: '
        + '256 Hz alone means roughly 15–30 dB, all three forks mean 45 or more. '
        + 'A negative Rinne with the Weber lateralising the wrong way is flagged '
        + 'as a contradiction, never reported as conductive — that is a dead ear, '
        + 'not a blocked one.',
  },
  {
    chapter: 'Measuring', at: '/new-test', on: '[data-tour="boa"]',
    title: 'Infants, honestly',
    body: 'Behavioural observation gives minimum response levels, not thresholds — '
        + 'a normal newborn responds around 78 dB SPL, some 75 dB above what they '
        + 'can hear. The panel never offers to write one into the grid above.',
  },
  {
    chapter: 'Measuring', at: '/immittance', on: '[data-tour="tympanogram"]',
    title: 'Eight types, and the curve',
    body: 'Not the five-type scheme: a notched peak is a scarred drum or a broken '
        + 'ossicular chain, which "deep" loses. Type B splits three ways on canal '
        + 'volume — the small-volume case is wax against the probe, an artefact '
        + 'otherwise reported as middle-ear disease.',
  },
  {
    chapter: 'Measuring', at: '/immittance', on: '[data-tour="oae"]',
    title: 'Damage before the audiogram moves',
    body: 'Outer hair cells die before thresholds shift. Absent emissions with a '
        + 'normal audiogram is injury that is still preventable — the difference '
        + 'between screening for harm already done and harm you can stop.',
  },
  {
    chapter: 'Measuring', at: '/immittance', on: '[data-tour="speech-audiometry"]',
    title: 'A word score is a sample',
    body: '88% and 76% on a 25-word list are not different, and the app says so — '
        + 'every score carries its exact binomial interval. A detection threshold '
        + 'poorer than a reception threshold is impossible, and that is checked '
        + 'too.',
  },
  {
    chapter: 'Measuring', at: '/evoked-potentials', on: '[data-tour="aep-battery"]',
    title: 'Where along the pathway',
    body: 'ABR, MLR and LLR sample the same ascending pathway at increasing '
        + 'heights. Their value is comparative: a normal ABR under an abnormal '
        + 'MLR puts the problem above the brainstem, and neither recording says '
        + 'that alone.',
  },

  {
    chapter: 'Measuring', at: '/evoked-potentials', on: '[data-tour="abr-latency"]',
    title: 'A latency needs its intensity',
    body: 'Wave V sits near 5.4 ms at 90 dB nHL and near 7.5 ms at 20 dB, so every '
        + 'measurement is judged against the normative row for the level actually '
        + 'used. Interpeak intervals lead: a conductive loss delays every wave '
        + 'equally, a retrocochlear lesion stretches the gaps between them.',
  },

  // ---------------------------------------------------------- the interpreting
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="verdict"]',
    title: 'The answer, first',
    body: 'One plain sentence, the figures that carry the decision, and the single '
        + 'next step. Everything below it is the evidence for that sentence.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="diagnostic-picture"]',
    title: 'Is this workup finished?',
    body: 'The question a clinician asks at the end of a session. It counts what '
        + 'was done, counts the independent findings that agree, and names the '
        + 'single test that would most change the answer — a conductive loss with '
        + 'no tympanogram has no mechanism, so that is critical, not optional.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="chart"]',
    title: 'A clinical audiogram',
    body: 'Correct notation — circles and crosses, brackets for bone conduction, '
        + 'no-response arrows. Square grid by default, because that is what the '
        + 'standard asks for.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="masking"]',
    title: 'Masking, per frequency',
    body: 'An unmasked threshold can belong to the other ear. Both air-conduction '
        + 'rules are applied, and where the noise needed exceeds the level at '
        + 'which it crosses back the app reports a masking dilemma rather than '
        + 'inventing a number. Switch the transducer to see the plan change.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="battery"]',
    title: 'Do the tests agree?',
    body: 'Diagnosis comes from corroboration. Conflicts sort above agreements, '
        + 'because two tests that cannot both be true is the finding — a page of '
        + 'green ticks that buries it is worse than no panel at all.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="ml-explain"]',
    title: 'Why the model said that',
    body: 'A counterfactual — "if 4 kHz were 10 dB better this would classify as '
        + 'flat" — the nearest reference cases, and a second opinion from the '
        + 'deep ensemble. Where the two models disagree the case is ambiguous, '
        + 'and it says so instead of picking a winner.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="cochlea"]',
    title: 'Where on the cochlea',
    body: 'Greenwood frequency-place mapping puts the loss somewhere anatomical — '
        + 'a 4 kHz notch becomes a lesion at the basal turn. Right ear in red, '
        + 'left in blue.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="norms"]',
    title: 'Hearing age',
    body: '"These ears are performing like a typical 55-year-old’s — 29 years older '
        + 'than the patient." One line that does more counselling work than a '
        + 'page of decibels.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="anatomy-video"]',
    title: 'Showing the patient their own ear',
    body: 'The tympanogram already named the mechanism, so this picks the one '
        + 'animation that matches it — a flat trace at a large canal volume is a '
        + 'hole in the drum, at a small one it is wax. It says on the clip that '
        + 'it is general anatomy and not their own ear, because a patient who '
        + 'thinks otherwise has been misled by the thing meant to inform them.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="linkage"]',
    title: 'Everything cross-checks everything',
    body: 'The image against the history, the image against the audiogram, the '
        + 'history against type and degree, the tympanogram against the disease '
        + 'list. None of it depends on any single test being right.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="safety-alerts"]',
    title: 'What must not be missed',
    body: 'Sudden loss and asymmetry sort above everything else on the page. Most '
        + 'audiogram tools would have called this "moderate sensorineural loss" '
        + 'and booked a hearing-aid fitting.',
  },
  {
    chapter: 'The answer', at: '/dashboard', on: '[data-tour="disability"]',
    title: 'Entitlement, with the working shown',
    body: 'India RPwD Act 2016, with every intermediate value printed. A number '
        + 'that decides someone’s entitlement should never be a black box.',
  },

  // ----------------------------------------------------------------- the doing
  {
    chapter: 'Acting on it', at: '/dashboard', on: '[data-tour="report-actions"]',
    title: 'Report, handout, referral',
    body: 'A verified report, a counselling sheet in six languages that the patient '
        + 'scans onto their own phone, and an ENT referral letter carrying the '
        + 'exact red-flag criteria that were met.',
  },
  {
    chapter: 'Acting on it', at: '/simulator', on: '[data-tour="ab-toggle"]',
    title: 'Hear the diagnosis',
    body: 'Normal, then this patient, then aided. The audiogram becomes a live '
        + 'filter cascade and the captions strike out the words they lose. This is '
        + 'the part that changes the conversation with a family.',
  },
  {
    chapter: 'Acting on it', at: '/listening-lab', on: '[data-tour="lab-tabs"]',
    title: 'What an audiogram misses',
    body: 'Spatial hearing, speech in noise, tinnitus matching. A clean audiogram '
        + 'with real disability is a common and easily missed picture.',
  },

  // ----------------------------------------------------------------- over time
  {
    chapter: 'Over time', at: '/progression', on: '[data-tour="progression-chart"]',
    title: 'Is it getting worse?',
    body: 'OSHA standard threshold shift and ASHA ototoxicity criteria, plus a '
        + 'five-year projection of continued exposure against effective '
        + 'protection — with the preventable loss stated in decibels.',
  },
  {
    chapter: 'Over time', at: '/progression', on: '[data-tour="forecast"]',
    title: 'What is still preventable',
    body: 'Continued exposure against effective protection, with an uncertainty '
        + 'band and the preventable loss stated in decibels. Labelled a '
        + 'counselling aid, not a validated prognosis — it is linear '
        + 'extrapolation from two measurements.',
  },
  {
    chapter: 'Over time', at: '/batch', on: '[data-tour="batch-actions"]',
    title: 'Built for a queue',
    body: 'A camp generates hundreds of audiograms in a day. This returns them as '
        + 'a worklist ordered by who needs a clinician first, each case carrying '
        + 'an explicit review-or-release decision with its reasons.',
  },
  {
    chapter: 'Over time', at: '/records', on: '[data-tour="records-list"]',
    title: 'The same ear, next year',
    body: 'Longitudinal history, so hearing conservation stops being a two-point '
        + 'comparison.',
  },

  // ------------------------------------------------------------ the honest bit
  {
    chapter: 'What it cannot do', at: '/dashboard', on: '[data-tour="verdict"]',
    title: 'What this is not',
    body: 'The pattern classifier is trained on synthetic audiograms, so its '
        + 'accuracy figure measures the generator, not a clinic. The otoscopy '
        + 'atlas is 22 source photographs. Screening thresholds come from '
        + 'uncalibrated headphones. Every one of those limits is stated on the '
        + 'screen it applies to, and the final diagnosis is still an '
        + 'audiologist’s.',
  },
]

const CHAPTERS = [...new Set(STEPS.map((s) => s.chapter))]

export default function GuidedTour({ onClose }) {
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState(null)
  const [seeded, setSeeded] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const {
    analysis, setAnalysis, patient, setPatient, setAssessment, setOtoscopy,
  } = useApp()
  const seedRan = useRef(false)

  const current = STEPS[step]

  // Most of the tour has nothing to point at without a case on file: the whole
  // dashboard chapter, the differential, the otoscopy concordance. So a case is
  // loaded up front — an existing one is never overwritten, because a clinician
  // who opens the tour mid-consultation must not lose their patient to it.
  //
  // The ref is the only guard here, deliberately. An earlier version also set a
  // `cancelled` flag in the effect cleanup, which StrictMode's mount/unmount/
  // mount cycle fired immediately: the first run started the fetch, its cleanup
  // cancelled it, and the second run bailed on the ref. The seed could never
  // apply, and eleven dashboard steps silently found nothing to highlight.
  useEffect(() => {
    if (seedRan.current) return
    seedRan.current = true
    if (analysis) return

    ;(async () => {
      setSeeding(true)
      try {
        const d = await api.demoCases()
        const demo = d.cases?.find((c) => /noise notch/i.test(c.label)) || d.cases?.[0]
        if (!demo) return

        // The three modalities the tour actually points at, in parallel. Any
        // one may fail without taking the others down — a tour missing its
        // otoscopy step is still a tour.
        const [result, assess] = await Promise.all([
          api.analyze({
            patient: demo.record.patient,
            right: demo.record.right, left: demo.record.left,
          }),
          api.symptoms({
            age: demo.record.patient?.age ?? 40, side: 'right',
            symptoms: ['hearing_loss', 'tinnitus'],
            free_text: 'gradual hearing loss, ringing after factory shifts',
          }).catch(() => null),
        ])

        if (!patient) setPatient({ onset: 'unknown', ...demo.record.patient })
        setAnalysis(result)
        if (assess) setAssessment(assess)
        setSeeded(true)

        // Otoscopy needs an actual image, so it runs last and separately: it is
        // the slowest call and the least essential to the narrative.
        try {
          const atlas = await api.otoscopyAtlas()
          const src = atlas?.classes?.[0]?.images?.[0]
          if (src) {
            const blob = await fetch(apiUrl(src)).then((r) => r.blob())
            const file = new File([blob], 'reference.jpg', { type: 'image/jpeg' })
            setOtoscopy(await api.otoscopy(file, 'right', result))
          }
        } catch { /* the otoscopy step will simply be skipped */ }
      } catch {
        /* the tour still runs; panels without data are skipped and say so */
      } finally {
        setSeeding(false)
      }
    })()
  }, [analysis, patient, setAnalysis, setPatient, setAssessment, setOtoscopy])

  useEffect(() => {
    if (current && location.pathname !== current.at) navigate(current.at)
  }, [step, current, location.pathname, navigate])

  const measure = useCallback(() => {
    if (!current) return null
    const el = document.querySelector(current.on)
    if (!el) { setRect(null); return null }
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    const r = el.getBoundingClientRect()
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height })
    return el
  }, [current])

  // Measuring once is not enough. A step that changes route lands on a page
  // that may still be fetching — the evoked-potential battery runs four
  // requests before its verdict strip exists — so a single attempt at 400 ms
  // reports "nothing to highlight" for a panel that appears a moment later.
  // Retry on a short schedule and stop as soon as the anchor is found.
  useEffect(() => {
    const timers = [100, 400, 800, 1400, 2200, 3200].map(
      (delay) => setTimeout(measure, delay))
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      timers.forEach(clearTimeout)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [measure, current, location.pathname])

  const go = useCallback((delta) => {
    setStep((s) => {
      // Panels render conditionally — red flags only when there are red flags,
      // masking only when it was indicated. Walk over any step whose anchor is
      // not on the page rather than spotlighting nothing.
      let next = s + delta
      while (next > 0 && next < STEPS.length) {
        const target = STEPS[next]
        if (target.at !== location.pathname) break        // cannot know yet
        if (document.querySelector(target.on)) break
        next += delta
      }
      if (next >= STEPS.length) { onClose(); return s }
      return Math.max(0, next)
    })
  }, [location.pathname, onClose])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight' || e.key === 'Enter') go(1)
      if (e.key === 'ArrowLeft') go(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, onClose])

  const chapterIndex = useMemo(
    () => CHAPTERS.indexOf(current?.chapter), [current])

  if (!current) return null
  const pad = 8
  const below = !rect || rect.top < 260
  const panelTop = rect
    ? (below ? rect.top + rect.height + 18 : rect.top - 216)
    : 120

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true"
      aria-label={`Tour step ${step + 1} of ${STEPS.length}: ${current.title}`}>
      <div className="absolute inset-0 bg-slate-900/55" onClick={onClose} />

      {rect && (
        <div
          className="pointer-events-none absolute rounded-xl ring-4 ring-teal-400 transition-all duration-300"
          style={{
            top: rect.top - pad, left: rect.left - pad,
            width: rect.width + pad * 2, height: rect.height + pad * 2,
            boxShadow: '0 0 0 9999px rgba(15,23,42,0.55)',
            background: 'transparent',
          }}
        />
      )}

      <div
        className="absolute left-1/2 w-[min(30rem,calc(100vw-2rem))] -translate-x-1/2 rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl transition-all duration-300 sm:left-auto sm:translate-x-0"
        style={{
          top: Math.max(16, Math.min(panelTop, window.innerHeight - 260)),
          ...(rect && window.innerWidth >= 640
            ? { left: Math.max(16, Math.min(rect.left, window.innerWidth - 512)) }
            : {}),
        }}
      >
        {/* Chapter rail — a thirty-step tour needs to show where it is. */}
        <div className="flex flex-wrap items-center gap-1">
          {CHAPTERS.map((c, i) => (
            <span key={c}
              title={c}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i < chapterIndex ? 'bg-teal-500'
                  : i === chapterIndex ? 'bg-teal-400' : 'bg-slate-200'}`} />
          ))}
        </div>

        <div className="mt-2.5 flex items-baseline justify-between gap-2">
          <span className="text-[10px] font-bold uppercase tracking-widest text-teal-700">
            {current.chapter}
          </span>
          <span className="font-mono text-[10.5px] text-slate-400">
            {step + 1} / {STEPS.length}
          </span>
        </div>

        <h2 className="mt-1 text-[16px] font-semibold tracking-tight text-slate-900">
          {current.title}
        </h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-slate-600">
          {current.body}
        </p>

        {seeding && (
          <p className="mt-2.5 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[11.5px] text-slate-500">
            Loading a demo case so every screen has something to show…
          </p>
        )}
        {seeded && !seeding && step === 0 && (
          <p className="mt-2.5 rounded-lg bg-teal-50 px-2.5 py-1.5 text-[11.5px] leading-relaxed text-teal-800">
            A demo case has been loaded so every screen has something to show.
          </p>
        )}
        {!rect && (
          <p className="mt-2.5 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[11.5px] leading-relaxed text-slate-500">
            This panel only appears when the finding it reports is present, so
            there is nothing to highlight on this case.
          </p>
        )}

        <div className="mt-4 flex items-center justify-between gap-2">
          <button onClick={onClose}
            className="text-[12.5px] font-medium text-slate-400 transition hover:text-slate-600">
            Close
          </button>
          <div className="flex items-center gap-2">
            <button onClick={() => go(-1)} disabled={step === 0}
              className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12.5px] font-medium text-slate-600 transition hover:border-slate-300 disabled:opacity-40">
              Back
            </button>
            <button onClick={() => go(1)}
              className="rounded-lg bg-teal-600 px-4 py-1.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-teal-700">
              {step === STEPS.length - 1 ? 'Done' : 'Next'}
            </button>
          </div>
        </div>
        <p className="mt-2 text-right text-[10.5px] text-slate-400">
          Arrow keys to move · Esc to close
        </p>
      </div>
    </div>
  )
}
