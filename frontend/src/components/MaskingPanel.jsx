// Masking, frequency by frequency.
//
// The decision is per-frequency and it has an exact answer, so it is shown as
// a grid rather than a sentence. A clinician can see at which frequencies
// masking was required, which of the two air-conduction rules fired, and —
// the part a summary always loses — where there is no usable masking level
// at all.
//
// The transducer is the single choice that changes whether masking is needed
// at all: supra-aural earphones give 40 dB of interaural attenuation, inserts
// 50-60 dB. Moving to inserts can drop several frequencies out of the masking
// requirement and can dissolve a masking dilemma outright. That is a decision
// made before the patient is back in the booth — which is why the transducer
// is switchable here, against these thresholds, rather than only on the form
// that produced them.

import { useEffect, useState } from 'react'
import { AC_FREQS, FREQ_LABELS, api } from '../lib/api.js'

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

/** Masked cells and unmaskable frequencies across both ears.
 *
 * The count is what makes a transducer change legible: "three fewer thresholds
 * need masking" is the sentence a clinician acts on, and it cannot be read off
 * two grids side by side without counting them by eye.
 */
function tally(review) {
  let cells = 0
  let dilemmas = 0
  for (const side of ['right', 'left']) {
    for (const row of review?.[side]?.rows || []) {
      if (row.ac?.required) cells += 1
      if (row.bc?.required) cells += 1
      if (row.dilemma) dilemmas += 1
    }
  }
  return { cells, dilemmas }
}

/** One sentence on what the transducer change did to the workload. */
function deltaSentence(before, after) {
  const parts = []
  const diff = before.cells - after.cells
  if (diff > 0) {
    parts.push(`${diff} fewer threshold${diff === 1 ? '' : 's'} would need masking`)
  } else if (diff < 0) {
    parts.push(`${-diff} more threshold${diff === -1 ? '' : 's'} would need masking`)
  } else {
    parts.push('the same thresholds would still need masking')
  }
  if (before.dilemmas > 0 && after.dilemmas === 0) {
    parts.push('and the masking dilemma disappears entirely')
  } else if (before.dilemmas > after.dilemmas) {
    parts.push(`and ${before.dilemmas - after.dilemmas} unmaskable frequenc`
      + `${before.dilemmas - after.dilemmas === 1 ? 'y becomes' : 'ies become'} maskable`)
  } else if (after.dilemmas > before.dilemmas) {
    parts.push(`but ${after.dilemmas - before.dilemmas} further frequenc`
      + `${after.dilemmas - before.dilemmas === 1 ? 'y becomes' : 'ies become'} unmaskable`)
  }
  return `${parts.join(' ')}.`
}

export default function MaskingPanel({ review, thresholds }) {
  const recordedKey = review?.transducer?.key || null
  const [reference, setReference] = useState(null)
  const [transducer, setTransducer] = useState(recordedKey)
  const [whatIf, setWhatIf] = useState(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(null)

  // The transducer list and the criteria behind the decision. Without this the
  // panel asserts "mask" and "dilemma" without ever showing the rule it
  // applied, which is not something a clinician should have to take on trust.
  useEffect(() => {
    let cancelled = false
    api.maskingReference()
      .then((r) => { if (!cancelled) setReference(r) })
      .catch(() => { if (!cancelled) setReference(null) })
    return () => { cancelled = true }
  }, [])

  // A new analysis carries its own recorded transducer, so any what-if from
  // the previous case has to be dropped rather than silently carried over.
  useEffect(() => {
    setTransducer(recordedKey)
    setWhatIf(null)
    setFailed(null)
  }, [recordedKey])

  const canRecompute = Boolean(thresholds?.right && thresholds?.left)
  const isWhatIf = Boolean(transducer && recordedKey && transducer !== recordedKey)

  useEffect(() => {
    if (!isWhatIf || !canRecompute || !review) {
      setWhatIf(null)
      setBusy(false)
      return undefined
    }
    let cancelled = false
    setBusy(true)
    setFailed(null)
    // The masked flags come from the recorded review rather than from the
    // thresholds, because whether masking was actually applied in the booth is
    // a property of the test that no transducer choice can change.
    api.masking({
      transducer,
      right: {
        ac: thresholds.right.ac || {},
        bc: thresholds.right.bc || {},
        masked: Boolean(review.right?.masking_reported),
      },
      left: {
        ac: thresholds.left.ac || {},
        bc: thresholds.left.bc || {},
        masked: Boolean(review.left?.masking_reported),
      },
    })
      .then((r) => { if (!cancelled) { setWhatIf(r); setBusy(false) } })
      .catch((e) => {
        if (!cancelled) { setWhatIf(null); setFailed(e.message); setBusy(false) }
      })
    return () => { cancelled = true }
  }, [transducer, isWhatIf, canRecompute, review, thresholds])

  if (!review) return null

  const showing = isWhatIf && whatIf ? whatIf : review
  const projecting = showing !== review
  const spec = showing.transducer
  const options = reference?.transducers || (spec ? [{ key: spec.key, ...spec }] : [])
  const selected = options.find((t) => t.key === transducer)

  return (
    <div className={`rounded-2xl border bg-white p-5 shadow-sm ${
      projecting ? 'border-teal-300 ring-1 ring-teal-100' : 'border-slate-200/80'}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">
          Masking — which ear do these thresholds belong to?
        </h2>
        <span className="text-[11.5px] text-slate-500">
          {spec?.label} · IA {spec?.ia_ac} dB
          {selected?.ia_range && selected.ia_range[0] !== selected.ia_range[1] && (
            <span className="text-slate-400">
              {' '}(reference {selected.ia_range[0]}–{selected.ia_range[1]} dB; the
              conservative end is used so masking is never skipped on an
              optimistic assumption)
            </span>
          )}
        </span>
      </div>

      {/* The transducer selector. Changing it re-runs the decision against the
          same thresholds, which is the question worth asking before fetching
          equipment: would inserts make this case easier? */}
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="masking-transducer"
            className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Transducer
          </label>
          <select id="masking-transducer" value={transducer || ''}
            disabled={!canRecompute}
            onChange={(e) => setTransducer(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-[12px] text-slate-700 disabled:opacity-50">
            {options.map((t) => (
              <option key={t.key} value={t.key}>
                {t.label} — IA {t.ia_ac} dB
                {t.key === recordedKey ? ' (as recorded)' : ''}
              </option>
            ))}
          </select>
          {busy && <span className="text-[11.5px] text-slate-400">Recomputing…</span>}
          {projecting && (
            <>
              <span className="rounded-full bg-teal-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-teal-700">
                what-if
              </span>
              <button type="button" onClick={() => setTransducer(recordedKey)}
                className="text-[11.5px] font-medium text-teal-700 hover:text-teal-900">
                back to what was recorded →
              </button>
            </>
          )}
        </div>

        {selected?.note && (
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-500">
            {selected.note}
          </p>
        )}
        {!canRecompute && (
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-400">
            Thresholds were not passed to this panel, so the plan cannot be
            recomputed for another transducer.
          </p>
        )}
        {failed && (
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-500">
            The masking service is unavailable ({failed}) — the plan below is
            still the one recorded with {review.transducer?.label}.
          </p>
        )}

        {/* A projection is not a measurement, and a panel that quietly swapped
            its numbers would be inviting a clinician to report thresholds that
            were never obtained this way. */}
        {projecting && (
          <p className="mt-2 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[11.5px] leading-relaxed text-teal-900">
            <b>Projection only.</b> These thresholds were obtained with{' '}
            {review.transducer?.label} and are shown here as they would be judged
            with {spec?.label}: {deltaSentence(tally(review), tally(showing))}{' '}
            Switching transducer changes which thresholds are attributable, not
            the thresholds themselves — re-test with the chosen transducer before
            reporting anything from this view.
          </p>
        )}
      </div>

      <p className={`mt-3 rounded-lg border px-3 py-2 text-[12.5px] font-medium ${
        showing.any_dilemma ? 'border-rose-300 bg-rose-50 text-rose-900'
          : showing.any_unmasked ? 'border-amber-300 bg-amber-50 text-amber-900'
            : 'border-emerald-300 bg-emerald-50 text-emerald-900'}`}>
        {showing.headline}
      </p>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <EarTable plan={showing.right} />
        <EarTable plan={showing.left} />
      </div>

      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-medium text-teal-700">
          The rules being applied
        </summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 text-[11.5px] leading-relaxed">
          <div className="rounded-lg bg-slate-50 px-3 py-2">
            <div className="font-semibold text-slate-700">Air conduction — either</div>
            <div className="mt-0.5 font-mono text-slate-600">
              {(reference?.rules?.air_conduction || [
                'AC(TE) − AC(NTE) ≥ IA', 'AC(TE) − BC(NTE) ≥ IA',
              ]).map((r) => <div key={r}>{r}</div>)}
            </div>
            <div className="mt-1 text-slate-500">
              Rule two catches the case rule one misses: a conductive loss in the
              non-test ear lowers the bar the crossed signal has to clear.
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 px-3 py-2">
            <div className="font-semibold text-slate-700">Bone conduction — either</div>
            <div className="mt-0.5 font-mono text-slate-600">
              {(reference?.rules?.bone_conduction || [
                'AC(TE) − BC(unmasked) ≥ 15 dB', 'ABG ≥ 15 dB',
              ]).map((r) => <div key={r}>{r}</div>)}
            </div>
            <div className="mt-1 text-slate-500">
              Bone conduction crosses the skull with essentially no attenuation
              {reference?.interaural_attenuation_bc != null
                && ` (IA ${reference.interaural_attenuation_bc} dB)`}, so an
              unmasked bone threshold never belongs to a known ear on its own.
            </div>
          </div>
        </div>
        {reference?.dilemma && (
          <div className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-[11.5px] leading-relaxed text-rose-900">
            <span className="font-semibold">The masking dilemma. </span>
            {reference.dilemma}
          </div>
        )}
        {/* Every transducer the service knows, so the interaural attenuation
            behind each option is visible rather than implied by the label. */}
        {reference?.transducers?.length > 0 && (
          <ul className="mt-2 space-y-1">
            {reference.transducers.map((t) => (
              <li key={t.key} className="text-[11.5px] leading-relaxed text-slate-600">
                <span className="font-medium text-slate-700">{t.label}</span>
                {' — IA '}
                {t.ia_range && t.ia_range[0] !== t.ia_range[1]
                  ? `${t.ia_range[0]}–${t.ia_range[1]}`
                  : t.ia_ac} dB
                {t.key === reference.default_transducer && (
                  <span className="text-slate-400"> · service default</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          Ranges under &ldquo;mask&rdquo; are the usable plateau in dB EM — minimum
          effective masking to maximum before the noise crosses back.{' '}
          {(reference?.citations || showing.right?.citations || []).join(' · ')}
        </p>
      </details>

      <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{showing.note}</p>
    </div>
  )
}
