// ABR, MLR and LLR — the same pathway sampled at increasing heights.
//
// The three recordings are on one page because their value is comparative.
// A normal ABR under an abnormal MLR puts the lesion above the brainstem;
// neither recording says that alone. The battery strip at the top is the
// conclusion the page exists to produce.
//
// Every ABR latency is plotted against the normative mean for the intensity
// actually used, with the 2 SD band drawn behind it, because Wave V sits near
// 5.4 ms at 90 dB nHL and near 7.5 ms at 20 dB — an absolute latency without
// its intensity cannot be judged.
//
// NOTHING ON THIS PAGE IS THE PATIENT'S UNTIL IT IS ATTACHED. An example is
// not a recording. Publishing the battery on render would tick "evoked
// potentials" done for a patient who never had the test and put "the pathway
// is intact" on their results beside an MRI referral. So a section only
// becomes this patient's when a value in it is typed, and the record changes
// only when the clinician presses Attach on a panel that lists exactly what
// will be stored — the same rule the BOA panel and the immittance attach
// button follow. The first value typed into an example clears the rest of it:
// an untouched example Wave I left beside a measured Wave V would be recorded
// as this patient's and make an interval measurable that never was.
//
// EVERY SECTION OPENS ON EMPTY FIELDS, waiting to be typed into. It used to
// open on a loaded example with the preset chips above the inputs, and that
// read as a demonstration rather than a form: the fields were always
// editable, but a clinician seeing numbers already in them and a row of
// scenario buttons on top reasonably concluded the page only did presets.
// Entry is the point of the page, so entry is the default and the examples
// are behind their own tab.

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, ComposedChart, ErrorBar, Legend, Line, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import StepNav from '../components/StepNav.jsx'

const EAR_TONE = { right: '#dc2626', left: '#2563eb' }
const OTHER_EAR = { right: 'left', left: 'right' }

const ABR_PRESETS = [
  { label: 'Normal (80 dB nHL)', intensity: 80, waves: { I: 1.62, III: 3.68, V: 5.47 } },
  { label: 'Retrocochlear — stretched I–V', intensity: 80,
    waves: { I: 1.62, III: 4.30, V: 6.60 } },
  { label: 'Conductive — whole trace shifted', intensity: 80,
    waves: { I: 2.42, III: 4.48, V: 6.27 } },
  { label: 'Near threshold (30 dB nHL)', intensity: 30, waves: { III: 5.45, V: 7.24 } },
  { label: 'No Wave V', intensity: 80, waves: { I: 1.62, III: 3.68 } },
]

const MLR_PRESETS = [
  { label: 'Normal', peaks: { Na: 18, Pa: 28, Nb: 38, Pb: 52 }, amp: 1.2 },
  { label: 'Delayed Pa only', peaks: { Na: 18, Pa: 38, Nb: 38, Pb: 52 }, amp: 1.0 },
  { label: 'All peaks delayed', peaks: { Na: 22, Pa: 38, Nb: 48, Pb: 62 }, amp: 1.0 },
  { label: 'Absent Na', peaks: { Pa: 28, Nb: 38, Pb: 52 }, amp: 0.9 },
  { label: 'Reduced amplitude', peaks: { Na: 18, Pa: 28, Nb: 38, Pb: 52 }, amp: 0.2 },
]

const LLR_PRESETS = [
  { label: 'Adult, normal', peaks: { P1: 52, N1: 105, P2: 180, N2: 320 },
    amp: 9, age: 300 },
  { label: 'Toddler, age-appropriate', peaks: { P1: 118, N1: 140, P2: 195 },
    amp: 7, age: 18 },
  { label: 'Delayed cortical maturation', peaks: { P1: 160, N1: 150, P2: 200 },
    amp: 4, age: 60 },
  { label: 'Absent N1', peaks: { P1: 52, P2: 180 }, amp: 3, age: 300 },
]

const ABR_FIELDS = ['I', 'III', 'V']
const MLR_FIELDS = ['Na', 'Pa', 'Nb', 'Pb']
const LLR_FIELDS = ['P1', 'N1', 'P2', 'N2']

// Inputs are held as strings so a half-typed value does not jump about; only
// finite numbers ever leave the page.
const num = (v) => (v === '' || v == null || !Number.isFinite(Number(v)) ? null : Number(v))
const asStrings = (obj, fields) =>
  Object.fromEntries(fields.map((k) => [k, obj?.[k] != null ? String(obj[k]) : '']))
const numbersOf = (fields, values) => Object.fromEntries(
  fields.map((k) => [k, num(values?.[k])]).filter(([, v]) => v != null))
const listValues = (obj, unit) => Object.entries(obj || {})
  .map(([k, v]) => `${k} ${v}`).join(' · ') + (Object.keys(obj || {}).length ? ` ${unit}` : '—')

function Chip({ tone = 'slate', children }) {
  const cls = {
    slate: 'bg-slate-100 text-slate-600',
    good: 'bg-emerald-100 text-emerald-700',
    warn: 'bg-amber-100 text-amber-800',
    bad: 'bg-rose-100 text-rose-700',
  }[tone]
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
      {children}
    </span>
  )
}

const STATUS_TONE = { normal: 'good', borderline: 'warn', indeterminate: 'warn', abnormal: 'bad' }

function Notes({ items }) {
  if (!items?.length) return null
  return (
    <ul className="mt-2 space-y-1.5">
      {items.map((n, i) => (
        <li key={i} className="rounded-lg bg-slate-50 px-3 py-1.5 text-[12px] leading-relaxed text-slate-600">
          {n}
        </li>
      ))}
    </ul>
  )
}

function Panel({ title, right, children, tour }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
      data-tour={tour}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
        {right}
      </div>
      {children}
    </div>
  )
}

function Presets({ options, active, onPick }) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {options.map((p) => (
        <button key={p.label} type="button" onClick={() => onPick(p)}
          className={`rounded-lg border px-2.5 py-1 text-[12px] transition ${
            active === p.label
              ? 'border-teal-500 bg-teal-50 font-medium text-teal-800'
              : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'}`}>
          {p.label}
        </button>
      ))}
    </div>
  )
}

/**
 * Enter values, or load a worked example.
 *
 * `source` is the single source of truth — 'entered' or 'example' — so the
 * tab cannot drift out of step with what the fields actually hold. Switching
 * to Enter values blanks the fields rather than leaving an example's numbers
 * in them to be mistaken for a measurement.
 */
function EntryTabs({ source, onValues, onExample }) {
  const mode = source === 'example' ? 'preset' : 'values'
  return (
    <div role="tablist" aria-label="How this recording was entered"
      className="mt-3 flex rounded-lg bg-slate-100 p-0.5 text-[12px]">
      {[['values', 'Enter values'], ['preset', 'Example traces']].map(([k, label]) => (
        <button key={k} type="button" role="tab" aria-selected={mode === k}
          onClick={() => (k === 'values' ? onValues() : onExample())}
          className={`flex-1 rounded-md px-3 py-1 font-medium transition ${
            mode === k ? 'bg-white text-teal-700 shadow-sm'
              : 'text-slate-500 hover:text-slate-700'}`}>
          {label}
        </button>
      ))}
    </div>
  )
}

// Which of the two a section is showing — said on the section itself, so an
// example can never be mistaken for a measurement.
function SourceNote({ source, label, empty = false }) {
  // An empty form has nothing to claim. Announcing "entered for this patient"
  // over blank fields told the reader a recording existed before one did.
  if (source === 'entered' && empty) {
    return (
      <p className="mt-2 text-[11.5px] leading-relaxed text-slate-400">
        Type the measurements from the recording. Nothing is attached to the
        patient until you press Attach below.
      </p>
    )
  }
  return source === 'entered' ? (
    <p className="mt-2 rounded-lg border border-teal-200 bg-teal-50/60 px-3 py-1.5 text-[11.5px] text-teal-900">
      <span className="font-semibold">Entered for this patient.</span> These values
      can be attached to the record below.
    </p>
  ) : (
    <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-1.5 text-[11.5px] text-amber-900">
      <span className="font-semibold">Example — {label}.</span> Not this patient and
      never attached. Typing into any field clears the example values, so only
      what you enter is recorded.
    </p>
  )
}

function NumField({ label, value, onChange, step = 'any', min }) {
  return (
    <label className="text-[12px]">
      <span className="mb-1 block font-medium text-slate-600">{label}</span>
      <input type="number" step={step} min={min} value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
    </label>
  )
}

// ------------------------------------------------------------------- ABR ---
const abrFromPreset = (p) => ({
  source: 'example', label: p.label, intensity: String(p.intensity),
  waves: asStrings(p.waves, ABR_FIELDS), includesDelay: false, cm: false,
})
// What an example becomes on its first edit. The insert-delay answer starts
// unanswered: a preset's values are already corrected, and inheriting that
// silently would shift a machine reading by 0.9 ms.
const blankAbr = () => ({
  source: 'entered', label: null, intensity: '',
  waves: asStrings({}, ABR_FIELDS), includesDelay: null, cm: false,
})

const abrRequest = (run, ear, sex, ageMonths) => {
  const intensity = num(run.intensity)
  if (intensity == null) return null
  return {
    ear, intensity_db_nhl: intensity, waves: numbersOf(ABR_FIELDS, run.waves),
    latencies_include_delay: run.includesDelay === true,
    cm_present: Boolean(run.cm), sex, age_months: ageMonths,
  }
}

// One ear's analysis, kept current whether or not that ear is on screen: the
// sex and age the backend judges against come from the patient, and the ear
// the clinician is not looking at must be re-judged when they change, or the
// interaural comparison and the record would carry a stale reading.
function useAbrRun(ear, run, sex, ageMonths, onResult, showToast) {
  const [result, setResult] = useState(null)
  const request = useMemo(() => abrRequest(run, ear, sex, ageMonths),
    [run, ear, sex, ageMonths])

  useEffect(() => {
    // Without a level there is no run, and the page must not keep offering the
    // last complete one for attachment while the field shows something else.
    if (!request) { setResult(null); onResult?.(ear, null); return undefined }
    let cancelled = false
    api.abr(request)
      .then((r) => {
        if (cancelled) return
        setResult(r)
        onResult?.(ear, { result: r, request, source: run.source, label: run.label,
          delayChosen: run.includesDelay != null })
      })
      .catch((e) => {
        if (cancelled) return
        setResult(null)
        onResult?.(ear, null)
        showToast(e.message, 'error')
      })
    return () => { cancelled = true }
  }, [request, ear, run.source, run.label, run.includesDelay, onResult, showToast])

  return result
}

function ABRSection({ ear, sex, ageMonths, onResult }) {
  const { showToast } = useApp()
  // Each ear keeps its own run. The two ears are recorded separately in the
  // booth, and a retrocochlear picture is one-sided by nature — carrying one
  // ear's trace over to the other would make the interaural comparison
  // meaningless before it was ever made.
  const [runs, setRuns] = useState(
    () => ({ right: blankAbr(), left: blankAbr() }))
  const run = runs[ear]
  const rightResult = useAbrRun('right', runs.right, sex, ageMonths, onResult, showToast)
  const leftResult = useAbrRun('left', runs.left, sex, ageMonths, onResult, showToast)
  const result = ear === 'right' ? rightResult : leftResult
  const [ladder, setLadder] = useState(null)

  const pickPreset = useCallback(
    (p) => setRuns((prev) => ({ ...prev, [ear]: abrFromPreset(p) })), [ear])

  // Any edit makes the run this patient's, and the first one starts it from
  // blank so that no example value is carried into the record.
  const edit = useCallback((change) => setRuns((prev) => {
    const was = prev[ear]
    const base = was.source === 'example' ? blankAbr() : was
    return { ...prev, [ear]: { ...change(base), source: 'entered', label: null } }
  }), [ear])

  // A fixed example ladder that shows how threshold estimation reads. It is
  // never this patient's and is never attached.
  useEffect(() => {
    api.abrThreshold([
      { intensity: 80, wave_v: 5.47 }, { intensity: 60, wave_v: 5.88 },
      { intensity: 40, wave_v: 6.65 }, { intensity: 30, wave_v: 7.24 },
      { intensity: 20, wave_v: null },
    ]).then(setLadder).catch(() => setLadder(null))
  }, [])

  // Latency against the normative mean, with the 2 SD band as an error bar.
  const chartData = useMemo(() => (result?.absolute || [])
    .filter((w) => w.present && w.norm)
    .map((w) => ({
      wave: w.wave,
      latency: w.latency,
      mean: w.norm.mean,
      sd2: [w.norm.sd * 2, w.norm.sd * 2],
      z: w.z,
    })), [result])

  const rowText = result && (result.norm_interpolated
    ? `interpolated between the ${result.norm_rows_db_nhl[0]} and ${result.norm_rows_db_nhl[1]} dB nHL rows`
    : `compared against the ${result.norm_row_db_nhl} dB nHL row`)

  return (
    <Panel
      title="ABR — eighth nerve and brainstem"
      tour="abr-latency"
      right={result && (
        <span className="flex items-center gap-2 text-[11.5px] text-slate-500">
          {rowText}
          <Chip tone={STATUS_TONE[result.status] || 'slate'}>{result.status}</Chip>
        </span>
      )}
    >
      <EntryTabs source={run.source}
        onValues={() => setRuns((prev) => ({ ...prev, [ear]: blankAbr() }))}
        onExample={() => pickPreset(ABR_PRESETS[0])} />

      {run.source === 'example' && (
        <Presets options={ABR_PRESETS} active={run.label} onPick={pickPreset} />
      )}

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <NumField label="Level (dB nHL)" value={run.intensity} step="5" min="0"
          onChange={(v) => edit((b) => ({ ...b, intensity: v }))} />
        {ABR_FIELDS.map((w) => (
          <NumField key={w} label={`Wave ${w} (ms)`} value={run.waves[w]} step="0.01"
            onChange={(v) => edit((b) => ({ ...b, waves: { ...b.waves, [w]: v } }))} />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] text-slate-600">
        <span className="font-medium">Latencies as entered:</span>
        <label className="flex items-center gap-1.5">
          <input type="radio" name={`delay-${ear}`} checked={run.includesDelay === true}
            onChange={() => edit((b) => ({ ...b, includesDelay: true }))} />
          include the 0.9 ms insert-earphone delay
        </label>
        <label className="flex items-center gap-1.5">
          <input type="radio" name={`delay-${ear}`} checked={run.includesDelay === false}
            onChange={() => edit((b) => ({ ...b, includesDelay: false }))} />
          already corrected
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={Boolean(run.cm)}
            onChange={(e) => {
              const checked = e.target.checked
              edit((b) => ({ ...b, cm: checked }))
            }} />
          cochlear microphonic seen
        </label>
      </div>
      {run.source === 'entered' && num(run.intensity) == null && (
        <p className="mt-1.5 text-[11.5px] font-medium text-amber-800">
          Enter the stimulus level — a latency cannot be judged without the
          intensity it was recorded at.
        </p>
      )}
      {run.source === 'entered' && run.includesDelay == null && (
        <p className="mt-1.5 text-[11.5px] font-medium text-amber-800">
          Say whether these latencies still contain the insert-earphone delay —
          a 0.9 ms error turns a normal trace into a delayed one. Until then the
          preview treats them as corrected and they cannot be attached.
        </p>
      )}
      <SourceNote source={run.source} label={run.label}
        empty={num(run.intensity) == null
          && ABR_FIELDS.every((w) => num(run.waves[w]) == null)} />

      {result && (
        <>
          <div className="mt-4 h-56 w-full">
            <ResponsiveContainer>
              <ComposedChart data={chartData}
                margin={{ top: 8, right: 12, bottom: 18, left: -6 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis dataKey="wave" tick={{ fontSize: 12, fill: '#64748b' }}
                  label={{ value: 'Wave', position: 'insideBottom', offset: -12,
                    fontSize: 10, fill: '#94a3b8' }} />
                <YAxis tick={{ fontSize: 11, fill: '#64748b' }} width={42}
                  label={{ value: 'Latency (ms)', angle: -90,
                    position: 'insideLeft', fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }}
                  formatter={(v, n) => [`${v} ms`, n === 'mean' ? 'Normative mean'
                    : 'This trace']} />
                <Legend wrapperStyle={{ fontSize: 10.5 }} />
                <Line name="mean" dataKey="mean" stroke="#94a3b8" strokeWidth={2}
                  strokeDasharray="5 4" dot={{ r: 3, fill: '#94a3b8' }}
                  isAnimationActive={false}>
                  <ErrorBar dataKey="sd2" width={6} strokeWidth={1.3}
                    stroke="#94a3b8" strokeOpacity={0.6} direction="y" />
                </Line>
                <Line name="latency" dataKey="latency" stroke={EAR_TONE[ear]}
                  strokeWidth={2.2} dot={{ r: 4, fill: EAR_TONE[ear] }}
                  isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-center text-[11px] text-slate-500">
            Grey is the normative mean with its 2 SD band at {result.intensity_db_nhl} dB nHL.
            A wave is delayed beyond 3 SD and borderline between 2 and 3 SD.
          </p>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[440px] text-left text-[12px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                  <th className="py-1 pr-3 font-medium">Wave</th>
                  <th className="py-1 pr-3 font-medium">Latency</th>
                  <th className="py-1 pr-3 font-medium">Normal</th>
                  <th className="py-1 font-medium">z</th>
                </tr>
              </thead>
              <tbody>
                {result.absolute.filter((w) => w.expected_at_this_level).map((w) => (
                  <tr key={w.wave} className="border-t border-slate-100">
                    <td className="py-1.5 pr-3 font-semibold text-slate-700">{w.wave}</td>
                    <td className="py-1.5 pr-3 font-mono">
                      {w.present ? `${w.latency} ms` : <span className="text-slate-400">absent</span>}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-slate-500">
                      {w.norm ? `${w.norm.sd2[0]}–${w.norm.sd2[1]}` : '—'}
                      {w.upper_limit != null && (
                        <span className="text-slate-400"> · delayed &gt; {w.upper_limit}</span>
                      )}
                    </td>
                    <td className="py-1.5">
                      {w.present && w.z !== undefined ? (
                        <Chip tone={w.delayed ? 'bad'
                          : (w.borderline || !w.within_3sd) ? 'warn' : 'good'}>
                          {w.z > 0 ? `+${w.z}` : w.z}
                        </Chip>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                  </tr>
                ))}
                {result.interwave.filter((e) => e.present).map((e) => (
                  <tr key={e.pair} className="border-t border-slate-100 bg-slate-50/60">
                    <td className="py-1.5 pr-3 font-semibold text-slate-700">{e.pair}</td>
                    <td className="py-1.5 pr-3 font-mono">{e.value} ms</td>
                    <td className="py-1.5 pr-3 font-mono text-slate-500">
                      ≤ {e.upper_limit} <span className="text-slate-400">(adult limit)</span>
                      {e.upper_95_cl != null && (
                        <span className="text-slate-400"> · 95% ≤ {e.upper_95_cl}</span>
                      )}
                    </td>
                    <td className="py-1.5">
                      <Chip tone={e.prolonged ? 'bad' : e.borderline ? 'warn' : 'good'}>
                        {e.prolonged ? 'prolonged' : e.borderline ? 'borderline' : 'within'}
                      </Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Notes items={result.findings} />

          {ladder && (
            <div className="mt-3 rounded-xl border border-slate-200 p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-[12px] font-semibold text-slate-700">
                  Threshold estimation
                </span>
                <Chip tone="warn">example ladder — not this patient</Chip>
              </div>
              <p className="mt-0.5 text-[11.5px] leading-relaxed text-slate-600">
                {ladder.message}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {ladder.rows.map((r) => (
                  <span key={r.intensity}
                    className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
                      r.present ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-slate-100 text-slate-400'}`}>
                    {r.intensity} dB nHL{r.present ? ` · ${r.wave_v} ms` : ' · none'}
                  </span>
                ))}
              </div>
              {ladder.caveat && (
                <p className="mt-1.5 text-[10.5px] leading-relaxed text-slate-400">{ladder.caveat}</p>
              )}
            </div>
          )}

          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{result.note}</p>
        </>
      )}
    </Panel>
  )
}

// ------------------------------------------------------------------- MLR ---
const mlrFromPreset = (p) => ({
  source: 'example', label: p.label, peaks: asStrings(p.peaks, MLR_FIELDS),
  amp: String(p.amp), sedated: false,
})

const blankMlr = () => ({
  source: 'entered', label: null, peaks: asStrings({}, MLR_FIELDS), amp: '', sedated: false,
})

function MLRSection({ ear, onResult }) {
  const [run, setRun] = useState(blankMlr)
  const [result, setResult] = useState(null)
  // The first edit of an example starts from blank (see the page header).
  const edit = (change) => setRun((prev) => ({
    ...change(prev.source === 'example' ? blankMlr() : prev), source: 'entered', label: null,
  }))

  const request = useMemo(() => {
    const amp = num(run.amp)
    return {
      ear, peaks: numbersOf(MLR_FIELDS, run.peaks),
      amplitudes: amp != null ? { 'Na-Pa': amp } : {}, sedated: Boolean(run.sedated),
    }
  }, [run, ear])

  useEffect(() => {
    let cancelled = false
    api.mlr(request)
      .then((r) => {
        if (cancelled) return
        setResult(r)
        onResult?.({ result: r, request, source: run.source, label: run.label })
      })
      .catch(() => { if (!cancelled) { setResult(null); onResult?.(null) } })
    return () => { cancelled = true }
  }, [request, run.source, run.label, onResult])

  return (
    <Panel
      title="MLR — thalamus and primary cortex"
      right={result && (
        <Chip tone={STATUS_TONE[result.status] || (result.abnormal ? 'warn' : 'good')}>
          {result.status || (result.abnormal ? 'abnormal' : 'normal')}
        </Chip>
      )}
    >
      <EntryTabs source={run.source}
        onValues={() => setRun(blankMlr())}
        onExample={() => setRun(mlrFromPreset(MLR_PRESETS[0]))} />

      {run.source === 'example' && (
        <Presets options={MLR_PRESETS} active={run.label}
          onPick={(p) => setRun(mlrFromPreset(p))} />
      )}

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {MLR_FIELDS.map((k) => (
          <NumField key={k} label={`${k} (ms)`} value={run.peaks[k]} step="0.5"
            onChange={(v) => edit((b) => ({ ...b, peaks: { ...b.peaks, [k]: v } }))} />
        ))}
        <NumField label="Na–Pa (µV)" value={run.amp} step="0.1"
          onChange={(v) => edit((b) => ({ ...b, amp: v }))} />
      </div>
      <label className="mt-2 flex items-center gap-1.5 text-[12px] text-slate-600">
        <input type="checkbox" checked={Boolean(run.sedated)}
          onChange={(e) => {
            const checked = e.target.checked
            edit((b) => ({ ...b, sedated: checked }))
          }} />
        recorded under sedation
      </label>
      <SourceNote source={run.source} label={run.label}
        empty={num(run.amp) == null
          && MLR_FIELDS.every((k) => num(run.peaks[k]) == null)} />

      {result && (
        <>
          <div className="mt-3 space-y-1.5">
            {result.peaks.map((p) => (
              <div key={p.peak} className="flex items-center gap-2 text-[12px]">
                <span className="w-8 font-semibold text-slate-700">{p.peak}</span>
                <span className="w-16 font-mono text-slate-600">
                  {p.present ? `${p.latency} ms` : '—'}
                </span>
                {/* The normative window drawn as a bar, with the recorded peak
                    marked on it — a range is easier to read than two numbers. */}
                <span className="relative h-3 flex-1 rounded bg-slate-100">
                  <span className="absolute inset-y-0 rounded bg-emerald-200"
                    style={{ left: `${(p.range[0] / 70) * 100}%`,
                      width: `${((p.range[1] - p.range[0]) / 70) * 100}%` }} />
                  {p.present && (
                    <span className={`absolute inset-y-0 w-0.5 ${
                      p.within_range ? 'bg-emerald-700' : 'bg-rose-600'}`}
                      style={{ left: `${Math.min((p.latency / 70) * 100, 99)}%` }} />
                  )}
                </span>
                <span className="w-24 text-right font-mono text-[11px] text-slate-400">
                  {p.range[0]}–{p.range[1]} ms
                </span>
              </div>
            ))}
          </div>
          <p className="mt-1 text-[11px] text-slate-500">
            Green is the normative window; the tick is this recording. Pa is the
            largest and most repeatable component and anchors interpretation.
          </p>

          {result.patterns.map((p) => (
            <div key={p.key}
              className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
              <div className="font-semibold">{p.label}</div>
              <div className="mt-0.5">{p.description}</div>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11.5px]">
                {p.causes.map((c) => <li key={c}>{c}</li>)}
              </ul>
            </div>
          ))}
          <Notes items={result.findings} />
        </>
      )}
    </Panel>
  )
}

// ------------------------------------------------------------------- LLR ---
const llrFromPreset = (p) => ({
  source: 'example', label: p.label, peaks: asStrings(p.peaks, LLR_FIELDS),
  amp: String(p.amp),
})
const blankLlr = () => ({
  source: 'entered', label: null, peaks: asStrings({}, LLR_FIELDS), amp: '',
})

function LLRSection({ ear, onResult }) {
  const { patient } = useApp()
  const [run, setRun] = useState(blankLlr)
  const [result, setResult] = useState(null)
  // P1 is the one measurement on this page that cannot be read without the
  // age. Normal P1 falls from about 200 ms at three months to about 60 ms by
  // twenty years (Sharma, Dorman & Spahr 2002), so the same 120 ms peak is
  // age-appropriate in a toddler and the marker of an unstimulated cortex in
  // an adult — the finding that decides cochlear-implant candidacy. The
  // recorded patient governs; a preset's own age is only the fallback when the
  // page is used standalone, with nobody registered. The API takes months, so
  // years are converted here.
  const recorded = Number(patient?.age)
  const recordedMonths = patient?.age == null || patient.age === '' || Number.isNaN(recorded)
    ? null : Math.round(recorded * 12)
  const [ageMonths, setAgeMonths] = useState(recordedMonths ?? LLR_PRESETS[0].age)

  useEffect(() => {
    if (recordedMonths != null) setAgeMonths(recordedMonths)
  }, [recordedMonths])

  // Picking a preset carries its scenario age only when there is no patient to
  // contradict it; otherwise the waveform is being judged for this patient.
  const pickPreset = useCallback((p) => {
    setRun(llrFromPreset(p))
    if (recordedMonths == null) setAgeMonths(p.age)
  }, [recordedMonths])
  // The first edit of an example starts from blank (see the page header).
  const edit = (change) => setRun((prev) => ({
    ...change(prev.source === 'example'
      ? { peaks: asStrings({}, LLR_FIELDS), amp: '' } : prev),
    source: 'entered', label: null,
  }))

  const request = useMemo(() => {
    const amp = num(run.amp)
    return {
      ear, peaks: numbersOf(LLR_FIELDS, run.peaks),
      amplitudes: amp != null ? { 'N1-P2': amp } : {},
      age_months: num(ageMonths),
    }
  }, [run, ear, ageMonths])

  useEffect(() => {
    let cancelled = false
    api.llr(request)
      .then((r) => {
        if (cancelled) return
        setResult(r)
        onResult?.({ result: r, request, source: run.source, label: run.label })
      })
      .catch(() => { if (!cancelled) { setResult(null); onResult?.(null) } })
    return () => { cancelled = true }
  }, [request, run.source, run.label, onResult])

  const maturation = result?.maturation

  return (
    <Panel
      title="LLR — auditory cortex"
      right={result && (
        <Chip tone={STATUS_TONE[result.status] || (result.flags.length ? 'warn' : 'good')}>
          {result.flags.length
            ? `${result.flags.length} finding${result.flags.length > 1 ? 's' : ''}`
            : result.status}
        </Chip>
      )}
    >
      <EntryTabs source={run.source}
        onValues={() => setRun(blankLlr())}
        onExample={() => pickPreset(LLR_PRESETS[0])} />

      {run.source === 'example' && (
        <Presets options={LLR_PRESETS} active={run.label} onPick={pickPreset} />
      )}

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-6">
        {LLR_FIELDS.map((k) => (
          <NumField key={k} label={`${k} (ms)`} value={run.peaks[k]} step="1"
            onChange={(v) => edit((b) => ({ ...b, peaks: { ...b.peaks, [k]: v } }))} />
        ))}
        <NumField label="N1–P2 (µV)" value={run.amp} step="0.5"
          onChange={(v) => edit((b) => ({ ...b, amp: v }))} />
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Age (months)</span>
          <input type="number" min="0" step="1" value={ageMonths}
            onChange={(e) => setAgeMonths(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
        </label>
      </div>
      <p className="mt-1.5 text-[10.5px] leading-snug">
        {recordedMonths == null ? (
          <span className="text-slate-400">
            No patient recorded, so P1 is judged against the age set here.
          </span>
        ) : Number(ageMonths) !== recordedMonths ? (
          <span className="text-amber-700">
            Recorded age is {recorded} {recorded === 1 ? 'year' : 'years'}{' '}
            ({recordedMonths} months). P1 is being judged against a different age.
          </span>
        ) : (
          <span className="text-slate-400">
            From the recorded age of {recorded} {recorded === 1 ? 'year' : 'years'}.
          </span>
        )}
      </p>
      <SourceNote source={run.source} label={run.label}
        empty={num(run.amp) == null
          && LLR_FIELDS.every((k) => num(run.peaks[k]) == null)} />

      {result && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {result.peaks.map((p) => (
              <div key={p.peak} className="rounded-lg bg-slate-50 px-2.5 py-2">
                <div className="flex items-baseline justify-between">
                  <span className="text-[11px] font-semibold text-slate-600">{p.peak}</span>
                  {p.present && (p.window_applies === false ? (
                    <Chip>child — no adult window</Chip>
                  ) : (
                    <Chip tone={p.within_range ? 'good' : 'warn'}>
                      {p.within_range ? 'in range' : p.delayed ? 'late' : 'early'}
                    </Chip>
                  ))}
                </div>
                <div className="mt-0.5 font-mono text-[13px] text-slate-800">
                  {p.present ? `${p.latency} ms` : '—'}
                </div>
                <div className="text-[10px] text-slate-400">
                  {p.window_applies === false ? 'adult window not applied'
                    : `${p.range[0]}–${p.range[1]} ms`}
                </div>
              </div>
            ))}
          </div>

          {maturation && (
            <div className={`mt-3 rounded-lg border px-3 py-2 text-[12px] leading-relaxed ${
              maturation.delayed ? 'border-amber-300 bg-amber-50 text-amber-900'
                : maturation.assessable === false ? 'border-slate-300 bg-slate-50 text-slate-700'
                  : 'border-emerald-300 bg-emerald-50 text-emerald-900'}`}>
              <div className="font-semibold">
                {maturation.adult ? 'P1 latency' : 'P1 cortical maturation'} — {maturation.band}
              </div>
              {maturation.assessable === false ? (
                <div className="mt-0.5">
                  Younger than the normative sample — not judged.
                </div>
              ) : maturation.adult ? (
                <div className="mt-0.5">
                  Recorded {maturation.p1_latency} ms against the 20-year end of the
                  normal-hearing curve ({maturation.expected} ms; 95% range{' '}
                  {maturation.lower_95}–{maturation.upper_95} ms). Maturation is
                  complete in an adult, so this is a latency check, not a
                  maturation or implant-candidacy measure.
                </div>
              ) : (
                <div className="mt-0.5">
                  Recorded {maturation.p1_latency} ms against a normal-hearing mean of{' '}
                  {maturation.expected} ms for this age ({maturation.difference > 0 ? '+' : ''}
                  {maturation.difference} ms); the 95% range is{' '}
                  {maturation.lower_95}–{maturation.upper_95} ms.
                </div>
              )}
              {maturation.source && (
                <div className="mt-0.5 text-[10.5px] opacity-70">{maturation.source}</div>
              )}
            </div>
          )}
          <Notes items={result.findings} />
          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{result.note}</p>
        </>
      )}
    </Panel>
  )
}

// ------------------------------------------------------- interaural Wave V ---
const hasWaveV = (r) =>
  Boolean(r?.result?.absolute?.some((w) => w.wave === 'V' && w.present))

// The 4 kHz air-conduction threshold for the Selters & Brackmann correction,
// from the audiogram already in the case. Absent or "no response" gives null,
// and the backend then states that no correction was made.
const threshold4k = (analysis, ear) => {
  const ac = analysis?.thresholds?.[ear]?.ac || {}
  const v = num(ac['4000'] ?? ac[4000])
  return v
}

// asymmetric beyond the criterion; borderline between Selters & Brackmann's
// 0.2 ms and the 0.37 ms corrected limit — never shown as symmetric.
const ASYM_TONE = { asymmetric: 'bad', borderline: 'warn', symmetric: 'good' }
const ASYM_BOX = {
  asymmetric: 'border-rose-300 bg-rose-50 text-rose-900',
  borderline: 'border-amber-300 bg-amber-50 text-amber-900',
  symmetric: 'border-emerald-300 bg-emerald-50 text-emerald-900',
}
const asymStatus = (r) => r?.status
  || (r?.significant ? 'asymmetric' : r?.borderline ? 'borderline' : 'symmetric')

function AsymmetrySection({ right, left }) {
  const { analysis } = useApp()
  const [result, setResult] = useState(null)
  const ready = hasWaveV(right) && hasWaveV(left)
  const example = [right, left].some((r) => r && r.source !== 'entered')
  const status = asymStatus(result)

  useEffect(() => {
    if (!ready) { setResult(null); return undefined }
    let cancelled = false
    api.abrAsymmetry(
      { ...right.request, ear: 'right', threshold_4k_db_hl: threshold4k(analysis, 'right') },
      { ...left.request, ear: 'left', threshold_4k_db_hl: threshold4k(analysis, 'left') })
      .then((a) => { if (!cancelled) setResult(a) })
      .catch(() => { if (!cancelled) setResult(null) })
    return () => { cancelled = true }
  }, [ready, right, left, analysis])

  return (
    <Panel
      title="Interaural Wave V — retrocochlear screen"
      right={result?.available !== false && result && (
        <Chip tone={ASYM_TONE[status] || 'slate'}>{status}</Chip>
      )}
    >
      {!ready && (
        <p className="mt-2 text-[12.5px] leading-relaxed text-slate-500">
          Record an ABR with an identifiable Wave V in both ears — switch the ear
          above and enter the other side. The comparison needs two traces at the
          same level; a single ear cannot be asymmetric with itself.
        </p>
      )}

      {ready && example && (
        <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-1.5 text-[11.5px] text-amber-900">
          At least one side is still an example preset, so this comparison is a
          demonstration, not this patient&rsquo;s result.
        </p>
      )}

      {ready && result?.available === false && (
        <p className="mt-2 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-[12.5px] leading-relaxed text-slate-700">
          {result.note}
        </p>
      )}

      {ready && result && result.available !== false && (
        <>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-200 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-red-600">
                Right Wave V
              </div>
              <div className="mt-0.5 font-mono text-[15px] text-slate-800">
                {result.right_wave_v} ms
              </div>
            </div>
            <div className="rounded-xl border border-slate-200 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-blue-600">
                Left Wave V
              </div>
              <div className="mt-0.5 font-mono text-[15px] text-slate-800">
                {result.left_wave_v} ms
              </div>
            </div>
            <div className={`rounded-xl border p-3 ${ASYM_BOX[status] || ''}`}>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Difference
              </div>
              <div className="mt-0.5 font-mono text-[15px] text-slate-800">
                {result.difference} ms
              </div>
              <div className="text-[10.5px] text-slate-500">
                criterion {result.criterion} ms
                {result.borderline_from != null
                  && ` (borderline from ${result.borderline_from} ms)`}
                {result.hearing_loss_correction?.applied
                  && ` · ${result.uncorrected_difference} ms before correction`}
              </div>
            </div>
          </div>

          <p className={`mt-3 rounded-lg border px-3 py-2 text-[12.5px] leading-relaxed ${
            ASYM_BOX[status] || 'border-slate-300 bg-slate-50 text-slate-800'}`}>
            {result.message}
            {result.poorer_ear && (
              <>
                {' '}The later response is on the{' '}
                <span className={`font-semibold ${
                  result.poorer_ear === 'right' ? 'text-red-600' : 'text-blue-600'}`}>
                  {result.poorer_ear}
                </span>.
              </>
            )}
          </p>

          <Notes items={result.limitations} />

          {/* An asymmetry beyond the criterion says the two sides conduct
              differently, not why. It raises the question of a lesion on the
              eighth nerve or in the brainstem; only imaging answers it. */}
          <p className="mt-2 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-[11.5px] leading-relaxed text-slate-700">
            <span className="font-semibold">A screen, not a diagnosis.</span> A
            difference beyond {result.criterion} ms means the later ear should be
            investigated for retrocochlear pathology — typically with MRI of the
            internal auditory meati — not that a tumour is present. Runs at
            different levels are refused rather than compared, because Wave V
            moves with level, and so is an ear whose click is less than 10 dB
            above its 4 kHz threshold. The 4 kHz thresholds come from the
            audiogram in this case; without both, no hearing-loss correction is
            made and the uncorrected 0.4 ms criterion applies.
          </p>
        </>
      )}
    </Panel>
  )
}

// ------------------------------------------------------ attach to record ---
// What would be stored, in the clinician's own terms — read before clicking.
function recordedLines(entered) {
  const lines = []
  for (const r of entered.abr) {
    const q = r.request
    // Sex and age decide which limits the latencies were judged against, so
    // they are part of what is recorded and are shown before attaching.
    lines.push({
      key: `abr-${q.ear}`,
      label: `ABR ${q.ear}`,
      text: `${q.intensity_db_nhl} dB nHL · ${listValues(q.waves, 'ms')} · `
        + `${q.latencies_include_delay ? 'insert delay included' : 'already corrected'}`
        + `${q.cm_present ? ' · CM seen' : ''}`
        + ` · judged as ${q.sex || 'sex not recorded'}`
        + `${q.age_months != null ? `, ${q.age_months} months` : ', age not recorded'}`,
    })
  }
  if (entered.mlr) {
    const q = entered.mlr.request
    lines.push({ key: 'mlr', label: 'MLR',
      text: `${listValues(q.peaks, 'ms')}${q.amplitudes['Na-Pa'] != null
        ? ` · Na–Pa ${q.amplitudes['Na-Pa']} µV` : ''}${q.sedated ? ' · sedated' : ''}` })
  }
  if (entered.llr) {
    const q = entered.llr.request
    lines.push({ key: 'llr', label: 'LLR',
      text: `${listValues(q.peaks, 'ms')}${q.amplitudes['N1-P2'] != null
        ? ` · N1–P2 ${q.amplitudes['N1-P2']} µV` : ''} · age ${q.age_months ?? '—'} months` })
  }
  return lines
}

// A cortical section counts only once something was typed into it: an
// emptied example is not a recording of an absent response.
const hasValues = (r) => Boolean(r?.request) && (
  Object.keys(r.request.peaks || {}).length > 0
  || Object.keys(r.request.amplitudes || {}).length > 0)

function batteryRequest(abrRuns, mlr, llr) {
  const body = {}
  if (abrRuns[0]) body.abr = abrRuns[0].request
  if (abrRuns[1]) body.abr_other_ear = abrRuns[1].request
  if (mlr) body.mlr = mlr.request
  if (llr) body.llr = llr.request
  return Object.keys(body).length ? body : null
}

function AttachAep({ abrByEar, mlr, llr }) {
  const { patient, aep, setAep, showToast } = useApp()
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState(null)

  const entered = useMemo(() => ({
    abr: ['right', 'left'].map((e) => abrByEar[e])
      .filter((r) => r?.source === 'entered' && r.request),
    mlr: mlr?.source === 'entered' && hasValues(mlr) ? mlr : null,
    llr: llr?.source === 'entered' && hasValues(llr) ? llr : null,
  }), [abrByEar, mlr, llr])
  const body = useMemo(
    () => batteryRequest(entered.abr, entered.mlr, entered.llr), [entered])
  const delayMissing = entered.abr.some((r) => !r.delayChosen)
  const examples = [
    ...['right', 'left'].filter((e) => abrByEar[e] && abrByEar[e].source !== 'entered')
      .map((e) => `ABR ${e} (${abrByEar[e].label})`),
    ...(mlr && mlr.source !== 'entered' ? [`MLR (${mlr.label})`] : []),
    ...(llr && llr.source !== 'entered' ? [`LLR (${llr.label})`] : []),
  ]

  useEffect(() => {
    if (!body) { setPreview(null); return undefined }
    let cancelled = false
    api.aepBattery(body)
      .then((b) => { if (!cancelled) setPreview(b) })
      .catch(() => { if (!cancelled) setPreview(null) })
    return () => { cancelled = true }
  }, [body])

  const stored = aep ? (aep.battery || aep) : null
  // A record without `recorded` did not come through this panel. It is the
  // shape of a battery written straight from the on-screen values — usually
  // the example presets — so it is shown for review, not trusted.
  const legacy = Boolean(aep && !aep.recorded)

  const attach = async () => {
    if (busy || !body || delayMissing || !patient) return
    setBusy(true)
    try {
      // Recomputed from exactly the values listed, at the moment of attaching.
      const b = await api.aepBattery(body)
      setAep({
        battery: b,
        recorded: {
          abr: entered.abr.map((r) => r.request),
          mlr: entered.mlr?.request || null,
          llr: entered.llr?.request || null,
        },
        patient: patient.name || null,
        attached_at: new Date().toISOString(),
      })
      showToast('Evoked potentials attached to this patient’s record.')
    } catch (e) {
      showToast(`Could not attach: ${e.message}`, 'error')
    } finally {
      setBusy(false)
    }
  }

  const remove = () => {
    setAep(null)
    showToast('Evoked potentials removed from this patient’s record.')
  }

  return (
    <div className="rounded-2xl border border-teal-200 bg-teal-50/40 p-5 shadow-sm">
      <h2 className="text-[15px] font-semibold text-slate-900">
        Record for {patient?.name ? `${patient.name}` : 'this patient'}
      </h2>

      {stored && (
        <div className={`mt-3 rounded-xl border p-3 ${
          legacy ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-white'}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Currently attached
              {aep.attached_at && ` · ${new Date(aep.attached_at).toLocaleString()}`}
            </span>
            <button type="button" onClick={remove}
              className="rounded-lg border border-rose-200 bg-white px-2.5 py-1 text-[12px] font-medium text-rose-700 transition hover:border-rose-300">
              Remove from record
            </button>
          </div>
          <p className="mt-1 text-[12.5px] leading-relaxed text-slate-800">{stored.headline}</p>
          {legacy ? (
            <p className="mt-1 text-[11.5px] leading-relaxed text-amber-900">
              This was stored automatically by an earlier version of this page from
              whatever it was showing — usually the example presets. Remove it
              unless these were genuinely this patient&rsquo;s recordings.
            </p>
          ) : (
            <ul className="mt-1.5 space-y-0.5 text-[11.5px] text-slate-600">
              {recordedLines({
                abr: (aep.recorded.abr || []).map((request) => ({ request })),
                mlr: aep.recorded.mlr ? { request: aep.recorded.mlr } : null,
                llr: aep.recorded.llr ? { request: aep.recorded.llr } : null,
              }).map((l) => (
                <li key={l.key}><span className="font-medium text-slate-700">{l.label}:</span> {l.text}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!patient ? (
        <p className="mt-3 rounded-lg border border-dashed border-slate-300 px-3 py-2 text-[11.5px] leading-relaxed text-slate-500">
          Register the patient first — evoked potentials are attached to a named
          patient, never to an anonymous page.
        </p>
      ) : !body ? (
        <p className="mt-3 rounded-lg border border-dashed border-slate-300 px-3 py-2 text-[11.5px] leading-relaxed text-slate-500">
          Nothing has been entered for this patient yet — every section is
          showing an example. Type the measured values into a section to make it
          attachable.
        </p>
      ) : (
        <div className="mt-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-teal-800">
            {stored ? 'Replace with' : 'Will be recorded'}
          </div>
          <ul className="mt-1 space-y-0.5 text-[12px] text-teal-950">
            {recordedLines(entered).map((l) => (
              <li key={l.key}><span className="font-semibold">{l.label}:</span> {l.text}</li>
            ))}
          </ul>
          {preview?.headline && (
            <p className="mt-1.5 text-[12px] leading-relaxed text-teal-900">
              <span className="font-semibold">Conclusion recorded:</span> {preview.headline}
            </p>
          )}
          {examples.length > 0 && (
            <p className="mt-1.5 text-[11px] text-slate-500">
              Not included (examples): {examples.join(', ')}.
            </p>
          )}
          {delayMissing && (
            <p className="mt-1.5 text-[11.5px] font-medium text-amber-800">
              An ABR entry does not yet say whether its latencies include the
              insert-earphone delay.
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <button type="button" onClick={attach} disabled={busy || delayMissing}
              className="rounded-lg bg-teal-600 px-3.5 py-1.5 text-[12.5px] font-semibold text-white transition hover:bg-teal-700 disabled:opacity-50">
              {busy ? 'Attaching…' : stored ? 'Replace attached result' : 'Attach to record'}
            </button>
            <span className="text-[10.5px] leading-snug text-teal-800/80">
              Exactly the values listed are recorded — attach only what was
              measured on this patient.
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

// -------------------------------------------------------------- reference ---
function ReferenceSection() {
  const [reference, setReference] = useState(null)

  useEffect(() => {
    let cancelled = false
    api.aepReference()
      .then((r) => { if (!cancelled) setReference(r) })
      .catch(() => { if (!cancelled) setReference(null) })
    return () => { cancelled = true }
  }, [])

  if (!reference?.abr) return null
  const { protocol, norms, note, insert_delay_ms: insertDelay,
    interaural_v_criterion_ms: interaural,
    interaural_v_corrected_criterion_ms: interauralCorrected,
    interaural_v_selters_brackmann_ms: interauralSB,
    interpeak_upper_limits_ms: ipl, i_v_upper_95_cl_ms: ivCl } = reference.abr

  const cell = (v) => (v ? (
    <>
      <span className="font-mono">{v.mean.toFixed(2)}</span>
      <span className="text-slate-400"> ± {v.sd.toFixed(2)}</span>
      <span className="ml-1 text-[10px] text-slate-300">n={v.n}</span>
    </>
  ) : <span className="text-slate-300">—</span>)

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <details>
        <summary className="cursor-pointer text-[12.5px] font-medium text-teal-700">
          The ABR normative table and protocol these judgements are made against
        </summary>

        <div className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Absolute and interwave latencies by stimulus intensity
        </div>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-[12px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                <th className="py-1 pr-3 font-medium">dB nHL</th>
                <th className="py-1 pr-3 font-medium">Peak SPL</th>
                <th className="py-1 pr-3 font-medium">Wave I</th>
                <th className="py-1 pr-3 font-medium">Wave III</th>
                <th className="py-1 pr-3 font-medium">Wave V</th>
                <th className="py-1 font-medium">I–V</th>
              </tr>
            </thead>
            <tbody>
              {norms.map((row) => (
                <tr key={row.intensity_db_nhl} className="border-t border-slate-100">
                  <td className="py-1.5 pr-3 font-semibold text-slate-700">
                    {row.intensity_db_nhl}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-slate-500">{row.psp_db}</td>
                  <td className="py-1.5 pr-3 text-slate-600">{cell(row.waves.I)}</td>
                  <td className="py-1.5 pr-3 text-slate-600">{cell(row.waves.III)}</td>
                  <td className="py-1.5 pr-3 text-slate-600">{cell(row.waves.V)}</td>
                  <td className="py-1.5 text-slate-600">{cell(row.interwave['I-V'])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
          Mean ± one standard deviation in milliseconds, with the number of
          subjects contributing each value. {note}
        </p>
        {/* A thin row is a weak norm. Wave I disappears below 40 dB nHL in most
            ears, so a missing early wave near threshold is expected rather than
            a finding — the n column is what makes that visible. */}
        <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
          Where n is small the row rests on very few ears, and a wave missing at
          that level is unremarkable. The table is from normal-hearing young
          adult females, so a man&rsquo;s later waves are allowed 0.15 ms more
          before they are called delayed, and the interpeak intervals are judged
          against adult clinical limits
          {ipl ? ` (I–III ${ipl['I-III']}, III–V ${ipl['III-V']}, I–V ${ipl['I-V']} ms)` : ''}{' '}
          rather than against this table
          {ivCl ? `, with an I–V beyond the adult 95% limit (women ${ivCl.female}, men ${ivCl.male} ms; Lightfoot 1992) reported as borderline` : ''}.
          A delay is read as peripheral only when Wave I is itself late. Under 3
          years none of these adult values apply.
        </p>

        <div className="mt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Recording protocol
        </div>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {[
            ['Stimulus', protocol.stimulus],
            ['Recording window', `${protocol.recording_window_ms} ms`],
            ['Clinically useful waves', protocol.clinically_useful_waves.join(', ')],
            ['Threshold wave', protocol.threshold_wave],
            ['Typical intensities',
              `${protocol.typical_intensities_db_nhl.join(' and ')} dB nHL`],
            ['Click rate', `${protocol.click_rates_per_s.join(' and ')} per second`],
            ['Expected amplitude',
              `${protocol.amplitude_uv[0]}–${protocol.amplitude_uv[1]} µV`],
            ['Insert-earphone delay', `${insertDelay} ms`],
            ['Interaural Wave V criterion',
              interauralCorrected != null
                ? `${interaural} ms uncorrected; ${interauralCorrected} ms after the `
                  + `Selters & Brackmann correction (borderline from ${interauralSB} ms); `
                  + 'same level only'
                : `${interaural} ms, same level only`],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-50 px-2.5 py-2">
              <div className="text-[10.5px] font-medium text-slate-500">{label}</div>
              <div className="mt-0.5 text-[12.5px] text-slate-800">{value}</div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          {protocol.note}
        </p>
      </details>
    </div>
  )
}

// --------------------------------------------------------------- the page ---
export default function EvokedPotentials() {
  const { patient } = useApp()
  const [ear, setEar] = useState('right')
  // Both ears are held, not just the one on screen, because the interaural
  // Wave V comparison needs the ear the clinician is not currently looking at.
  // Each entry is {result, request, source, label}: the request is what was
  // entered, and it is what the battery and the record are built from.
  const [abrByEar, setAbrByEar] = useState({})
  const [mlr, setMlr] = useState(null)
  const [llr, setLlr] = useState(null)
  const [battery, setBattery] = useState(null)

  // The table is female-only and adult-only, so the backend needs both facts
  // to know how far to trust it.
  const sex = patient?.sex || null
  const recordedAge = Number(patient?.age)
  const ageMonths = patient?.age == null || patient.age === '' || Number.isNaN(recordedAge)
    ? null : Math.round(recordedAge * 12)

  const handleAbr = useCallback(
    (e, run) => setAbrByEar((prev) => ({ ...prev, [e]: run })), [])

  // The on-screen battery, examples included. It is recomputed from the
  // current sections because its whole value is comparative, and it is a
  // preview only: nothing here reaches the record except through AttachAep.
  const previewBody = useMemo(() => batteryRequest(
    [abrByEar[ear], abrByEar[OTHER_EAR[ear]]].filter((r) => r?.request), mlr, llr),
  [abrByEar, ear, mlr, llr])
  const showingExamples = [abrByEar.right, abrByEar.left, mlr, llr]
    .some((r) => r && r.source !== 'entered')

  useEffect(() => {
    if (!previewBody) { setBattery(null); return undefined }
    let cancelled = false
    api.aepBattery(previewBody)
      .then((b) => { if (!cancelled) setBattery(b) })
      .catch(() => { if (!cancelled) setBattery(null) })
    return () => { cancelled = true }
  }, [previewBody])

  return (
    <div className="mx-auto max-w-5xl">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">
            Evoked potentials
          </h1>
          <p className="mt-1 max-w-3xl text-[13.5px] leading-relaxed text-slate-500">
            ABR, MLR and LLR sample the same ascending pathway at increasing
            heights — brainstem, thalamocortical, cortex. Running one alone can
            only exclude a problem at that height.
          </p>
        </div>
        <div className="flex rounded-lg bg-slate-100 p-0.5">
          {['right', 'left'].map((e) => (
            <button key={e} type="button" onClick={() => setEar(e)}
              className={`rounded-md px-3 py-1 text-[12px] font-semibold capitalize transition ${
                ear === e ? 'bg-white shadow-sm' : 'text-slate-500'}`}
              style={ear === e ? { color: EAR_TONE[e] } : undefined}>
              {e}
            </button>
          ))}
        </div>
      </header>

      {battery?.available && (
        <div className="mt-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
          data-tour="aep-battery">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Where along the pathway
            </h2>
            {showingExamples && <Chip tone="warn">preview — includes examples</Chip>}
          </div>
          <p className={`mt-2 rounded-lg border px-3 py-2 text-[13px] font-medium ${
            battery.abnormal_levels.length
              ? 'border-amber-300 bg-amber-50 text-amber-900'
              : battery.uncertain_levels?.length
                ? 'border-slate-300 bg-slate-50 text-slate-800'
                : 'border-emerald-300 bg-emerald-50 text-emerald-900'}`}>
            {battery.headline}
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {battery.levels.map((l) => (
              <div key={l.test}
                className={`rounded-xl border p-3 ${
                  l.status === 'abnormal' ? 'border-amber-300 bg-amber-50/50'
                    : l.status === 'normal' ? 'border-emerald-200 bg-emerald-50/40'
                      : 'border-slate-300 bg-slate-50'}`}>
                <div className="flex items-baseline justify-between">
                  <span className="text-[13px] font-semibold text-slate-800">{l.test}</span>
                  <Chip tone={STATUS_TONE[l.status] || 'slate'}>{l.status}</Chip>
                </div>
                <div className="mt-0.5 font-mono text-[10.5px] text-slate-500">
                  {l.window_ms[0]}–{l.window_ms[1]} ms
                </div>
                <div className="mt-1 text-[11.5px] leading-snug text-slate-600">
                  {l.level}
                </div>
                {l.detail && (
                  <div className="mt-1 text-[11px] leading-snug text-slate-500">{l.detail}</div>
                )}
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
            {battery.note} This strip reads whatever is on screen and is not part
            of the patient&rsquo;s record — use the panel at the foot of the page
            to attach measured values.
          </p>
        </div>
      )}

      <div className="mt-5 space-y-5">
        <ABRSection ear={ear} sex={sex} ageMonths={ageMonths} onResult={handleAbr} />
        <AsymmetrySection right={abrByEar.right} left={abrByEar.left} />
        <MLRSection ear={ear} onResult={setMlr} />
        <LLRSection ear={ear} onResult={setLlr} />
        <AttachAep abrByEar={abrByEar} mlr={mlr} llr={llr} />
        <ReferenceSection />
      </div>

      <StepNav stepKey="aep" />
    </div>
  )
}
