// The footer that makes the consultation walkable: where you are, what is
// next, and — for the optional tests — a way to say "not doing this, and here
// is why".
//
// Skipping is deliberately NOT the same as leaving a step empty. A skip records
// a reason, and the reason is a clinical fact: "no tympanometer on site" is
// different from "forgot". What it never does is invent a result. Nothing here
// touches the analysis, so a battery with three skipped steps is interpreted
// from exactly the evidence that was actually collected — the dashboard simply
// stops prompting for what the clinician has already ruled out.

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApp } from '../lib/store.jsx'
import {
  SKIP_REASONS, STEP_BY_KEY, nextStep, prevStep, stepState,
} from '../lib/flow.js'

export default function StepNav({ stepKey }) {
  const navigate = useNavigate()
  const {
    patient, assessment, otoscopy, analysis, aep, skipped, skipStep, unskipStep,
  } = useApp()
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState(SKIP_REASONS[0])
  const [other, setOther] = useState('')

  const step = STEP_BY_KEY[stepKey]
  if (!step) return null

  const ctx = { patient, assessment, otoscopy, analysis, aep, skipped }
  const state = stepState(stepKey, ctx)
  const next = nextStep(stepKey, ctx)
  const prev = prevStep(stepKey)

  const confirmSkip = () => {
    skipStep(stepKey, reason === 'Other' ? (other.trim() || 'Skipped') : reason)
    setAsking(false)
    if (next) navigate(next.to)
  }

  return (
    <nav className="mt-6 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm"
      aria-label="Consultation step" data-tour="step-nav">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[12px]">
          {prev ? (
            <Link to={prev.to}
              className="rounded-lg border border-slate-200 px-2.5 py-1 font-medium text-slate-600 transition hover:border-slate-300">
              ← {prev.short}
            </Link>
          ) : <span />}

          {state === 'skipped' && (
            <span className="rounded-lg bg-slate-100 px-2 py-1 text-[11.5px] text-slate-600">
              Skipped — {skipped[stepKey]}
              <button onClick={() => unskipStep(stepKey)}
                className="ml-1.5 font-semibold text-teal-700 underline underline-offset-2">
                undo
              </button>
            </span>
          )}
          {state === 'done' && (
            <span className="rounded-lg bg-emerald-50 px-2 py-1 text-[11.5px] font-medium text-emerald-800">
              ✓ recorded
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!step.required && state !== 'done' && state !== 'skipped' && (
            <button onClick={() => setAsking((v) => !v)}
              className="rounded-lg border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-slate-500 transition hover:border-slate-300 hover:text-slate-700">
              Skip this step
            </button>
          )}
          {next && (
            <Link to={next.to}
              className="rounded-lg bg-teal-600 px-3.5 py-1.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-teal-700">
              Next: {next.short} →
            </Link>
          )}
        </div>
      </div>

      {asking && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[12px] font-medium text-slate-700">
            Why is {step.label.toLowerCase()} not being done?
          </p>
          <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
            This is recorded as <b>not performed</b>, never as a normal result, and
            it changes nothing about the interpretation — the dashboard will still
            show this part of the battery as missing if a finding later makes it
            matter.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {[...SKIP_REASONS, 'Other'].map((r) => (
              <button key={r} onClick={() => setReason(r)}
                className={`rounded-lg border px-2 py-0.5 text-[11.5px] transition ${
                  reason === r
                    ? 'border-teal-500 bg-teal-50 font-medium text-teal-800'
                    : 'border-slate-200 bg-white text-slate-600'}`}>
                {r}
              </button>
            ))}
          </div>
          {reason === 'Other' && (
            <input value={other} onChange={(e) => setOther(e.target.value)}
              placeholder="Reason"
              className="mt-2 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-[12.5px]" />
          )}
          <div className="mt-3 flex justify-end gap-2">
            <button onClick={() => setAsking(false)}
              className="rounded-lg border border-slate-200 px-2.5 py-1 text-[12px] text-slate-600">
              Cancel
            </button>
            <button onClick={confirmSkip}
              className="rounded-lg bg-slate-700 px-3 py-1 text-[12px] font-semibold text-white">
              Skip and continue
            </button>
          </div>
        </div>
      )}

      {step.skipHint && !asking && state === 'ready' && (
        <p className="mt-2 text-[11px] text-slate-400">
          Optional — commonly skipped when: {step.skipHint.toLowerCase()}.
        </p>
      )}
    </nav>
  )
}
