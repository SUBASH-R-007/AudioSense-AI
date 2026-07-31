import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import { captureSvgAsPng } from '../lib/svgCapture.js'
import AudiogramChart, { buildChartData } from '../components/AudiogramChart.jsx'
import CochleaMap from '../components/CochleaMap.jsx'
import { speak, stopSpeaking, voiceAvailable } from '../lib/speech.js'

const Card = ({ title, children, badge }) => (
  <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
    <div className="flex items-center justify-between">
      <h3 className="text-[11.5px] font-semibold uppercase tracking-wider text-slate-400">{title}</h3>
      {badge}
    </div>
    <div className="mt-2">{children}</div>
  </div>
)

const PATTERN_OPTIONS = [
  ['flat', 'Flat'],
  ['sloping_high_frequency', 'Sloping (high-frequency)'],
  ['ski_slope', 'Ski-slope'],
  ['rising', 'Rising (low-frequency)'],
  ['noise_notch_4k', 'Noise notch (4 kHz)'],
  ['cookie_bite', 'Cookie-bite (mid-frequency)'],
  ['corner_audiogram', 'Corner audiogram'],
]

/** Clinician override — the disagreement is the training signal. */
function CorrectionControl({ analysis, ear, ml, showToast }) {
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState(ml.pattern)
  const [stats, setStats] = useState(null)
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    setSaving(true)
    try {
      const res = await api.feedback({
        ear,
        predicted: ml.pattern,
        confidence: ml.confidence,
        corrected: choice,
        thresholds: analysis.thresholds,
      })
      setStats(res)
      showToast(
        choice === ml.pattern
          ? 'Agreement recorded — thanks'
          : 'Correction logged for the next training run',
      )
      setOpen(false)
    } catch (e) {
      showToast(`Could not save: ${e.message}`, 'error')
    }
    setSaving(false)
  }

  if (!open) {
    return (
      <div className="flex items-center gap-2">
        <button onClick={() => setOpen(true)}
          className="text-[11.5px] font-medium text-slate-400 hover:text-teal-700">
          Disagree? Correct this label →
        </button>
        {stats && (
          <span className="text-[11px] text-slate-400">
            {stats.total} clinician review{stats.total === 1 ? '' : 's'} logged
          </span>
        )}
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-teal-200 bg-teal-50/50 p-2">
      <div className="text-[11.5px] font-semibold text-slate-700">
        Correct classification for the {ear} ear
      </div>
      <select value={choice} onChange={(e) => setChoice(e.target.value)}
        className="mt-1.5 w-full rounded-md border border-slate-300 px-2 py-1.5 text-[12px]">
        {PATTERN_OPTIONS.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
      <div className="mt-2 flex gap-2">
        <button onClick={submit} disabled={saving}
          className="rounded-md bg-teal-600 px-3 py-1.5 text-[11.5px] font-semibold text-white hover:bg-teal-700 disabled:opacity-50">
          {saving ? 'Saving…' : 'Submit'}
        </button>
        <button onClick={() => setOpen(false)}
          className="rounded-md px-2 py-1.5 text-[11.5px] font-medium text-slate-500 hover:bg-slate-100">
          Cancel
        </button>
      </div>
    </div>
  )
}

const EarRow = ({ side, color, children }) => (
  <div className="flex items-start gap-2 py-1">
    <span className={`mt-0.5 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${color}`}>{side}</span>
    <div className="text-[13.5px] leading-snug text-slate-700">{children}</div>
  </div>
)

export default function Dashboard() {
  const { analysis, showToast } = useApp()
  const [bundle, setBundle] = useState(null)
  const [loadingReport, setLoadingReport] = useState(false)
  const [tab, setTab] = useState('report')
  const [lang, setLang] = useState('english')
  const [showBanana, setShowBanana] = useState(false)
  const [showPhonemes, setShowPhonemes] = useState(false)
  const [pdfBusy, setPdfBusy] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [cochleaEar, setCochleaEar] = useState('right')
  const [handout, setHandout] = useState(null)
  const [handoutBusy, setHandoutBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedId, setSavedId] = useState(null)
  const [referralBusy, setReferralBusy] = useState(false)
  const chartRef = useRef(null)

  useEffect(() => () => stopSpeaking(), [])

  useEffect(() => {
    if (!analysis) return
    setLoadingReport(true)
    api.report(analysis)
      .then((b) => {
        setBundle(b)
        if (b.fallback_used) showToast(`AI provider unavailable — offline engine used (${b.fallback_reason || ''})`, 'warn')
      })
      .catch((e) => showToast(`Report failed: ${e.message}`, 'error'))
      .finally(() => setLoadingReport(false))
  }, [analysis, showToast])

  const chartData = useMemo(
    () => (analysis ? buildChartData(analysis.thresholds, analysis.ml) : []),
    [analysis],
  )

  if (!analysis) {
    return (
      <div className="mx-auto mt-24 max-w-md text-center">
        <div className="text-4xl">📊</div>
        <h2 className="mt-3 text-lg font-semibold">No analysis yet</h2>
        <p className="mt-1 text-sm text-slate-500">Run a test first — or load a demo case in seconds.</p>
        <Link to="/new-test" className="mt-4 inline-block rounded-lg bg-teal-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-teal-700">
          Go to New Test
        </Link>
      </div>
    )
  }

  const { patient, rules, ml, phonemes } = analysis
  const disability = rules.disability
  const betterPhonemes = phonemes?.better || phonemes?.right
  const sii = analysis.sii?.better || analysis.sii?.right || analysis.sii?.left

  const readAloud = () => {
    if (speaking) { stopSpeaking(); setSpeaking(false); return }
    const sheet = bundle?.counseling?.[lang]
    if (!sheet) return
    const res = speak([...sheet.summary, ...sheet.tips], lang, {
      onEnd: () => setSpeaking(false),
    })
    if (!res.ok) showToast(res.reason, 'warn')
    else setSpeaking(true)
  }

  const saveVisit = async () => {
    setSaving(true)
    try {
      const res = await api.saveVisit(analysis)
      if (res.saved) {
        setSavedId(res.patient_id)
        showToast('Visit saved to the patient record')
      } else {
        showToast(res.reason || 'Could not save', 'warn')
      }
    } catch (e) {
      showToast(`Save failed: ${e.message}`, 'error')
    }
    setSaving(false)
  }

  const downloadReferral = async () => {
    setReferralBusy(true)
    try {
      const blob = await api.referral({ patient, analysis })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Referral_${(patient.name || 'patient').replace(/\s+/g, '_')}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      showToast(`Referral failed: ${e.message}`, 'error')
    }
    setReferralBusy(false)
  }

  const makeHandout = async () => {
    setHandoutBusy(true)
    try {
      setHandout(await api.handout({
        patient, analysis, counseling: bundle?.counseling,
      }))
    } catch (e) {
      showToast(`Could not create handout: ${e.message}`, 'error')
    }
    setHandoutBusy(false)
  }

  const downloadPdf = async () => {
    setPdfBusy(true)
    try {
      const png = await captureSvgAsPng(chartRef.current)
      const blob = await api.pdf({
        patient, analysis, report_bundle: bundle, chart_png_b64: png,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `AudioSense_${(patient.name || 'report').replace(/\s+/g, '_')}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      showToast(`PDF failed: ${e.message}`, 'error')
    }
    setPdfBusy(false)
  }

  const Toggle = ({ on, set, children }) => (
    <button onClick={() => set(!on)}
      className={`rounded-full px-3 py-1 text-[12px] font-medium transition ${
        on ? 'bg-teal-600 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
      }`}>{children}</button>
  )

  return (
    <div className="mx-auto max-w-6xl">
      {/* safety alerts — these outrank everything else on the page */}
      {analysis.safety?.alerts?.length > 0 && (
        <div className="mb-4 space-y-2">
          {analysis.safety.alerts.map((a, i) => {
            const style = {
              emergency: 'border-rose-300 bg-rose-50 text-rose-900',
              urgent: 'border-orange-300 bg-orange-50 text-orange-900',
              validity: 'border-amber-300 bg-amber-50 text-amber-900',
              info: 'border-slate-200 bg-slate-50 text-slate-700',
            }[a.level]
            const badge = {
              emergency: 'bg-rose-600', urgent: 'bg-orange-500',
              validity: 'bg-amber-500', info: 'bg-slate-400',
            }[a.level]
            return (
              <div key={i} className={`rounded-xl border px-4 py-3 ${style} ${
                a.level === 'emergency' ? 'animate-pulse-soft shadow-md shadow-rose-200' : ''}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white ${badge}`}>
                    {a.level === 'emergency' ? '⚠ emergency' : a.level}
                  </span>
                  <span className="text-[13.5px] font-semibold">{a.title}</span>
                  {a.ear && (
                    <span className="rounded bg-white/70 px-1.5 py-0.5 text-[10.5px] font-bold uppercase">
                      {a.ear} ear
                    </span>
                  )}
                </div>
                <div className="mt-1 text-[13px] leading-snug">{a.detail}</div>
                {a.action && (
                  <div className="mt-1 text-[13px] font-semibold">→ {a.action}</div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{patient.name || 'Unnamed patient'}</h1>
          <p className="mt-0.5 text-[13px] text-slate-500">
            {patient.age} y · {patient.sex} · {patient.occupation || 'occupation n/a'} · tested {patient.test_date || '—'}
          </p>
          {analysis.triage && (
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <span className={`rounded-md px-2 py-0.5 text-[10.5px] font-bold uppercase ${
                analysis.triage.level === 'critical' ? 'bg-rose-600 text-white'
                : analysis.triage.level === 'urgent' ? 'bg-orange-500 text-white'
                : analysis.triage.level === 'review' ? 'bg-amber-400 text-amber-950'
                : 'bg-emerald-100 text-emerald-700'}`}>
                {analysis.triage.label}
              </span>
              <span className="text-[12px] text-slate-500">
                {analysis.triage.auto_releasable
                  ? 'draft can be released'
                  : `audiologist review required · ${analysis.triage.sla}`}
              </span>
              {analysis.timing && (
                <span className="text-[11.5px] text-slate-400">
                  interpreted in {analysis.timing.interpretation_ms} ms
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <Link to="/simulator"
            className="rounded-lg border border-slate-300 px-4 py-2 text-[13px] font-semibold text-slate-700 transition hover:border-teal-400 hover:text-teal-700">
            🎧 Hear as this patient
          </Link>
          <button onClick={saveVisit} disabled={saving}
            className="rounded-lg border border-slate-300 px-4 py-2 text-[13px] font-semibold text-slate-700 transition hover:border-teal-400 hover:text-teal-700 disabled:opacity-40">
            {saving ? 'Saving…' : savedId ? '✓ Saved' : '💾 Save visit'}
          </button>
          {analysis.safety?.has_urgent && (
            <button onClick={downloadReferral} disabled={referralBusy}
              className="rounded-lg bg-rose-600 px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-rose-700 disabled:opacity-40">
              {referralBusy ? 'Building…' : '📄 ENT Referral'}
            </button>
          )}
          <button onClick={downloadPdf} disabled={pdfBusy || !bundle}
            className="rounded-lg bg-slate-900 px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-slate-700 disabled:opacity-40">
            {pdfBusy ? 'Building…' : '⬇ PDF Report'}
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        {/* chart */}
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm xl:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">Clinical Audiogram</h2>
            <div className="flex gap-1.5">
              <Toggle on={showBanana} set={setShowBanana}>Speech banana</Toggle>
              <Toggle on={showPhonemes} set={setShowPhonemes}>Phonemes</Toggle>
            </div>
          </div>
          <div ref={chartRef} className="mt-2">
            <AudiogramChart
              data={chartData}
              phonemes={betterPhonemes?.phonemes}
              showBanana={showBanana}
              showPhonemes={showPhonemes}
              showGlow
            />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-slate-500">
            <span><span className="font-bold text-red-600">O / [</span> right AC / BC</span>
            <span><span className="font-bold text-blue-600">X / ]</span> left AC / BC</span>
            <span className="text-teal-600">⬤ teal glow = regions driving the AI classification</span>
            {showPhonemes && <span className="text-red-600">red phonemes = inaudible</span>}
          </div>
        </div>

        {/* side cards */}
        <div className="space-y-4">
          <Card title="AI Pattern Classification"
            badge={ml?.right?.ood || ml?.left?.ood ? (
              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold uppercase text-rose-700">
                atypical — review
              </span>
            ) : null}>
            {['right', 'left'].map((side) => {
              const m = ml?.[side]
              if (!m) return <EarRow key={side} side={side[0]} color={side === 'right' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}>—</EarRow>
              return (
                <EarRow key={side} side={side[0].toUpperCase()}
                  color={side === 'right' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}>
                  <b>{m.pattern_label}</b>
                  <div className="mt-1 flex items-center gap-2">
                    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-teal-500" style={{ width: `${m.confidence * 100}%` }} />
                    </div>
                    <span className="text-[11.5px] text-slate-500">{Math.round(m.confidence * 100)}%</span>
                  </div>
                  {m.ood && <div className="mt-1 text-[11.5px] font-medium text-rose-600">{m.ood_message}</div>}
                </EarRow>
              )
            })}

            {/* why the model said this — counterfactuals + case support */}
            {(() => {
              const m = ml?.[cochleaEar] || ml?.right || ml?.left
              if (!m) return null
              return (
                <details className="mt-2 border-t border-slate-100 pt-2">
                  <summary className="cursor-pointer text-[12px] font-medium text-teal-700">
                    Why this classification?
                  </summary>
                  <div className="mt-2 space-y-2">
                    {m.counterfactuals?.length > 0 ? (
                      <ul className="space-y-1">
                        {m.counterfactuals.map((c, i) => (
                          <li key={i} className="text-[12px] leading-snug text-slate-600">
                            <span className="font-semibold text-slate-800">{c.freq} Hz</span>{' '}
                            {c.delta_db > 0 ? '+' : ''}{c.delta_db} dB → {c.new_label}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-[12px] leading-snug text-slate-600">
                        {m.counterfactual_note}
                      </p>
                    )}
                    {m.similar_cases && (
                      <div className="rounded-lg bg-slate-50 p-2">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
                            <div className="h-full rounded-full bg-teal-500"
                              style={{ width: `${m.similar_cases.agreement_pct}%` }} />
                          </div>
                          <span className="text-[11px] font-semibold text-slate-600">
                            {m.similar_cases.agree}/{m.similar_cases.k}
                          </span>
                        </div>
                        <p className="mt-1 text-[11.5px] leading-snug text-slate-500">
                          {m.similar_cases.text}
                          {m.similar_cases.dissenting_display &&
                            ` Closest alternative: ${m.similar_cases.dissenting_display}.`}
                        </p>
                      </div>
                    )}
                    <CorrectionControl analysis={analysis} ear={cochleaEar} ml={m}
                      showToast={showToast} />
                  </div>
                </details>
              )
            })()}
          </Card>

          <Card title="Degree (WHO 2021)">
            {['right', 'left'].map((side) => {
              const g = rules[side]?.who_grade
              return (
                <EarRow key={side} side={side[0].toUpperCase()}
                  color={side === 'right' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}>
                  {g ? <><b>{g.grade}</b> <span className="text-slate-400">· PTA {g.pta} dB</span></> : 'not assessable'}
                </EarRow>
              )
            })}
          </Card>

          <Card title="Type">
            {['right', 'left'].map((side) => {
              const ear = rules[side]
              return (
                <EarRow key={side} side={side[0].toUpperCase()}
                  color={side === 'right' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}>
                  <b>{ear.type}</b>
                  {ear.abg && <span className="text-slate-400"> · ABG {ear.abg.value} dB</span>}
                  {ear.provisional && (
                    <div className="mt-0.5 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10.5px] font-semibold text-amber-700">
                      provisional — BC incomplete
                    </div>
                  )}
                </EarRow>
              )
            })}
          </Card>

          {sii && (
            <Card title="Speech Intelligibility Index"
              badge={<span className="text-[10px] font-medium text-slate-400">better ear</span>}>
              <div className="flex items-end gap-3">
                <div>
                  <div className="text-2xl font-bold text-slate-900">
                    {sii.quiet.percent}<span className="text-base font-semibold text-slate-400">%</span>
                  </div>
                  <div className="text-[11px] font-medium text-slate-500">in quiet</div>
                </div>
                {sii.noise && (
                  <div>
                    <div className="text-xl font-bold text-amber-600">
                      {sii.noise.percent}<span className="text-sm font-semibold text-amber-400">%</span>
                    </div>
                    <div className="text-[11px] font-medium text-slate-500">in noise</div>
                  </div>
                )}
                {sii.aided_quiet && sii.aided_gain_quiet > 0 && (
                  <div className="ml-auto text-right">
                    <div className="text-xl font-bold text-emerald-600">
                      {sii.aided_quiet.percent}<span className="text-sm font-semibold text-emerald-400">%</span>
                    </div>
                    <div className="text-[11px] font-medium text-emerald-600">aided ↑{sii.aided_gain_quiet}</div>
                  </div>
                )}
              </div>
              <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="bg-teal-500" style={{ width: `${sii.quiet.percent}%` }} />
                {sii.aided_quiet && (
                  <div className="bg-emerald-300"
                    style={{ width: `${Math.max(0, sii.aided_quiet.percent - sii.quiet.percent)}%` }} />
                )}
              </div>
              <p className="mt-2 text-[12px] leading-snug text-slate-600">
                {sii.quiet.descriptor}.
              </p>
              <p className="mt-1 text-[10.5px] leading-snug text-slate-400">
                Share of speech cues audible (ANSI S3.5-style). {sii.caveat}
              </p>
            </Card>
          )}

          <Card title="Cochlear damage map"
            badge={
              <div className="flex rounded-lg bg-slate-100 p-0.5">
                {['right', 'left'].map((e) => (
                  <button key={e} onClick={() => setCochleaEar(e)}
                    className={`rounded-md px-2 py-0.5 text-[10.5px] font-semibold capitalize transition ${
                      cochleaEar === e
                        ? e === 'right' ? 'bg-white text-red-600 shadow-sm' : 'bg-white text-blue-600 shadow-sm'
                        : 'text-slate-500'
                    }`}>{e}</button>
                ))}
              </div>
            }>
            <CochleaMap thresholds={analysis.thresholds} ear={cochleaEar} />
            <p className="mt-1 text-[10.5px] leading-snug text-slate-400">
              Greenwood frequency-place map: high frequencies sit at the base, which
              noise and ageing damage first.
            </p>
          </Card>

          <Card title="Disability (RPwD Act 2016)"
            badge={disability?.benchmark_disability ? (
              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold uppercase text-rose-700">benchmark ≥40%</span>
            ) : null}>
            {disability ? (
              <>
                <div className="text-2xl font-bold text-slate-900">
                  {disability.binaural_pct}<span className="text-base font-semibold text-slate-400">%</span>
                  <span className="ml-2 text-[12px] font-medium text-slate-500">binaural hearing disability</span>
                </div>
                <details className="mt-2 text-[12.5px] text-slate-600">
                  <summary className="cursor-pointer font-medium text-teal-700">Show formula steps</summary>
                  <div className="mt-1.5 space-y-1 rounded-lg bg-slate-50 p-2.5 font-mono text-[11.5px]">
                    <div>R: {disability.right.formula}</div>
                    <div>L: {disability.left.formula}</div>
                    <div>Binaural: {disability.binaural_formula}</div>
                    <div className="text-slate-400">{disability.benchmark_note}</div>
                  </div>
                </details>
              </>
            ) : <span className="text-[13px] text-slate-500">Not computable — PTA incomplete.</span>}
          </Card>
        </div>
      </div>

      {/* cross-modal test battery */}
      {analysis.battery?.tests_run > 1 && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Test battery — do the tests agree?
            </h2>
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold uppercase ${
              analysis.battery.has_contradictions
                ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-700'
            }`}>
              {analysis.battery.has_contradictions
                ? `${analysis.battery.contradiction_count} disagreement${analysis.battery.contradiction_count === 1 ? '' : 's'}`
                : 'all agree'}
            </span>
          </div>
          <p className="mt-1 text-[14px] font-semibold text-slate-800">
            {analysis.battery.headline}
          </p>

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {['right', 'left'].map((side) => {
              const ear = analysis.battery[side]
              const imm = analysis.immittance?.[side]
              const oaeEar = analysis.oae?.[side]
              if (!ear) return null
              return (
                <div key={side} className="rounded-xl border border-slate-200 p-3">
                  <div className={`text-[12px] font-bold uppercase ${
                    side === 'right' ? 'text-red-600' : 'text-blue-600'}`}>{side} ear</div>

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {imm?.tympanogram && (
                      <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700"
                        title={imm.tympanogram.interpretation}>
                        Tymp {imm.tympanogram.type}
                      </span>
                    )}
                    {imm?.reflexes && (
                      <span className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                        imm.reflexes.pattern === 'present' ? 'bg-emerald-100 text-emerald-700'
                          : imm.reflexes.pattern === 'absent' ? 'bg-rose-100 text-rose-700'
                          : 'bg-amber-100 text-amber-700'
                      }`}>Reflexes {imm.reflexes.pattern}</span>
                    )}
                    {oaeEar && (
                      <span className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                        oaeEar.all_present ? 'bg-emerald-100 text-emerald-700'
                          : oaeEar.all_absent ? 'bg-rose-100 text-rose-700'
                          : 'bg-amber-100 text-amber-700'
                      }`}>
                        OAE {oaeEar.all_present ? 'present'
                          : oaeEar.all_absent ? 'absent'
                          : `absent at ${oaeEar.absent_freqs.join('/')} Hz`}
                      </span>
                    )}
                  </div>

                  {ear.confirmations.map((c, i) => (
                    <div key={`c${i}`} className={`mt-2 rounded-lg p-2 ${
                      c.priority ? 'bg-amber-50 ring-1 ring-amber-300' : 'bg-emerald-50'}`}>
                      <div className="text-[12.5px] font-semibold text-slate-800">
                        {c.priority ? '⚠ ' : '✓ '}{c.title}
                      </div>
                      <div className="mt-0.5 text-[12px] leading-snug text-slate-600">{c.detail}</div>
                    </div>
                  ))}
                  {ear.contradictions.map((c, i) => (
                    <div key={`x${i}`} className="mt-2 rounded-lg bg-amber-50 p-2">
                      <div className="text-[12.5px] font-semibold text-amber-900">⚠ {c.title}</div>
                      <div className="mt-0.5 text-[12px] leading-snug text-slate-600">{c.detail}</div>
                      {c.action && (
                        <div className="mt-1 text-[12px] font-medium text-amber-800">→ {c.action}</div>
                      )}
                    </div>
                  ))}
                  {!ear.confirmations.length && !ear.contradictions.length && (
                    <div className="mt-2 text-[12px] text-slate-400">
                      No cross-checks available for this ear.
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {analysis.fitting?.right || analysis.fitting?.left ? (
            <div className="mt-4 rounded-xl border border-slate-200 p-3">
              <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
                Hearing-aid verification
              </div>
              {['right', 'left'].map((side) => {
                const f = analysis.fitting[side]
                if (!f) return null
                return (
                  <div key={side} className="mt-1.5 text-[12.5px] text-slate-700">
                    <b className={side === 'right' ? 'text-red-600' : 'text-blue-600'}>
                      {side}:
                    </b>{' '}
                    {f.summary}
                    {f.action && <span className="font-medium text-amber-700"> {f.action}</span>}
                  </div>
                )
              })}
            </div>
          ) : null}
        </div>
      )}

      {/* report + counseling */}
      <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <div className="flex gap-1">
            {[['report', 'Clinical Report'], ['counseling', 'Patient Counseling']].map(([t, l]) => (
              <button key={t} onClick={() => setTab(t)}
                className={`rounded-lg px-3.5 py-1.5 text-[13px] font-semibold transition ${
                  tab === t ? 'bg-teal-50 text-teal-700' : 'text-slate-500 hover:text-slate-800'
                }`}>{l}</button>
            ))}
          </div>
          {bundle && (
            <div className="flex items-center gap-2 text-[11.5px]">
              <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-500">
                engine: {bundle.engine}
              </span>
              {bundle.verified && (
                <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 font-semibold text-emerald-700"
                  title={`${bundle.verification?.method} — ${(bundle.verification?.checks || bundle.verification?.issues_found || []).length} checks`}>
                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
                  verified
                </span>
              )}
            </div>
          )}
        </div>

        <div className="px-5 py-4">
          {loadingReport && <div className="py-8 text-center text-sm text-slate-400">Generating report…</div>}

          {bundle && tab === 'report' && (
            <div className="grid gap-5 md:grid-cols-2">
              {[['Findings', 'findings'], ['Pattern & Likely Etiologies', 'pattern_etiology'],
                ['Degree & Type', 'degree_type'], ['Disability Assessment', 'disability'],
                ['Functional Impact', 'functional_impact'], ['Recommendations', 'recommendations']]
                .map(([title, key]) => (
                  <div key={key}>
                    <h3 className="text-[12px] font-semibold uppercase tracking-wider text-teal-700">{title}</h3>
                    <ul className="mt-1.5 space-y-1.5">
                      {(bundle.report[key] || []).map((line, i) => (
                        <li key={i} className="flex gap-2 text-[13.5px] leading-relaxed text-slate-700">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-300" />{line}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              <div className="md:col-span-2 rounded-lg bg-slate-50 px-3 py-2 text-[12px] italic text-slate-500">
                {bundle.report.disclaimer}
              </div>
            </div>
          )}

          {bundle && tab === 'counseling' && (
            <div>
              <div className="flex flex-wrap gap-1.5">
                {Object.keys(bundle.counseling.languages || { english: 1 }).map((l) => (
                  <button key={l} onClick={() => setLang(l)}
                    className={`rounded-full px-3.5 py-1 text-[12.5px] font-semibold transition ${
                      lang === l ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}>{bundle.counseling[l]?.native || l}</button>
                ))}
                <button onClick={readAloud}
                  className={`ml-auto flex items-center gap-1.5 rounded-full px-3 py-1 text-[12.5px] font-semibold transition ${
                    speaking ? 'bg-rose-100 text-rose-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                  title="Read this sheet aloud">
                  {speaking ? '■ Stop' : '🔊 Read aloud'}
                  {lang !== 'english' && !voiceAvailable(bundle.counseling[lang]?.tts) && (
                    <span className="text-[10px] font-normal text-amber-600">no voice</span>
                  )}
                </button>
                <button onClick={makeHandout} disabled={handoutBusy}
                  className="flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-[12.5px] font-semibold text-slate-600 transition hover:bg-slate-200 disabled:opacity-50">
                  {handoutBusy ? 'Creating…' : '📱 Patient QR'}
                </button>
                <span className="self-center text-[11px] text-slate-400">
                  {bundle.counseling.reading_level} reading level
                </span>
              </div>
              {handout && (
                <div className="mt-3 flex items-center gap-4 rounded-xl border border-teal-200 bg-teal-50/50 p-3">
                  <img src={handout.qr_url} alt="QR code for the patient handout"
                    className="h-28 w-28 rounded-lg bg-white p-1" />
                  <div>
                    <div className="text-[13px] font-semibold text-slate-800">
                      Patient handout ready
                    </div>
                    <p className="mt-0.5 max-w-md text-[12px] leading-snug text-slate-600">
                      The patient scans this to open their own counseling sheet — in
                      every language — on their phone, to keep and to show family.
                      Works on the clinic network with no internet.
                    </p>
                    <a href={handout.url} target="_blank" rel="noreferrer"
                      className="mt-1 inline-block text-[11.5px] font-medium text-teal-700 underline">
                      open the handout
                    </a>
                  </div>
                </div>
              )}
              <div className="mt-3">
                <h3 className="text-[15px] font-semibold text-slate-800">
                  {bundle.counseling[lang].heading}
                </h3>
                <ul className="mt-2 space-y-2">
                  {bundle.counseling[lang].summary.map((s, i) => (
                    <li key={i} className="text-[14px] leading-relaxed text-slate-700">{s}</li>
                  ))}
                </ul>
                <h4 className="mt-4 text-[12px] font-semibold uppercase tracking-wider text-teal-700">
                  {lang === 'tamil' ? 'நடைமுறை குறிப்புகள்' : 'Practical tips'}
                </h4>
                <ul className="mt-1.5 space-y-1.5">
                  {bundle.counseling[lang].tips.map((s, i) => (
                    <li key={i} className="flex gap-2 text-[13.5px] leading-relaxed text-slate-700">
                      <span className="text-teal-500">✓</span>{s}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
