// Tympanometry and otoacoustic emissions, as instruments rather than fields.
//
// Both tests are curves, and both are routinely run without a pure-tone
// audiogram to attach them to — a newborn screen, a post-grommet check, an
// occupational monitoring visit. So this page stands alone: enter a sweep or
// a DP-gram, get the plot, the type or the pass/refer, and the interpretation.
//
// The tympanogram plot exists because the gradient is invisible in a table of
// three numbers. A peak of normal height that is too broad is an early
// effusion, and you can see that at a glance on the curve and not at all in
// the summary.

import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis, Bar, BarChart, Legend,
} from 'recharts'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

const TYPE_STYLE = {
  A: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  As: 'border-amber-300 bg-amber-50 text-amber-900',
  Ad: 'border-amber-300 bg-amber-50 text-amber-900',
  B: 'border-rose-300 bg-rose-50 text-rose-900',
  C: 'border-sky-300 bg-sky-50 text-sky-900',
}

const OUTCOME_STYLE = {
  pass: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  refer: 'border-rose-300 bg-rose-50 text-rose-900',
  incomplete: 'border-amber-300 bg-amber-50 text-amber-900',
}

// Presets are real curve shapes, so the plot demonstrates what the numbers
// mean rather than requiring twenty values to be typed first.
const TYMP_PRESETS = [
  { label: 'Normal (Type A)', peak: -20, height: 0.85, tail: 0.9, width: 85 },
  { label: 'Effusion (Type B)', peak: 0, height: 0.02, tail: 1.0, width: 400 },
  { label: 'Perforation (Type B, large volume)', peak: 0, height: 0.02, tail: 2.8, width: 400 },
  { label: 'ET dysfunction (Type C)', peak: -230, height: 0.55, tail: 0.9, width: 100 },
  { label: 'Stiff (Type As)', peak: -10, height: 0.18, tail: 0.9, width: 80 },
  { label: 'Early effusion (broad peak)', peak: -60, height: 0.5, tail: 0.9, width: 200 },
]

const OAE_PRESETS = [
  { label: 'Normal emissions', build: (f) => ({ amplitude: 11, noise_floor: -13 }) },
  {
    label: 'Pre-clinical noise damage',
    build: (f) => (f >= 3000 ? { amplitude: -18, noise_floor: -13 }
      : { amplitude: 10, noise_floor: -13 }),
  },
  { label: 'Absent throughout', build: () => ({ amplitude: -18, noise_floor: -13 }) },
  { label: 'Too noisy to judge', build: () => ({ amplitude: 4, noise_floor: 17 }) },
]

function buildTrace({ peak, height, tail, width }) {
  const sigma = width / 2.355
  const out = []
  for (let p = -400; p <= 200; p += 10) {
    out.push({
      pressure: p,
      admittance: Number((tail + height * Math.exp(
        -((p - peak) ** 2) / (2 * sigma ** 2))).toFixed(4)),
    })
  }
  return out
}

function Panel({ title, children, right }) {
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

function Measure({ label, value, unit, ok }) {
  const tone = ok === false ? 'text-rose-700' : ok === true ? 'text-emerald-700' : 'text-slate-800'
  return (
    <div className="rounded-lg bg-slate-50 px-2.5 py-2">
      <div className="text-[11px] font-medium text-slate-500">{label}</div>
      <div className={`mt-0.5 font-mono text-[13.5px] ${tone}`}>
        {value === null || value === undefined ? '—' : value}
        {value !== null && value !== undefined && unit ? (
          <span className="ml-0.5 text-[11px] text-slate-400">{unit}</span>
        ) : null}
      </div>
    </div>
  )
}

// -------------------------------------------------------- tympanometry ----
function Tympanometry({ reference }) {
  const { showToast } = useApp()
  const [ear, setEar] = useState('right')
  const [ageYears, setAgeYears] = useState(30)
  const [probeHz, setProbeHz] = useState(226)
  const [preset, setPreset] = useState(TYMP_PRESETS[0])
  const [ipsi, setIpsi] = useState('85')
  const [contra, setContra] = useState('90')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const trace = useMemo(() => buildTrace(preset), [preset])

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    const reflexes = {}
    if (ipsi !== '') reflexes.ipsi = ipsi === 'absent' ? null : Number(ipsi)
    if (contra !== '') reflexes.contra = contra === 'absent' ? null : Number(contra)
    api.tympanometry({
      ear, trace, age_years: Number(ageYears), probe_hz: Number(probeHz), reflexes,
    })
      .then((r) => { if (!cancelled) setResult(r) })
      .catch((e) => { if (!cancelled) showToast(e.message, 'error') })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [ear, ageYears, probeHz, trace, ipsi, contra, showToast])

  const norms = result?.curve?.normative
  const jerger = result?.tympanogram

  return (
    <Panel
      title="Tympanometry"
      right={jerger && (
        <span className={`rounded-lg border px-2.5 py-1 text-[12px] font-semibold ${
          TYPE_STYLE[jerger.type] || 'border-slate-300 bg-slate-50 text-slate-700'}`}>
          {jerger.label}
        </span>
      )}
    >
      <div className="mt-3 flex flex-wrap gap-2">
        {TYMP_PRESETS.map((p) => (
          <button key={p.label} type="button" onClick={() => setPreset(p)}
            className={`rounded-lg border px-2.5 py-1 text-[12px] transition ${
              preset.label === p.label
                ? 'border-teal-500 bg-teal-50 font-medium text-teal-800'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'}`}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Ear</span>
          <select value={ear} onChange={(e) => setEar(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]">
            <option value="right">Right</option><option value="left">Left</option>
          </select>
        </label>
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Age (years)</span>
          <input type="number" min="0" step="0.25" value={ageYears}
            onChange={(e) => setAgeYears(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
        </label>
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Probe</span>
          <select value={probeHz} onChange={(e) => setProbeHz(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]">
            <option value="226">226 Hz</option><option value="1000">1000 Hz</option>
          </select>
        </label>
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Ipsi reflex</span>
          <input value={ipsi} onChange={(e) => setIpsi(e.target.value)} placeholder="dB HL"
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
        </label>
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Contra reflex</span>
          <input value={contra} onChange={(e) => setContra(e.target.value)} placeholder="dB HL"
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
        </label>
      </div>

      <div className="mt-4 h-64 w-full">
        <ResponsiveContainer>
          <LineChart data={result?.curve?.points || trace}
            margin={{ top: 8, right: 12, bottom: 24, left: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            {norms && (
              <ReferenceArea x1={norms.pressure[0]} x2={norms.pressure[1]}
                fill="#0d9488" fillOpacity={0.07} />
            )}
            <ReferenceLine x={0} stroke="#94a3b8" strokeDasharray="4 4" />
            <XAxis dataKey="pressure" type="number" domain={[-400, 200]}
              ticks={[-400, -300, -200, -100, 0, 100, 200]}
              tick={{ fontSize: 11, fill: '#64748b' }}
              label={{ value: 'Ear-canal pressure (daPa)', position: 'insideBottom',
                offset: -14, fontSize: 11, fill: '#64748b' }} />
            <YAxis tick={{ fontSize: 11, fill: '#64748b' }} width={44}
              label={{ value: 'Admittance (mmho)', angle: -90, position: 'insideLeft',
                fontSize: 11, fill: '#64748b' }} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }}
              formatter={(v) => [`${v} mmho`, 'Admittance']}
              labelFormatter={(l) => `${l} daPa`} />
            <Line type="monotone" dataKey="admittance" stroke="#0d9488" strokeWidth={2.2}
              dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {result && (
        <>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Measure label="Peak pressure" value={result.measurements.peak_pressure}
              unit="daPa" ok={result.within_normal.pressure} />
            <Measure label="Static compliance" value={result.measurements.static_compliance}
              unit="mmho" ok={result.within_normal.compliance} />
            <Measure label="Canal volume" value={result.measurements.ecv}
              unit="cm³" ok={result.within_normal.ecv} />
            <Measure label="Gradient (width)" value={result.measurements.width}
              unit="daPa" ok={result.within_normal.width} />
          </div>

          {result.infant_warning && (
            <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] leading-relaxed text-rose-900">
              {result.infant_warning}
            </p>
          )}
          {result.flags.map((f) => (
            <p key={f} className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
              {f}
            </p>
          ))}

          <ul className="mt-3 space-y-1.5 text-[12.5px] leading-relaxed text-slate-600">
            {result.interpretation.map((line, i) => <li key={i}>· {line}</li>)}
          </ul>

          {norms && (
            <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
              Normal ranges for the {norms.band} band — pressure {norms.pressure[0]} to{' '}
              {norms.pressure[1]} daPa, compliance {norms.compliance[0]}–{norms.compliance[1]} mmho,
              volume {norms.ecv[0]}–{norms.ecv[1]} cm³, width {norms.width[0]}–{norms.width[1]} daPa.
              {' '}{norms.citations.join('; ')}.
            </p>
          )}
        </>
      )}
      {busy && !result && <p className="mt-2 text-[12px] text-slate-400">Analysing…</p>}
    </Panel>
  )
}

// ------------------------------------------------------------------ OAE ---
function Emissions({ reference }) {
  const { analysis, showToast } = useApp()
  const [ear, setEar] = useState('right')
  const [protocol, setProtocol] = useState('screening')
  const [preset, setPreset] = useState(OAE_PRESETS[1])
  const [result, setResult] = useState(null)

  const freqs = reference?.frequencies || [1000, 2000, 3000, 4000, 6000, 8000]
  const points = useMemo(
    () => freqs.map((f) => ({ freq: f, ...preset.build(f) })),
    [freqs, preset],
  )

  // Thresholds from the current case, so absent emissions above the ceiling
  // are marked uninformative rather than counted as fresh damage.
  const ac = useMemo(() => {
    const source = analysis?.thresholds?.[ear]?.ac || {}
    const out = {}
    for (const [k, v] of Object.entries(source)) {
      if (typeof v === 'number') out[k] = v
    }
    return out
  }, [analysis, ear])

  useEffect(() => {
    let cancelled = false
    api.oae({ ear, protocol, points, ac })
      .then((r) => { if (!cancelled) setResult(r) })
      .catch((e) => { if (!cancelled) showToast(e.message, 'error') })
    return () => { cancelled = true }
  }, [ear, protocol, points, ac, showToast])

  const chartData = (result?.points || points).map((p) => ({
    name: p.freq >= 1000 ? `${p.freq / 1000}k` : `${p.freq}`,
    emission: p.amplitude,
    noise: p.noise_floor,
    verdict: p.verdict,
  }))

  return (
    <Panel
      title="Otoacoustic emissions"
      right={result && (
        <span className={`rounded-lg border px-2.5 py-1 text-[12px] font-semibold uppercase ${
          OUTCOME_STYLE[result.outcome] || 'border-slate-300 bg-slate-50 text-slate-700'}`}>
          {result.outcome}
        </span>
      )}
    >
      <div className="mt-3 flex flex-wrap gap-2">
        {OAE_PRESETS.map((p) => (
          <button key={p.label} type="button" onClick={() => setPreset(p)}
            className={`rounded-lg border px-2.5 py-1 text-[12px] transition ${
              preset.label === p.label
                ? 'border-teal-500 bg-teal-50 font-medium text-teal-800'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'}`}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Ear</span>
          <select value={ear} onChange={(e) => setEar(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]">
            <option value="right">Right</option><option value="left">Left</option>
          </select>
        </label>
        <label className="col-span-2 text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Protocol</span>
          <select value={protocol} onChange={(e) => setProtocol(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]">
            {(reference?.protocols || []).map((p) => (
              <option key={p.key} value={p.key}>{p.name}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4 h-64 w-full">
        <ResponsiveContainer>
          <BarChart data={chartData} margin={{ top: 8, right: 12, bottom: 24, left: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }}
              label={{ value: 'f2 frequency (Hz)', position: 'insideBottom', offset: -14,
                fontSize: 11, fill: '#64748b' }} />
            <YAxis tick={{ fontSize: 11, fill: '#64748b' }} width={44}
              label={{ value: 'dB SPL', angle: -90, position: 'insideLeft',
                fontSize: 11, fill: '#64748b' }} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="noise" name="Noise floor" fill="#cbd5e1" isAnimationActive={false} />
            <Bar dataKey="emission" name="Emission" fill="#0d9488" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {result?.available && (
        <>
          <p className="mt-1 text-[13px] font-medium text-slate-800">{result.headline}</p>
          <p className="mt-0.5 text-[11.5px] text-slate-500">
            {result.protocol.name}: {result.protocol.required} of{' '}
            {result.protocol.freqs.length} frequencies must reach{' '}
            {result.protocol.snr} dB SNR. {result.protocol.note}
          </p>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-[12px]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-slate-400">
                  <th className="py-1 pr-3 font-medium">Hz</th>
                  <th className="py-1 pr-3 font-medium">SNR</th>
                  <th className="py-1 pr-3 font-medium">Threshold</th>
                  <th className="py-1 pr-3 font-medium">Verdict</th>
                  <th className="py-1 font-medium">Cochlear place</th>
                </tr>
              </thead>
              <tbody>
                {result.points.map((p) => (
                  <tr key={p.freq} className="border-t border-slate-100">
                    <td className="py-1.5 pr-3 font-mono">{p.freq}</td>
                    <td className="py-1.5 pr-3 font-mono">{p.snr}</td>
                    <td className="py-1.5 pr-3 font-mono text-slate-500">
                      {p.threshold ?? '—'}
                    </td>
                    <td className="py-1.5 pr-3">
                      <span className={`rounded px-1.5 py-0.5 text-[10.5px] font-semibold uppercase ${
                        p.verdict === 'pass' ? 'bg-emerald-100 text-emerald-700'
                          : p.verdict === 'refer' ? 'bg-rose-100 text-rose-700'
                            : p.verdict === 'invalid' ? 'bg-amber-100 text-amber-700'
                              : 'bg-slate-100 text-slate-600'}`}>
                        {p.verdict}
                      </span>
                    </td>
                    <td className="py-1.5 text-slate-500">{p.region}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {result.cochlear_profile && (
            <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[12.5px] leading-relaxed text-slate-700">
              <span className="font-semibold capitalize">{result.cochlear_profile.pattern}</span>
              {' — '}{result.cochlear_profile.summary}
            </p>
          )}

          {/* The headline and the cochlear summary already have their own
              places on screen; the list is what is left to say. */}
          <ul className="mt-2.5 space-y-1.5 text-[12.5px] leading-relaxed text-slate-600">
            {result.interpretation
              .filter((line) => line !== result.headline
                && line !== result.cochlear_profile?.summary)
              .map((line, i) => <li key={i}>· {line}</li>)}
          </ul>

          {Object.keys(ac).length === 0 && (
            <p className="mt-2 text-[11.5px] text-slate-400">
              No audiogram loaded, so absent emissions cannot be checked against the
              thresholds that would explain them.
            </p>
          )}
        </>
      )}
    </Panel>
  )
}

export default function Immittance() {
  const [tympRef, setTympRef] = useState(null)
  const [oaeRef, setOaeRef] = useState(null)

  useEffect(() => {
    api.tympanometryReference().then(setTympRef).catch(() => {})
    api.oaeReference().then(setOaeRef).catch(() => {})
  }, [])

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">
          Immittance &amp; emissions
        </h1>
        <p className="mt-1 max-w-3xl text-[13.5px] leading-relaxed text-slate-500">
          Tympanometry and otoacoustic emissions as full instruments — the curve, the
          gradient, the pass criterion and the cochlear place — usable on their own,
          without a pure-tone audiogram to attach them to.
        </p>
      </header>

      <div className="mt-5 space-y-5">
        <Tympanometry reference={tympRef} />
        <Emissions reference={oaeRef} />
      </div>

      {tympRef && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-slate-50/60 p-5">
          <h2 className="text-[13px] font-semibold text-slate-800">Jerger classification</h2>
          <dl className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {tympRef.types.map((t) => (
              <div key={t.type} className="rounded-lg bg-white px-3 py-2">
                <dt className="text-[12.5px] font-semibold text-slate-800">
                  Type {t.type} — {t.label}
                </dt>
                <dd className="mt-0.5 text-[11.5px] leading-relaxed text-slate-600">
                  {t.detail}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-[11.5px] leading-relaxed text-slate-500">
            {tympRef.infant_note}
          </p>
        </div>
      )}
    </div>
  )
}
