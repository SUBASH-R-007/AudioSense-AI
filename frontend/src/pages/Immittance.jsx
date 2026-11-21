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
import TympanogramAtlas from '../components/TympanogramAtlas.jsx'
import SpeechAudiometry from '../components/SpeechAudiometry.jsx'
import StepNav from '../components/StepNav.jsx'
import Collapsible, { Reveal, ReferenceSection } from '../components/Collapsible.jsx'
import {
  EntryModeTabs, FrequencyEditor, OutcomeLimits, OutcomePicker,
} from '../components/EntryMode.jsx'

//: The eight types, for the type-only entry mode. Ordered as the reference
//: document orders them, not alphabetically — A/As/Ad/Add are one family.
const TYMP_TYPE_KEYS = ['A', 'As', 'Ad', 'Add', 'B', 'C', 'D', 'E']

const TYPE_STYLE = {
  A: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  As: 'border-amber-300 bg-amber-50 text-amber-900',
  Ad: 'border-amber-300 bg-amber-50 text-amber-900',
  Add: 'border-rose-300 bg-rose-50 text-rose-900',
  B: 'border-rose-300 bg-rose-50 text-rose-900',
  C: 'border-sky-300 bg-sky-50 text-sky-900',
  D: 'border-violet-300 bg-violet-50 text-violet-900',
  E: 'border-rose-300 bg-rose-50 text-rose-900',
}

// The 1000 Hz infant outcomes ('1k-peak', '1k-low-peak', '1k-no-peak') are
// not Jerger types; they are styled by what they mean — refer, or a pass
// that is only provisional when the trace was incomplete.
const typeStyle = (t) => {
  if (!t) return 'border-slate-300 bg-slate-50 text-slate-700'
  if (TYPE_STYLE[t.type]) return TYPE_STYLE[t.type]
  if (t.refer) return 'border-rose-300 bg-rose-50 text-rose-900'
  if (t.provisional) return 'border-amber-300 bg-amber-50 text-amber-900'
  if (String(t.type || '').startsWith('1k')) return 'border-emerald-300 bg-emerald-50 text-emerald-900'
  return 'border-slate-300 bg-slate-50 text-slate-700'
}

const OUTCOME_STYLE = {
  pass: 'border-emerald-300 bg-emerald-50 text-emerald-900',
  refer: 'border-rose-300 bg-rose-50 text-rose-900',
  incomplete: 'border-amber-300 bg-amber-50 text-amber-900',
}

// Presets are real curve shapes, so the plot demonstrates what the numbers
// mean rather than requiring twenty values to be typed first.
const TYMP_PRESETS = [
  { label: 'Normal (A)', peak: -20, height: 0.85, tail: 0.9, width: 85 },
  { label: 'Stiff (As)', peak: -10, height: 0.25, tail: 0.9, width: 80 },
  { label: 'Flaccid (Ad)', peak: -10, height: 2.4, tail: 0.9, width: 90 },
  { label: 'Off-scale (Add)', peak: -10, height: 7.2, tail: 0.9, width: 95, ceiling: 4 },
  { label: 'Effusion (B, normal ECV)', peak: 0, height: 0.02, tail: 1.0, width: 400 },
  { label: 'Perforation (B, large ECV)', peak: 0, height: 0.02, tail: 2.8, width: 400 },
  { label: 'Wax / blocked probe (B, small ECV)', peak: 0, height: 0.02, tail: 0.35, width: 400 },
  { label: 'ET dysfunction (C)', peak: -230, height: 0.55, tail: 0.9, width: 100 },
  { label: 'Scarred drum (D, narrow notch)', peak: -10, height: 0.9, tail: 0.9, width: 70, notched: true, notchWidth: 45 },
  { label: 'Ossicular disruption (E, wide notch)', peak: -10, height: 2.3, tail: 0.9, width: 120, notched: true, notchWidth: 110 },
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

// Module scope, deliberately. Written inline as a fallback it was a fresh
// array on every render, which gave the `points` memo a new identity, which
// re-ran the fetch effect, whose setState re-rendered — a tight loop of failing
// POSTs and error toasts for as long as the OAE reference was unavailable.
const DEFAULT_OAE_FREQS = [1000, 2000, 3000, 4000, 6000, 8000]

function buildTrace({ peak, height, tail, width, notched = false, notchWidth = 60,
                     ceiling = null }) {
  const sigma = width / 2.355
  const bump = (p, mu, s) => Math.exp(-((p - mu) ** 2) / (2 * s ** 2))
  const out = []
  for (let p = -400; p <= 200; p += 10) {
    // Two shoulders either side of the centre produce the W shape that defines
    // Types D and E. Mirrors synthesize_trace on the server so the drawn curve
    // and the classified curve are the same curve.
    const shape = notched
      ? Math.max(bump(p, peak - notchWidth / 2, Math.max(sigma * 0.55, 12)),
                 bump(p, peak + notchWidth / 2, Math.max(sigma * 0.55, 12)))
      : bump(p, peak, sigma)
    const value = tail + height * shape
    // Past the instrument ceiling there is no reading. Recording null keeps
    // the limbs of a Type Add trace from being joined into an apex that was
    // never measured.
    out.push(ceiling !== null && value > ceiling
      ? { pressure: p, admittance: null, off_scale: true }
      : { pressure: p, admittance: Number(value.toFixed(4)) })
  }
  return out
}

function Panel({ title, children, right, tour }) {
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


// ------------------------------------------- attach to this patient ----
//
// The instrument panels on this page used to be a sealed playground: a
// clinician following the consultation order — audiogram first, then here —
// typed a real tympanogram into a page that silently discarded it, and the
// results were interpreted on a subset of what had been collected. This
// merges a measurement into the stored analyze request and re-runs the whole
// interpretation over it.
//
// Attaching is EXPLICIT, and the exact values travel on the button. The
// panels are preset-driven, so most of what they show at any moment is an
// example, not this patient — the same trap the BOA panel had, where merely
// opening a page published fabricated findings. Nothing here reaches the
// analysis until the clinician has read the payload and clicked.
function AttachToAnalysis({ ear, summary, patch }) {
  const { analysis, record, setAnalysis, setRecord, showToast } = useApp()
  const [busy, setBusy] = useState(false)

  if (!record) {
    return (
      <p className="mt-3 rounded-lg border border-dashed border-slate-300 px-3 py-2 text-[11.5px] leading-relaxed text-slate-400">
        Run the pure-tone audiogram first — these measurements can then be
        attached to that patient&rsquo;s analysis and the interpretation re-run
        over everything collected.
      </p>
    )
  }
  if (!patch) return null

  const attach = async () => {
    if (busy) return
    setBusy(true)
    try {
      const merged = { ...record, [ear]: { ...(record[ear] || {}), ...patch } }
      const updated = await api.analyze(merged)
      setAnalysis(updated)
      setRecord(merged)
      showToast(`Attached to the ${ear} ear — the analysis now includes this measurement.`)
    } catch (e) {
      showToast(`Could not re-run the analysis: ${e.message}`, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-3 rounded-xl border border-teal-200 bg-teal-50/50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-teal-800">
            Attach to {analysis?.patient?.name ? `${analysis.patient.name}’s` : 'the patient’s'} {ear} ear
          </div>
          <div className="mt-0.5 text-[11.5px] leading-snug text-teal-900">{summary}</div>
        </div>
        <button type="button" onClick={attach} disabled={busy}
          className="rounded-lg bg-teal-600 px-3.5 py-1.5 text-[12.5px] font-semibold text-white transition hover:bg-teal-700 disabled:opacity-50">
          {busy ? 'Re-running analysis…' : 'Attach & re-analyse'}
        </button>
      </div>
      <p className="mt-1.5 text-[10.5px] leading-snug text-teal-700/80">
        Exactly the values above are recorded — attach only what was actually
        measured on this patient, not an example preset.
      </p>
    </div>
  )
}

// -------------------------------------------------------- tympanometry ----
function Tympanometry({ reference, onType }) {
  const { patient, showToast } = useApp()
  const [ear, setEar] = useState('right')
  // Age is not a label on this test, it is the test. It picks the normative
  // band — ear-canal volume 0.3–1.0 ml in a child against 0.6–2.0 in an adult,
  // static compliance 0.35–1.25 against 0.37–1.66 — and a 226 Hz probe is
  // refused under six months because the compliant infant canal can return a
  // normal-looking trace over a middle ear full of fluid (Baldwin 2006; BSA
  // 2024 §4.1).
  // Defaulting to 30 therefore judged every child's tympanogram against adult
  // norms, which reads a stiff paediatric ear as normal.
  const recorded = Number(patient?.age)
  const recordedAge = patient?.age == null || patient.age === '' || Number.isNaN(recorded)
    ? null : recorded
  const [ageYears, setAgeYears] = useState(recordedAge ?? 30)
  // Re-seed when the patient arrives or changes — this page is reachable
  // before the demographics are entered, and stale age is the whole bug.
  useEffect(() => { if (recordedAge != null) setAgeYears(recordedAge) }, [recordedAge])
  const [probeHz, setProbeHz] = useState(226)
  const [preset, setPreset] = useState(TYMP_PRESETS[0])
  // Reflexes start EMPTY, not prefilled. Example values in a field that can be
  // attached to a patient record are a trap, and the "include reflexes"
  // checkbox below existed only to defuse it. Blank fields need no defusing.
  const [ipsi, setIpsi] = useState('')
  const [contra, setContra] = useState('')
  // "Enter values" is the default: this page is for recording a patient, and
  // the examples are for learning the instrument. Opening on an example meant
  // every visit started with fabricated numbers on screen.
  const [mode, setMode] = useState('values')
  // Blank, for the same reason. The placeholders show the shape of a normal
  // trace without putting it in the record.
  const [manual, setManual] = useState({ ecv: '', pp: '', sc: '', grad: '' })
  //: Type-only entry, for a printout or referral letter that gives the letter
  //: and nothing else.
  const [recordedType, setRecordedType] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const trace = useMemo(() => buildTrace(preset), [preset])

  // Whether the clinician has actually entered anything in the current mode.
  // Nothing is sent, and no result is shown, until they have — an instrument
  // panel that interprets an empty form is interpreting nothing.
  const hasValues = mode === 'values'
    && ['pp', 'sc'].some((k) => manual[k] !== '')
  const reflexEntered = ipsi !== '' || contra !== ''
  const ready = mode === 'preset' || (mode === 'values' && hasValues)
    || (mode === 'type' && Boolean(recordedType))
    // Reflexes on their own are a result: absent reflexes with no tympanogram
    // still localise a lesion, and refusing to interpret them would discard a
    // measurement the clinic actually took.
    || (mode === 'values' && reflexEntered)

  useEffect(() => {
    if (!ready) { setResult(null); return }
    let cancelled = false
    setBusy(true)
    const reflexes = {}
    if (ipsi !== '') reflexes.ipsi = ipsi === 'absent' ? null : Number(ipsi)
    if (contra !== '') reflexes.contra = contra === 'absent' ? null : Number(contra)
    const num = (v) => (v === '' || v === null ? undefined : Number(v))
    const common = { ear, age_years: Number(ageYears),
                     probe_hz: Number(probeHz), reflexes }
    const body = mode === 'values'
      ? {
          ...common,
          peak_pressure: num(manual.pp), compliance: num(manual.sc),
          ecv: num(manual.ecv), gradient: num(manual.grad),
        }
      : mode === 'type'
        ? { ...common, recorded_type: recordedType }
        : { ...common, trace }
    api.tympanometry(body)
      .then((r) => { if (!cancelled) setResult(r) })
      .catch((e) => { if (!cancelled) showToast(e.message, 'error') })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [ear, ageYears, probeHz, trace, ipsi, contra, mode, manual, recordedType,
      ready, showToast])

  const norms = result?.curve?.normative
  const jerger = result?.tympanogram
  const offScale = Boolean(result?.curve?.off_scale)

  // Lifted so the type atlas below can highlight the row this ear landed on.
  useEffect(() => { onType?.(jerger?.type || null) }, [jerger?.type, onType])

  return (
    <Panel
      title="Tympanometry"
      tour="tympanogram"
      right={jerger && (
        <span className={`rounded-lg border px-2.5 py-1 text-[12px] font-semibold ${
          typeStyle(jerger)}`}>
          {jerger.label}{jerger.provisional ? ' (provisional)' : ''}
        </span>
      )}
    >
      <EntryModeTabs mode={mode} onMode={setMode}
        modes={['values', 'type', 'preset']}
        labels={{ values: 'Enter values', type: 'Type only',
                  preset: 'Example traces' }} />

      {mode === 'values' && (
        <div className="mt-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ['ecv', 'ECV', 'ml', '0.1', 'ear-canal volume', '1.0'],
              ['pp', 'PP', 'daPa', '5', 'peak pressure', '-20'],
              ['sc', 'SC', 'mmho', '0.05', 'static compliance', '0.85'],
              ['grad', 'GRAD', '', '0.01', 'gradient, 0–1', '0.55'],
            ].map(([key, label, unit, step, hint, eg]) => (
              <label key={key} className="text-[12px]">
                <span className="mb-1 block font-medium text-slate-600">
                  {label}{unit && <span className="ml-1 text-slate-400">({unit})</span>}
                </span>
                <input type="number" step={step} value={manual[key]}
                  placeholder={eg}
                  onChange={(e) => setManual({ ...manual, [key]: e.target.value })}
                  className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
                <span className="mt-0.5 block text-[10.5px] text-slate-400">{hint}</span>
              </label>
            ))}
          </div>
          {!hasValues ? (
            <p className="mt-2 rounded-lg border border-dashed border-slate-300 px-3 py-2 text-[12px] leading-relaxed text-slate-500">
              Enter at least the peak pressure and static compliance — the two
              the type is decided on. The canal volume splits Type B three ways,
              and the gradient catches an early effusion that peak height misses.
            </p>
          ) : (
            <Reveal className="mt-2" label="How the curve is drawn from these">
              <p className="text-[11.5px] leading-relaxed text-slate-500">
                The curve is modelled from these four values, and the gradient
                shapes it — a curve drawn from GRAD 0.30 measures back as 0.30.
                It is a drawing of the numbers, not a recorded sweep.
              </p>
            </Reveal>
          )}
        </div>
      )}

      {mode === 'type' && (
        <div className="mt-3">
          <span className="mb-1.5 block text-[12px] font-medium text-slate-600">
            Type as recorded
          </span>
          <div className="flex flex-wrap gap-1.5">
            {TYMP_TYPE_KEYS.map((t) => (
              <button key={t} type="button" aria-pressed={recordedType === t}
                onClick={() => setRecordedType(recordedType === t ? null : t)}
                className={`rounded-lg border px-3 py-1.5 text-[12.5px] transition ${
                  recordedType === t
                    ? 'border-teal-500 bg-teal-50 font-semibold text-teal-800 ring-1 ring-teal-300'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-teal-300'}`}>
                Type {t}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11.5px] leading-relaxed text-slate-500">
            For a printout or referral letter that gives the letter and nothing
            else. The type is most of what a tympanogram contributes to a
            differential — what it cannot give is listed with the result.
          </p>
        </div>
      )}

      {mode === 'preset' && (
        <div className="mt-3">
          <p className="rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-[11.5px] leading-relaxed text-amber-900">
            These are worked examples for learning the instrument, not this
            patient. Nothing here can be attached to a record.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
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
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
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
          {recordedAge != null && Number(ageYears) !== recordedAge && (
            <span className="mt-1 block text-[10.5px] leading-snug text-amber-700">
              Recorded age is {recordedAge}. These norms are not this patient's.
            </span>
          )}
          {recordedAge == null && (
            <span className="mt-1 block text-[10.5px] leading-snug text-slate-400">
              No patient recorded — adult norms assumed.
            </span>
          )}
        </label>
        <label className="text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">Probe</span>
          <select value={probeHz} onChange={(e) => setProbeHz(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]">
            <option value="226">226 Hz</option><option value="1000">1000 Hz</option>
          </select>
        </label>
      </div>

      {/* Reflexes are their own measurement, not two more boxes in the
          tympanogram row — and they are entered the way they are recorded:
          usually just present or absent, sometimes with a threshold. */}
      <ReflexEntry ipsi={ipsi} contra={contra} onIpsi={setIpsi} onContra={setContra} />

      {/* No curve in type-only mode: there is nothing measured to draw, and
          sketching a representative shape for the letter would be putting a
          measurement on screen that nobody took. */}
      {mode !== 'type' && (
      <div className="mt-4 h-64 w-full">
        <ResponsiveContainer>
          <LineChart data={result?.curve?.points || (mode === 'preset' ? trace : [])}
            margin={{ top: 8, right: 12, bottom: 24, left: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            {norms && norms.applicable !== false && norms.pressure?.length === 2 && (
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
              domain={offScale ? [0, result.curve.ceiling] : [0, 'auto']}
              allowDataOverflow
              label={{ value: 'Admittance (mmho)', angle: -90, position: 'insideLeft',
                fontSize: 11, fill: '#64748b' }} />
            {offScale && (
              <ReferenceLine y={result.curve.ceiling} stroke="#dc2626"
                strokeDasharray="4 4"
                label={{ value: 'instrument ceiling — no measurable peak',
                  position: 'insideTopRight', fontSize: 10, fill: '#dc2626' }} />
            )}
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }}
              formatter={(v) => [`${v} mmho`, 'Admittance']}
              labelFormatter={(l) => `${l} daPa`} />
            <Line type="monotone" dataKey="admittance" stroke="#0d9488" strokeWidth={2.2}
              dot={false} isAnimationActive={false} connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      )}

      {!ready && (
        <p className="mt-3 rounded-xl border border-dashed border-slate-300 px-3 py-6 text-center text-[12.5px] text-slate-400">
          {mode === 'type'
            ? 'Pick the type that was recorded.'
            : 'Enter the measured values to get a type and an interpretation.'}
        </p>
      )}

      {result && (
        <>
          {mode !== 'type' && (
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
          )}

          {result.measurements?.static_compliance_reference && (
            <p className="mt-1.5 text-[11px] leading-snug text-slate-500">
              Static compliance measured {result.measurements.static_compliance_reference}.
            </p>
          )}
          {result.not_typed && (
            <p className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
              {result.not_typed}
            </p>
          )}
          {(jerger?.caveats || []).map((c) => (
            <p key={c} className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
              {c}
            </p>
          ))}
          {result.infant_warning && (
            <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] leading-relaxed text-rose-900">
              {result.infant_warning}
            </p>
          )}
          {result.curve?.gradient_note && (
            <p className="mt-2 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-[12px] leading-relaxed text-slate-700">
              {result.curve.gradient_note}
            </p>
          )}
          {(result.flags || []).map((f) => (
            <p key={f} className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
              {f}
            </p>
          ))}

          {/* The type and its clinical meaning lead; the derivation — gradient,
              width, normative bands, citations — is evidence behind it. */}
          <ul className="mt-3 space-y-1.5 text-[12.5px] leading-relaxed text-slate-600">
            {result.interpretation.slice(0, 2).map((line, i) => <li key={i}>· {line}</li>)}
          </ul>
          {result.interpretation.length > 2 && (
            <Reveal className="mt-2"
              label={`${result.interpretation.length - 2} more on how this was read`}>
              <ul className="space-y-1.5 text-[12.5px] leading-relaxed text-slate-600">
                {result.interpretation.slice(2).map((line, i) => <li key={i}>· {line}</li>)}
              </ul>
            </Reveal>
          )}

          {norms && norms.applicable === false && (
            <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
              {norms.note || 'The 226 Hz normal ranges do not apply to this probe tone and age.'}
              {(norms.citations || []).length > 0 && ` ${norms.citations.join('; ')}.`}
            </p>
          )}
          {norms && norms.applicable !== false && norms.pressure?.length === 2 && (
            <Reveal className="mt-2.5" label="Normal ranges used">
              <p className="text-[11px] leading-relaxed text-slate-400">
                For the {norms.band} band — pressure {norms.pressure[0]} to{' '}
                {norms.pressure[1]} daPa, compliance {norms.compliance[0]}–{norms.compliance[1]} mmho,
                volume {norms.ecv[0]}–{norms.ecv[1]} cm³, width {norms.width[0]}–{norms.width[1]} daPa.
                {' '}{(norms.citations || []).join('; ')}.
              </p>
            </Reveal>
          )}
        </>
      )}

      {/* An example can be read but never filed. */}
      {result && mode === 'preset' && (
        <p className="mt-3 rounded-lg border border-dashed border-amber-300 bg-amber-50/60 px-3 py-2 text-[11.5px] leading-relaxed text-amber-900">
          This is the “{preset.label}” example, not a measurement — switch to
          Enter values or Type only to record this patient.
        </p>
      )}

      {result && mode !== 'preset' && result.probe_mode
        && result.probe_mode !== 'jerger' && (
        <p className="mt-3 rounded-lg border border-dashed border-slate-300 px-3 py-2 text-[11.5px] leading-relaxed text-slate-500">
          This result cannot be attached to the analysis: the test battery types a
          tympanogram on 226 Hz rules from its peak pressure, admittance and canal
          volume, and this {probeHz === '1000' || probeHz === 1000 ? '1000 Hz' : 'infant'} trace
          is read differently. Report it from this page.
        </p>
      )}

      {result && mode !== 'preset'
        && (!result.probe_mode || result.probe_mode === 'jerger') && (
        <AttachToAnalysis
          ear={ear}
          summary={
            (mode === 'type'
              ? `Type ${recordedType} as recorded — no values behind it`
              : `PP ${result.measurements.peak_pressure} daPa · `
                + `SC ${result.measurements.static_compliance} mmho · `
                + `ECV ${result.measurements.ecv} ml`
                + (jerger ? ` — Type ${jerger.type}` : ''))
            + (reflexEntered
              ? ` · reflexes ipsi ${ipsi === 'absent' ? 'absent' : `${ipsi} dB`}, contra ${contra === 'absent' ? 'absent' : `${contra} dB`}`
              : ' · no reflexes recorded')
          }
          patch={{
            // Only what this mode actually measured. Sending nulls for the
            // rest matters: it clears a value left over from a previous
            // attach rather than leaving a stale number in the record.
            ...(mode === 'type'
              ? { tymp_type: recordedType, tymp_pressure: null,
                  tymp_compliance: null, tymp_ecv: null }
              : { tymp_pressure: result.measurements.peak_pressure,
                  tymp_compliance: result.measurements.static_compliance,
                  tymp_ecv: result.measurements.ecv, tymp_type: null }),
            ...(reflexEntered ? {
              reflexes: {
                ipsi: ipsi === 'absent' || ipsi === '' ? null : Number(ipsi),
                contra: contra === 'absent' || contra === '' ? null : Number(contra),
              },
            } : {}),
          }}
        />
      )}
      {busy && !result && <p className="mt-2 text-[12px] text-slate-400">Analysing…</p>}
    </Panel>
  )
}

// ----------------------------------------------------------- reflexes ----
//
// A reflex is recorded three ways in practice, and all three have to be
// enterable: a threshold in dB HL, "absent at maximum output", or not tested
// at all. The difference between the last two is clinical, not clerical —
// absent reflexes behind a Type A trace point at otosclerosis, while untested
// reflexes point at nothing — so the control makes it impossible to confuse
// them: Absent is a button you press, blank means untested.
function ReflexEntry({ ipsi, contra, onIpsi, onContra }) {
  const row = (label, value, onChange, hint) => {
    const absent = value === 'absent'
    return (
      <div key={label} className="rounded-lg border border-slate-200 bg-white p-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] font-medium text-slate-600">{label}</span>
          <span className="text-[10.5px] text-slate-400">{hint}</span>
        </div>
        <div className="mt-1.5 flex items-center gap-1.5">
          <input type="number" step="5" min="0" max="125"
            value={absent ? '' : value} placeholder="dB HL"
            onChange={(e) => onChange(e.target.value)}
            className="w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-[13px] disabled:bg-slate-50"
            disabled={absent} />
          <button type="button" aria-pressed={absent}
            onClick={() => onChange(absent ? '' : 'absent')}
            className={`rounded-lg border px-2.5 py-1.5 text-[12px] transition ${
              absent
                ? 'border-rose-400 bg-rose-50 font-semibold text-rose-800'
                : 'border-slate-200 bg-white text-slate-600 hover:border-rose-300'}`}>
            Absent
          </button>
          {value !== '' && (
            <button type="button" onClick={() => onChange('')}
              className="text-[11.5px] text-slate-400 underline hover:text-slate-600">
              clear
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="mt-3">
      <span className="text-[12px] font-medium text-slate-600">
        Acoustic reflexes
        <span className="ml-1.5 text-[10.5px] font-normal text-slate-400">
          leave blank if not tested — blank and absent are different findings
        </span>
      </span>
      <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
        {row('Ipsilateral', ipsi, onIpsi, 'same ear')}
        {row('Contralateral', contra, onContra, 'opposite ear')}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ OAE ---
function Emissions({ reference }) {
  const { analysis, showToast } = useApp()
  const [ear, setEar] = useState('right')
  const [protocol, setProtocol] = useState('screening')
  const [preset, setPreset] = useState(OAE_PRESETS[1])
  const [mode, setMode] = useState('values')
  const [result, setResult] = useState(null)
  // The frequency set is the clinic's, not ours. An occupational programme
  // tests 3, 4 and 6 kHz; somebody chasing a noise notch wants 5 kHz, which
  // no preset offered. Scoring a clinic against frequencies it did not test —
  // or silently dropping the ones it added — produces a decision that does
  // not describe the test that was run.
  const [testFreqs, setTestFreqs] = useState(DEFAULT_OAE_FREQS)
  //: freq -> { amplitude, noise_floor } as typed. Strings, so a half-typed
  //: "-" or "1." does not become NaN mid-keystroke.
  const [entered, setEntered] = useState({})
  const [outcome, setOutcome] = useState(null)
  const [outcomeNote, setOutcomeNote] = useState('')
  //: For a custom set: how many must pass. Blank = all of them.
  const [required, setRequired] = useState('')

  const protocolFreqs = useMemo(() => {
    const spec = (reference?.protocols || []).find((p) => p.key === protocol)
    return spec?.freqs || []
  }, [reference, protocol])

  // Picking a published protocol sets the frequency set it is defined on —
  // that list IS part of the criterion. The clinician can still edit it
  // afterwards, which is exactly when the custom protocol earns its place.
  useEffect(() => {
    if (protocolFreqs.length) setTestFreqs(protocolFreqs)
  }, [protocolFreqs])

  const num = (v) => {
    if (v === '' || v === null || v === undefined) return null
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }

  const points = useMemo(() => {
    if (mode === 'preset') {
      return testFreqs.map((f) => ({ freq: f, ...preset.build(f) }))
    }
    if (mode !== 'values') return []
    // Only frequencies with BOTH an emission and a noise floor. One without
    // the other cannot be judged — the SNR needs both — and sending a
    // half-entered row would have it scored as an absent emission.
    return testFreqs
      .map((f) => ({ freq: f, amplitude: num(entered[f]?.amplitude),
                     noise_floor: num(entered[f]?.noise_floor) }))
      .filter((p) => p.amplitude !== null && p.noise_floor !== null)
  }, [mode, testFreqs, preset, entered])

  const partialRows = mode === 'values' && testFreqs.some((f) => {
    const a = num(entered[f]?.amplitude)
    const n = num(entered[f]?.noise_floor)
    return (a === null) !== (n === null)
  })

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

  const ready = mode === 'outcome' ? Boolean(outcome) : points.length > 0

  useEffect(() => {
    if (!ready) { setResult(null); return }
    let cancelled = false
    api.oae({
      ear, protocol, points, ac,
      ...(protocol === 'custom' && required !== ''
        ? { required: Number(required) } : {}),
      ...(mode === 'outcome'
        ? { recorded_outcome: outcome, outcome_note: outcomeNote,
            freqs: testFreqs }
        : {}),
    })
      .then((r) => { if (!cancelled) setResult(r) })
      .catch((e) => { if (!cancelled) showToast(e.message, 'error') })
    return () => { cancelled = true }
  }, [ear, protocol, points, ac, mode, outcome, outcomeNote, testFreqs,
      required, ready, showToast])

  const chartData = (result?.points || points).map((p) => ({
    name: p.freq >= 1000 ? `${p.freq / 1000}k` : `${p.freq}`,
    emission: p.amplitude,
    noise: p.noise_floor,
    verdict: p.verdict,
  }))

  const setCell = (freq, key, value) => setEntered((prev) => ({
    ...prev, [freq]: { ...(prev[freq] || {}), [key]: value },
  }))

  return (
    <Panel
      title="Otoacoustic emissions"
      tour="oae"
      right={result && (
        <span className={`rounded-lg border px-2.5 py-1 text-[12px] font-semibold uppercase ${
          OUTCOME_STYLE[result.outcome] || 'border-slate-300 bg-slate-50 text-slate-700'}`}>
          {result.outcome}
        </span>
      )}
    >
      <EntryModeTabs mode={mode} onMode={setMode}
        modes={['values', 'outcome', 'preset']} />

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
          {protocol !== 'custom'
            && protocolFreqs.length > 0
            && (testFreqs.length !== protocolFreqs.length
              || testFreqs.some((f, i) => f !== protocolFreqs[i])) && (
            <span className="mt-1 block text-[10.5px] leading-snug text-amber-700">
              This protocol is defined on {protocolFreqs.join(', ')} Hz. You have
              changed the set, so only its own frequencies are scored — switch
              to “As tested” to score what you actually measured.
            </span>
          )}
        </label>
      </div>

      <FrequencyEditor freqs={testFreqs} onChange={setTestFreqs}
        suggestions={[...(reference?.frequencies || DEFAULT_OAE_FREQS),
                      ...(reference?.extra_frequencies || [])]
          .filter((f, i, a) => a.indexOf(f) === i).sort((a, b) => a - b)}
        label={mode === 'outcome' ? 'Frequencies the screen covered'
          : 'Frequencies tested'} />

      {protocol === 'custom' && mode !== 'outcome' && (
        <label className="mt-2 block text-[12px]">
          <span className="mb-1 block font-medium text-slate-600">
            How many must pass
            <span className="ml-1 font-normal text-slate-400">
              (blank = all {testFreqs.length})
            </span>
          </span>
          <input type="number" min="0" max={testFreqs.length} value={required}
            onChange={(e) => setRequired(e.target.value)}
            placeholder={String(testFreqs.length)}
            className="w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
        </label>
      )}

      {mode === 'values' && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[340px] text-left text-[12px]">
            <thead>
              <tr className="text-[10.5px] uppercase tracking-wide text-slate-400">
                <th className="py-1 pr-3 font-medium">f2 (Hz)</th>
                <th className="py-1 pr-3 font-medium">Emission (dB SPL)</th>
                <th className="py-1 font-medium">Noise floor (dB SPL)</th>
              </tr>
            </thead>
            <tbody>
              {testFreqs.map((f) => (
                <tr key={f} className="border-t border-slate-100">
                  <td className="py-1.5 pr-3 font-mono text-slate-700">{f}</td>
                  <td className="py-1.5 pr-3">
                    <input type="number" step="0.5" placeholder="e.g. 11"
                      value={entered[f]?.amplitude ?? ''}
                      onChange={(e) => setCell(f, 'amplitude', e.target.value)}
                      className="w-24 rounded-lg border border-slate-300 px-2 py-1 text-[12.5px]" />
                  </td>
                  <td className="py-1.5">
                    <input type="number" step="0.5" placeholder="e.g. -13"
                      value={entered[f]?.noise_floor ?? ''}
                      onChange={(e) => setCell(f, 'noise_floor', e.target.value)}
                      className="w-24 rounded-lg border border-slate-300 px-2 py-1 text-[12.5px]" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {partialRows && (
            <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] leading-relaxed text-amber-900">
              A frequency needs both the emission and the noise floor to be
              judged — the signal-to-noise ratio is the whole criterion. Rows
              with only one of the two are left out rather than scored as an
              absent emission.
            </p>
          )}
          {points.length === 0 && (
            <p className="mt-2 rounded-lg border border-dashed border-slate-300 px-3 py-2 text-[12px] leading-relaxed text-slate-500">
              Enter the emission and noise floor for at least one frequency.
              Only have a PASS or REFER off the screener? Use “Pass / refer only”.
            </p>
          )}
        </div>
      )}

      {mode === 'outcome' && (
        <>
          <OutcomePicker value={outcome} onChange={setOutcome}
            note={outcomeNote} onNote={setOutcomeNote}
            label="Screening outcome as recorded" />
          {!outcome && (
            <p className="mt-2 text-[11.5px] leading-relaxed text-slate-500">
              How a newborn screener, a camp tablet or a referral letter
              actually reports it. Recorded faithfully — and it supports less
              than a full DP-gram, which the result spells out.
            </p>
          )}
        </>
      )}

      {mode === 'preset' && (
        <>
          <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-[11.5px] leading-relaxed text-amber-900">
            Worked examples for learning the test, not this patient. Nothing
            here can be attached to a record.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
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
        </>
      )}

      {mode !== 'outcome' && chartData.length > 0 && (
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
      )}

      {result?.available === false && result?.note && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
          {result.note}
        </p>
      )}

      {result?.available && (
        <>
          <p className="mt-3 text-[13px] font-medium text-slate-800">{result.headline}</p>
          <Reveal className="mt-1" label="The criterion behind that">
            <p className="text-[11.5px] leading-relaxed text-slate-500">
              {result.protocol.name}
              {result.protocol.required != null && result.protocol.freqs?.length > 0 && (
                <>: {result.protocol.required} of {result.protocol.freqs.length}{' '}
                  frequencies ({result.protocol.freqs.join(', ')} Hz) must reach{' '}
                  {result.protocol.snr} dB SNR</>
              )}
              . {result.protocol.note}
            </p>
          </Reveal>

          {/* An outcome-only record: say what it is, and what it is not. */}
          <OutcomeLimits limits={result.limits} />

          {result.points?.length > 0 && (
            <Collapsible title="Frequency by frequency" defaultOpen
              subtitle="SNR, verdict and the cochlear place each dropout maps to."
              badge={result.points.length}>
              <div className="overflow-x-auto">
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
                        <td className="py-1.5 pr-3 font-mono">
                          {p.freq}
                          {p.in_protocol === false && (
                            <span className="ml-1 text-[9.5px] uppercase text-slate-400"
                              title="Outside the chosen protocol, so not scored">
                              extra
                            </span>
                          )}
                        </td>
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
              <Reveal className="mt-2.5" label="Why each frequency got that verdict">
                <ul className="space-y-1 text-[11.5px] leading-relaxed text-slate-600">
                  {result.points.filter((p) => p.reason).map((p) => (
                    <li key={p.freq}>
                      <span className="font-mono text-slate-700">{p.freq} Hz</span>
                      {' — '}{p.reason}
                    </li>
                  ))}
                </ul>
              </Reveal>
            </Collapsible>
          )}

          {result.cochlear_profile && (
            <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[12.5px] leading-relaxed text-slate-700">
              <span className="font-semibold capitalize">{result.cochlear_profile.pattern}</span>
              {' — '}{result.cochlear_profile.summary}
            </p>
          )}

          {/* The headline and the cochlear summary already have their own
              places on screen; the list is what is left to say. */}
          {(() => {
            const rest = result.interpretation
              .filter((line) => line !== result.headline
                && line !== result.cochlear_profile?.summary)
            if (rest.length === 0) return null
            return (
              <Reveal className="mt-2.5"
                label={`${rest.length} further note${rest.length === 1 ? '' : 's'} on this recording`}>
                <ul className="space-y-1.5 text-[12.5px] leading-relaxed text-slate-600">
                  {rest.map((line, i) => <li key={i}>· {line}</li>)}
                </ul>
              </Reveal>
            )
          })()}

          {Object.keys(ac).length === 0 && mode !== 'outcome' && (
            <p className="mt-2 text-[11.5px] text-slate-400">
              No audiogram loaded, so absent emissions cannot be checked against the
              thresholds that would explain them.
            </p>
          )}

          {mode === 'preset' ? (
            <p className="mt-3 rounded-lg border border-dashed border-amber-300 bg-amber-50/60 px-3 py-2 text-[11.5px] leading-relaxed text-amber-900">
              This is the “{preset.label}” example — switch to Enter values or
              Pass / refer only to record this patient.
            </p>
          ) : (
            <AttachToAnalysis
              ear={ear}
              summary={mode === 'outcome'
                ? `Screening outcome ${String(outcome).toUpperCase()}`
                  + (testFreqs.length ? ` over ${testFreqs.join(', ')} Hz` : '')
                  + ' — no per-frequency levels'
                : `${points.length} DP-gram point${points.length === 1 ? '' : 's'} `
                  + `(${points.map((p) => p.freq).join(', ')} Hz) — `
                  + `outcome ${result.outcome}`}
              patch={mode === 'outcome'
                ? { oae: [], oae_outcome: outcome, oae_freqs: testFreqs }
                : { oae: points.map(({ freq, amplitude, noise_floor }) =>
                    ({ freq, amplitude, noise_floor })),
                    oae_outcome: null, oae_freqs: [] }}
            />
          )}
        </>
      )}

      {!ready && (
        <p className="mt-3 rounded-xl border border-dashed border-slate-300 px-3 py-6 text-center text-[12.5px] text-slate-400">
          {mode === 'outcome'
            ? 'Record the screening outcome above.'
            : 'Enter at least one frequency to get a result.'}
        </p>
      )}
    </Panel>
  )
}

export default function Immittance() {
  const [tympRef, setTympRef] = useState(null)
  const [oaeRef, setOaeRef] = useState(null)
  const [linkRef, setLinkRef] = useState(null)
  const [activeType, setActiveType] = useState(null)

  useEffect(() => {
    api.tympanometryReference().then(setTympRef).catch(() => {})
    api.oaeReference().then(setOaeRef).catch(() => {})
    api.linkageReference().then(setLinkRef).catch(() => {})
  }, [])

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">
          Immittance, emissions &amp; speech
        </h1>
        <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-slate-500">
          Tympanometry, otoacoustic emissions and speech audiometry — enter the
          values, or just the pass/refer if that is all the instrument printed.
          Each works on its own, without a pure-tone audiogram to attach it to.
        </p>
      </header>

      <div className="mt-5 space-y-5">
        <Tympanometry reference={tympRef} onType={setActiveType} />
        <Emissions reference={oaeRef} />
        <SpeechAudiometry />
      </div>

      {/* Each of the five types against the disease reference. A tympanogram
          is only worth running because it moves diseases on and off the
          differential, so the differential is what the table shows. */}
      {linkRef && (
        <div className="mt-5">
        <ReferenceSection
          title="What each tympanogram type means for the diagnosis"
          badge={`${linkRef.tympanogram_types.length} types`}
          subtitle="Every type with the conditions it supports and the ones it takes off the table — a Type A trace diagnoses nothing on its own, but it removes most of the conductive differential in one measurement.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-[12px]">
              <thead>
                <tr className="text-[10.5px] uppercase tracking-wide text-slate-400">
                  <th className="py-1.5 pr-3 font-medium">Type</th>
                  <th className="py-1.5 pr-3 font-medium text-emerald-600">Supports</th>
                  <th className="py-1.5 pr-3 font-medium text-rose-600">Argues against</th>
                  <th className="py-1.5 font-medium">Also consider</th>
                </tr>
              </thead>
              <tbody>
                {linkRef.tympanogram_types.map((t) => (
                  <tr key={t.type} className="border-t border-slate-100 align-top">
                    <td className="py-2 pr-3">
                      <div className="font-semibold text-slate-800">Type {t.type}</div>
                      <div className="mt-0.5 text-[11px] leading-snug text-slate-500">
                        {t.meaning}
                      </div>
                    </td>
                    <td className="py-2 pr-3 text-slate-700">
                      {t.supports.length
                        ? t.supports.join(' · ')
                        : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="py-2 pr-3 text-slate-700">
                      {t.argues_against.length
                        ? t.argues_against.join(' · ')
                        : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="py-2 text-slate-600">{t.also_consider.join(' · ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ReferenceSection>
        </div>
      )}

      {/* The atlas highlights the row this ear landed on, so it stays useful —
          but it is 8 generated curves of reference material, not this
          patient's result, and it opens closed. */}
      {tympRef && (
        <div className="mt-5">
          <ReferenceSection title="Tympanogram atlas — all eight types"
            badge={activeType ? `this ear: ${activeType}` : `${tympRef.types.length} curves`}
            subtitle="Every type with its generated curve and the criteria that define it. The row matching this ear is highlighted.">
            <TympanogramAtlas reference={tympRef} activeType={activeType} />
            <dl className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
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
          </ReferenceSection>
        </div>
      )}

      <StepNav stepKey="immittance" />
    </div>
  )
}
