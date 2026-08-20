// The complete diagnostic picture — coverage, convergence, and the next test.
//
// Every other panel on the dashboard reports one modality. This one stands back
// and answers the question a clinician asks at the end of a session: do I have
// enough to diagnose this patient, and if not, what do I do next?
//
// Three things earn its place:
//
//   COVERAGE makes a half-finished workup LOOK half-finished. A conductive loss
//   with no tympanogram is not a diagnosis, and a page that renders it like one
//   is worse than no page.
//
//   CONVERGENCE counts the findings that agree while being independent of each
//   other. That count is the honest basis for confidence — not the model's.
//
//   THE NEXT TEST is the actionable part: the single measurement that would
//   most change the answer, with the reason it is being asked for.

import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

const CONFIDENCE = {
  insufficient: { label: 'Nothing to interpret', cls: 'border-slate-300 bg-slate-50 text-slate-700', dot: 'bg-slate-400' },
  incomplete:   { label: 'Workup incomplete',    cls: 'border-amber-300 bg-amber-50 text-amber-900', dot: 'bg-amber-500' },
  conflicted:   { label: 'Tests disagree',       cls: 'border-rose-300 bg-rose-50 text-rose-900',    dot: 'bg-rose-500' },
  provisional:  { label: 'Provisional',          cls: 'border-sky-300 bg-sky-50 text-sky-900',       dot: 'bg-sky-500' },
  adequate:     { label: 'Adequate',             cls: 'border-teal-300 bg-teal-50 text-teal-900',    dot: 'bg-teal-500' },
  corroborated: { label: 'Corroborated',         cls: 'border-emerald-300 bg-emerald-50 text-emerald-900', dot: 'bg-emerald-500' },
}

const PRIORITY = {
  critical:    { label: 'critical',    cls: 'bg-rose-100 text-rose-700' },
  recommended: { label: 'recommended', cls: 'bg-amber-100 text-amber-800' },
  optional:    { label: 'optional',    cls: 'bg-slate-100 text-slate-600' },
}

// The clinician skips a STEP; the diagnostic module reasons about MODALITIES,
// and the two are not one-to-one.
//
// "Immittance" is one decision made at the bench about one piece of equipment:
// if there is no probe in the room there is no tympanogram, no reflex, no
// emission and no speech measured through it. So that single skip has to fan
// out to all four modalities, or the panel keeps asking for a probe that is not
// in the building — which is exactly the nagging a recorded skip is meant to
// stop. Steps that are not tests (patient, results) map to nothing.
//
// Written out rather than inferred: the backend silently drops a key it does
// not recognise, so a wrong guess here fails quietly and the skip is simply
// never heard.
const STEP_TO_MODALITIES = {
  symptoms: ['symptoms'],
  otoscopy: ['otoscopy'],
  pure_tone: ['pure_tone'],
  immittance: ['tympanometry', 'reflexes', 'oae', 'speech'],
  aep: ['aep'],
}

/** Coverage as a row of ticks — the shape of the battery at a glance. */
function Coverage({ coverage, performed, total, skipped }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Battery coverage
        </span>
        <span className="font-mono text-[11.5px] text-slate-600">
          {performed} of {total}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
        <div className="h-full rounded-full bg-teal-500 transition-all"
          style={{ width: `${(performed / total) * 100}%` }} />
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
        {coverage.map((m) => {
          // A skip is a third state, not a pass. The test is still absent, so
          // the label stays dimmed and an essential one still shouts; what the
          // hollow amber ring adds is that nobody forgot — somebody decided.
          const reason = !m.performed ? (skipped || {})[m.key] : null
          return (
            <div key={m.key} className="flex items-start gap-1.5 text-[11.5px]"
              title={reason ? `Not performed — skipped: ${reason}. ${m.why}` : m.why}>
              <span aria-hidden="true" className={`mt-[3px] inline-block h-2 w-2 shrink-0 rounded-full ${
                m.performed ? 'bg-teal-500'
                  : reason ? 'border-[1.5px] border-amber-500 bg-amber-50'
                    : m.essential ? 'bg-rose-400' : 'bg-slate-300'}`} />
              <span className={m.performed ? 'text-slate-700' : 'text-slate-400'}>
                {m.label}
                {!m.performed && m.essential && (
                  <span className="ml-1 text-[10px] font-semibold uppercase text-rose-500">
                    essential
                  </span>
                )}
                {reason && (
                  <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                    skipped
                  </span>
                )}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function DiagnosticPicture({ analysis }) {
  const { assessment, otoscopy, aep, tuningFork, boa, skipped } = useApp()
  const [picture, setPicture] = useState(null)
  const [reference, setReference] = useState(null)
  const [error, setError] = useState(null)

  // The age drives the one rule that reorders the whole battery: under six
  // months there is no conditioned response to shape, so pure tones are not
  // the reference test and objective testing becomes critical.
  const ageMonths = useMemo(() => {
    const y = analysis?.patient?.age
    return typeof y === 'number' ? y * 12 : null
  }, [analysis])

  // What the clinician declined, in the vocabulary the module judges by. This
  // never softens the verdict — a skipped tympanogram is a missing tympanogram
  // — it only lets the panel distinguish a decision from an oversight, and name
  // the decisions the findings have since overtaken.
  const skippedModalities = useMemo(() => {
    const out = {}
    for (const [step, reason] of Object.entries(skipped || {})) {
      for (const key of STEP_TO_MODALITIES[step] || []) out[key] = reason
    }
    return out
  }, [skipped])

  // The criteria the module judges by do not change between patients, so they
  // are fetched once. They are supplementary — a clinician who cannot see the
  // thresholds still gets the verdict — so a failure here leaves the reference
  // null and the section simply does not render.
  useEffect(() => {
    let cancelled = false
    api.diagnosisReference()
      .then((r) => { if (!cancelled) setReference(r) })
      .catch(() => { if (!cancelled) setReference(null) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!analysis) { setPicture(null); return }
    let cancelled = false
    api.diagnosisPicture({
      analysis, assessment, otoscopy, aep, tuning_fork: tuningFork, boa,
      age_months: ageMonths, skipped: skippedModalities,
    })
      .then((p) => { if (!cancelled) { setPicture(p); setError(null) } })
      .catch((e) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [analysis, assessment, otoscopy, aep, tuningFork, boa, ageMonths,
      skippedModalities])

  if (error) {
    return (
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 text-[12.5px] text-slate-500 shadow-sm">
        The diagnostic picture could not be built: {error}
      </div>
    )
  }
  if (!picture) return null

  const conf = CONFIDENCE[picture.confidence] || CONFIDENCE.provisional
  const critical = picture.next_tests.filter((t) => t.priority === 'critical')
  const reconsider = picture.reconsider || []

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">
          Complete diagnostic picture
        </h2>
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${conf.cls}`}>
          <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${conf.dot}`} />
          {conf.label}
        </span>
      </div>

      <p className={`mt-2.5 rounded-xl border px-3 py-2 text-[13px] font-medium leading-relaxed ${conf.cls}`}>
        {picture.verdict}
      </p>

      {/* Above everything actionable, because it is the one thing on this panel
          the clinician cannot already know. Every other item is a test that was
          never started; these are decisions that were correct when they were
          made and that the findings have since overtaken — a tympanometer left
          behind because the ears looked clear, before an air-bone gap appeared.
          Nobody re-reads a skip they have already reasoned through, so the
          panel has to raise it, and raise it as news rather than as a scolding:
          the reason for skipping is quoted back so the decision is visible as
          the sound one it was. */}
      {reconsider.length > 0 && (
        <section className="mt-3.5 rounded-xl border-2 border-amber-400 bg-amber-50 p-3.5"
          aria-labelledby="dx-reconsider">
          <div className="flex items-center gap-2">
            <span aria-hidden="true"
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500 text-[12px] font-bold leading-none text-white">
              !
            </span>
            <h3 id="dx-reconsider"
              className="text-[11px] font-semibold uppercase tracking-wide text-amber-800">
              Something has changed since you skipped {reconsider.length > 1
                ? `${reconsider.length} tests` : 'a test'}
            </h3>
          </div>
          <ul className="mt-2 space-y-1.5">
            {reconsider.map((r, i) => (
              <li key={i}
                className="text-[13px] font-medium leading-relaxed text-amber-900">
                {r}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] leading-relaxed text-amber-800">
            These were reasonable calls on the information available at the time.
            What has moved is the findings, not the decision — each of these now
            sits on the critical path, so it is worth asking whether it can still
            be obtained today or needs a return visit.
          </p>
        </section>
      )}

      {/* The actionable part goes above the evidence, because it is the part
          that changes what the clinician does in the next five minutes. */}
      {picture.next_tests.length > 0 && (
        <div className="mt-4">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            What to do next
          </span>
          <ol className="mt-1.5 space-y-1.5">
            {picture.next_tests.map((t) => (
              <li key={t.test}
                className={`rounded-xl border px-3 py-2 ${
                  t.priority === 'critical'
                    ? 'border-rose-200 bg-rose-50/60'
                    : 'border-slate-200 bg-slate-50/60'}`}>
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-[13px] font-semibold text-slate-900">{t.test}</span>
                  <span className={`rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide ${PRIORITY[t.priority].cls}`}>
                    {PRIORITY[t.priority].label}
                  </span>
                  <span className="text-[11px] text-slate-500">— {t.because}</span>
                </div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-slate-600">{t.why}</p>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="mt-4">
        <Coverage coverage={picture.coverage} performed={picture.performed}
          total={picture.total} skipped={picture.skipped} />
      </div>

      {picture.findings.length > 0 && (
        <div className="mt-4">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            What each test said
          </span>
          <ul className="mt-1.5 space-y-1">
            {picture.findings.map((f) => (
              <li key={f.key} className="flex items-start gap-2 text-[12px] leading-relaxed">
                <span className={`mt-0.5 w-[132px] shrink-0 font-medium ${
                  f.alarm ? 'text-rose-700' : 'text-slate-500'}`}>
                  {f.label}
                </span>
                <span className="text-slate-700">
                  {f.says}
                  {f.detail && <span className="text-slate-400"> · {f.detail}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(picture.agreements.length > 0 || picture.conflicts.length > 0) && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {picture.conflicts.length > 0 && (
            <div className="rounded-xl border border-rose-200 bg-rose-50/60 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-rose-700">
                Cannot all be true ({picture.conflicts.length})
              </div>
              <ul className="mt-1.5 space-y-1 text-[11.5px] leading-relaxed text-rose-900">
                {picture.conflicts.map((c, i) => <li key={i}>· {c}</li>)}
              </ul>
            </div>
          )}
          {picture.agreements.length > 0 && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                Independent findings that agree ({picture.agreements.length})
              </div>
              <ul className="mt-1.5 space-y-1 text-[11.5px] leading-relaxed text-emerald-900">
                {picture.agreements.map((a, i) => <li key={i}>· {a}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      <p className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-600">
        <span className="font-semibold">Coverage is not accuracy.</span>{' '}
        {picture.caveat.replace('Coverage is not accuracy. ', '')}
        {critical.length > 0 && (
          <span className="mt-1 block font-medium text-amber-800">
            {critical.length} critical test{critical.length > 1 ? 's are' : ' is'} still
            outstanding, so this interpretation is not final.
          </span>
        )}
      </p>

      {/* A confidence word and a coverage count are a judgement, and a judgement
          a clinician cannot audit is one they cannot safely act on or overrule.
          The criteria are collapsed rather than absent: they are not needed to
          read the verdict, but they must be available to anyone who disagrees
          with it, and the numeric thresholds must be the ones actually used. */}
      {reference?.confidence_levels && reference?.modalities && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[12px] font-medium text-teal-700">
            How this judgement was reached
          </summary>

          <div className="mt-2.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              What each confidence word means
            </span>
            <ul className="mt-1.5 space-y-1 text-[11.5px] leading-relaxed">
              {reference.confidence_levels.map((l) => {
                const inForce = l.key === picture.confidence
                return (
                  <li key={l.key} className={inForce ? 'text-slate-800' : 'text-slate-500'}>
                    <span className={`font-medium ${inForce ? 'text-teal-700' : 'text-slate-600'}`}>
                      {(CONFIDENCE[l.key] || {}).label || l.key}
                    </span>
                    {inForce && (
                      <span className="ml-1 rounded bg-teal-100 px-1 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-teal-700">
                        in force
                      </span>
                    )}
                    <span> — {l.meaning}</span>
                  </li>
                )
              })}
            </ul>
          </div>

          <div className="mt-2.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              The numbers these rest on
            </span>
            <ul className="mt-1.5 space-y-1 text-[11.5px] leading-relaxed text-slate-600">
              {/* Exclusive, not inclusive. The rule is `> 10`, pinned by the
                  test suite and by WALKTHROUGH.md — a gap of exactly 10 dB is
                  NOT significant. This panel exists so a clinician can audit
                  the verdict, so it is the one place that must not restate the
                  threshold loosely. */}
              <li>
                · An air-bone gap is called a conductive component only above{' '}
                <span className="font-mono font-medium text-slate-800">
                  {reference.significant_abg_db} dB
                </span>. A gap of exactly{' '}
                <span className="font-mono font-medium text-slate-800">
                  {reference.significant_abg_db} dB
                </span>, and anything smaller, sits inside ordinary test-retest
                variation and is not read as a mechanism.
              </li>
              <li>
                · Below{' '}
                <span className="font-mono font-medium text-slate-800">
                  {reference.infant_months} months
                </span>{' '}
                there is no conditioned response to shape, so behavioural
                audiometry is not obtainable and objective testing — not pure
                tones — becomes the critical outstanding test.
              </li>
            </ul>
          </div>

          <div className="mt-2.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Why each test is in the battery
            </span>
            <ul className="mt-1.5 space-y-1 text-[11.5px] leading-relaxed">
              {reference.modalities.map((m) => (
                <li key={m.key}>
                  <span className="font-medium text-slate-700">{m.label}</span>
                  {m.essential && (
                    <span className="ml-1 text-[10px] font-semibold uppercase text-rose-500">
                      essential
                    </span>
                  )}
                  <span className="text-slate-500"> — {m.why}</span>
                </li>
              ))}
            </ul>
          </div>

          <p className="mt-2.5 text-[11px] leading-relaxed text-slate-500">
            These criteria decide what the panel says, not what the patient has.
            They are thresholds for calling a workup complete and its findings
            consistent; a battery that satisfies every one of them can still be
            measuring the wrong ear or a patient who did not understand the task.
          </p>

          {reference.citations?.length > 0 && (
            <p className="mt-1.5 text-[10.5px] text-slate-400">
              {reference.citations.join(' · ')}
            </p>
          )}
        </details>
      )}
    </div>
  )
}
