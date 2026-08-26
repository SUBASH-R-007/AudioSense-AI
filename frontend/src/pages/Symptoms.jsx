// Signs and symptoms — what the patient says, before any test is run.
//
// Two ways in, because clinics work both ways: a checklist for structured
// intake, and a free-text box for "she says water keeps coming out of her
// ear". Both feed the same deterministic matcher, and anything it did not
// understand is shown back rather than silently dropped — a symptom checker
// that quietly ignores a word is how a red flag goes missing.
//
// The result is a ranked differential, not an answer, and every entry carries
// which of the two source documents put it there.

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import LinkagePanel from '../components/LinkagePanel.jsx'
import StepNav from '../components/StepNav.jsx'

const URGENCY = {
  emergency: { label: 'Emergency', cls: 'border-rose-300 bg-rose-50 text-rose-900' },
  urgent: { label: 'Urgent', cls: 'border-amber-300 bg-amber-50 text-amber-900' },
  watch: { label: 'Watch', cls: 'border-sky-300 bg-sky-50 text-sky-900' },
  routine: { label: 'Routine', cls: 'border-emerald-300 bg-emerald-50 text-emerald-900' },
  none: { label: 'Nothing entered', cls: 'border-slate-200 bg-slate-50 text-slate-600' },
}

const CATEGORY_STYLE = {
  emergency: 'bg-rose-100 text-rose-700',
  unsafe: 'bg-rose-100 text-rose-700',
  neoplasm: 'bg-rose-100 text-rose-700',
  acute: 'bg-amber-100 text-amber-700',
  chronic: 'bg-sky-100 text-sky-700',
  guide: 'bg-slate-100 text-slate-600',
}

// One hue per symptom group, so "three amber chips lit" reads as a discharge
// story at a glance. Keys match the group names the catalog endpoint emits;
// anything it grows later falls back to the app's own teal. Selection is
// never colour alone: a selected chip changes fill, border AND weight, and
// carries aria-pressed. Full literal class strings throughout — Tailwind's
// scanner cannot see classes assembled at runtime.
//
// Fills are the 700 shades: every one keeps white 12px text above the WCAG AA
// 4.5:1 line, which the lighter 500/600s of amber and cyan do not.
const GROUP_STYLES = {
  'Discharge': {
    dot: 'bg-amber-500',
    selected: 'border-amber-700 bg-amber-700 font-medium text-white',
    unselected: 'border-amber-200 bg-white text-slate-600 hover:border-amber-400',
  },
  'Pain': {
    dot: 'bg-rose-500',
    selected: 'border-rose-700 bg-rose-700 font-medium text-white',
    unselected: 'border-rose-200 bg-white text-slate-600 hover:border-rose-400',
  },
  'Hearing': {
    dot: 'bg-sky-500',
    selected: 'border-sky-700 bg-sky-700 font-medium text-white',
    unselected: 'border-sky-200 bg-white text-slate-600 hover:border-sky-400',
  },
  'Ear noise': {
    dot: 'bg-violet-500',
    selected: 'border-violet-700 bg-violet-700 font-medium text-white',
    unselected: 'border-violet-200 bg-white text-slate-600 hover:border-violet-400',
  },
  'Balance': {
    dot: 'bg-emerald-500',
    selected: 'border-emerald-700 bg-emerald-700 font-medium text-white',
    unselected: 'border-emerald-200 bg-white text-slate-600 hover:border-emerald-400',
  },
  'Pressure': {
    dot: 'bg-cyan-500',
    selected: 'border-cyan-700 bg-cyan-700 font-medium text-white',
    unselected: 'border-cyan-200 bg-white text-slate-600 hover:border-cyan-400',
  },
  'Systemic': {
    dot: 'bg-orange-500',
    selected: 'border-orange-700 bg-orange-700 font-medium text-white',
    unselected: 'border-orange-200 bg-white text-slate-600 hover:border-orange-400',
  },
  'Children': {
    dot: 'bg-fuchsia-500',
    selected: 'border-fuchsia-700 bg-fuchsia-700 font-medium text-white',
    unselected: 'border-fuchsia-200 bg-white text-slate-600 hover:border-fuchsia-400',
  },
  'History and exposure': {
    dot: 'bg-indigo-500',
    selected: 'border-indigo-700 bg-indigo-700 font-medium text-white',
    unselected: 'border-indigo-200 bg-white text-slate-600 hover:border-indigo-400',
  },
  default: {
    dot: 'bg-teal-500',
    selected: 'border-teal-700 bg-teal-700 font-medium text-white',
    unselected: 'border-teal-200 bg-white text-slate-600 hover:border-teal-400',
  },
}

// Each correlation line opens with the ear it describes. Colouring that first
// word red for right and blue for left is the convention the audiogram itself
// uses, and it is what lets a clinician see at a glance whether the ear that
// disagrees is the ear the history was about.
function EarLine({ text }) {
  const [first, ...rest] = text.split(' ')
  const cls = first === 'Right' ? 'font-semibold text-red-600'
    : first === 'Left' ? 'font-semibold text-blue-600' : ''
  if (!cls) return text
  return <><span className={cls}>{first}</span> {rest.join(' ')}</>
}

export default function Symptoms() {
  const { patient, analysis, assessment, setAssessment, showToast } = useApp()
  const [catalog, setCatalog] = useState(null)
  // The age band is not a detail here — it is what decides whether ear discharge
  // is otitis media in a child or necrotizing otitis externa at seventy, and
  // whether a red flag is raised at all. It therefore has to come from the
  // patient recorded at the start of the consultation. This screen runs BEFORE
  // the audiogram, so seeding it from the analysis meant it was never available
  // and every history was assessed as a 40-year-old's.
  const [age, setAge] = useState(patient?.age ?? analysis?.patient?.age ?? 40)
  const [side, setSide] = useState(patient?.side || 'unspecified')
  const [onset, setOnset] = useState('unknown')
  const [duration, setDuration] = useState('unspecified')
  const [picked, setPicked] = useState(() => new Set())
  const [notes, setNotes] = useState('')
  // The assessment is kept in the shared store, not here: the otoscopy page
  // and the dashboard both cross-check against it, and a finding that only
  // exists in one page's local state cannot be linked from another.
  const result = assessment
  const setResult = setAssessment
  const [busy, setBusy] = useState(false)
  const [correlation, setCorrelation] = useState(null)
  const [correlating, setCorrelating] = useState(false)

  useEffect(() => {
    api.symptomCatalog().then(setCatalog).catch(() => setCatalog(null))
  }, [])

  // The differential above is built from what the patient said, and nothing
  // else. Once thresholds exist the two can be held against each other: a
  // condition that predicts a conductive loss, in an ear measured as purely
  // sensorineural, is a differential that needs revisiting rather than a
  // result to be reported. The check runs itself, because a clinician who has
  // to press a button for it is a clinician who will sometimes not press it.
  useEffect(() => {
    if (!result || !analysis) { setCorrelation(null); return }
    let cancelled = false
    setCorrelating(true)
    api.correlateSymptoms(result, analysis)
      .then((r) => { if (!cancelled) setCorrelation(r) })
      .catch(() => { if (!cancelled) setCorrelation(null) })
      .finally(() => { if (!cancelled) setCorrelating(false) })
    return () => { cancelled = true }
  }, [result, analysis])

  // Coming back to the page should show the checklist that produced the
  // assessment on screen, not an empty form beside a filled-in result.
  useEffect(() => {
    if (!assessment) return
    setPicked(new Set((assessment.reported?.symptoms || []).map((s) => s.key)))
    setAge(assessment.age)
    setOnset(assessment.onset || 'unknown')
    setSide(assessment.side || 'unspecified')
    setDuration(assessment.duration || 'unspecified')
    // Deliberately once, on mount: re-running on every assessment change would
    // fight the user's edits between one Assess and the next.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggle = (key) => setPicked((prev) => {
    const next = new Set(prev)
    if (!next.delete(key)) next.add(key)
    return next
  })

  const canRun = picked.size > 0 || notes.trim().length > 0

  // The age stays editable because a clinician does sometimes take a history
  // about somebody other than the patient on file — the accompanying child, the
  // relative in the room. What it must never do is diverge quietly: the
  // differential below is ranked for the age in this box, not the one in the
  // record, and the two disagreeing is worth seeing.
  // This page is reachable before /patient is filled in, so the age has to
  // follow the record when it arrives — otherwise a history opened first stays
  // pinned to the fallback 40 for the rest of the consultation. Immittance
  // already re-seeds this way; without it the two screens disagree about the
  // same patient.
  useEffect(() => {
    if (patient?.age != null && patient.age !== '') setAge(patient.age)
  }, [patient?.age])

  const recordedAge = patient?.age ?? null
  const ageDiffers = recordedAge != null && Number(age) !== Number(recordedAge)

  async function run() {
    setBusy(true)
    try {
      const assessment = await api.symptoms({
        age: Number(age), symptoms: [...picked], notes, side, duration, onset,
      })
      setResult(assessment)
    } catch (e) {
      showToast(e.message || 'Assessment failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  function reset() {
    setPicked(new Set())
    setNotes('')
    setResult(null)
  }

  const urgency = URGENCY[result?.urgency] || URGENCY.none
  const band = result?.age_band?.label

  // Disagreement outranks agreement: one ear whose measured type contradicts
  // the leading diagnosis is the finding, even if the other ear fits.
  const disagrees = Boolean(correlation?.available && correlation.against?.length)
  const agrees = Boolean(correlation?.available && !disagrees
    && correlation.supports?.length)

  const examples = useMemo(() => ([
    { label: 'Water discharge from the ear', age: 34,
      symptoms: ['ear_discharge', 'hearing_loss'], notes: '' },
    { label: 'Child with fever and neck stiffness', age: 6,
      symptoms: ['fever', 'stiff_neck', 'drowsiness'], notes: '' },
    { label: 'Vertigo, ringing and fullness', age: 45,
      symptoms: ['vertigo', 'tinnitus', 'aural_fullness', 'fluctuating_hearing_loss'],
      notes: '' },
    { label: 'Factory worker, ringing in the ears', age: 45,
      symptoms: ['noise_exposure', 'tinnitus', 'speech_in_noise_difficulty'], notes: '' },
  ]), [])

  function loadExample(ex) {
    setAge(ex.age)
    setPicked(new Set(ex.symptoms))
    setNotes(ex.notes)
    setResult(null)
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">
          Signs and symptoms
        </h1>
        <p className="mt-1 max-w-3xl text-[13.5px] leading-relaxed text-slate-500">
          Record the presenting complaint and get a ranked differential, the red flags
          it raises, and the test battery that separates the possibilities — from a
          fixed clinical reference set, with no network call.
        </p>
      </header>

      <div className="mt-4 flex flex-wrap gap-2">
        {examples.map((ex) => (
          <button key={ex.label} type="button" onClick={() => loadExample(ex)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-600 shadow-sm transition hover:border-teal-300 hover:text-teal-700">
            {ex.label}
          </button>
        ))}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1.2fr]">
        {/* --- intake ---------------------------------------------------- */}
        <div data-tour="symptom-intake" className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="text-[12.5px]">
              <span className="mb-1 block font-medium text-slate-600">Age</span>
              <input type="number" min="0" max="120" value={age}
                onChange={(e) => setAge(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px]" />
            </label>
            <label className="text-[12.5px]">
              <span className="mb-1 block font-medium text-slate-600">Side</span>
              <select value={side} onChange={(e) => setSide(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px]">
                <option value="unspecified">Unspecified</option>
                <option value="right">Right</option>
                <option value="left">Left</option>
                <option value="both">Both</option>
              </select>
            </label>
            <label className="text-[12.5px]">
              <span className="mb-1 block font-medium text-slate-600">Onset</span>
              <select value={onset} onChange={(e) => setOnset(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px]">
                <option value="unknown">Unknown</option>
                <option value="sudden">Sudden</option>
                <option value="gradual">Gradual</option>
              </select>
            </label>
            <label className="text-[12.5px]">
              <span className="mb-1 block font-medium text-slate-600">Duration</span>
              <select value={duration} onChange={(e) => setDuration(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px]">
                <option value="unspecified">Unspecified</option>
                <option value="acute">Days</option>
                <option value="subacute">Weeks</option>
                <option value="chronic">Months or longer</option>
              </select>
            </label>
          </div>

          {ageDiffers && (
            <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] leading-relaxed text-amber-900">
              This history is being assessed for a {age}-year-old, but{' '}
              {(patient?.name || '').trim() || 'the patient on file'} is recorded
              as {recordedAge}. Age bands change which conditions are likely and
              which red flags apply — correct it here, or on the patient details
              step, so the differential is ranked for the right person.
            </p>
          )}

          <label className="mt-4 block text-[12.5px]">
            <span className="mb-1 block font-medium text-slate-600">
              In the patient's own words
            </span>
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="water keeps coming out of my right ear and I cannot hear"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-[13px]" />
          </label>

          <div className="mt-4 max-h-[26rem] space-y-4 overflow-y-auto pr-1">
            {catalog?.symptom_groups.map((group) => {
              const c = GROUP_STYLES[group.group] || GROUP_STYLES.default
              return (
                <fieldset key={group.group}>
                  <legend className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    <span aria-hidden="true"
                      className={`inline-block h-2 w-2 rounded-full ${c.dot}`} />
                    {group.group}
                  </legend>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {group.symptoms.map((s) => (
                      <button key={s.key} type="button" onClick={() => toggle(s.key)}
                        aria-pressed={picked.has(s.key)}
                        className={`rounded-lg border px-2.5 py-1 text-[12px] transition ${
                          picked.has(s.key) ? c.selected : c.unselected
                        }`}>
                        {s.label}
                      </button>
                    ))}
                  </div>
                </fieldset>
              )
            })}
          </div>

          <div className="mt-4 flex items-center gap-2">
            <button type="button" onClick={run} disabled={!canRun || busy}
              className="rounded-lg bg-teal-600 px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:bg-teal-700 disabled:opacity-40">
              {busy ? 'Assessing…' : 'Assess'}
            </button>
            <button type="button" onClick={reset}
              className="rounded-lg border border-slate-200 px-3 py-2 text-[13px] font-medium text-slate-600 hover:bg-slate-50">
              Clear
            </button>
            <span className="text-[12px] text-slate-400">
              {picked.size} selected
            </span>
          </div>
        </div>

        {/* --- result ---------------------------------------------------- */}
        <div className="space-y-5">
          {!result && (
            <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-[13px] text-slate-400">
              Select the presenting symptoms, or describe them, then press Assess.
            </div>
          )}

          {result && (
            <>
              <div className={`rounded-2xl border p-5 shadow-sm ${urgency.cls}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider">
                    {urgency.label}
                  </span>
                  <span className="text-[12px] opacity-80">{band}</span>
                </div>
                <p className="mt-1.5 text-[14px] font-medium leading-relaxed">
                  {result.summary}
                </p>
              </div>

              {result.red_flags.length > 0 && (
                <div data-tour="red-flags" className="rounded-2xl border border-rose-200 bg-white p-5 shadow-sm">
                  <h2 className="text-[15px] font-semibold text-rose-900">Red flags</h2>
                  <ul className="mt-2 space-y-2.5">
                    {result.red_flags.map((f) => (
                      <li key={f.id} className="rounded-lg bg-rose-50 px-3 py-2 text-[12.5px] leading-relaxed">
                        <div className="font-semibold text-rose-900">{f.title}</div>
                        <div className="mt-0.5 text-rose-800">{f.detail}</div>
                        <div className="mt-1 font-medium text-rose-900">→ {f.action}</div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.reported.unmatched.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-900">
                  <span className="font-semibold">Not recognised:</span>{' '}
                  {result.reported.unmatched.join('; ')}. These were not used — pick the
                  closest item from the checklist so nothing is lost.
                </div>
              )}

              <div data-tour="differential" className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                <h2 className="text-[15px] font-semibold text-slate-900">Differential</h2>
                <ul className="mt-3 space-y-3">
                  {result.differential.map((d, i) => (
                    <li key={d.key} className="rounded-xl border border-slate-200 p-3">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className={`text-[13.5px] ${i === 0 ? 'font-semibold text-slate-900' : 'font-medium text-slate-700'}`}>
                          {d.name}
                        </span>
                        <span className="flex items-center gap-2">
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                            CATEGORY_STYLE[d.category] || 'bg-slate-100 text-slate-600'}`}>
                            {d.category}
                          </span>
                          <span className="font-mono text-[12px] text-slate-500">
                            {Math.round(d.score * 100)}
                          </span>
                        </span>
                      </div>

                      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                        <div className={`h-full rounded-full ${i === 0 ? 'bg-teal-500' : 'bg-slate-300'}`}
                          style={{ width: `${Math.max(3, Math.round(d.score * 100))}%` }} />
                      </div>

                      {d.matched.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {d.matched.map((m) => (
                            <span key={m.key}
                              className="rounded bg-teal-50 px-1.5 py-0.5 text-[11px] text-teal-800">
                              {m.label}
                            </span>
                          ))}
                        </div>
                      )}
                      {d.missing_key_features.length > 0 && (
                        <div className="mt-1.5 text-[11.5px] text-slate-500">
                          Not reported: {d.missing_key_features.join(', ')}
                          {d.missing_defining_feature && ' — defining feature absent, so ranked down.'}
                        </div>
                      )}
                      {d.guide_complaint && (
                        <p className="mt-1.5 text-[11.5px] italic leading-relaxed text-slate-500">
                          Guide: “{d.guide_complaint}”{d.guide_note && ` — ${d.guide_note}`}
                        </p>
                      )}
                      {d.audiology_note && (
                        <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-600">
                          {d.audiology_note}
                        </p>
                      )}
                      <div className="mt-1.5 text-[10.5px] uppercase tracking-wide text-slate-400">
                        {d.sources.join(' + ')}
                        {!d.age_fit && ' · outside the usual age group'}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Sits immediately under the differential, and deliberately so:
                  the list above is the thing this card can overturn, and a
                  ranking read without the thresholds that contradict it is a
                  ranking read wrongly. It asks a narrower question than the
                  case linkage panel further down — only whether the type of
                  loss the leading diagnosis predicts is the type measured. */}
              <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                <h2 className="text-[15px] font-semibold text-slate-900">
                  Does the audiogram fit?
                </h2>
                <p className="mt-1 text-[12px] text-slate-500">
                  The leading possibility, checked against the thresholds
                  actually measured.
                </p>

                {!analysis ? (
                  <p className="mt-3 rounded-xl border border-dashed border-slate-300 px-3 py-2.5 text-[12.5px] leading-relaxed text-slate-500">
                    No audiogram in this session, so there is nothing to check the
                    differential against — it rests on the history alone. Enter or
                    import thresholds on{' '}
                    <Link to="/new-test" className="font-medium text-teal-700 underline">
                      New test
                    </Link>{' '}and this card fills itself in.
                  </p>
                ) : correlating ? (
                  <p className="mt-3 text-[12.5px] text-slate-400">Reconciling…</p>
                ) : !correlation ? (
                  <p className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-[12.5px] leading-relaxed text-slate-600">
                    The correlation could not be run. Nothing above has changed —
                    the differential still stands on the history — but it has not
                    been checked against the thresholds.
                  </p>
                ) : !correlation.available ? (
                  // Most conditions in the reference set predict no particular
                  // audiometric type, and saying so is a real answer. Dressing
                  // it up as a failure would teach the reader to distrust a
                  // card that is working exactly as intended.
                  <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                      Nothing to reconcile
                    </span>
                    <p className="mt-1 text-[12.5px] leading-relaxed text-slate-600">
                      {correlation.note}
                    </p>
                  </div>
                ) : (
                  <>
                    <div className={`mt-3 rounded-xl border px-3 py-2.5 ${
                      disagrees ? 'border-amber-300 bg-amber-50'
                        : agrees ? 'border-emerald-300 bg-emerald-50'
                          : 'border-slate-200 bg-slate-50'}`}>
                      <span className={`text-[11px] font-semibold uppercase tracking-wide ${
                        disagrees ? 'text-amber-700'
                          : agrees ? 'text-emerald-700' : 'text-slate-500'}`}>
                        {disagrees ? 'Differential worth revisiting'
                          : agrees ? 'Consistent' : 'Not enough to say'}
                      </span>
                      <p className={`mt-1 text-[13px] font-medium leading-relaxed ${
                        disagrees ? 'text-amber-900'
                          : agrees ? 'text-emerald-900' : 'text-slate-600'}`}>
                        {disagrees ? '⚠ ' : agrees ? '✓ ' : ''}{correlation.verdict}
                      </p>
                      <p className={`mt-1 text-[11.5px] leading-relaxed ${
                        disagrees ? 'text-amber-800'
                          : agrees ? 'text-emerald-800' : 'text-slate-500'}`}>
                        {correlation.diagnosis} predicts a {correlation.expected_type}
                        {' '}picture — {correlation.expected_pattern}.
                      </p>
                    </div>

                    {/* Ears that contradict the diagnosis are listed first and
                        never folded away behind the verdict line. */}
                    {correlation.against?.length > 0 && (
                      <ul className="mt-2.5 space-y-1.5">
                        {correlation.against.map((line) => (
                          <li key={line}
                            className="rounded-lg bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
                            <EarLine text={line} />
                          </li>
                        ))}
                      </ul>
                    )}
                    {correlation.supports?.length > 0 && (
                      <ul className="mt-2.5 space-y-1.5">
                        {correlation.supports.map((line) => (
                          <li key={line}
                            className="rounded-lg bg-emerald-50 px-3 py-2 text-[12px] leading-relaxed text-emerald-900">
                            <EarLine text={line} />
                          </li>
                        ))}
                      </ul>
                    )}

                    <p className="mt-2.5 text-[11px] leading-relaxed text-slate-400">
                      One field of one diagnosis: the type of loss predicted
                      against the type measured, ear by ear. Agreement is not
                      confirmation — several conditions predict the same type,
                      and the degree, configuration and immittance are not read
                      here. Disagreement points at the history or the
                      thresholds; it does not rule the diagnosis out.
                    </p>
                  </>
                )}
              </div>

              <div data-tour="battery-order" className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                <h2 className="text-[15px] font-semibold text-slate-900">
                  Recommended battery
                </h2>
                <p className="mt-1 text-[12px] text-slate-500">
                  Ordered so the first test separates the most candidates.
                </p>
                <ol className="mt-2.5 space-y-1.5">
                  {result.recommended_battery.slice(0, 7).map((b, i) => (
                    <li key={b.test} className="flex gap-2.5 text-[12.5px]">
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">
                        {i + 1}
                      </span>
                      <span>
                        <span className="font-medium text-slate-800">{b.test}</span>
                        <span className="block text-[11.5px] text-slate-500">
                          for {b.for.slice(0, 3).join(', ')}
                        </span>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>

              {/* Every cross-check this history now enables — against the
                  audiogram, the otoscope image and the tympanogram. This
                  replaced a narrower "against the audiogram" card that said a
                  subset of the same thing in a second place on the page. */}
              <LinkagePanel side={side === 'left' ? 'left' : 'right'} />

              {result.complaint_guides.map((g) => (
                <div key={g.complaint}
                  className="rounded-2xl border border-slate-200/80 bg-slate-50/60 p-5">
                  <h2 className="text-[13.5px] font-semibold text-slate-800">
                    {g.name} — commonest causes for {band?.toLowerCase()}
                  </h2>
                  <ol className="mt-2 space-y-1.5">
                    {g.causes.map((c) => (
                      <li key={c.rank} className="text-[12.5px] leading-relaxed">
                        <span className="font-medium text-slate-800">{c.rank}. {c.condition}</span>
                        {c.red_flag && (
                          <span className="ml-1.5 rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-rose-700">
                            not to be missed
                          </span>
                        )}
                        <span className="block text-slate-600">{c.complaint}</span>
                        {c.note && <span className="block text-[11.5px] italic text-slate-500">{c.note}</span>}
                      </li>
                    ))}
                  </ol>
                </div>
              ))}

              <p className="text-[11.5px] leading-relaxed text-slate-400">
                {result.disclaimer} Sources: {result.sources.join(' ')}
              </p>
            </>
          )}
        </div>
      </div>

      <StepNav stepKey="symptoms" />
    </div>
  )
}
