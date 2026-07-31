import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, FREQ_LABELS } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import { SCREEN_FREQS, Staircase, ToneAudiometer } from '../audio/toneAudiometer.js'
import { BayesianThreshold, ReliabilityMonitor } from '../audio/bayesianThreshold.js'

const EARS = ['right', 'left']
const STEPS = EARS.flatMap((ear) => SCREEN_FREQS.map((freq) => ({ ear, freq })))

export default function Screening() {
  const navigate = useNavigate()
  const { setAnalysis, showToast } = useApp()
  const audioRef = useRef(null)
  const stairRef = useRef(null)
  const [stage, setStage] = useState('intro') // intro | calibrate | testing | done
  const [volume, setVolume] = useState(0.05)
  const [stepIdx, setStepIdx] = useState(0)
  const [results, setResults] = useState({ right: {}, left: {} })
  const [presenting, setPresenting] = useState(false)
  const [awaiting, setAwaiting] = useState(false)
  const [level, setLevel] = useState(40)
  const [analyzing, setAnalyzing] = useState(false)
  const [method, setMethod] = useState('bayesian') // 'bayesian' | 'staircase'
  const [posterior, setPosterior] = useState(null)
  const [ci, setCi] = useState(null)
  const [isCatch, setIsCatch] = useState(false)
  const [reliability, setReliability] = useState(null)
  const relRef = useRef(null)
  const [intervals, setIntervals] = useState({ right: {}, left: {} })
  const [patient, setPatient] = useState({
    name: '', age: 30, sex: 'other', occupation: '',
    test_date: new Date().toISOString().slice(0, 10),
  })

  const tone = () => {
    if (!audioRef.current) audioRef.current = new ToneAudiometer()
    return audioRef.current
  }

  useEffect(() => () => audioRef.current?.dispose(), [])

  const step = STEPS[stepIdx]

  const present = useCallback(async () => {
    if (!step || presenting) return
    setPresenting(true)
    setAwaiting(false)
    const est = stairRef.current
    const lvl = method === 'bayesian' ? est.nextLevel() : est.level
    setLevel(lvl)

    // Silent catch trial: present nothing and see whether they respond anyway.
    const doCatch = relRef.current.shouldCatch()
    setIsCatch(doCatch)
    if (doCatch) {
      await new Promise((r) => setTimeout(r, 900))
    } else {
      await tone().playTone(step.freq, lvl, step.ear)
    }
    setPresenting(false)
    setAwaiting(true)
  }, [step, presenting, method])

  const newEstimator = () =>
    method === 'bayesian' ? new BayesianThreshold(-10, 90, 30) : new Staircase(40)

  const startTest = () => {
    tone().stopCalibrationTone()
    relRef.current = new ReliabilityMonitor()
    stairRef.current = newEstimator()
    setLevel(40)
    setStepIdx(0)
    setResults({ right: {}, left: {} })
    setIntervals({ right: {}, left: {} })
    setPosterior(null)
    setCi(null)
    setReliability(null)
    setStage('testing')
  }

  useEffect(() => {
    if (stage === 'testing' && stairRef.current && !presenting && !awaiting) {
      const t = setTimeout(present, 500)
      return () => clearTimeout(t)
    }
  }, [stage, stepIdx, presenting, awaiting, present])

  const respond = (heard) => {
    if (!awaiting || !stairRef.current) return
    setAwaiting(false)

    // A catch trial measures the patient, not the threshold — never let it
    // contaminate the estimate.
    if (isCatch) {
      relRef.current.record(heard)
      setReliability(relRef.current.summary())
      setIsCatch(false)
      return
    }

    const est = stairRef.current
    if (method === 'bayesian') {
      const state = est.record(level, heard)
      setCi(state.ci)
      setPosterior(est.distribution())
      if (!est.done) return
      const s = est.summary()
      setResults((r) => ({ ...r, [step.ear]: { ...r[step.ear], [step.freq]: s.threshold } }))
      setIntervals((iv) => ({ ...iv, [step.ear]: { ...iv[step.ear], [step.freq]: s } }))
    } else {
      const threshold = est.record(heard)
      setLevel(est.level)
      if (threshold === null) return
      setResults((r) => ({ ...r, [step.ear]: { ...r[step.ear], [step.freq]: threshold } }))
    }

    const next = stepIdx + 1
    stairRef.current = newEstimator()
    setPosterior(null)
    setCi(null)
    setLevel(40)
    if (next >= STEPS.length) {
      setReliability(relRef.current.summary())
      setStage('done')
    } else {
      setStepIdx(next)
    }
  }

  // Spacebar = "I hear it" (the standard patient response button).
  useEffect(() => {
    const onKey = (e) => {
      if (e.code === 'Space' && stage === 'testing') {
        e.preventDefault()
        if (awaiting) respond(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const analyze = async () => {
    setAnalyzing(true)
    try {
      const record = {
        patient: { ...patient, name: patient.name || 'Screening subject' },
        right: { ac: results.right, bc: {} },
        left: { ac: results.left, bc: {} },
      }
      setAnalysis(await api.analyze(record))
      navigate('/dashboard')
    } catch (e) {
      showToast(`Analysis failed: ${e.message}`, 'error')
    }
    setAnalyzing(false)
  }

  const progress = Math.round((stepIdx / STEPS.length) * 100)
  const field = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20'

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold tracking-tight">Hearing Screening</h1>
      <p className="mt-1 text-[13.5px] text-slate-500">
        A modified Hughson-Westlake pure-tone screening, run in the browser — the
        result flows straight into the full AudioSense analysis.
      </p>

      <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800">
        <b>Screening, not a diagnostic audiogram.</b> Consumer headphones and browser
        audio are not calibrated to ISO 389 reference levels. Absolute dB HL values are
        approximate; use this to detect and demonstrate hearing loss, never to certify it.
        Run it in a quiet room with wired headphones.
      </div>

      {/* ---------------------------------------------------------- intro -- */}
      {stage === 'intro' && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
            Before you start
          </h2>
          <ol className="mt-3 space-y-2 text-[13.5px] text-slate-700">
            <li><b>1.</b> Put on wired headphones (left/right matters — the test pans each ear).</li>
            <li><b>2.</b> Sit somewhere quiet and set your system volume to a normal listening level.</li>
            <li><b>3.</b> Calibrate on the next screen, then press <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold">Space</kbd> (or the button) every time you hear a tone — however faint.</li>
          </ol>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <label className="block"><span className="text-[12px] font-medium text-slate-600">Name</span>
              <input className={field} value={patient.name}
                onChange={(e) => setPatient({ ...patient, name: e.target.value })}
                placeholder="Screening subject" /></label>
            <label className="block"><span className="text-[12px] font-medium text-slate-600">Age</span>
              <input type="number" className={field} value={patient.age}
                onChange={(e) => setPatient({ ...patient, age: +e.target.value })} /></label>
            <label className="block"><span className="text-[12px] font-medium text-slate-600">Occupation</span>
              <input className={field} value={patient.occupation}
                onChange={(e) => setPatient({ ...patient, occupation: e.target.value })} /></label>
          </div>
          <div className="mt-4">
            <span className="text-[12px] font-medium text-slate-600">Procedure</span>
            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
              {[['bayesian', 'Bayesian adaptive', 'Posterior over threshold — a confidence interval on every result, and fewer tones'],
                ['staircase', 'Hughson-Westlake', 'The classic clinical staircase: down 10 dB, up 5 dB']].map(([k, title, sub]) => (
                <button key={k} onClick={() => setMethod(k)}
                  className={`rounded-xl border px-3 py-2.5 text-left transition ${
                    method === k ? 'border-teal-500 bg-teal-50/60 ring-1 ring-teal-500'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}>
                  <div className="text-[13px] font-semibold text-slate-800">{title}</div>
                  <div className="mt-0.5 text-[11px] leading-snug text-slate-500">{sub}</div>
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11.5px] leading-relaxed text-slate-400">
              Measured over 300 simulated listeners with realistic response noise, the
              Bayesian procedure needed <b>9.6 presentations per frequency versus 11.6</b>
              {' '}for the staircase, with a mean absolute error of 2.7 dB versus 3.3 dB
              and almost no bias — at the cost of occasional larger misses (1.3% of
              thresholds off by more than 10 dB, versus 0.3%). Its real advantage is
              that it reports how sure it is.
            </p>
            <p className="mt-1.5 text-[11.5px] text-slate-400">
              Both procedures insert silent catch trials — if you respond when nothing
              was played, the results are flagged unreliable.
            </p>
          </div>
          <button onClick={() => { setStage('calibrate'); tone().setAnchorGain(volume); tone().startCalibrationTone() }}
            className="mt-5 rounded-xl bg-teal-600 px-6 py-3 text-[14px] font-semibold text-white shadow-md shadow-teal-600/25 hover:bg-teal-700">
            Start calibration →
          </button>
        </div>
      )}

      {/* ------------------------------------------------------ calibrate -- */}
      {stage === 'calibrate' && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
          <h2 className="text-[15px] font-semibold text-slate-800">Calibration</h2>
          <p className="mt-1 text-[13.5px] text-slate-600">
            A 1 kHz tone is playing. Move the slider until it is <b>soft but clearly
            audible</b> — the quietest level you would still call comfortable. This
            anchors the scale at 40 dB HL.
          </p>
          <input type="range" min="0.0005" max="0.25" step="0.0005" value={volume}
            onChange={(e) => { const v = +e.target.value; setVolume(v); tone().setAnchorGain(v); tone().updateCalibrationTone() }}
            className="mt-6 w-full accent-teal-600" />
          <div className="mt-1 flex justify-between text-[11px] text-slate-400">
            <span>barely audible</span><span>comfortable</span><span>loud</span>
          </div>
          <div className="mt-5 flex gap-2">
            <button onClick={startTest}
              className="rounded-xl bg-teal-600 px-6 py-3 text-[14px] font-semibold text-white shadow-md shadow-teal-600/25 hover:bg-teal-700">
              Begin screening →
            </button>
            <button onClick={() => { tone().stopCalibrationTone(); setStage('intro') }}
              className="rounded-xl px-4 py-3 text-[14px] font-medium text-slate-500 hover:bg-slate-100">
              Back
            </button>
          </div>
        </div>
      )}

      {/* -------------------------------------------------------- testing -- */}
      {stage === 'testing' && step && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`rounded-lg px-2.5 py-1 text-[12px] font-bold uppercase ${
                step.ear === 'right' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
              }`}>{step.ear} ear</span>
              <span className="text-[13px] font-semibold text-slate-700">
                {FREQ_LABELS[step.freq]} Hz
              </span>
            </div>
            <span className="text-[12px] text-slate-400">
              {stepIdx + 1} of {STEPS.length} · testing at {level} dB HL
            </span>
          </div>

          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-teal-500 transition-all duration-500"
              style={{ width: `${progress}%` }} />
          </div>

          <div className="mt-8 flex flex-col items-center">
            <div className={`flex h-28 w-28 items-center justify-center rounded-full transition-all duration-300 ${
              presenting ? 'animate-pulse-soft bg-teal-100 ring-8 ring-teal-200/60' : 'bg-slate-100'
            }`}>
              <svg viewBox="0 0 24 24" className={`h-10 w-10 ${presenting ? 'text-teal-600' : 'text-slate-300'}`}
                fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <path d="M3 10v4m4-8v12m4-15v18m4-14v10m4-7v4" />
              </svg>
            </div>
            <div className="mt-4 text-[14px] font-medium text-slate-600">
              {presenting ? 'Listening…' : awaiting ? 'Did you hear it?' : 'Get ready…'}
            </div>

            {/* live posterior — the estimator thinking out loud */}
            {method === 'bayesian' && posterior && (
              <div className="mt-4 w-full max-w-md">
                <div className="flex items-end justify-between text-[11px] text-slate-500">
                  <span>threshold posterior</span>
                  {ci && (
                    <span className="font-semibold text-teal-700">
                      95% CI {ci[0]}–{ci[1]} dB
                    </span>
                  )}
                </div>
                <svg viewBox="0 0 300 60" className="mt-1 w-full">
                  {(() => {
                    const max = Math.max(...posterior.map((d) => d.p)) || 1
                    const pts = posterior.map((d, i) => {
                      const x = (i / (posterior.length - 1)) * 300
                      const y = 58 - (d.p / max) * 52
                      return `${x.toFixed(1)},${y.toFixed(1)}`
                    })
                    return (
                      <>
                        <polyline points={pts.join(' ')} fill="none"
                          stroke="#0d9488" strokeWidth="2" />
                        <polygon points={`0,58 ${pts.join(' ')} 300,58`}
                          fill="#0d9488" fillOpacity="0.12" />
                      </>
                    )
                  })()}
                </svg>
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>−10 dB</span><span>40</span><span>90 dB</span>
                </div>
              </div>
            )}

            {isCatch && awaiting && (
              <div className="mt-2 rounded-lg bg-slate-100 px-3 py-1.5 text-[11px] text-slate-500">
                (silent catch trial — nothing was played)
              </div>
            )}

            <div className="mt-5 flex gap-3">
              <button onClick={() => respond(true)} disabled={!awaiting}
                className="rounded-xl bg-teal-600 px-8 py-3.5 text-[15px] font-semibold text-white shadow-md shadow-teal-600/25 transition hover:bg-teal-700 disabled:opacity-30">
                ✓ I heard it <span className="ml-1 text-[11px] opacity-70">(Space)</span>
              </button>
              <button onClick={() => respond(false)} disabled={!awaiting}
                className="rounded-xl border border-slate-300 px-8 py-3.5 text-[15px] font-semibold text-slate-600 transition hover:border-slate-400 disabled:opacity-30">
                ✗ Nothing
              </button>
            </div>
            <button onClick={present} disabled={presenting}
              className="mt-3 text-[12px] font-medium text-slate-400 hover:text-teal-700 disabled:opacity-40">
              replay this tone
            </button>
          </div>

          <div className="mt-6 border-t border-slate-100 pt-3 text-[11.5px] text-slate-400">
            {method === 'bayesian'
              ? 'Procedure: Bayesian adaptive estimation (QUEST/ZEST family). Each '
                + 'response updates a posterior over threshold; the next tone is the '
                + 'one whose outcome is least predictable, and testing stops when the '
                + '95% credible interval narrows to 10 dB.'
              : 'Procedure: start 40 dB HL, down 10 dB after a response, up 5 dB after '
                + 'none; threshold is the lowest level heard on 2 of 3 ascending '
                + 'presentations (modified Hughson-Westlake, ASHA 2005).'}
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------- done -- */}
      {stage === 'done' && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
          <h2 className="text-[15px] font-semibold text-slate-800">Screening complete</h2>
          <p className="mt-1 text-[13.5px] text-slate-500">
            Your measured thresholds — review, then run the full analysis.
          </p>

          {reliability && (
            <div className={`mt-3 rounded-xl border px-3 py-2 text-[12.5px] ${
              reliability.reliable
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                : 'border-rose-300 bg-rose-50 text-rose-900'
            }`}>
              <b>{reliability.reliable ? 'Responses reliable' : 'Results unreliable'}</b>
              {' — '}{reliability.message}
            </div>
          )}
          <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-center text-[13px]">
              <thead>
                <tr className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="px-3 py-2.5 text-left font-semibold">Ear</th>
                  {[250, 500, 1000, 2000, 4000, 8000].map((f) => (
                    <th key={f} className="px-2 py-2.5 font-semibold">{FREQ_LABELS[f]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {EARS.map((ear) => (
                  <tr key={ear} className="border-t border-slate-100">
                    <td className={`px-3 py-2 text-left font-semibold ${
                      ear === 'right' ? 'text-red-600' : 'text-blue-600'
                    }`}>{ear === 'right' ? 'O Right' : 'X Left'}</td>
                    {[250, 500, 1000, 2000, 4000, 8000].map((f) => {
                      const iv = intervals[ear][f]
                      return (
                        <td key={f} className="px-2 py-2 font-medium text-slate-800">
                          {results[ear][f] ?? '—'}
                          {iv && (
                            <div className="text-[10px] font-normal text-slate-400">
                              ±{Math.round(iv.ci_width / 2)} · {iv.presentations}t
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-5 flex gap-2">
            <button onClick={analyze} disabled={analyzing}
              className="rounded-xl bg-teal-600 px-7 py-3 text-[15px] font-semibold text-white shadow-md shadow-teal-600/25 hover:bg-teal-700 disabled:opacity-50">
              {analyzing ? 'Analyzing…' : 'Analyze my hearing →'}
            </button>
            <button onClick={() => setStage('intro')}
              className="rounded-xl px-4 py-3 text-[14px] font-medium text-slate-500 hover:bg-slate-100">
              Test again
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
