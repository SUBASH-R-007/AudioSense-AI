import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import { SpatialScene, nextAngle } from '../audio/spatialAudio.js'
import { DigitsInNoiseTest } from '../audio/digitsInNoise.js'
import { TinnitusTool } from '../audio/tinnitus.js'

const TABS = [
  { id: 'spatial', label: 'Spatial hearing', icon: '🧭',
    blurb: 'Where is the sound coming from?' },
  { id: 'noise', label: 'Speech in noise', icon: '🍽',
    blurb: 'The complaint an audiogram cannot show' },
  { id: 'tinnitus', label: 'Tinnitus', icon: '🔔',
    blurb: 'Match it, then mask it' },
]

const BAND_STYLE = {
  normal: 'bg-emerald-100 text-emerald-800',
  reduced: 'bg-amber-100 text-amber-800',
  insufficient: 'bg-amber-100 text-amber-800',
  impaired: 'bg-rose-100 text-rose-800',
  poor: 'bg-rose-100 text-rose-800',
}

/* ----------------------------------------------------- spatial hearing -- */

function SpatialTest({ analysis, showToast }) {
  const sceneRef = useRef(null)
  const [impaired, setImpaired] = useState(true)
  const [angle, setAngle] = useState(null)
  const [trials, setTrials] = useState([])
  const [awaiting, setAwaiting] = useState(false)
  const [result, setResult] = useState(null)
  const [xr, setXr] = useState(false)
  const [predicted, setPredicted] = useState(null)

  const scene = () => {
    if (!sceneRef.current) sceneRef.current = new SpatialScene()
    return sceneRef.current
  }

  useEffect(() => {
    SpatialScene.xrSupported().then(setXr)
    return () => sceneRef.current?.dispose()
  }, [])

  useEffect(() => {
    const th = analysis?.thresholds
    if (!th) return
    api.predictLocalization(th.right.ac, th.left.ac).then(setPredicted).catch(() => {})
  }, [analysis])

  const applyHearing = useCallback(() => {
    const th = analysis?.thresholds
    scene().setHearing(
      impaired && th ? th.right.ac : null,
      impaired && th ? th.left.ac : null,
    )
  }, [analysis, impaired])

  useEffect(() => { if (sceneRef.current?.ctx) applyHearing() }, [applyHearing])

  const present = async () => {
    const a = nextAngle(angle)
    setAngle(a)
    const s = scene()
    applyHearing()
    s.setAngle(a)
    setAwaiting(false)
    await s.playBurst()
    setAwaiting(true)
  }

  const respond = (respondedDeg) => {
    if (!awaiting || angle == null) return
    const next = [...trials, { presented_deg: angle, responded_deg: respondedDeg }]
    setTrials(next)
    setAwaiting(false)
    if (next.length >= 8) score(next)
    else setTimeout(present, 400)
  }

  const score = async (allTrials) => {
    try {
      const th = analysis?.thresholds
      setResult(await api.localization(allTrials, th?.right.ac || {}, th?.left.ac || {}))
    } catch (e) {
      showToast(`Scoring failed: ${e.message}`, 'error')
    }
  }

  const reset = () => { setTrials([]); setResult(null); setAngle(null); setAwaiting(false) }

  // Click position on the compass -> angle in degrees.
  const onCompassClick = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - r.left - r.width / 2
    const y = e.clientY - r.top - r.height / 2
    respond(Math.round((Math.atan2(x, -y) * 180) / Math.PI))
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <h3 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
          Localization test
        </h3>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-600">
          A noise burst plays from somewhere around you. Click where you heard it.
          Eight trials. <b>Headphones are essential</b> — the spatial cues live in
          the difference between your two ears.
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button onClick={() => setImpaired(!impaired)}
            className={`rounded-lg px-3 py-1.5 text-[12.5px] font-semibold transition ${
              impaired ? 'bg-amber-500 text-white' : 'bg-teal-600 text-white'}`}>
            {impaired ? "Patient's ears" : 'Normal ears'}
          </button>
          <button onClick={present} disabled={awaiting}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-[12.5px] font-semibold text-white disabled:opacity-40">
            {trials.length ? 'Replay' : 'Start'}
          </button>
          <button onClick={reset}
            className="rounded-lg px-3 py-1.5 text-[12.5px] font-medium text-slate-500 hover:bg-slate-100">
            Reset
          </button>
          <span className="ml-auto text-[12px] text-slate-500">
            {trials.length}/8 trials
          </span>
        </div>

        {/* top-down compass */}
        <div className="mt-4 flex justify-center">
          <div onClick={onCompassClick}
            role="button" tabIndex={0} aria-label="Click the direction you heard the sound"
            className={`relative h-56 w-56 rounded-full border-2 transition ${
              awaiting ? 'cursor-crosshair border-teal-400 bg-teal-50/40'
                : 'border-slate-200 bg-slate-50'}`}>
            {[0, 90, 180, 270].map((deg) => (
              <span key={deg}
                className="absolute text-[10px] font-semibold text-slate-400"
                style={{
                  left: `${50 + 44 * Math.sin((deg * Math.PI) / 180)}%`,
                  top: `${50 - 44 * Math.cos((deg * Math.PI) / 180)}%`,
                  transform: 'translate(-50%,-50%)',
                }}>
                {{ 0: 'front', 90: 'right', 180: 'behind', 270: 'left' }[deg]}
              </span>
            ))}
            <span className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-700" />
            {result && trials.map((t, i) => (
              <span key={i} className="absolute h-2 w-2 rounded-full bg-teal-500/70"
                style={{
                  left: `${50 + 40 * Math.sin((t.presented_deg * Math.PI) / 180)}%`,
                  top: `${50 - 40 * Math.cos((t.presented_deg * Math.PI) / 180)}%`,
                  transform: 'translate(-50%,-50%)',
                }} />
            ))}
            {awaiting && (
              <span className="absolute inset-0 flex items-center justify-center text-[12px] font-semibold text-teal-700">
                click where you heard it
              </span>
            )}
          </div>
        </div>
        {xr && (
          <p className="mt-3 rounded-lg bg-slate-100 px-3 py-2 text-[11.5px] text-slate-600">
            A VR headset is available on this device — the same HRTF scene runs
            immersively with head tracking.
          </p>
        )}
      </div>

      <div className="space-y-4">
        {predicted && (
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <h3 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Predicted from the audiogram
            </h3>
            <div className="mt-2 flex items-center gap-2">
              <span className={`rounded-md px-2 py-0.5 text-[11px] font-bold uppercase ${
                BAND_STYLE[predicted.band] || 'bg-slate-100 text-slate-600'}`}>
                {predicted.band}
              </span>
              <span className="text-[12.5px] text-slate-500">
                interaural asymmetry {predicted.asymmetry_db} dB
              </span>
            </div>
            <p className="mt-2 text-[13px] leading-relaxed text-slate-600">
              {predicted.expectation}
            </p>
          </div>
        )}
        {result && (
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <h3 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Measured
            </h3>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-slate-900">
                {result.result.rms_error_deg}°
              </span>
              <span className={`rounded-md px-2 py-0.5 text-[11px] font-bold uppercase ${
                BAND_STYLE[result.result.band]}`}>{result.result.band}</span>
            </div>
            <p className="mt-2 text-[13px] leading-relaxed text-slate-700">
              {result.result.interpretation}
            </p>
            <p className="mt-2 text-[11px] text-slate-400">{result.result.normative}</p>
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------------------------------------------------- speech in noise --- */

function DigitsTest({ analysis, showToast }) {
  const testRef = useRef(null)
  const [running, setRunning] = useState(false)
  const [triplet, setTriplet] = useState(null)
  const [entry, setEntry] = useState('')
  const [state, setState] = useState({ trial: 0, snr: 0, reversals: 0 })
  const [result, setResult] = useState(null)

  const test = () => {
    if (!testRef.current) testRef.current = new DigitsInNoiseTest()
    return testRef.current
  }
  useEffect(() => () => testRef.current?.dispose(), [])

  const start = async () => {
    const t = test()
    t.startNoise()
    setRunning(true)
    setResult(null)
    await nextTrial(t)
  }

  const nextTrial = async (t) => {
    const trip = t.nextTriplet()
    setTriplet(trip)
    setEntry('')
    await t.speak(trip)
  }

  const submit = async () => {
    const t = test()
    const correct = entry.replace(/\D/g, '') === t.currentTriplet.join('')
    const s = t.record(correct)
    setState(s)
    if (t.done) {
      t.stopNoise()
      setRunning(false)
      try {
        const th = analysis?.thresholds
        setResult(await api.digitsInNoise(
          t.reversals, th?.right.ac || {}, th?.left.ac || {}))
      } catch (e) {
        showToast(`Scoring failed: ${e.message}`, 'error')
      }
    } else {
      await nextTrial(t)
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <h3 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
          Digit triplet test
        </h3>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-600">
          Three digits are spoken against noise. Type what you hear — guess if you
          must. The noise stays put and the speech moves, converging on the
          signal-to-noise ratio where you get half of them right.
        </p>
        <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-[12px] text-slate-600">
          Only the <b>ratio</b> of speech to noise matters here, not the absolute
          level — which is why this test works on uncalibrated equipment when
          pure-tone screening does not.
        </p>

        {!running && !result && (
          <button onClick={start}
            className="mt-4 rounded-xl bg-teal-600 px-6 py-3 text-[14px] font-semibold text-white shadow-md shadow-teal-600/25 hover:bg-teal-700">
            Start test
          </button>
        )}

        {running && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-[12px] text-slate-500">
              <span>Trial {state.trial + 1}</span>
              <span>SNR {state.snr > 0 ? '+' : ''}{state.snr} dB · {state.reversals}/6 reversals</span>
            </div>
            <input value={entry} onChange={(e) => setEntry(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && entry && submit()}
              inputMode="numeric" autoFocus placeholder="e.g. 4 7 2"
              aria-label="Type the three digits you heard"
              className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-center text-2xl tracking-[0.4em] focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20" />
            <div className="mt-2 flex gap-2">
              <button onClick={submit} disabled={!entry}
                className="rounded-lg bg-slate-900 px-5 py-2 text-[13px] font-semibold text-white disabled:opacity-40">
                Submit
              </button>
              <button onClick={() => test().speak(triplet)}
                className="rounded-lg border border-slate-300 px-4 py-2 text-[13px] font-medium text-slate-600">
                Repeat
              </button>
            </div>
          </div>
        )}
      </div>

      {result && (
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h3 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
            Speech reception threshold in noise
          </h3>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-slate-900">
              {result.result.srt_db_snr > 0 ? '+' : ''}{result.result.srt_db_snr}
            </span>
            <span className="text-[13px] text-slate-500">dB SNR</span>
            <span className={`ml-auto rounded-md px-2 py-0.5 text-[11px] font-bold uppercase ${
              BAND_STYLE[result.result.band]}`}>{result.result.band}</span>
          </div>
          <p className="mt-2 text-[13px] leading-relaxed text-slate-700">
            {result.result.interpretation}
          </p>
          {result.versus_audiogram?.hidden_hearing_loss && (
            <div className="mt-3 rounded-xl bg-amber-50 p-3">
              <div className="text-[12.5px] font-semibold text-amber-900">
                Normal audiogram, abnormal speech in noise
              </div>
              <p className="mt-1 text-[12.5px] leading-relaxed text-amber-900">
                {result.versus_audiogram.note}
              </p>
            </div>
          )}
          <p className="mt-2 text-[11px] text-slate-400">{result.result.normative}</p>
        </div>
      )}
    </div>
  )
}

/* --------------------------------------------------------- tinnitus ----- */

function TinnitusTool_({ analysis, showToast }) {
  const toolRef = useRef(null)
  const [pitch, setPitch] = useState(4000)
  const [level, setLevel] = useState(15)
  const [ear, setEar] = useState('both')
  const [playing, setPlaying] = useState(false)
  const [masking, setMasking] = useState(false)
  const [result, setResult] = useState(null)

  const tool = () => {
    if (!toolRef.current) toolRef.current = new TinnitusTool()
    return toolRef.current
  }
  useEffect(() => () => toolRef.current?.dispose(), [])

  const toggleTone = () => {
    const t = tool()
    if (playing) { t.stopMatchTone(); setPlaying(false) }
    else { t.startMatchTone(pitch, level, ear); setPlaying(true) }
  }

  const toggleMasker = () => {
    const t = tool()
    if (masking) { t.stopMasker(); setMasking(false) }
    else { t.startNotchedMasker(pitch); setMasking(true) }
  }

  const analyze = async () => {
    try {
      const th = analysis?.thresholds
      setResult(await api.tinnitus({
        pitch_hz: pitch, loudness_db_sl: level, ear,
        right_ac: th?.right.ac || {}, left_ac: th?.left.ac || {},
      }))
    } catch (e) {
      showToast(`Analysis failed: ${e.message}`, 'error')
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <h3 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
          Pitch and loudness match
        </h3>
        <p className="mt-1 text-[13px] leading-relaxed text-slate-600">
          Play the tone and adjust it until it sounds like the ringing. The pitch
          you land on almost always sits inside the region of hearing loss.
        </p>

        <div className="mt-4 space-y-4">
          <label className="block">
            <div className="flex justify-between text-[12px] font-medium text-slate-600">
              <span>Pitch</span><span className="font-bold text-slate-800">{pitch} Hz</span>
            </div>
            <input type="range" min="250" max="12000" step="50" value={pitch}
              onChange={(e) => { const v = +e.target.value; setPitch(v); tool().setPitch(v) }}
              className="mt-1 w-full accent-teal-600" />
          </label>
          <label className="block">
            <div className="flex justify-between text-[12px] font-medium text-slate-600">
              <span>Loudness above your threshold</span>
              <span className="font-bold text-slate-800">{level} dB SL</span>
            </div>
            <input type="range" min="0" max="40" step="1" value={level}
              onChange={(e) => { const v = +e.target.value; setLevel(v); tool().setLevel(v) }}
              className="mt-1 w-full accent-teal-600" />
          </label>
          <div className="flex rounded-lg bg-slate-100 p-1">
            {['left', 'both', 'right'].map((e) => (
              <button key={e} onClick={() => setEar(e)}
                className={`flex-1 rounded-md px-3 py-1.5 text-[12.5px] font-semibold capitalize transition ${
                  ear === e ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500'}`}>
                {e}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={toggleTone}
              className={`rounded-lg px-4 py-2 text-[13px] font-semibold text-white ${
                playing ? 'bg-rose-500' : 'bg-teal-600'}`}>
              {playing ? '■ Stop tone' : '▶ Play tone'}
            </button>
            <button onClick={toggleMasker}
              className={`rounded-lg px-4 py-2 text-[13px] font-semibold ${
                masking ? 'bg-amber-500 text-white' : 'border border-slate-300 text-slate-700'}`}>
              {masking ? '■ Stop masker' : '🔊 Notched masker'}
            </button>
            <button onClick={analyze}
              className="rounded-lg bg-slate-900 px-4 py-2 text-[13px] font-semibold text-white">
              Analyze match
            </button>
          </div>
        </div>
      </div>

      {result && (
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h3 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
            Match interpretation
          </h3>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-slate-50 p-3">
              <div className="text-[10.5px] uppercase tracking-wider text-slate-400">Pitch</div>
              <div className="text-xl font-bold text-slate-800">{result.pitch_hz} Hz</div>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <div className="text-[10.5px] uppercase tracking-wider text-slate-400">
                Threshold there
              </div>
              <div className="text-xl font-bold text-slate-800">
                {result.threshold_at_pitch ?? '—'} <span className="text-[12px]">dB HL</span>
              </div>
            </div>
          </div>
          <ul className="mt-3 space-y-2">
            {result.notes.map((n, i) => (
              <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-slate-700">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-400" />{n}
              </li>
            ))}
          </ul>
          <div className="mt-3 rounded-xl bg-teal-50/70 p-3 text-[12.5px] leading-relaxed text-teal-900">
            <b>Notch {result.notch.low_hz}–{result.notch.high_hz} Hz.</b>{' '}
            {result.therapy}
          </div>
          <p className="mt-2 text-[11px] italic text-slate-400">{result.disclaimer}</p>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------- page ----- */

export default function ListeningLab() {
  const { analysis, showToast } = useApp()
  const [tab, setTab] = useState('spatial')

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-xl font-semibold tracking-tight">Listening Lab</h1>
      <p className="mt-1 max-w-3xl text-[13.5px] text-slate-500">
        Three measures the pure-tone audiogram cannot give you — where sound comes
        from, speech in a crowd, and the ringing that never stops. Each is the
        complaint patients actually arrive with.
      </p>
      {!analysis && (
        <div className="mt-3 rounded-xl bg-amber-50 px-4 py-2.5 text-[12.5px] text-amber-800">
          No analysis loaded — the tests still run, but they cannot be compared
          against this patient's audiogram.
        </div>
      )}

      <div className="mt-5 grid gap-2 sm:grid-cols-3" data-tour="lab-tabs">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            aria-pressed={tab === t.id}
            className={`rounded-xl border px-4 py-3 text-left transition ${
              tab === t.id ? 'border-teal-500 bg-teal-50/60 ring-1 ring-teal-500'
                : 'border-slate-200 bg-white hover:border-slate-300'}`}>
            <div className="text-[14px] font-semibold text-slate-800">
              <span aria-hidden="true" className="mr-1.5">{t.icon}</span>{t.label}
            </div>
            <div className="mt-0.5 text-[11.5px] text-slate-500">{t.blurb}</div>
          </button>
        ))}
      </div>

      <div className="mt-5">
        {tab === 'spatial' && <SpatialTest analysis={analysis} showToast={showToast} />}
        {tab === 'noise' && <DigitsTest analysis={analysis} showToast={showToast} />}
        {tab === 'tinnitus' && <TinnitusTool_ analysis={analysis} showToast={showToast} />}
      </div>
    </div>
  )
}
