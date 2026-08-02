// Behavioural Observation Audiometry, sitting under the pure-tone form.
//
// It belongs here because it is where paediatric audiometry starts and because
// the mistake it invites is to write its numbers onto an audiogram. Those are
// minimum response levels, not thresholds — a normal-hearing newborn responds
// to a warble tone near 78 dB SPL, some 75 dB above what they can hear. The
// panel states that in the interface rather than in a footnote, and never
// offers to transfer a value into the threshold grid.

import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { api } from '../lib/api.js'

export default function BOAPanel() {
  const [reference, setReference] = useState(null)
  const [ageMonths, setAgeMonths] = useState(3)
  const [level, setLevel] = useState(70)
  const [responses, setResponses] = useState(['eye_blink'])
  const [observers, setObservers] = useState(1)
  const [presentations, setPresentations] = useState(3)
  const [result, setResult] = useState(null)

  useEffect(() => {
    api.boaReference().then(setReference).catch(() => setReference(null))
  }, [])

  useEffect(() => {
    let cancelled = false
    api.boa({
      age_months: Number(ageMonths), observed_level_db_spl: Number(level),
      responses, observers: Number(observers),
      presentations: Number(presentations),
    })
      .then((r) => { if (!cancelled) setResult(r) })
      .catch(() => { if (!cancelled) setResult(null) })
    return () => { cancelled = true }
  }, [ageMonths, level, responses, observers, presentations])

  // The developmental curve is the point: the level falls because the baby's
  // behaviour matures, not because their hearing improves.
  const curve = useMemo(() => (reference?.bands || []).map((b) => ({
    age: b.low_months,
    band: b.band,
    warble: b.warble_db_spl,
    speech: b.speech_db_spl,
  })), [reference])

  const toggle = (key) => setResponses((prev) =>
    prev.includes(key) ? prev.filter((r) => r !== key) : [...prev, key])

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">
          Behavioural Observation Audiometry
        </h2>
        <span className="text-[11.5px] text-slate-500">
          under 6 months · minimum response levels, not thresholds
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Age (months)</span>
          <input type="number" min="0" max="60" step="0.5" value={ageMonths}
            onChange={(e) => setAgeMonths(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
        </label>
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Level (dB SPL)</span>
          <input type="number" min="0" max="120" step="5" value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
        </label>
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Observers</span>
          <select value={observers} onChange={(e) => setObservers(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]">
            <option value="1">1</option>
            <option value="2">2 (one blind)</option>
          </select>
        </label>
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Presentations</span>
          <input type="number" min="1" max="20" value={presentations}
            onChange={(e) => setPresentations(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
        </label>
      </div>

      {reference && (
        <div className="mt-3">
          <span className="text-[11px] font-medium text-slate-600">
            Behaviours observed
          </span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {reference.responses.map((r) => (
              <button key={r.key} type="button" onClick={() => toggle(r.key)}
                aria-pressed={responses.includes(r.key)}
                className={`rounded-lg border px-2 py-0.5 text-[11.5px] transition ${
                  responses.includes(r.key)
                    ? 'border-teal-500 bg-teal-50 font-medium text-teal-800'
                    : 'border-slate-200 bg-white text-slate-600'}`}>
                {r.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {curve.length > 0 && (
        <div className="mt-4">
          <div className="h-48 w-full">
            <ResponsiveContainer>
              <LineChart data={curve} margin={{ top: 8, right: 14, bottom: 18, left: -8 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis dataKey="age" type="number" domain={[0, 24]}
                  ticks={[0, 4, 8, 12, 16, 20, 24]}
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  label={{ value: 'Age (months)', position: 'insideBottom',
                    offset: -12, fontSize: 10, fill: '#94a3b8' }} />
                <YAxis domain={[0, 90]} tick={{ fontSize: 11, fill: '#64748b' }}
                  width={40}
                  label={{ value: 'dB SPL', angle: -90, position: 'insideLeft',
                    fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }}
                  formatter={(v, n) => [`${v} dB SPL`,
                    n === 'warble' ? 'Warble tone MRL' : 'Speech MRL']}
                  labelFormatter={(l) => `${l} months`} />
                <Line dataKey="warble" stroke="#0d9488" strokeWidth={2.2}
                  dot={{ r: 3, fill: '#0d9488' }} isAnimationActive={false} />
                <Line dataKey="speech" stroke="#94a3b8" strokeWidth={1.8}
                  strokeDasharray="4 4" dot={{ r: 2.5, fill: '#94a3b8' }}
                  isAnimationActive={false} />
                {result?.observed_level_db_spl != null && (
                  <ReferenceDot x={Number(ageMonths)} y={Number(level)} r={6}
                    fill={result.concern ? '#dc2626' : '#0d9488'} stroke="#fff"
                    strokeWidth={2} />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-center text-[11px] text-slate-500">
            Minimum response levels fall as the infant&rsquo;s behaviour matures —
            not as their hearing improves. The dot is this observation.
          </p>
        </div>
      )}

      {result?.available && (
        <>
          <p className={`mt-3 rounded-lg border px-3 py-2 text-[12.5px] font-medium ${
            result.concern ? 'border-rose-300 bg-rose-50 text-rose-900'
              : 'border-emerald-300 bg-emerald-50 text-emerald-900'}`}>
            {result.headline}
          </p>

          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 text-[12px]">
            {[
              ['Age band', result.band],
              ['Expected warble', `${result.expected_mrl_db_spl} dB SPL`],
              ['Observed', `${result.observed_level_db_spl} dB SPL`],
              ['Difference', `${result.difference_db > 0 ? '+' : ''}${result.difference_db} dB`],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg bg-slate-50 px-2.5 py-2">
                <div className="text-[10.5px] font-medium text-slate-500">{label}</div>
                <div className="mt-0.5 text-[12.5px] text-slate-800">{value}</div>
              </div>
            ))}
          </div>

          <div className="mt-3 text-[11.5px] leading-relaxed text-slate-600">
            <span className="font-semibold text-slate-700">Expected at this age:</span>{' '}
            {result.expected_behaviours.join(' · ')}
          </div>

          {result.findings.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {result.findings.map((f, i) => (
                <li key={i}
                  className="rounded-lg bg-amber-50 px-3 py-1.5 text-[12px] leading-relaxed text-amber-900">
                  {f}
                </li>
              ))}
            </ul>
          )}

          <p className="mt-3 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-[11.5px] leading-relaxed text-slate-700">
            <span className="font-semibold">Not a threshold.</span> {result.caveat}
          </p>
        </>
      )}

      {reference?.limits && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[12px] font-medium text-teal-700">
            What BOA cannot do
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
