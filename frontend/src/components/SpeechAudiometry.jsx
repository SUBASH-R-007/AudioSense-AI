// Speech audiometry as an instrument: SDT, SRT and WRS.
//
// The performance-intensity function is plotted because rollover — word
// recognition falling as level rises — is a shape, not a number, and it is the
// classic retrocochlear indicator.
//
// Every word score is drawn with its exact binomial confidence interval. A
// 25-word list gives an interval tens of points wide, so 88% and 76% on 25
// words are not different results, and a chart that plots them as two distinct
// points invites exactly that mistake.

import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, ErrorBar, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Scatter, ComposedChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../lib/api.js'

const EAR_TONE = { right: '#dc2626', left: '#2563eb' }

const PRESETS = [
  {
    label: 'Normal', ac: 10,
    sdt: 5, srt: 10, wrs: [{ level: 45, score: 100, n_words: 50 }],
  },
  {
    label: 'Cochlear loss', ac: 45,
    sdt: 38, srt: 45, wrs: [{ level: 80, score: 84, n_words: 50 }],
  },
  {
    label: 'Rollover — retrocochlear', ac: 45,
    sdt: 38, srt: 45,
    wrs: [{ level: 65, score: 72, n_words: 50 },
          { level: 85, score: 44, n_words: 50 },
          { level: 100, score: 28, n_words: 50 }],
  },
  {
    label: 'Non-organic (SRT beats tones)', ac: 60,
    sdt: 25, srt: 30, wrs: [{ level: 65, score: 92, n_words: 50 }],
  },
  {
    label: 'Paediatric — SDT only', ac: 40,
    sdt: 35, srt: null, wrs: [],
  },
  {
    label: 'Score taken too near threshold', ac: 40,
    sdt: 33, srt: 40, wrs: [{ level: 50, score: 48, n_words: 25 }],
  },
]

const FREQS = [250, 500, 1000, 2000, 4000, 8000]

function Row({ label, value, unit, tone }) {
  return (
    <div className="rounded-lg bg-slate-50 px-2.5 py-2">
      <div className="text-[11px] font-medium text-slate-500">{label}</div>
      <div className={`mt-0.5 font-mono text-[13.5px] ${tone || 'text-slate-800'}`}>
        {value === null || value === undefined ? '—' : value}
        {value !== null && value !== undefined && unit
          ? <span className="ml-0.5 text-[11px] text-slate-400">{unit}</span> : null}
      </div>
    </div>
  )
}

function Notes({ items, tone = 'slate' }) {
  if (!items?.length) return null
  const cls = tone === 'amber'
    ? 'bg-amber-50 text-amber-900' : 'bg-slate-50 text-slate-600'
  return (
    <ul className="mt-2 space-y-1.5">
      {items.map((n, i) => (
        <li key={i} className={`rounded-lg px-3 py-1.5 text-[12px] leading-relaxed ${cls}`}>
          {n}
        </li>
      ))}
    </ul>
  )
}

export default function SpeechAudiometry() {
  const [reference, setReference] = useState(null)
  const [ear, setEar] = useState('right')
  const [preset, setPreset] = useState(PRESETS[2])
  const [result, setResult] = useState(null)

  useEffect(() => {
    api.speechReference().then(setReference).catch(() => {})
  }, [])

  const payload = useMemo(() => ({
    ear,
    ac: Object.fromEntries(FREQS.map((f) => [f, preset.ac])),
    sdt: preset.sdt,
    srt: preset.srt,
    wrs: preset.wrs,
  }), [ear, preset])

  useEffect(() => {
    let cancelled = false
    api.speech(payload)
      .then((r) => { if (!cancelled) setResult(r) })
      .catch(() => { if (!cancelled) setResult(null) })
    return () => { cancelled = true }
  }, [payload])

  // Performance-intensity data, with the confidence interval as an error bar
  // so the uncertainty is on the chart rather than in a footnote.
  const piData = useMemo(() => (result?.wrs?.points || []).map((p) => ({
    level: p.level,
    score: p.score,
    ci: [p.score - p.ci.low, p.ci.high - p.score],
  })), [result])

  const sdt = result?.sdt
  const srt = result?.srt
  const wrs = result?.wrs

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">
          Speech audiometry — SDT, SRT, WRS
        </h2>
        <span className="text-[11.5px] text-slate-500">
          scores shown with their 95% binomial interval
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button key={p.label} type="button" onClick={() => setPreset(p)}
            className={`rounded-lg border px-2.5 py-1 text-[12px] transition ${
              preset.label === p.label
                ? 'border-teal-500 bg-teal-50 font-medium text-teal-800'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'}`}>
            {p.label}
          </button>
        ))}
        <div className="ml-auto flex rounded-lg bg-slate-100 p-0.5">
          {['right', 'left'].map((e) => (
            <button key={e} type="button" onClick={() => setEar(e)}
              className={`rounded-md px-2.5 py-0.5 text-[11.5px] font-semibold capitalize transition ${
                ear === e ? 'bg-white shadow-sm' : 'text-slate-500'}`}
              style={ear === e ? { color: EAR_TONE[e] } : undefined}>
              {e}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <Row label="SDT" value={sdt?.sdt} unit="dB HL" />
        <Row label="SRT" value={srt?.srt} unit="dB HL"
          tone={srt && !srt.agrees ? 'text-rose-700' : undefined} />
        <Row label="PB max" value={wrs?.pb_max} unit="%"
          tone={wrs?.adequate_level === false ? 'text-amber-700' : undefined} />
        <Row label="Rollover index" value={wrs?.rollover_index}
          tone={wrs?.rollover ? 'text-rose-700' : undefined} />
      </div>

      {/* --- performance-intensity function ------------------------------ */}
      {piData.length > 0 && (
        <div className="mt-4">
          <div className="h-56 w-full">
            <ResponsiveContainer>
              <ComposedChart data={piData}
                margin={{ top: 8, right: 14, bottom: 20, left: -6 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <ReferenceArea y1={90} y2={100} fill="#10b981" fillOpacity={0.08} />
                {srt?.srt != null && (
                  <ReferenceLine x={srt.srt} stroke="#94a3b8" strokeDasharray="4 4"
                    label={{ value: 'SRT', position: 'top', fontSize: 10,
                      fill: '#94a3b8' }} />
                )}
                <XAxis dataKey="level" type="number"
                  domain={['dataMin - 10', 'dataMax + 10']}
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  label={{ value: 'Presentation level (dB HL)',
                    position: 'insideBottom', offset: -12, fontSize: 10,
                    fill: '#94a3b8' }} />
                <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]}
                  tick={{ fontSize: 11, fill: '#64748b' }} width={40}
                  label={{ value: 'Words correct (%)', angle: -90,
                    position: 'insideLeft', fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }}
                  formatter={(v, n) => (n === 'score' ? [`${v}%`, 'Score'] : null)}
                  labelFormatter={(l) => `${l} dB HL`} />
                <Line dataKey="score" stroke={EAR_TONE[ear]} strokeWidth={2.2}
                  dot={{ r: 4, fill: EAR_TONE[ear] }} isAnimationActive={false}>
                  <ErrorBar dataKey="ci" width={5} strokeWidth={1.4}
                    stroke={EAR_TONE[ear]} strokeOpacity={0.55} direction="y" />
                </Line>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-center text-[11px] text-slate-500">
            Performance-intensity function. Whiskers are the 95% binomial
            interval — two scores whose whiskers overlap are not different.
          </p>
        </div>
      )}

      {/* --- the three readings ------------------------------------------ */}
      <div className="mt-4 space-y-3">
        {sdt && (
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[12.5px] font-semibold text-slate-800">
                Speech detection threshold
              </span>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                sdt.agrees ? 'bg-emerald-100 text-emerald-700'
                  : 'bg-amber-100 text-amber-700'}`}>
                {sdt.agrees ? 'consistent' : 'check'}
              </span>
            </div>
            <p className="mt-1 text-[11.5px] text-slate-500">{sdt.criterion}</p>
            <Notes items={sdt.notes} tone={sdt.agrees ? 'slate' : 'amber'} />
          </div>
        )}

        {srt && (
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[12.5px] font-semibold text-slate-800">
                Speech reception threshold
              </span>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                srt.non_organic_suspected ? 'bg-rose-100 text-rose-700'
                  : srt.agrees ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-amber-100 text-amber-700'}`}>
                {srt.non_organic_suspected ? 'non-organic?'
                  : srt.agrees ? 'agrees' : 'disagrees'}
              </span>
            </div>
            <div className="mt-1.5 grid grid-cols-3 gap-1.5 text-[11px]">
              <Row label="4-frequency PTA" value={srt.pta} unit="dB" />
              <Row label="Fletcher (best 2)" value={srt.pta_fletcher} unit="dB" />
              <Row label="PTA − SRT" value={srt.difference} unit="dB" />
            </div>
            <Notes items={[srt.message, srt.masking_note].filter(Boolean)}
              tone={srt.agrees && !srt.masking_note ? 'slate' : 'amber'} />
          </div>
        )}

        {wrs && (
          <div className="rounded-xl border border-slate-200 p-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[12.5px] font-semibold text-slate-800">
                Word recognition
              </span>
              <span className="text-[11.5px] text-slate-500">
                {wrs.n_words}-word list
              </span>
            </div>
            <p className="mt-1 text-[12.5px] text-slate-700">{wrs.interpretation}</p>
            <p className="mt-1 text-[11.5px] text-slate-500">
              PB max {wrs.pb_max}% at {wrs.pb_max_level} dB HL — 95% CI{' '}
              {wrs.pb_max_ci.low}–{wrs.pb_max_ci.high}%
              {wrs.suprathreshold_target != null && (
                <> · target level ≥ {wrs.suprathreshold_target} dB HL</>
              )}
            </p>
            <Notes items={wrs.notes} tone="amber" />
          </div>
        )}
      </div>

      {reference && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[12px] font-medium text-teal-700">
            What each test measures
          </summary>
          <dl className="mt-2 space-y-2">
            {reference.tests.map((t) => (
              <div key={t.key} className="rounded-lg bg-slate-50 px-3 py-2">
                <dt className="text-[12px] font-semibold text-slate-800">{t.name}</dt>
                <dd className="mt-0.5 text-[11.5px] leading-relaxed text-slate-600">
                  {t.measures} <span className="text-slate-500">{t.use}</span>{' '}
                  <span className="italic text-slate-500">{t.expects}</span>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
            {reference.note} {reference.citations.join(' · ')}
          </p>
        </details>
      )}
    </div>
  )
}
