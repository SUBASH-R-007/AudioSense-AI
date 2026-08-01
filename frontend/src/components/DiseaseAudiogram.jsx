// A ranked differential from the audiogram alone, with the characteristic
// curve of each candidate drawn against the patient's own thresholds.
//
// No history is required and none is used. The audiogram is matched against
// textbook configurations on four independent axes — shape, degree, type and
// symmetry — and all four are shown, because a disease can match the shape
// perfectly and still be excluded by the type, and the clinician needs to see
// which one disagreed.
//
// Shape is compared with the overall level removed, so a 4 kHz notch matches a
// 4 kHz notch whether the patient's is 20 dB deep or 50.

import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, AC_FREQS, FREQ_LABELS } from '../lib/api.js'

const EAR_TONE = { right: '#dc2626', left: '#2563eb' }

function Bar({ value, label }) {
  const pct = Math.round((value ?? 0) * 100)
  return (
    <div>
      <div className="flex justify-between text-[10px] text-slate-500">
        <span>{label}</span><span className="font-mono">{pct}</span>
      </div>
      <div className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-teal-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function DiseaseAudiogram({ analysis, side = 'right' }) {
  const [result, setResult] = useState(null)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    if (!analysis) { setResult(null); return }
    let cancelled = false
    api.diseasesFromAudiogram(analysis, side)
      .then((r) => { if (!cancelled) { setResult(r); setSelected(null) } })
      .catch(() => { if (!cancelled) setResult(null) })
    return () => { cancelled = true }
  }, [analysis, side])

  const active = useMemo(() => {
    if (!result?.differential?.length) return null
    return result.differential.find((d) => d.key === selected) || result.differential[0]
  }, [result, selected])

  const chartData = useMemo(() => {
    if (!result || !active) return []
    return AC_FREQS.map((f) => ({
      freq: String(f),
      patient: result.measured_ac[f] ?? result.measured_ac[String(f)] ?? null,
      typical: active.reference_ac[f] ?? active.reference_ac[String(f)] ?? null,
    }))
  }, [result, active])

  if (!result?.available) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 p-5 text-[12.5px] text-slate-400">
        {result?.note || 'Run an audiogram to match it against the disease patterns.'}
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">
          Diseases matching this audiogram
        </h2>
        <span className="text-[11.5px] capitalize text-slate-500">
          {side} ear · no history used
        </span>
      </div>
      <p className={`mt-2 rounded-lg border px-3 py-2 text-[12.5px] leading-relaxed ${
        result.normal_audiogram
          ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
          : 'border-slate-200 bg-slate-50 text-slate-700'}`}>
        {result.headline}
      </p>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <div className="h-64 w-full">
            <ResponsiveContainer>
              <LineChart data={chartData} margin={{ top: 8, right: 10, bottom: 18, left: -8 }}>
                <CartesianGrid stroke="#e2e8f0" />
                <ReferenceArea y1={-10} y2={20} fill="#10b981" fillOpacity={0.07} />
                <XAxis dataKey="freq" tickFormatter={(f) => FREQ_LABELS[f] || f}
                  tick={{ fontSize: 10, fill: '#64748b' }}
                  label={{ value: 'Frequency (Hz)', position: 'insideBottom',
                    offset: -10, fontSize: 10, fill: '#94a3b8' }} />
                <YAxis domain={[-10, 120]} reversed
                  ticks={[0, 20, 40, 60, 80, 100, 120]}
                  tick={{ fontSize: 10, fill: '#64748b' }} width={38}
                  label={{ value: 'dB HL', angle: -90, position: 'insideLeft',
                    fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }}
                  formatter={(v, n) => [`${v} dB HL`, n]}
                  labelFormatter={(f) => `${f} Hz`} />
                <Legend wrapperStyle={{ fontSize: 10.5 }} />
                <Line name="Typical for this disease" dataKey="typical"
                  stroke="#94a3b8" strokeWidth={2} strokeDasharray="5 4"
                  dot={{ r: 3, fill: '#94a3b8' }} isAnimationActive={false}
                  connectNulls />
                <Line name={`This patient (${side})`} dataKey="patient"
                  stroke={EAR_TONE[side]} strokeWidth={2.2}
                  dot={{ r: 4, fill: EAR_TONE[side] }} isAnimationActive={false}
                  connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {active && (
            <div className="mt-1 rounded-lg bg-slate-50 px-3 py-2 text-[11.5px] leading-relaxed text-slate-600">
              <span className="font-semibold text-slate-800">{active.name}</span> —
              {' '}{active.expected_shape}. {active.note}
            </div>
          )}
        </div>

        <ol className="space-y-2">
          {result.differential.map((d, i) => {
            const chosen = active?.key === d.key
            return (
              <li key={d.key}>
                <button type="button" onClick={() => setSelected(d.key)}
                  aria-pressed={chosen}
                  className={`w-full rounded-xl border p-2.5 text-left transition ${
                    chosen ? 'border-teal-500 bg-teal-50/50'
                      : 'border-slate-200 hover:border-slate-300'}`}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className={`text-[12.5px] ${
                      i === 0 ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>
                      {d.name}
                    </span>
                    <span className="font-mono text-[11.5px] text-slate-500">
                      {Math.round(d.score * 100)}
                    </span>
                  </div>
                  <div className="mt-1.5 grid grid-cols-4 gap-1.5">
                    <Bar value={d.shape_match} label="shape" />
                    <Bar value={d.level_match} label="degree" />
                    <Bar value={d.type_match} label="type" />
                    <Bar value={d.laterality_match} label="side" />
                  </div>
                </button>
              </li>
            )
          })}
        </ol>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-slate-400">{result.note}</p>
    </div>
  )
}
