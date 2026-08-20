// Tuning forks — the bedside battery, above the threshold grid because that
// is the order the examination actually happens in.
//
// Two things this panel exists to show and a printed form cannot:
//
//   1. THE BRACKET. The frequency at which the Rinne reverses sizes the
//      air-bone gap. Reversal at 256 alone means a small gap; at all three
//      forks it means a large one. That is drawn as a band on a dB axis, with
//      the gap actually measured from the audiogram marked on the same axis —
//      prediction and measurement side by side rather than in two places.
//
//   2. THE CONTRADICTION. A negative Rinne with the Weber lateralising the
//      other way cannot be a conductive loss; it is almost always a dead ear
//      whose bone-conducted sound crossed the skull. That result gets a red
//      banner and no diagnosis, because reporting it as conductive is the
//      single most consequential mistake this battery invites.

import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

const EARS = ['right', 'left']
const EAR_TONE = { right: 'text-red-600', left: 'text-blue-600' }

const RINNE_OPTS = [
  { key: 'ac_louder', short: 'AC', title: 'Air louder — positive Rinne' },
  { key: 'bc_louder', short: 'BC', title: 'Bone louder — negative Rinne' },
  { key: 'equal', short: '=', title: 'Equal / cannot choose' },
  { key: 'not_heard', short: '—', title: 'Not heard at either placement' },
]

const WEBER_OPTS = [
  { key: 'right', label: 'Right' },
  { key: 'midline', label: 'Midline' },
  { key: 'left', label: 'Left' },
  { key: 'none', label: 'Not heard' },
]

const LEVEL_STYLE = {
  contradiction: 'border-rose-300 bg-rose-50 text-rose-900',
  validity: 'border-slate-300 bg-slate-50 text-slate-700',
  warning: 'border-amber-300 bg-amber-50 text-amber-900',
  annotation: 'border-amber-300 bg-amber-50 text-amber-900',
  grid: 'border-emerald-300 bg-emerald-50 text-emerald-900',
}

const PRESETS = [
  {
    label: 'Normal',
    right: { 250: 'ac_louder', 500: 'ac_louder', 1000: 'ac_louder' },
    left: { 250: 'ac_louder', 500: 'ac_louder', 1000: 'ac_louder' },
    weber: 'midline',
  },
  {
    label: 'Right conductive',
    right: { 250: 'bc_louder', 500: 'bc_louder', 1000: 'ac_louder' },
    left: { 250: 'ac_louder', 500: 'ac_louder', 1000: 'ac_louder' },
    weber: 'right',
  },
  {
    label: 'Left sensorineural',
    right: { 250: 'ac_louder', 500: 'ac_louder', 1000: 'ac_louder' },
    left: { 250: 'ac_louder', 500: 'ac_louder', 1000: 'ac_louder' },
    weber: 'right',
  },
  {
    label: 'False-negative Rinne',
    right: { 250: 'bc_louder', 500: 'bc_louder', 1000: 'bc_louder' },
    left: { 250: 'ac_louder', 500: 'ac_louder', 1000: 'ac_louder' },
    weber: 'left',
  },
  {
    label: 'Bilateral conductive',
    right: { 250: 'bc_louder', 500: 'bc_louder', 1000: 'ac_louder' },
    left: { 250: 'bc_louder', 500: 'bc_louder', 1000: 'ac_louder' },
    weber: 'midline',
  },
]

/** The bracket the forks imply, with the measured gap on the same axis. */
function GapBracket({ ear, bracket, measured }) {
  if (!bracket || bracket.detected === null) return null
  const MAX = 60
  const lo = bracket.low_db ?? 0
  const hi = bracket.high_db ?? MAX
  const pct = (v) => `${Math.min(100, (v / MAX) * 100)}%`

  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className={`text-[12px] font-bold uppercase ${EAR_TONE[ear]}`}>
          {ear} ear
        </span>
        <span className="text-[12px] font-semibold text-slate-700">
          {bracket.detected ? bracket.label : `no gap ≥ ${bracket.high_db} dB detected`}
        </span>
      </div>

      <div className="relative mt-2 h-7">
        <div className="absolute inset-x-0 top-2.5 h-2 rounded bg-slate-100" />
        {bracket.detected && (
          <div
            className="absolute top-2.5 h-2 rounded bg-teal-500/70"
            style={{ left: pct(lo), width: pct(Math.max(0, hi - lo)) }}
            title={`Air-bone gap implied by the forks: ${bracket.label}`}
          />
        )}
        {measured != null && (
          <div className="absolute top-0 flex -translate-x-1/2 flex-col items-center"
            style={{ left: pct(Math.max(0, Math.min(MAX, measured))) }}>
            <div className="h-4 w-0.5 bg-slate-900" />
            <span className="mt-0.5 whitespace-nowrap text-[10px] font-semibold text-slate-900">
              {measured} dB
            </span>
          </div>
        )}
      </div>

      <div className="flex justify-between text-[9.5px] text-slate-400">
        {[0, 15, 30, 45, 60].map((t) => <span key={t}>{t}</span>)}
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
        {bracket.statement}
      </p>
    </div>
  )
}

export default function TuningForkPanel({ thresholds }) {
  const { setTuningFork } = useApp()
  const [reference, setReference] = useState(null)
  const [freq, setFreq] = useState(500)
  const [responses, setResponses] = useState({ right: {}, left: {} })
  const [weber, setWeber] = useState(null)
  const [masked, setMasked] = useState({ right: false, left: false })
  const [otoscopy, setOtoscopy] = useState({ right: 'not_performed', left: 'not_performed' })
  const [bing, setBing] = useState({ right: null, left: null })
  const [reserve, setReserve] = useState({ right: null, left: null })
  const [useThresholds, setUseThresholds] = useState(true)
  const [result, setResult] = useState(null)

  useEffect(() => {
    api.tuningForkReference().then(setReference).catch(() => setReference(null))
  }, [])

  // The audiogram is only sent when it has something to say — an empty grid
  // would otherwise read as "no gap measured" and silently overrule the forks.
  const hasThresholds = useMemo(() => EARS.every((e) =>
    Object.keys(thresholds?.[e]?.ac || {}).length &&
    Object.keys(thresholds?.[e]?.bc || {}).length), [thresholds])

  const payload = useMemo(() => {
    const num = (o) => Object.fromEntries(Object.entries(o || {})
      .filter(([, v]) => v !== '' && v != null)
      .map(([k, v]) => [k, v]))
    const body = {
      weber, weber_freq: freq,
      right: { responses: responses.right, masked: masked.right, otoscopy: otoscopy.right },
      left: { responses: responses.left, masked: masked.left, otoscopy: otoscopy.left },
      bing: Object.fromEntries(EARS.filter((e) => bing[e])
        .map((e) => [e, { response: bing[e], freq: 250 }])),
      reserve: Object.fromEntries(EARS.filter((e) => reserve[e])
        .map((e) => [e, { schwabach: reserve[e], examiner_normal_hearing: true }])),
    }
    if (useThresholds && hasThresholds) {
      body.right_thresholds = { ac: num(thresholds.right.ac), bc: num(thresholds.right.bc) }
      body.left_thresholds = { ac: num(thresholds.left.ac), bc: num(thresholds.left.bc) }
    }
    return body
  }, [responses, weber, freq, masked, otoscopy, bing, reserve,
      useThresholds, hasThresholds, thresholds])

  // Nothing is sent until at least one Rinne or the Weber has been answered.
  // An unanswered battery must not reach the store either: the dashboard would
  // then show the forks as performed, and a fork battery nobody did is a
  // stronger claim than no fork battery at all.
  useEffect(() => {
    const anything = weber || EARS.some((e) => Object.keys(responses[e]).length)
    if (!anything) { setResult(null); return }
    let cancelled = false
    api.tuningFork(payload)
      .then((r) => {
        if (cancelled) return
        setResult(r)
        // The whole response goes up, not just the headline — the dashboard
        // cross-checks side, type and level against the audiogram, and the rule
        // that produced them is what makes a disagreement auditable.
        if (r?.grid) setTuningFork(r)
      })
      .catch(() => { if (!cancelled) setResult(null) })
    return () => { cancelled = true }
  }, [payload, weber, responses, setTuningFork])

  const setRinne = (ear, f, value) => setResponses((prev) => {
    const next = { ...prev[ear] }
    if (next[f] === value) delete next[f]
    else next[f] = value
    return { ...prev, [ear]: next }
  })

  const applyPreset = (p) => {
    setResponses({ right: { ...p.right }, left: { ...p.left } })
    setWeber(p.weber)
    setFreq(500)
    setMasked({ right: true, left: true })
    setOtoscopy({ right: 'clear', left: 'clear' })
  }

  const forks = reference?.forks || []
  const rinneForks = forks.filter((f) => f.rinne)
  const grid = result?.grid

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">Tuning fork tests</h2>
        <span className="text-[11.5px] text-slate-500">
          a side and a type — never a threshold
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <button key={p.label} type="button" onClick={() => applyPreset(p)}
            className="rounded-lg border border-slate-200 bg-white px-2 py-0.5 text-[11.5px] text-slate-600 transition hover:border-teal-300 hover:text-teal-700">
            {p.label}
          </button>
        ))}
      </div>

      {/* ---- Rinne, one row per fork ------------------------------------ */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[440px] text-[12px]">
          <thead>
            <tr className="border-b border-slate-200 text-[10.5px] uppercase tracking-wide text-slate-400">
              <th className="px-1 py-1.5 text-left">Fork</th>
              <th className="px-1 py-1.5 text-center">Reverses at</th>
              {EARS.map((e) => (
                <th key={e} className={`px-1 py-1.5 text-center ${EAR_TONE[e]}`}>
                  {e} Rinne
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {forks.map((f) => (
              <tr key={f.nominal_hz} className="border-b border-slate-100 last:border-0">
                <td className="px-1 py-1.5">
                  <span className="font-medium text-slate-800">{f.fork_hz} Hz</span>
                  {f.role === 'standard' && (
                    <span className="ml-1.5 rounded bg-teal-100 px-1 py-0.5 text-[9px] font-semibold uppercase text-teal-700">
                      standard
                    </span>
                  )}
                  <span className="ml-1 block text-[10px] text-slate-400">
                    ({f.nominal_hz} Hz)
                  </span>
                </td>
                <td className="px-1 py-1.5 text-center">
                  {f.crossover_db == null ? (
                    <span className="text-[10.5px] text-slate-400" title={f.note}>
                      no valid value
                    </span>
                  ) : (
                    <span className="font-mono text-[11px] text-slate-600"
                      title={`Sources give ${f.crossover_range?.join('–')} dB`}>
                      ≥{f.crossover_db} dB
                    </span>
                  )}
                </td>
                {EARS.map((ear) => (
                  <td key={ear} className="px-1 py-1.5">
                    <div className="flex justify-center gap-0.5">
                      {RINNE_OPTS.map((o) => {
                        const on = responses[ear][f.nominal_hz] === o.key
                        const usable = f.rinne
                        return (
                          <button key={o.key} type="button" title={o.title}
                            onClick={() => setRinne(ear, f.nominal_hz, o.key)}
                            className={`h-6 w-7 rounded border text-[10.5px] font-semibold transition ${
                              on
                                ? o.key === 'bc_louder'
                                  ? 'border-amber-500 bg-amber-100 text-amber-800'
                                  : 'border-teal-500 bg-teal-50 text-teal-800'
                                : usable
                                  ? 'border-slate-200 bg-white text-slate-500 hover:border-slate-300'
                                  : 'border-slate-100 bg-slate-50 text-slate-300'}`}>
                            {o.short}
                          </button>
                        )
                      })}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[10.5px] leading-relaxed text-slate-400">
        AC = air louder (positive) · BC = bone louder (negative) · = equal · — not heard.
        2048 and 4096 Hz have no established crossover value, so no air-bone gap is
        inferred from them however they are answered.
      </p>

      {/* ---- Weber and conditions --------------------------------------- */}
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-200 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Weber — lateralises to
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {WEBER_OPTS.map((o) => (
              <button key={o.key} type="button"
                onClick={() => setWeber(weber === o.key ? null : o.key)}
                className={`rounded-lg border px-2 py-0.5 text-[11.5px] transition ${
                  weber === o.key
                    ? 'border-teal-500 bg-teal-50 font-medium text-teal-800'
                    : 'border-slate-200 bg-white text-slate-600'}`}>
                {o.label}
              </button>
            ))}
          </div>
          <label className="mt-2 block text-[11px]">
            <span className="text-slate-500">at</span>
            <select value={freq} onChange={(e) => setFreq(Number(e.target.value))}
              className="ml-1.5 rounded-lg border border-slate-300 px-1.5 py-0.5 text-[11.5px]">
              {forks.map((f) => (
                <option key={f.nominal_hz} value={f.nominal_hz} disabled={!f.weber}>
                  {f.fork_hz} Hz{f.weber ? '' : ' — invalid'}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="rounded-xl border border-slate-200 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Conditions
          </div>
          {EARS.map((ear) => (
            <div key={ear} className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px]">
              <span className={`w-10 font-bold uppercase ${EAR_TONE[ear]}`}>{ear}</span>
              <label className="flex cursor-pointer items-center gap-1 text-slate-600">
                <input type="checkbox" checked={masked[ear]} className="h-3 w-3 accent-teal-600"
                  onChange={(e) => setMasked({ ...masked, [ear]: e.target.checked })} />
                masked
              </label>
              <select value={otoscopy[ear]} className="rounded border border-slate-300 px-1 py-0.5 text-[11px]"
                onChange={(e) => setOtoscopy({ ...otoscopy, [ear]: e.target.value })}>
                <option value="not_performed">otoscopy?</option>
                <option value="clear">clear</option>
                <option value="obstructed">obstructed</option>
              </select>
              <select value={bing[ear] || ''} className="rounded border border-slate-300 px-1 py-0.5 text-[11px]"
                onChange={(e) => setBing({ ...bing, [ear]: e.target.value || null })}>
                <option value="">Bing?</option>
                <option value="louder">louder</option>
                <option value="no_change">no change</option>
              </select>
              <select value={reserve[ear] || ''} className="rounded border border-slate-300 px-1 py-0.5 text-[11px]"
                onChange={(e) => setReserve({ ...reserve, [ear]: e.target.value || null })}>
                <option value="">Schwabach?</option>
                <option value="normal">normal</option>
                <option value="shortened">shortened</option>
                <option value="prolonged">prolonged</option>
              </select>
            </div>
          ))}
        </div>
      </div>

      {/* ---- The verdict ------------------------------------------------- */}
      {grid && (
        <>
          <div className={`mt-4 rounded-xl border px-3 py-2.5 ${
            LEVEL_STYLE[grid.level] || LEVEL_STYLE.grid}`}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider opacity-70">
                {grid.level === 'contradiction' ? 'These cannot both be true'
                  : grid.level === 'validity' ? 'Suppressed'
                    : grid.level === 'warning' ? 'Provisional' : 'Fork battery'}
              </span>
              <span className="rounded bg-white/60 px-1.5 py-0.5 font-mono text-[9.5px] font-semibold">
                rule {grid.rule}
              </span>
            </div>
            <p className="mt-1 text-[13px] font-medium leading-relaxed">{grid.headline}</p>
            {grid.notes?.map((n, i) => (
              <p key={i} className="mt-1.5 text-[11.5px] leading-relaxed opacity-90">{n}</p>
            ))}
          </div>

          {grid.recommendations?.length > 0 && (
            <ul className="mt-2 space-y-1">
              {grid.recommendations.map((r, i) => (
                <li key={i} className="text-[11.5px] leading-relaxed text-slate-600">
                  → {r}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {/* ---- Bracket vs the audiogram ------------------------------------ */}
      {result?.gap_bracket && (
        <div className="mt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-[12px] font-semibold uppercase tracking-wide text-slate-500">
              Air-bone gap implied by the forks
            </h3>
            {hasThresholds && (
              <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-600">
                <input type="checkbox" checked={useThresholds} className="h-3 w-3 accent-teal-600"
                  onChange={(e) => setUseThresholds(e.target.checked)} />
                check against the audiogram above
              </label>
            )}
          </div>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {EARS.map((ear) => (
              <GapBracket key={ear} ear={ear} bracket={result.gap_bracket[ear]}
                measured={result.cross_check?.[ear]?.gaps?.[String(freq)]} />
            ))}
          </div>
        </div>
      )}

      {result?.cross_check && Object.values(result.cross_check).some((c) => c?.disagreements?.length) && (
        <div className="mt-3 space-y-1.5">
          {EARS.map((ear) => (result.cross_check[ear]?.disagreements || []).map((d, i) => (
            <p key={`${ear}-${i}`}
              className="rounded-lg bg-amber-50 px-3 py-1.5 text-[11.5px] leading-relaxed text-amber-900">
              <span className="font-semibold uppercase">{ear}:</span> {d}
            </p>
          )))}
        </div>
      )}

      {result?.urgent?.map((u, i) => (
        <p key={i} className="mt-3 rounded-lg border border-rose-400 bg-rose-50 px-3 py-2 text-[12px] font-semibold text-rose-900">
          {u}
        </p>
      ))}

      {reference?.limits && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[12px] font-medium text-teal-700">
            What tuning forks cannot do
          </summary>
          <ul className="mt-1.5 space-y-1 text-[11.5px] leading-relaxed text-slate-600">
            {reference.limits.map((l) => <li key={l}>· {l}</li>)}
          </ul>
          <p className="mt-1.5 text-[10.5px] text-slate-400">
            {reference.citations.join(' · ')}
          </p>
        </details>
      )}
    </div>
  )
}
