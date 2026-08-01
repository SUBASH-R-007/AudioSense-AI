// Masking, frequency by frequency.
//
// The decision is per-frequency and it has an exact answer, so it is shown as
// a grid rather than a sentence. A clinician can see at which frequencies
// masking was required, which of the two air-conduction rules fired, and —
// the part a summary always loses — where there is no usable masking level
// at all.

import { AC_FREQS, FREQ_LABELS } from '../lib/api.js'

const EAR_TONE = { right: 'text-red-600', left: 'text-blue-600' }

function Cell({ row, mode }) {
  const decision = row[mode]
  const levels = row[`${mode}_levels`]
  if (!decision?.testable) {
    return <td className="px-1.5 py-1 text-center text-slate-300">—</td>
  }
  if (!decision.required) {
    return (
      <td className="px-1.5 py-1 text-center">
        <span className="text-[11px] text-slate-400">no</span>
      </td>
    )
  }
  const dilemma = levels?.dilemma
  return (
    <td className="px-1.5 py-1 text-center">
      <span className={`inline-block rounded px-1.5 py-0.5 text-[10.5px] font-semibold ${
        dilemma ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-800'}`}>
        {dilemma ? 'dilemma' : 'mask'}
      </span>
      {/* The ceiling needs a bone threshold, and bone conduction is not
          tested at 8 kHz. Showing "65–" there would read as a broken range
          rather than an unknown one. */}
      {levels && !dilemma && levels.minimum != null && (
        <span className="mt-0.5 block font-mono text-[10px] text-slate-500"
          title={levels.maximum == null
            ? 'Maximum needs a bone-conduction threshold at this frequency'
            : 'Usable masking plateau, dB EM'}>
          {levels.maximum == null
            ? `≥${levels.minimum}`
            : `${levels.minimum}–${levels.maximum}`}
        </span>
      )}
    </td>
  )
}

function EarTable({ plan }) {
  if (!plan) return null
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className={`text-[12px] font-bold uppercase ${EAR_TONE[plan.ear]}`}>
          {plan.ear} ear
        </span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
          plan.has_dilemma ? 'bg-rose-100 text-rose-700'
            : plan.warning ? 'bg-amber-100 text-amber-800'
              : plan.masking_indicated ? 'bg-sky-100 text-sky-700'
                : 'bg-emerald-100 text-emerald-700'}`}>
          {plan.has_dilemma ? 'unmaskable'
            : plan.warning ? 'indicated, not recorded'
              : plan.masking_indicated ? 'masked' : 'not required'}
        </span>
      </div>

      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[320px] text-[11px]">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-slate-400">
              <th className="py-1 pr-2 text-left font-medium">Hz</th>
              {AC_FREQS.map((f) => (
                <th key={f} className="px-1.5 py-1 font-medium">
                  {FREQ_LABELS[f] || f}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-slate-100">
              <th className="py-1 pr-2 text-left font-medium text-slate-600">AC</th>
              {plan.rows.map((r) => <Cell key={r.freq} row={r} mode="ac" />)}
            </tr>
            <tr className="border-t border-slate-100">
              <th className="py-1 pr-2 text-left font-medium text-slate-600">BC</th>
              {plan.rows.map((r) => <Cell key={r.freq} row={r} mode="bc" />)}
            </tr>
          </tbody>
        </table>
      </div>

      {plan.reasons.length > 0 && (
        <ul className="mt-2 space-y-1">
          {plan.reasons.map((r, i) => (
            <li key={i} className={`rounded-lg px-2.5 py-1.5 text-[11.5px] leading-relaxed ${
              r.includes('dilemma') ? 'bg-rose-50 text-rose-900'
                : 'bg-slate-50 text-slate-600'}`}>
              {r}
            </li>
          ))}
        </ul>
      )}
      {plan.message && (
        <p className="mt-2 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11.5px] leading-relaxed text-amber-900">
          {plan.message}
        </p>
      )}
    </div>
  )
}

export default function MaskingPanel({ review }) {
  if (!review) return null
  const transducer = review.transducer

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">
          Masking — which ear do these thresholds belong to?
        </h2>
        <span className="text-[11.5px] text-slate-500">
          {transducer?.label} · IA {transducer?.ia_ac} dB
        </span>
      </div>

      <p className={`mt-2 rounded-lg border px-3 py-2 text-[12.5px] font-medium ${
        review.any_dilemma ? 'border-rose-300 bg-rose-50 text-rose-900'
          : review.any_unmasked ? 'border-amber-300 bg-amber-50 text-amber-900'
            : 'border-emerald-300 bg-emerald-50 text-emerald-900'}`}>
        {review.headline}
      </p>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EarTable plan={review.right} />
        <EarTable plan={review.left} />
      </div>

      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-medium text-teal-700">
          The rules being applied
        </summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 text-[11.5px] leading-relaxed">
          <div className="rounded-lg bg-slate-50 px-3 py-2">
            <div className="font-semibold text-slate-700">Air conduction — either</div>
            <div className="mt-0.5 font-mono text-slate-600">
              AC(TE) − AC(NTE) ≥ IA<br />AC(TE) − BC(NTE) ≥ IA
            </div>
            <div className="mt-1 text-slate-500">
              Rule two catches the case rule one misses: a conductive loss in the
              non-test ear lowers the bar the crossed signal has to clear.
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 px-3 py-2">
            <div className="font-semibold text-slate-700">Bone conduction — either</div>
            <div className="mt-0.5 font-mono text-slate-600">
              AC(TE) − BC(unmasked) ≥ 15 dB<br />ABG ≥ 15 dB
            </div>
            <div className="mt-1 text-slate-500">
              Bone conduction crosses the skull essentially unattenuated, so an
              unmasked bone threshold never belongs to a known ear on its own.
            </div>
          </div>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          Ranges under &ldquo;mask&rdquo; are the usable plateau in dB EM — minimum
          effective masking to maximum before the noise crosses back.{' '}
          {review.right?.citations?.join(' · ')}
        </p>
      </details>

      <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{review.note}</p>
    </div>
  )
}
