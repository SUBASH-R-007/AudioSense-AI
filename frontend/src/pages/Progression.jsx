import { useEffect, useState } from 'react'
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, AC_FREQS, FREQ_LABELS } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

function ForecastPanel({ forecast }) {
  const [ear, setEar] = useState('right')
  const f = forecast[ear]
  if (!f) return null

  const data = f.exposed_pta.map((p, i) => ({
    year: `+${p.year}y`,
    Exposed: p.pta,
    Protected: f.protected_pta[i].pta,
    // Recharts stacks an Area from a [low, high] tuple for the band.
    band: [forecast[ear].uncertainty_band[i].low, forecast[ear].uncertainty_band[i].high],
  }))

  return (
    <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
            {forecast.horizon_years}-year projection
          </h2>
          <p className="mt-0.5 text-[12px] text-slate-500">
            Measured shift rate {f.mean_slope > 0 ? '+' : ''}{f.mean_slope} dB/year over{' '}
            {forecast.interval_years} years, projected forward.
          </p>
        </div>
        <div className="flex rounded-lg bg-slate-100 p-1">
          {['right', 'left'].map((e) => (
            <button key={e} onClick={() => setEar(e)}
              className={`rounded-md px-3 py-1.5 text-[12.5px] font-semibold capitalize transition ${
                ear === e
                  ? e === 'right' ? 'bg-white text-red-600 shadow-sm' : 'bg-white text-blue-600 shadow-sm'
                  : 'text-slate-500'
              }`}>{e} ear</button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 12, fill: '#475569' }} tickLine={false} />
          <YAxis reversed domain={[0, 'dataMax + 10']} tick={{ fontSize: 11, fill: '#475569' }}
            tickLine={false}
            label={{ value: 'PTA (dB HL)', angle: -90, position: 'insideLeft', fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip formatter={(v, n) => [Array.isArray(v) ? `${v[0]}–${v[1]} dB` : `${v} dB HL`, n]}
            contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 12 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine y={25} stroke="#94a3b8" strokeDasharray="4 4"
            label={{ value: 'RPwD 25 dB floor', fontSize: 10, fill: '#94a3b8', position: 'right' }} />
          <ReferenceLine y={35} stroke="#f43f5e" strokeDasharray="4 4"
            label={{ value: 'moderate', fontSize: 10, fill: '#f43f5e', position: 'right' }} />
          <Area name="uncertainty" dataKey="band" stroke="none" fill="#f43f5e" fillOpacity={0.12} />
          <Line name="Continued exposure" dataKey="Exposed" stroke="#e11d48" strokeWidth={2.4}
            dot={{ r: 3 }} isAnimationActive={false} />
          <Line name="With hearing protection" dataKey="Protected" stroke="#059669" strokeWidth={2.4}
            strokeDasharray="6 4" dot={{ r: 3 }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl bg-rose-50 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-rose-700">
            If exposure continues
          </div>
          <div className="mt-1 text-[14px] font-bold text-slate-800">{f.exposed_grade}</div>
          <div className="text-[12px] text-slate-600">
            PTA {f.exposed_pta[f.exposed_pta.length - 1].pta} dB in {forecast.horizon_years} years
            {f.grade_change && <span className="font-semibold text-rose-700"> — grade worsens</span>}
          </div>
        </div>
        <div className="rounded-xl bg-emerald-50 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
            With hearing protection
          </div>
          <div className="mt-1 text-[14px] font-bold text-slate-800">{f.protected_grade}</div>
          <div className="text-[12px] text-slate-600">
            PTA {f.protected_pta[f.protected_pta.length - 1].pta} dB — age-related change only
          </div>
        </div>
        <div className="rounded-xl bg-slate-50 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Preventable loss
          </div>
          <div className="mt-1 text-[20px] font-bold text-teal-700">
            {f.preventable_db ?? 0} dB
          </div>
          <div className="text-[12px] text-slate-600">
            {f.years_to_disability_floor == null
              ? 'not trending toward the disability floor'
              : f.years_to_disability_floor === 0
                ? 'already past the 25 dB disability floor'
                : `crosses the 25 dB disability floor in ~${f.years_to_disability_floor} years`}
          </div>
        </div>
      </div>

      {forecast.disability_projected && (
        <div className="mt-3 rounded-xl border border-slate-200 px-3 py-2 text-[12.5px] text-slate-600">
          Projected binaural disability rises from{' '}
          <b>{forecast.disability_now.binaural_pct}%</b> to{' '}
          <b className={forecast.disability_projected.benchmark_disability ? 'text-rose-600' : ''}>
            {forecast.disability_projected.binaural_pct}%
          </b>
          {forecast.disability_projected.benchmark_disability &&
            ' — crossing the RPwD 40% benchmark'}
          .
        </div>
      )}

      <p className="mt-2 text-[11px] text-slate-400">{forecast.caveat} {forecast.method}.</p>
    </div>
  )
}

export default function Progression() {
  const { history, showToast } = useApp()
  const [pair, setPair] = useState(null) // {baseline, current, label}
  const [result, setResult] = useState(null)
  const [baseIdx, setBaseIdx] = useState('')
  const [currIdx, setCurrIdx] = useState('')
  const [busy, setBusy] = useState(false)

  const loadDemo = async () => {
    try {
      const d = await api.demoCases()
      setPair({ ...d.progression_pair })
    } catch (e) {
      showToast(`Backend not reachable: ${e.message}`, 'error')
    }
  }

  const compareHistory = () => {
    if (baseIdx === '' || currIdx === '' || baseIdx === currIdx) {
      return showToast('Pick two different saved tests', 'warn')
    }
    setPair({
      label: 'Saved tests comparison',
      baseline: history[+baseIdx].record,
      current: history[+currIdx].record,
    })
  }

  useEffect(() => {
    if (!pair) return
    setBusy(true)
    api.progression(pair.baseline, pair.current)
      .then(setResult)
      .catch((e) => showToast(`Progression failed: ${e.message}`, 'error'))
      .finally(() => setBusy(false))
  }, [pair, showToast])

  const chartData = result
    ? AC_FREQS.map((f) => ({
        freq: FREQ_LABELS[f],
        Right: result.progression.right.deltas[f],
        Left: result.progression.left.deltas[f],
      }))
    : []

  const FlagCard = ({ side, prog }) => (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <h3 className={`text-[12px] font-bold uppercase tracking-wider ${
        side === 'right' ? 'text-red-600' : 'text-blue-600'}`}>{side} ear</h3>
      <div className="mt-3 space-y-3">
        <div className={`rounded-xl p-3 ${prog.osha_sts.flag ? 'bg-rose-50' : 'bg-emerald-50'}`}>
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-semibold text-slate-800">OSHA Standard Threshold Shift</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
              prog.osha_sts.flag ? 'bg-rose-600 text-white' : 'bg-emerald-600 text-white'}`}>
              {prog.osha_sts.flag ? 'FLAGGED' : 'clear'}
            </span>
          </div>
          <div className="mt-1 text-[12px] text-slate-600">
            Avg shift at 2k/4k: <b>{prog.osha_sts.avg_shift ?? '—'} dB</b> (criterion ≥ 10 dB)
          </div>
        </div>
        <div className={`rounded-xl p-3 ${prog.asha_ototoxicity.flag ? 'bg-rose-50' : 'bg-emerald-50'}`}>
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-semibold text-slate-800">ASHA Ototoxicity Criteria</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
              prog.asha_ototoxicity.flag ? 'bg-rose-600 text-white' : 'bg-emerald-600 text-white'}`}>
              {prog.asha_ototoxicity.flag ? 'FLAGGED' : 'clear'}
            </span>
          </div>
          {prog.asha_ototoxicity.triggers.length > 0 && (
            <ul className="mt-1 list-inside list-disc text-[12px] text-slate-600">
              {prog.asha_ototoxicity.triggers.map((t, i) => <li key={i}>{t}</li>)}
            </ul>
          )}
        </div>
        <div className="text-[12px] text-slate-500">
          Max single-frequency shift: <b>{prog.max_shift ?? '—'} dB</b>
        </div>
      </div>
    </div>
  )

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-xl font-semibold tracking-tight">Progression Analysis</h1>
      <p className="mt-1 text-[13.5px] text-slate-500">
        Compare two dated tests — detect OSHA standard threshold shifts and ASHA ototoxicity criteria.
      </p>

      <div className="mt-5 flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <button onClick={loadDemo}
          className="rounded-lg bg-teal-600 px-4 py-2 text-[13px] font-semibold text-white shadow-sm hover:bg-teal-700">
          Load demo pair (3-year noise exposure)
        </button>
        <span className="text-[12px] text-slate-400">or compare saved tests:</span>
        <select value={baseIdx} onChange={(e) => setBaseIdx(e.target.value)}
          className="rounded-lg border border-slate-300 px-2.5 py-2 text-[13px]">
          <option value="">Baseline…</option>
          {history.map((h, i) => <option key={h.id} value={i}>{h.label}</option>)}
        </select>
        <select value={currIdx} onChange={(e) => setCurrIdx(e.target.value)}
          className="rounded-lg border border-slate-300 px-2.5 py-2 text-[13px]">
          <option value="">Current…</option>
          {history.map((h, i) => <option key={h.id} value={i}>{h.label}</option>)}
        </select>
        <button onClick={compareHistory}
          className="rounded-lg border border-slate-300 px-4 py-2 text-[13px] font-semibold text-slate-700 hover:border-teal-400 hover:text-teal-700">
          Compare
        </button>
      </div>

      {busy && <div className="mt-8 text-center text-sm text-slate-400">Comparing…</div>}

      {result && !busy && (
        <>
          {result.progression.narrative && (
            <div className={`mt-5 rounded-2xl border p-5 shadow-sm ${
              result.progression.narrative.flagged
                ? 'border-rose-200 bg-rose-50/50' : 'border-emerald-200 bg-emerald-50/40'}`}>
              <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
                What changed
              </h2>
              <p className={`mt-1 text-[15px] font-semibold ${
                result.progression.narrative.flagged ? 'text-rose-800' : 'text-emerald-800'}`}>
                {result.progression.narrative.headline}
              </p>
              <ul className="mt-2 space-y-1.5">
                {result.progression.narrative.lines.map((line, i) => (
                  <li key={i} className="flex gap-2 text-[13.5px] leading-relaxed text-slate-700">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
                Threshold shift by frequency (positive = worse)
              </h2>
              <span className="text-[12px] text-slate-500">
                {result.baseline_date || 'baseline'} → {result.current_date || 'current'}
                {result.patient?.name ? ` · ${result.patient.name}` : ''}
              </span>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} margin={{ top: 16, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="freq" tick={{ fontSize: 12, fill: '#475569' }} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#475569' }} tickLine={false}
                  label={{ value: 'Shift (dB)', angle: -90, position: 'insideLeft', fontSize: 11, fill: '#94a3b8' }} />
                <Tooltip formatter={(v) => `${v > 0 ? '+' : ''}${v} dB`}
                  contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={10} stroke="#f43f5e" strokeDasharray="5 4"
                  label={{ value: 'significant (+10)', fontSize: 10, fill: '#f43f5e', position: 'right' }} />
                <ReferenceLine y={0} stroke="#94a3b8" />
                <Bar dataKey="Right" fill="#dc2626" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Left" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <FlagCard side="right" prog={result.progression.right} />
            <FlagCard side="left" prog={result.progression.left} />
          </div>

          {result.forecast?.available && <ForecastPanel forecast={result.forecast} />}
        </>
      )}
    </div>
  )
}
