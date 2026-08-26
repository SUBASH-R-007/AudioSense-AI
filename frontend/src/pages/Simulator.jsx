import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { api, AC_FREQS, FREQ_LABELS } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import { HearingSimulator } from '../audio/simulatorGraph.js'
import { SOUNDSCAPES, buildSoundscape } from '../audio/soundscapes.js'
import { ConversationListener, recognitionSupported } from '../lib/conversation.js'
import { LANGUAGES, setLanguage } from '../i18n/index.js'

// Fallback thresholds (presbycusis-like) when no analysis is loaded.
const DEMO_THRESHOLDS = { 250: 20, 500: 25, 1000: 35, 2000: 50, 4000: 65, 8000: 75 }

// Titles and subtitles live in the locale files under modes.<id>; only the
// identity and the colour belong here.
const MODES = [
  { id: 'normal', tone: 'teal' },
  { id: 'patient', tone: 'amber' },
  { id: 'aided', tone: 'emerald' },
]

//: The speech sample, per interface language. Only the English recording is
//: bundled today; the Hindi entry is the drop point.
//: TODO(hindi-audio): record a Hindi sentence at matched RMS level and save it
//: as frontend/public/audio/hi/speech_sample.wav — the loader below already
//: prefers it and falls back to the English sample until it exists.
const SAMPLE_URLS = {
  en: '/audio/speech_sample.wav',
  hi: '/audio/hi/speech_sample.wav',
}

const TONE = {
  teal: { text: 'text-teal-700', ring: 'ring-teal-500/40', bar: '#0d9488', bar2: '#2dd4bfaa' },
  amber: { text: 'text-amber-600', ring: 'ring-amber-500/40', bar: '#f59e0b', bar2: '#fbbf24aa' },
  emerald: { text: 'text-emerald-600', ring: 'ring-emerald-500/40', bar: '#059669', bar2: '#34d399aa' },
}

export default function Simulator() {
  const { t, i18n } = useTranslation('simulator')
  const uiLang = i18n.language?.startsWith('hi') ? 'hi' : 'en'
  const { analysis, showToast } = useApp()
  const simRef = useRef(null)
  const canvasRef = useRef(null)
  const rafRef = useRef(0)
  const [playing, setPlaying] = useState(false)
  const [mode, setMode] = useState('normal')
  const [ear, setEar] = useState('right')
  const [source, setSource] = useState('sample')
  const [distortion, setDistortion] = useState(false)
  const [autoDistortion, setAutoDistortion] = useState(false)
  const [ready, setReady] = useState(false)
  const [prescription, setPrescription] = useState(null)
  const [words, setWords] = useState(null)
  const [noiseOn, setNoiseOn] = useState(false)
  const [snr, setSnr] = useState(5)
  const [aidType, setAidType] = useState('nal')
  const [scape, setScape] = useState(null)
  const [binaural, setBinaural] = useState(false)
  const [headShadow, setHeadShadow] = useState(true)
  const [listening, setListening] = useState(false)
  const [liveWords, setLiveWords] = useState(null)
  const listenerRef = useRef(null)
  const fileRef = useRef(null)

  const thresholds = useMemo(() => {
    const ac = analysis?.thresholds?.[ear]?.ac
    return ac && Object.keys(ac).length ? ac : DEMO_THRESHOLDS
  }, [analysis, ear])

  const usingDemo = !analysis?.thresholds?.[ear]?.ac ||
    !Object.keys(analysis?.thresholds?.[ear]?.ac || {}).length
  const sii = analysis?.sii?.[ear]

  const sim = () => {
    if (!simRef.current) {
      simRef.current = new HearingSimulator()
      window.__audiosenseSim = simRef.current // diagnostics / automated demo checks
    }
    return simRef.current
  }

  useEffect(() => () => { cancelAnimationFrame(rafRef.current); simRef.current?.dispose() }, [])

  // keep filters in sync with the selected ear / analysis
  useEffect(() => {
    if (simRef.current?.ctx) {
      simRef.current.setThresholds(thresholds)
      const severe = simRef.current.severity() >= 40
      setAutoDistortion(severe)
      simRef.current.setDistortion(distortion || severe)
    }
  }, [thresholds, distortion])

  // fetch the NAL-R prescription + word-level audibility for these thresholds
  useEffect(() => {
    let cancelled = false
    api.prescription({ ac: thresholds, bc: {} })
      .then((p) => {
        if (cancelled) return
        setPrescription(p)
        setWords(p.words)
        simRef.current?.ctx && simRef.current.setAidGains(p.gains)
      })
      .catch(() => { if (!cancelled) { setPrescription(null); setWords(null) } })
    return () => { cancelled = true }
  }, [thresholds])

  // keep noise + aid type in sync with the controls
  useEffect(() => {
    if (simRef.current?.ctx) simRef.current.setNoiseSNR(snr, noiseOn)
  }, [snr, noiseOn])

  useEffect(() => {
    if (simRef.current?.ctx) simRef.current.setAidType(aidType)
  }, [aidType])

  // binaural: each ear gets its own audiogram, in stereo
  useEffect(() => {
    const s = simRef.current
    if (!s?.ctx) return
    if (binaural && analysis?.thresholds) {
      s.setBinaural(true, analysis.thresholds.right.ac,
        analysis.thresholds.left.ac, headShadow)
    } else {
      s.setBinaural(false)
      s.setThresholds(thresholds)
    }
  }, [binaural, headShadow, analysis, thresholds])

  useEffect(() => () => listenerRef.current?.stop(), [])

  const scoreTranscript = useCallback(async (text) => {
    try {
      // Goes through the api client rather than a bare fetch so it carries the
      // session token. A raw fetch here would 401 on every utterance once the
      // instance is password-protected, and — because the swallowed catch
      // below is the whole error path — it would do so in complete silence.
      setLiveWords(await api.speechWords(thresholds, text))
    } catch { /* transient — keep listening */ }
  }, [thresholds])

  const toggleListening = () => {
    if (listening) {
      listenerRef.current?.stop()
      setListening(false)
      return
    }
    // Stop whatever came before. Without this a listener that errored out but
    // is still running gets orphaned here — unreachable even by the unmount
    // cleanup, which only ever sees the newest ref.
    listenerRef.current?.stop()
    const listener = new ConversationListener(
      (text) => scoreTranscript(text),
      (err) => {
        showToast(err, 'error')
        // The library already stops itself on a fatal error; this covers the
        // rest, so a listener is never left running behind a button that has
        // reverted to "Start talking".
        listenerRef.current?.stop()
        setListening(false)
      },
    )
    if (listener.start()) {
      listenerRef.current = listener
      setListening(true)
      setLiveWords(null)
      showToast(t('toasts.speakNormally'))
    }
  }

  const playScape = async (id) => {
    const s = sim()
    s._ensureCtx()
    setScape(id)
    setSource('scape')
    s.buffer = buildSoundscape(s.ctx, id)
    s.sourceKind = 'sample'
    s.setThresholds(thresholds)
    if (prescription?.gains) s.setAidGains(prescription.gains)
    s.setAidType(aidType)
    s.setMode(mode)
    s.start()
    setPlaying(true)
    setReady(true)
    drawBars()
  }

  const ensureSource = async () => {
    const s = sim()
    if (source === 'mic') {
      if (!s._micStream) await s.useMic()
      return
    }
    if (source === 'scape' && scape) {
      s.buffer = buildSoundscape(s.ctx, scape)
      s.sourceKind = 'sample'
      return
    }
    if (!s.buffer || s.sourceKind === 'mic') {
      // Prefer the sample recorded in the interface language, then the
      // English recording, then synthesis — each step a strictly worse but
      // still working demonstration.
      try {
        await s.loadSampleUrl(SAMPLE_URLS[uiLang])
      } catch {
        try {
          if (uiLang !== 'en') showToast(t('toasts.hindiSampleMissing'), 'warn')
          await s.loadSampleUrl(SAMPLE_URLS.en)
        } catch {
          s.synthesizeFallback()
          showToast(t('toasts.sampleMissing'), 'warn')
        }
      }
    }
  }

  const togglePlay = async () => {
    const s = sim()
    if (playing) {
      s.stop()
      setPlaying(false)
      cancelAnimationFrame(rafRef.current)
      return
    }
    try {
      await ensureSource()
      s.setThresholds(thresholds)
      if (prescription?.gains) s.setAidGains(prescription.gains)
      s.setAidType(aidType)
      s.setNoiseSNR(snr, noiseOn)
      const severe = s.severity() >= 40
      setAutoDistortion(severe)
      s.setDistortion(distortion || severe)
      s.setMode(mode)
      s.start()
      setPlaying(true)
      setReady(true)
      drawBars()
    } catch (e) {
      showToast(t('toasts.audioFailed', { msg: e.message }), 'error')
    }
  }

  const switchMode = (m) => {
    setMode(m)
    if (simRef.current?.ctx) simRef.current.setMode(m)
  }

  const onFile = async (file) => {
    if (!file) return
    try {
      await sim().loadFile(file)
      setSource('file')
      showToast(t('toasts.loadedFile', { name: file.name }))
      if (playing) sim().start()
    } catch {
      showToast(t('toasts.badAudio'), 'error')
    }
  }

  const pickSource = async (kind) => {
    setSource(kind)
    const s = sim()
    if (kind === 'mic') {
      try {
        await s.useMic()
        s.sourceKind = 'mic'
        showToast(t('toasts.micLive'), 'warn')
        if (playing) s.start()
      } catch {
        showToast(t('toasts.micDenied'), 'error')
        setSource('sample')
      }
    } else if (kind === 'sample') {
      s.releaseMic()
      s.sourceKind = 'sample'
      s.buffer = null
      if (playing) { await ensureSource(); s.start() }
    } else if (kind === 'file') {
      fileRef.current?.click()
    }
  }

  const drawBars = () => {
    const canvas = canvasRef.current
    const s = simRef.current
    if (!canvas || !s?.analyser) return
    const ctx2d = canvas.getContext('2d')
    const data = new Uint8Array(s.analyser.frequencyBinCount)
    const render = () => {
      s.analyser.getByteFrequencyData(data)
      const { width, height } = canvas
      ctx2d.clearRect(0, 0, width, height)
      const bars = 56
      const step = Math.floor(data.length / bars)
      const bw = width / bars
      const tone = TONE[MODES.find((m) => m.id === s.mode)?.tone || 'teal']
      for (let i = 0; i < bars; i++) {
        const v = data[i * step] / 255
        const h = Math.max(3, v * height * 0.92)
        const grad = ctx2d.createLinearGradient(0, height - h, 0, height)
        grad.addColorStop(0, tone.bar)
        grad.addColorStop(1, tone.bar2)
        ctx2d.fillStyle = grad
        ctx2d.beginPath()
        ctx2d.roundRect(i * bw + 1.5, height - h, bw - 3, h, 3)
        ctx2d.fill()
      }
      rafRef.current = requestAnimationFrame(render)
    }
    render()
  }

  const bandAtten = AC_FREQS.map((f) => {
    const raw = thresholds[f]
    const db = raw === 'NR' ? 120 : raw ?? 0
    return { f, atten: Math.min(70, Math.max(0, db - 20)) }
  })

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t('header.title')}</h1>
          <p className="mt-1 text-[13.5px] text-slate-500">
            {t('header.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {usingDemo && (
            <div className="rounded-lg bg-amber-50 px-3 py-1.5 text-[12px] font-medium text-amber-700">
              {t('header.demoBanner')}{' '}
              <Link to="/new-test" className="underline">{t('header.runTest')}</Link>
            </div>
          )}
          <div className="flex items-center gap-1.5" role="group" aria-label={t('lang.label')}>
            {LANGUAGES.map((l) => (
              <button key={l.code} onClick={() => setLanguage(l.code)}
                aria-pressed={uiLang === l.code}
                className={`rounded-lg border px-2.5 py-1 text-[12px] font-semibold transition ${
                  uiLang === l.code
                    ? 'border-teal-500 bg-teal-50 text-teal-800'
                    : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300'
                }`}>{l.native}</button>
            ))}
          </div>
        </div>
      </div>

      {/* The big three-state toggle */}
      <div className="mt-6 rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <div className="relative mx-auto grid max-w-2xl grid-cols-3 rounded-2xl bg-slate-100 p-2"
          data-tour="ab-toggle" role="group" aria-label={t('modes.groupLabel')}>
          <div
            className={`absolute inset-y-2 w-[calc(33.333%-5.5px)] rounded-xl bg-white shadow-md ring-1 transition-all duration-300 ${TONE[MODES.find((m) => m.id === mode).tone].ring}`}
            style={{ left: `calc(${MODES.findIndex((m) => m.id === mode) * 33.333}% + 8px)` }}
          />
          {MODES.map((m) => (
            <button key={m.id} onClick={() => switchMode(m.id)}
              className="relative z-10 rounded-xl px-4 py-4 text-center transition">
              <div className={`text-[15px] font-bold ${
                mode === m.id ? TONE[m.tone].text : 'text-slate-400'
              }`}>{t(`modes.${m.id}.title`)}</div>
              <div className="text-[11.5px] font-medium text-slate-400">{t(`modes.${m.id}.sub`)}</div>
            </button>
          ))}
        </div>

        {/* visualizer */}
        <div className="mt-5 overflow-hidden rounded-2xl bg-slate-900 p-4">
          <canvas ref={canvasRef} width={840} height={130} className="h-[130px] w-full" />
          <div className="mt-2 flex items-center justify-between text-[11px] font-medium text-slate-400">
            <span>
              {playing
                ? mode === 'patient' ? t('viz.simulatingPatient')
                  : mode === 'aided' ? t('viz.aided')
                  : t('viz.normalRef')
                : t('viz.stopped')}
            </span>
            <span>{ready && simRef.current ? t('viz.avgAtten', { db: Math.round(simRef.current.severity()) }) : ''}</span>
          </div>

          {/* live captions — what the patient actually receives */}
          {words && (
            <div className="mt-3 rounded-xl bg-slate-800/70 p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                {t('viz.reaches')}
              </div>
              <p className="mt-1.5 text-[14px] leading-relaxed">
                {words.words.map((w, i) => {
                  const degraded = mode !== 'normal' && w.status !== 'clear'
                  const missed = mode !== 'normal' && w.status === 'missed'
                  // The aid restores audibility, so words come back in aided mode.
                  const shown = mode === 'aided' ? 'clear' : w.status
                  const isMissed = missed && shown !== 'clear'
                  const isDegraded = degraded && shown !== 'clear' && !isMissed
                  return (
                    <span key={i}
                      className={`mr-1.5 inline-block transition-all duration-300 ${
                        isMissed ? 'text-rose-400/60 line-through decoration-rose-400/70'
                        : isDegraded ? 'text-amber-300/80 underline decoration-dotted decoration-amber-400/70 underline-offset-2'
                        : 'text-slate-100'
                      }`}
                      title={w.lost_phonemes?.length ? `${t('viz.inaudible')} ${w.lost_phonemes.map((p) => `/${p}/`).join(' ')}` : ''}
                    >{w.word}</span>
                  )
                })}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 text-[10.5px] text-slate-500">
                <span><span className="text-rose-400/70 line-through">{t('viz.struck')}</span> {t('viz.struckMeans')}</span>
                <span><span className="text-amber-300/80 underline decoration-dotted">{t('viz.dotted')}</span> {t('viz.dottedMeans')}</span>
                {mode === 'aided' && <span className="text-emerald-400">{t('viz.aidRestores')}</span>}
              </div>
            </div>
          )}
        </div>

        {/* transport + config row */}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
          <button onClick={togglePlay}
            className={`flex h-14 w-14 items-center justify-center rounded-full text-white shadow-lg transition ${
              playing ? 'bg-rose-500 shadow-rose-500/30 hover:bg-rose-600' : 'bg-teal-600 shadow-teal-600/30 hover:bg-teal-700'
            }`}>
            {playing ? (
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" className="ml-1 h-6 w-6" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
            )}
          </button>

          <div className="flex items-center gap-1.5">
            {['sample', 'file', 'mic'].map((k) => (
              <button key={k} onClick={() => pickSource(k)}
                className={`rounded-lg px-3 py-2 text-[12.5px] font-semibold transition ${
                  source === k ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}>{t(`sources.${k}`)}</button>
            ))}
            <input ref={fileRef} type="file" accept="audio/*" className="hidden"
              onChange={(e) => onFile(e.target.files?.[0])} />
          </div>

          <div className="flex items-center gap-3">
            <div className="flex rounded-lg bg-slate-100 p-1">
              {['right', 'left'].map((e) => (
                <button key={e} onClick={() => { setEar(e); setBinaural(false) }}
                  disabled={binaural}
                  className={`rounded-md px-3 py-1.5 text-[12.5px] font-semibold capitalize transition disabled:opacity-40 ${
                    ear === e && !binaural
                      ? e === 'right' ? 'bg-white text-red-600 shadow-sm' : 'bg-white text-blue-600 shadow-sm'
                      : 'text-slate-500'
                  }`}>{t(`ears.${e}`)}</button>
              ))}
              <button onClick={() => setBinaural(!binaural)}
                disabled={!analysis?.thresholds}
                title={t('ears.bothTitle')}
                className={`rounded-md px-3 py-1.5 text-[12.5px] font-semibold transition disabled:opacity-40 ${
                  binaural ? 'bg-white text-teal-700 shadow-sm' : 'text-slate-500'
                }`}>{t('ears.both')}</button>
            </div>
            {binaural && (
              <label className="flex cursor-pointer items-center gap-1.5 text-[12px] font-medium text-slate-600">
                <input type="checkbox" checked={headShadow} className="h-3.5 w-3.5 accent-teal-600"
                  onChange={(e) => setHeadShadow(e.target.checked)} />
                {t('ears.headShadow')}
              </label>
            )}
            <label className="flex cursor-pointer items-center gap-1.5 text-[12.5px] font-medium text-slate-600">
              <input type="checkbox" checked={distortion || autoDistortion}
                disabled={autoDistortion}
                onChange={(e) => setDistortion(e.target.checked)}
                className="h-3.5 w-3.5 accent-teal-600" />
              {t('distortion.label')}{autoDistortion && <span className="text-[10.5px] text-amber-600">{t('distortion.auto')}</span>}
            </label>
          </div>
        </div>
      </div>

      {/* live conversation mode */}
      <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
              {t('conversation.title')}
            </h2>
            <p className="mt-1 text-[12.5px] text-slate-500">
              {t('conversation.subtitle')}
            </p>
          </div>
          <button onClick={toggleListening} disabled={!recognitionSupported()}
            className={`rounded-xl px-5 py-2.5 text-[13px] font-semibold transition disabled:opacity-40 ${
              listening ? 'bg-rose-500 text-white shadow-md shadow-rose-500/25'
                : 'bg-slate-900 text-white hover:bg-slate-700'
            }`}>
            {listening ? t('conversation.stop') : t('conversation.start')}
          </button>
        </div>
        {!recognitionSupported() && (
          <div className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            {t('conversation.unsupported')}
          </div>
        )}
        <div className="mt-3 min-h-[64px] rounded-xl bg-slate-900 p-4">
          {liveWords?.words?.length ? (
            <p className="text-[16px] leading-relaxed">
              {liveWords.words.map((w, i) => (
                <span key={i}
                  className={`mr-1.5 inline-block ${
                    w.status === 'missed' ? 'text-rose-400/60 line-through decoration-rose-400/70'
                    : w.status === 'degraded' ? 'text-amber-300/80 underline decoration-dotted decoration-amber-400/70 underline-offset-2'
                    : 'text-slate-100'
                  }`}
                  title={w.lost_phonemes?.length
                    ? `${t('viz.inaudible')} ${w.lost_phonemes.map((p) => `/${p}/`).join(' ')}` : ''}
                >{w.word}</span>
              ))}
            </p>
          ) : (
            <p className="text-[13px] text-slate-500">
              {listening ? t('conversation.listening') : t('conversation.pressStart')}
            </p>
          )}
        </div>
        {liveWords?.counts && (
          <div className="mt-2 flex flex-wrap gap-3 text-[11.5px] text-slate-500">
            <span className="text-rose-600">{t('conversation.missed', { n: liveWords.counts.missed })}</span>
            <span className="text-amber-600">{t('conversation.degraded', { n: liveWords.counts.degraded })}</span>
            <span className="text-emerald-600">{t('conversation.clear', { n: liveWords.counts.clear })}</span>
            <span className="ml-auto font-semibold">
              {t('conversation.missedPct', { pct: liveWords.missed_pct })}
            </span>
          </div>
        )}
      </div>

      {/* restaurant noise + aid comparison */}
      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
              {t('noise.title')}
            </h2>
            <button onClick={() => setNoiseOn(!noiseOn)}
              className={`rounded-full px-3 py-1 text-[12px] font-semibold transition ${
                noiseOn ? 'bg-amber-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}>{noiseOn ? t('noise.on') : t('noise.off')}</button>
          </div>
          <p className="mt-1.5 text-[12.5px] leading-snug text-slate-500">
            {t('noise.subtitle')}
          </p>
          <div className="mt-3">
            <div className="flex items-center justify-between text-[11.5px] font-medium text-slate-500">
              <span>{t('noise.snr')}</span>
              <span className={`font-bold ${snr <= 0 ? 'text-rose-600' : snr < 8 ? 'text-amber-600' : 'text-emerald-600'}`}>
                {snr > 0 ? '+' : ''}{snr} dB SNR
              </span>
            </div>
            <input type="range" min="-6" max="20" step="1" value={snr}
              disabled={!noiseOn}
              onChange={(e) => setSnr(+e.target.value)}
              className="mt-1.5 w-full accent-amber-500 disabled:opacity-40" />
            <div className="flex justify-between text-[10.5px] text-slate-400">
              <span>{t('noise.pub')}</span><span>{t('noise.cafe')}</span><span>{t('noise.quiet')}</span>
            </div>
          </div>
          {sii && (
            <div className="mt-3 flex items-center gap-3 rounded-xl bg-slate-50 p-3">
              <div>
                <div className="text-[10.5px] font-semibold uppercase tracking-wider text-slate-400">
                  {t('noise.cues')}
                </div>
                <div className="mt-0.5 flex items-baseline gap-2">
                  <span className="text-xl font-bold text-slate-800">
                    {(noiseOn ? sii.noise : sii.quiet).percent}%
                  </span>
                  <span className="text-[11.5px] text-slate-500">
                    {noiseOn ? t('noise.inNoise') : t('noise.inQuiet')}
                  </span>
                </div>
              </div>
              {noiseOn && sii.noise && (
                <div className="ml-auto text-right">
                  <div className="text-[11px] font-semibold text-rose-600">
                    {t('noise.lostPoints', { n: (sii.quiet.percent - sii.noise.percent).toFixed(1) })}
                  </div>
                  <div className="text-[10.5px] text-slate-400">{t('noise.lostToNoise')}</div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h2 className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
            {t('aid.title')}
          </h2>
          <p className="mt-1.5 text-[12.5px] leading-snug text-slate-500">
            {t('aid.subtitle1')} <b>{t('aid.subtitleBold')}</b> {t('aid.subtitle2')}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {['nal', 'flat'].map((k) => (
              <button key={k} onClick={() => setAidType(k)}
                className={`rounded-xl border px-3 py-2.5 text-left transition ${
                  aidType === k
                    ? k === 'nal'
                      ? 'border-emerald-500 bg-emerald-50/60 ring-1 ring-emerald-500'
                      : 'border-amber-500 bg-amber-50/60 ring-1 ring-amber-500'
                    : 'border-slate-200 hover:border-slate-300'
                }`}>
                <div className="text-[12.5px] font-semibold text-slate-800">{t(`aid.${k}.title`)}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">{t(`aid.${k}.sub`)}</div>
              </button>
            ))}
          </div>
          {mode !== 'aided' && (
            <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[11.5px] text-slate-500">
              {t('aid.switchHint1')} <b>{t('aid.switchHintBold')}</b> {t('aid.switchHint2')}
            </div>
          )}
        </div>
      </div>

      {/* everyday sounds */}
      <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <h2 className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
          {t('scapes.title')}
        </h2>
        <p className="mt-1.5 text-[12.5px] text-slate-500">
          {t('scapes.subtitle')}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
          {SOUNDSCAPES.map((s) => (
            <button key={s.id} onClick={() => playScape(s.id)}
              title={t(`scapes.items.${s.id}.why`, { defaultValue: s.why })}
              className={`rounded-xl border px-3 py-3 text-center transition ${
                scape === s.id && source === 'scape'
                  ? 'border-teal-500 bg-teal-50/60 ring-1 ring-teal-500'
                  : 'border-slate-200 hover:border-teal-300 hover:bg-teal-50/30'
              }`}>
              <div className="text-xl">{s.icon}</div>
              <div className="mt-1 text-[12px] font-semibold text-slate-700">{t(`scapes.items.${s.id}.label`, { defaultValue: s.label })}</div>
              <div className="text-[10.5px] text-slate-400">{s.band}</div>
            </button>
          ))}
        </div>
        {scape && source === 'scape' && (
          <div className="mt-3 rounded-lg bg-teal-50/60 px-3 py-2 text-[12px] text-teal-800">
            {t(`scapes.items.${scape}.why`, { defaultValue: SOUNDSCAPES.find((s) => s.id === scape)?.why })}
          </div>
        )}
      </div>

      {/* band attenuation readout */}
      <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <h2 className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
          {t('filter.title', { ear: t(`ears.${ear}Word`) })}
        </h2>
        <div className="mt-3 grid grid-cols-6 gap-2">
          {bandAtten.map(({ f, atten }) => (
            <div key={f} className="rounded-xl bg-slate-50 p-3 text-center">
              <div className="text-[11px] font-semibold text-slate-400">{FREQ_LABELS[f]} Hz</div>
              <div className={`mt-1 text-[15px] font-bold ${
                atten === 0 ? 'text-emerald-600' : atten < 30 ? 'text-amber-600' : 'text-rose-600'
              }`}>−{atten} dB</div>
              <div className="mx-auto mt-2 h-14 w-2 overflow-hidden rounded-full bg-slate-200">
                <div className="w-full rounded-full bg-gradient-to-b from-rose-400 to-rose-600 transition-all duration-500"
                  style={{ height: `${(atten / 70) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
        {prescription && (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50/50 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[12px] font-semibold text-emerald-800">
                {t('filter.prescription', { method: prescription.method })}
              </span>
              <span className="text-[11px] text-emerald-700">
                {t('filter.active')}
              </span>
            </div>
            <div className="mt-2 grid grid-cols-6 gap-2">
              {AC_FREQS.map((f) => (
                <div key={f} className="rounded-lg bg-white/70 py-1.5 text-center">
                  <div className="text-[10.5px] text-slate-400">{FREQ_LABELS[f]}</div>
                  <div className={`text-[13px] font-bold ${
                    prescription.gains[f] > 0 ? 'text-emerald-700' : 'text-slate-300'
                  }`}>+{prescription.gains[f] ?? 0} dB</div>
                </div>
              ))}
            </div>
          </div>
        )}
        <p className="mt-3 text-[11.5px] text-slate-400">
          {t('filter.formula')}
        </p>
      </div>
    </div>
  )
}
