// Cross-modal linkage, shown wherever a case is being assembled.
//
// The same component appears on the Dashboard, the Otoscopy page and the
// Symptoms page, because the question it answers — do these findings agree? —
// is the same one from all three directions, and a clinician should not have
// to remember which screen carries it.
//
// Conflicts are listed before agreements and are never collapsed behind a
// summary. A page of green ticks that hides one line saying two measurements
// cannot both be true is worse than no panel at all.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

const LINK_LABEL = {
  otoscopy_symptoms: 'Otoscopy ↔ symptoms',
  otoscopy_audiogram: 'Otoscopy ↔ audiogram',
  symptoms_audiogram: 'Symptoms ↔ audiogram',
  immittance_diseases: 'Immittance ↔ diseases',
}
const LINK_COUNT = Object.keys(LINK_LABEL).length

const VERDICT_STYLE = {
  conflicting: 'border-amber-300 bg-amber-50 text-amber-900',
  consistent: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  insufficient: 'border-slate-200 bg-slate-50 text-slate-600',
}

function Finding({ f }) {
  const conflict = f.kind === 'conflict'
  return (
    <li className={`rounded-lg px-3 py-2 text-[12px] leading-relaxed ${
      conflict ? 'bg-amber-50 text-amber-900' : 'bg-emerald-50 text-emerald-900'}`}>
      <div className="font-semibold">{conflict ? '⚠' : '✓'} {f.title}</div>
      <div className="mt-0.5">{f.detail}</div>
      {f.action && <div className="mt-1 font-medium">→ {f.action}</div>}
    </li>
  )
}

function LinkBlock({ id, link }) {
  if (!link?.available) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 px-3 py-2.5">
        <div className="text-[12px] font-semibold text-slate-500">{LINK_LABEL[id]}</div>
        <div className="mt-0.5 text-[11.5px] leading-relaxed text-slate-400">
          {link?.note}
        </div>
      </div>
    )
  }
  const findings = [...(link.conflicts || []), ...(link.agreements || [])]
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[12px] font-semibold text-slate-700">{LINK_LABEL[id]}</span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
          link.verdict === 'conflicting' ? 'bg-amber-100 text-amber-700'
            : link.verdict === 'consistent' ? 'bg-emerald-100 text-emerald-700'
              : 'bg-slate-100 text-slate-500'}`}>
          {link.verdict}
        </span>
      </div>

      {/* Immittance carries a differential rather than findings alone: which
          diseases this trace supports, and which it takes off the table. */}
      {id === 'immittance_diseases' && (
        <div className="mt-2 space-y-1.5 text-[11.5px] leading-relaxed">
          <div className="font-medium text-slate-700">
            {link.label} — {link.ear} ear
          </div>
          <div className="text-slate-600">{link.meaning}</div>
          {link.supports?.length > 0 && (
            <div>
              <span className="font-semibold text-emerald-700">Supports:</span>{' '}
              <span className="text-slate-600">
                {link.supports.map((s) => s.name).join(' · ')}
              </span>
            </div>
          )}
          {link.argues_against?.length > 0 && (
            <div>
              <span className="font-semibold text-rose-700">Argues against:</span>{' '}
              <span className="text-slate-600">
                {link.argues_against.map((s) => s.name).join(' · ')}
              </span>
            </div>
          )}
          {link.also_consider?.length > 0 && (
            <div>
              <span className="font-semibold text-slate-600">Also consider:</span>{' '}
              <span className="text-slate-600">{link.also_consider.join(' · ')}</span>
            </div>
          )}
          {link.reflex_findings?.map((r) => (
            <div key={r.when} className="rounded bg-slate-50 px-2 py-1.5">
              <span className="font-semibold text-slate-700 capitalize">{r.when}</span>
              {' — '}{r.meaning}
              {(r.supports.length > 0 || r.also_consider.length > 0) && (
                <span className="block text-slate-500">
                  {[...r.supports, ...r.also_consider].join(' · ')}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* The audiogram link is three separate predictions; showing what was
          expected next to what was measured is more use than the verdict. */}
      {id === 'symptoms_audiogram' && link.rank_note && (
        <p className="mt-2 rounded bg-slate-50 px-2 py-1.5 text-[11px] leading-relaxed text-slate-600">
          {link.rank_note}
        </p>
      )}

      {id === 'symptoms_audiogram' && link.measured && (
        <dl className="mt-2 grid grid-cols-3 gap-1.5 text-[11px]">
          {[
            ['Expected type', link.expected_type],
            ['Expected PTA', `${link.expected_pta?.[0]}–${link.expected_pta?.[1]} dB`],
            ['Measured', `${link.measured.better_ear_pta} dB (${link.measured.grade})`],
          ].map(([k, v]) => (
            <div key={k} className="rounded bg-slate-50 px-2 py-1.5">
              <dt className="text-[10px] font-medium text-slate-500">{k}</dt>
              <dd className="mt-0.5 font-medium text-slate-800">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      {id === 'otoscopy_symptoms' && link.expected_symptoms?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {link.expected_symptoms.map((s) => (
            <span key={s.key}
              className={`rounded px-1.5 py-0.5 text-[10.5px] ${
                s.present ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-slate-100 text-slate-500 line-through'}`}>
              {s.label}
            </span>
          ))}
        </div>
      )}

      {findings.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {findings.map((f, i) => <Finding key={i} f={f} />)}
        </ul>
      )}
    </div>
  )
}

/**
 * @param side which ear the immittance link should read.
 * @param compact hides the per-link detail, keeping only the headline and
 *        conflicts — used where the panel is a sidebar rather than the subject.
 */
export default function LinkagePanel({ side = 'right', compact = false }) {
  const { analysis, assessment, otoscopy } = useApp()
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!analysis && !assessment && !otoscopy) { setResult(null); return }
    let cancelled = false
    setBusy(true)
    api.linkage({ analysis, assessment, otoscopy, side })
      .then((r) => { if (!cancelled) setResult(r) })
      .catch(() => { if (!cancelled) setResult(null) })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [analysis, assessment, otoscopy, side])

  if (!result) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 p-5 text-[12.5px] text-slate-400">
        {busy ? 'Cross-checking…' : (
          <>
            Record a symptom history, an otoscope image or an audiogram and this
            panel reconciles them against each other.{' '}
            <Link to="/symptoms" className="font-medium text-teal-700 underline">
              Start with the history
            </Link>.
          </>
        )}
      </div>
    )
  }

  const missing = result.missing_inputs || []

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">Case linkage</h2>
        <span className="text-[11.5px] text-slate-500">
          {result.links_available.length} of {LINK_COUNT} links active
        </span>
      </div>

      <div className={`mt-2 rounded-xl border px-3 py-2.5 text-[13px] font-medium ${
        VERDICT_STYLE[result.verdict] || VERDICT_STYLE.insufficient}`}>
        {result.headline}
        {result.conflict_count > 0 && (
          <span className="ml-1 font-normal opacity-80">
            {result.agreement_count} other check
            {result.agreement_count === 1 ? '' : 's'} agree.
          </span>
        )}
      </div>

      {compact ? (
        result.top_conflicts.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {result.top_conflicts.map((f, i) => <Finding key={i} f={f} />)}
          </ul>
        )
      ) : (
        <div className="mt-3 space-y-3">
          {Object.entries(result.links).map(([id, link]) => (
            <LinkBlock key={id} id={id} link={link} />
          ))}
        </div>
      )}

      {missing.length > 0 && (
        <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[11.5px] leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-600">To link more:</span>{' '}
          {missing.join('; ')}.
        </div>
      )}

      <p className="mt-2.5 text-[11px] leading-relaxed text-slate-400">{result.note}</p>
    </div>
  )
}
