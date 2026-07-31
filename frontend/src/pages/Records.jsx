import { useCallback, useEffect, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

const PATTERN_COLORS = {
  flat: '#0d9488',
  sloping_high_frequency: '#2563eb',
  ski_slope: '#7c3aed',
  rising: '#db2777',
  noise_notch_4k: '#f59e0b',
  cookie_bite: '#059669',
  corner_audiogram: '#dc2626',
}

function PatientHistory({ id }) {
  const [history, setHistory] = useState(null)

  useEffect(() => {
    if (!id) return
    api.patientHistory(id).then(setHistory).catch(() => setHistory(null))
  }, [id])

  if (!history) return null
  const data = history.visits.map((v) => ({
    date: v.test_date || v.recorded.slice(0, 10),
    Right: v.right_pta, Left: v.left_pta,
  }))

  return (
    <div className="mt-4 rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[14px] font-semibold text-slate-800">
          {history.patient.name}
          <span className="ml-2 text-[12px] font-normal text-slate-500">
            {history.patient.age} y · {history.patient.occupation || 'occupation n/a'}
          </span>
        </h3>
        {history.trend && (
          <span className={`rounded-full px-2.5 py-1 text-[11.5px] font-semibold ${
            history.trend.worsening ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'
          }`}>
            {history.trend.worsening ? 'Worsening' : 'Stable'} over {history.trend.span}
          </span>
        )}
      </div>

      {data.length >= 2 ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 16, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} />
            <YAxis reversed domain={[0, 'dataMax + 10']} tick={{ fontSize: 11, fill: '#475569' }}
              tickLine={false}
              label={{ value: 'PTA (dB HL)', angle: -90, position: 'insideLeft', fontSize: 11, fill: '#94a3b8' }} />
            <Tooltip formatter={(v) => `${v} dB HL`}
              contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line dataKey="Right" stroke="#dc2626" strokeWidth={2.2} dot={{ r: 3 }} />
            <Line dataKey="Left" stroke="#2563eb" strokeWidth={2.2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="mt-2 text-[13px] text-slate-500">
          One visit recorded — a second test unlocks the trend line and the
          OSHA shift comparison.
        </p>
      )}

      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-[12.5px]">
          <thead>
            <tr className="border-b border-slate-100 text-[10.5px] uppercase tracking-wider text-slate-400">
              <th className="py-1.5 font-semibold">Date</th>
              <th className="py-1.5 font-semibold">Right PTA</th>
              <th className="py-1.5 font-semibold">Left PTA</th>
              <th className="py-1.5 font-semibold">Grade</th>
              <th className="py-1.5 font-semibold">Pattern</th>
            </tr>
          </thead>
          <tbody>
            {history.visits.map((v) => (
              <tr key={v.id} className="border-b border-slate-50">
                <td className="py-1.5">{v.test_date || v.recorded.slice(0, 10)}</td>
                <td className="py-1.5">{v.right_pta ?? '—'}</td>
                <td className="py-1.5">{v.left_pta ?? '—'}</td>
                <td className="py-1.5">{v.grade || '—'}</td>
                <td className="py-1.5 text-slate-500">{v.pattern || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function NoiseDose() {
  const { showToast } = useApp()
  const [rows, setRows] = useState([
    { label: 'Machine shop', level_dba: 95, hours: 6 },
    { label: 'Break area', level_dba: 70, hours: 2 },
  ])
  const [nrr, setNrr] = useState(31)
  const [worn, setWorn] = useState(false)
  const [result, setResult] = useState(null)

  const compute = useCallback(async () => {
    try {
      setResult(await api.noiseDose({
        exposures: rows.map((r) => ({ ...r, level_dba: +r.level_dba, hours: +r.hours })),
        nrr: +nrr, protection_worn: worn,
      }))
    } catch (e) {
      showToast(`Dose failed: ${e.message}`, 'error')
    }
  }, [rows, nrr, worn, showToast])

  useEffect(() => { compute() }, [compute])

  const setRow = (i, patch) =>
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const field = 'w-full rounded-md border border-slate-300 px-2 py-1.5 text-[12.5px] focus:border-teal-500 focus:outline-none'

  const riskColor = {
    high: 'bg-rose-50 text-rose-800 border-rose-300',
    action: 'bg-amber-50 text-amber-800 border-amber-300',
    niosh: 'bg-amber-50 text-amber-800 border-amber-200',
    low: 'bg-emerald-50 text-emerald-800 border-emerald-300',
  }[result?.risk] || 'bg-slate-50 text-slate-700 border-slate-200'

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
        Noise-exposure calculator
      </h2>
      <p className="mt-1 text-[12.5px] text-slate-500">
        A trend line says hearing is getting worse. A dose says why — and how much
        of it a pair of earplugs would remove.
      </p>

      <div className="mt-3 space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-[1fr_5rem_5rem_2rem] items-center gap-2">
            <input className={field} value={r.label}
              onChange={(e) => setRow(i, { label: e.target.value })} placeholder="Task" />
            <input type="number" className={field} value={r.level_dba}
              onChange={(e) => setRow(i, { level_dba: e.target.value })} placeholder="dBA" />
            <input type="number" step="0.5" className={field} value={r.hours}
              onChange={(e) => setRow(i, { hours: e.target.value })} placeholder="hrs" />
            <button onClick={() => setRows(rows.filter((_, j) => j !== i))}
              className="text-slate-400 hover:text-rose-600">×</button>
          </div>
        ))}
        <button onClick={() => setRows([...rows, { label: '', level_dba: 85, hours: 1 }])}
          className="text-[12px] font-medium text-teal-700 hover:underline">+ add exposure</button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-[12.5px] text-slate-600">
          <input type="checkbox" checked={worn} className="h-3.5 w-3.5 accent-teal-600"
            onChange={(e) => setWorn(e.target.checked)} />
          hearing protection worn
        </label>
        <label className="flex items-center gap-1.5 text-[12.5px] text-slate-600">
          NRR
          <input type="number" value={nrr} disabled={!worn}
            onChange={(e) => setNrr(e.target.value)}
            className="w-16 rounded-md border border-slate-300 px-2 py-1 text-[12.5px] disabled:opacity-40" />
        </label>
      </div>

      {result?.available && (
        <div className={`mt-3 rounded-xl border p-3 ${riskColor}`}>
          <div className="flex flex-wrap items-baseline gap-4">
            <div>
              <div className="text-[10.5px] font-semibold uppercase tracking-wider opacity-70">OSHA dose</div>
              <div className="text-2xl font-bold">{result.osha_dose_pct}%</div>
            </div>
            <div>
              <div className="text-[10.5px] font-semibold uppercase tracking-wider opacity-70">NIOSH dose</div>
              <div className="text-xl font-bold">{result.niosh_dose_pct}%</div>
            </div>
            {result.twa_dba != null && (
              <div>
                <div className="text-[10.5px] font-semibold uppercase tracking-wider opacity-70">8-h TWA</div>
                <div className="text-xl font-bold">{result.twa_dba} dBA</div>
              </div>
            )}
          </div>
          <p className="mt-1.5 text-[12.5px] leading-snug">{result.verdict}</p>
          <p className="mt-1 text-[11px] opacity-70">{result.protection_note}</p>
        </div>
      )}
    </div>
  )
}

function Atlas() {
  const { analysis } = useApp()
  const [points, setPoints] = useState(null)
  const [me, setMe] = useState(null)

  useEffect(() => {
    api.atlas(700).then((d) => setPoints(d.points)).catch(() => setPoints([]))
  }, [])

  useEffect(() => {
    const ear = analysis?.thresholds?.right
    if (!ear) return
    api.atlasProject(ear).then(setMe).catch(() => setMe(null))
  }, [analysis])

  if (!points?.length) return null
  const byPattern = points.reduce((acc, p) => {
    (acc[p.pattern] ||= []).push(p)
    return acc
  }, {})

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
        Population atlas
      </h2>
      <p className="mt-1 text-[12.5px] text-slate-500">
        Every audiogram the model was trained on, projected to two dimensions.
        A patient landing in empty space between the clusters is exactly what
        the out-of-distribution flag is detecting.
      </p>
      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="#f1f5f9" />
          <XAxis type="number" dataKey="x" tick={{ fontSize: 10, fill: '#94a3b8' }}
            tickLine={false} label={{ value: 'PC 1', position: 'insideBottom', offset: -4, fontSize: 10, fill: '#94a3b8' }} />
          <YAxis type="number" dataKey="y" tick={{ fontSize: 10, fill: '#94a3b8' }}
            tickLine={false} label={{ value: 'PC 2', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#94a3b8' }} />
          <ZAxis range={[24, 24]} />
          <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 12 }}
            formatter={(v, n, p) => [p.payload.label, 'pattern']} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {Object.entries(byPattern).map(([pattern, pts]) => (
            <Scatter key={pattern} name={pts[0].label} data={pts}
              fill={PATTERN_COLORS[pattern] || '#94a3b8'} fillOpacity={0.4} />
          ))}
          {me && (
            <Scatter name="This patient" data={[me]} fill="#0f172a" shape="star"
              legendType="star" />
          )}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Records() {
  const { showToast } = useApp()
  const [patients, setPatients] = useState([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)

  const load = useCallback(async (q) => {
    try {
      setPatients((await api.patients(q)).patients)
    } catch (e) {
      showToast(`Could not load records: ${e.message}`, 'error')
    }
  }, [showToast])

  useEffect(() => { load(query) }, [load, query])

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-xl font-semibold tracking-tight">Patient Records</h1>
      <p className="mt-1 text-[13.5px] text-slate-500">
        Every saved visit, so hearing conservation becomes longitudinal rather
        than a pair of tests.
      </p>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search patients…"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20" />
          <div className="mt-3 space-y-1.5">
            {patients.length === 0 && (
              <p className="text-[13px] text-slate-400">
                No records yet — analyze a test and press <b>Save visit</b>.
              </p>
            )}
            {patients.map((p) => (
              <button key={p.id} onClick={() => setSelected(p.id)}
                className={`w-full rounded-lg px-3 py-2 text-left transition ${
                  selected === p.id ? 'bg-teal-50 ring-1 ring-teal-400' : 'hover:bg-slate-50'
                }`}>
                <div className="text-[13.5px] font-semibold text-slate-800">{p.name}</div>
                <div className="text-[11.5px] text-slate-500">
                  {p.visits} visit{p.visits === 1 ? '' : 's'}
                  {p.last_visit ? ` · last ${p.last_visit}` : ''}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="lg:col-span-2">
          {selected ? <PatientHistory id={selected} /> : (
            <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-[13px] text-slate-400">
              Select a patient to see their history and trend.
            </div>
          )}
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <NoiseDose />
        <Atlas />
      </div>
    </div>
  )
}
