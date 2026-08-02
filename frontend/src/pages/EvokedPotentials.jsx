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

import { useEffect, useMemo, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, ComposedChart, ErrorBar, Legend, Line,
  ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

const EAR_TONE = { right: '#dc2626', left: '#2563eb' }

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

function Panel({ title, right, children }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
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

// ------------------------------------------------------------------- ABR ---
function ABRSection({ ear, onResult }) {
  const { showToast } = useApp()
  const [preset, setPreset] = useState(ABR_PRESETS[0])
  const [result, setResult] = useState(null)
  const [ladder, setLadder] = useState(null)

  useEffect(() => {
    let cancelled = false
    api.abr({
      ear, intensity_db_nhl: preset.intensity, waves: preset.waves,
      latencies_include_delay: false,
    })
      .then((r) => { if (!cancelled) { setResult(r); onResult?.(r) } })
      .catch((e) => { if (!cancelled) showToast(e.message, 'error') })
    return () => { cancelled = true }
  }, [ear, preset, onResult, showToast])

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
      band: [w.norm.mean - w.norm.sd * 2, w.norm.sd * 2 * 2].slice(0, 1)
        .concat([w.norm.sd * 2]),
      sd2: [w.norm.sd * 2, w.norm.sd * 2],
      z: w.z,
    })), [result])

  return (
    <Panel
      title="ABR — eighth nerve and brainstem"
      right={result && (
        <span className="text-[11.5px] text-slate-500">
          compared against the {result.norm_row_db_nhl} dB nHL row
        </span>
      )}
    >
      <Presets options={ABR_PRESETS} active={preset.label} onPick={setPreset} />

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
                    : 'This patient']} />
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
            Grey is the normative mean with its 2 SD band at {preset.intensity} dB nHL.
          </p>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[440px] text-left text-[12px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                  <th className="py-1 pr-3 font-medium">Wave</th>
                  <th className="py-1 pr-3 font-medium">Latency</th>
                  <th className="py-1 pr-3 font-medium">Normal (2 SD)</th>
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
                    </td>
                    <td className="py-1.5">
                      {w.present && w.z !== undefined ? (
                        <Chip tone={w.within_2sd ? 'good' : w.within_3sd ? 'warn' : 'bad'}>
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
                      {e.norm ? `${e.norm.sd2[0]}–${e.norm.sd2[1]}` : '—'}
                    </td>
                    <td className="py-1.5">
                      {e.z !== undefined && (
                        <Chip tone={e.within_2sd ? 'good' : 'bad'}>
                          {e.z > 0 ? `+${e.z}` : e.z}
                        </Chip>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Notes items={result.findings} />

          {ladder && (
            <div className="mt-3 rounded-xl border border-slate-200 p-3">
              <div className="text-[12px] font-semibold text-slate-700">
                Threshold estimation
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
                    {r.intensity} dB{r.present ? ` · ${r.wave_v} ms` : ' · none'}
                  </span>
                ))}
              </div>
            </div>
          )}

          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{result.note}</p>
        </>
      )}
    </Panel>
  )
}

// ------------------------------------------------------------------- MLR ---
function MLRSection({ ear, onResult }) {
  const [preset, setPreset] = useState(MLR_PRESETS[0])
  const [result, setResult] = useState(null)

  useEffect(() => {
    let cancelled = false
    api.mlr({ ear, peaks: preset.peaks, amplitudes: { 'Na-Pa': preset.amp } })
      .then((r) => { if (!cancelled) { setResult(r); onResult?.(r) } })
      .catch(() => { if (!cancelled) setResult(null) })
    return () => { cancelled = true }
  }, [ear, preset, onResult])

  return (
    <Panel
      title="MLR — thalamus and primary cortex"
      right={result && (
        <Chip tone={result.abnormal ? 'warn' : 'good'}>
          {result.abnormal ? 'abnormal' : 'normal'}
        </Chip>
      )}
    >
      <Presets options={MLR_PRESETS} active={preset.label} onPick={setPreset} />

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
function LLRSection({ ear, onResult }) {
  const [preset, setPreset] = useState(LLR_PRESETS[0])
  const [result, setResult] = useState(null)

  useEffect(() => {
    let cancelled = false
    api.llr({ ear, peaks: preset.peaks, amplitudes: { 'N1-P2': preset.amp },
      age_months: preset.age })
      .then((r) => { if (!cancelled) { setResult(r); onResult?.(r) } })
      .catch(() => { if (!cancelled) setResult(null) })
    return () => { cancelled = true }
  }, [ear, preset, onResult])

  const maturation = result?.maturation

  return (
    <Panel
      title="LLR — auditory cortex"
      right={result && (
        <Chip tone={result.flags.length ? 'warn' : 'good'}>
          {result.flags.length ? `${result.flags.length} finding` : 'normal'}
        </Chip>
      )}
    >
      <Presets options={LLR_PRESETS} active={preset.label} onPick={setPreset} />

      {result && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {result.peaks.map((p) => (
              <div key={p.peak} className="rounded-lg bg-slate-50 px-2.5 py-2">
                <div className="flex items-baseline justify-between">
                  <span className="text-[11px] font-semibold text-slate-600">{p.peak}</span>
                  {p.present && (
                    <Chip tone={p.within_range ? 'good' : 'warn'}>
                      {p.within_range ? 'in range' : p.delayed ? 'late' : 'early'}
                    </Chip>
                  )}
                </div>
                <div className="mt-0.5 font-mono text-[13px] text-slate-800">
                  {p.present ? `${p.latency} ms` : '—'}
                </div>
                <div className="text-[10px] text-slate-400">
                  {p.range[0]}–{p.range[1]} ms
                </div>
              </div>
            ))}
          </div>

          {maturation && (
            <div className={`mt-3 rounded-lg border px-3 py-2 text-[12px] leading-relaxed ${
              maturation.delayed ? 'border-amber-300 bg-amber-50 text-amber-900'
                : 'border-emerald-300 bg-emerald-50 text-emerald-900'}`}>
              <div className="font-semibold">
                P1 cortical maturation — {maturation.band}
              </div>
              <div className="mt-0.5">
                Recorded {maturation.p1_latency} ms against an age-typical{' '}
                {maturation.expected} ms ({maturation.difference > 0 ? '+' : ''}
                {maturation.difference} ms).
              </div>
            </div>
          )}
          <Notes items={result.findings} />
          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{result.note}</p>
        </>
      )}
    </Panel>
  )
}

// --------------------------------------------------------------- the page ---
export default function EvokedPotentials() {
  const [ear, setEar] = useState('right')
  const [abr, setAbr] = useState(null)
  const [mlr, setMlr] = useState(null)
  const [llr, setLlr] = useState(null)
  const [battery, setBattery] = useState(null)

  // The battery is recomputed from the three current results, because its
  // whole value is comparative — which level is abnormal with which below it.
  useEffect(() => {
    if (!abr && !mlr && !llr) return
    let cancelled = false
    const level = (r, fields) => (r ? fields(r) : undefined)
    api.aepBattery({
      abr: level(abr, (r) => ({
        ear: r.ear, intensity_db_nhl: r.intensity_db_nhl,
        waves: Object.fromEntries(r.absolute.filter((w) => w.present)
          .map((w) => [w.wave, w.latency])),
        latencies_include_delay: false,
      })),
      mlr: level(mlr, (r) => ({
        ear: r.ear,
        peaks: Object.fromEntries(r.peaks.filter((p) => p.present)
          .map((p) => [p.peak, p.latency])),
        amplitudes: r.na_pa_amplitude_uv ? { 'Na-Pa': r.na_pa_amplitude_uv } : {},
      })),
      llr: level(llr, (r) => ({
        ear: r.ear, age_months: r.age_months,
        peaks: Object.fromEntries(r.peaks.filter((p) => p.present)
          .map((p) => [p.peak, p.latency])),
      })),
    })
      .then((b) => { if (!cancelled) setBattery(b) })
      .catch(() => { if (!cancelled) setBattery(null) })
    return () => { cancelled = true }
  }, [abr, mlr, llr])

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
        <div className="mt-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
            Where along the pathway
          </h2>
          <p className={`mt-2 rounded-lg border px-3 py-2 text-[13px] font-medium ${
            battery.abnormal_levels.length
              ? 'border-amber-300 bg-amber-50 text-amber-900'
              : 'border-emerald-300 bg-emerald-50 text-emerald-900'}`}>
            {battery.headline}
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {battery.levels.map((l) => (
              <div key={l.test}
                className={`rounded-xl border p-3 ${
                  l.abnormal ? 'border-amber-300 bg-amber-50/50'
                    : 'border-emerald-200 bg-emerald-50/40'}`}>
                <div className="flex items-baseline justify-between">
                  <span className="text-[13px] font-semibold text-slate-800">{l.test}</span>
                  <Chip tone={l.abnormal ? 'warn' : 'good'}>
                    {l.abnormal ? 'abnormal' : 'normal'}
                  </Chip>
                </div>
                <div className="mt-0.5 font-mono text-[10.5px] text-slate-500">
                  {l.window_ms[0]}–{l.window_ms[1]} ms
                </div>
                <div className="mt-1 text-[11.5px] leading-snug text-slate-600">
                  {l.level}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">{battery.note}</p>
        </div>
      )}

      <div className="mt-5 space-y-5">
        <ABRSection ear={ear} onResult={setAbr} />
        <MLRSection ear={ear} onResult={setMlr} />
        <LLRSection ear={ear} onResult={setLlr} />
      </div>
    </div>
  )
}
