// MODULE 4 — Hearing Loss Simulator audio engine (Web Audio API).
//
// Graph:  source ─ inputGain ─┬─ dryGain ──────────────────────────────────────┐
//                             └─ aid filters ─ compressor ─ loss filters ─ shaper ─ wetGain ─┴─ master ─ analyser ─ out
//
// The wet chain models the signal path in physical order: a hearing aid
// (NAL-R insertion gain + output compression, bypassed unless "aided" mode
// is active) feeds the impaired ear, whose loss is a cascade of one
// BiquadFilter per audiometric band attenuating by the patient's AC
// threshold relative to normal hearing (0–20 dB HL).
//
// Three states crossfade cleanly:
//   normal  → dry path (unfiltered reference)
//   patient → loss filters only
//   aided   → aid gain + compression, then the same loss filters
//
// Optional soft-clip WaveShaper approximates the distortion percept of
// severe sensorineural loss, which amplification cannot undo — that's why
// the aided state improves audibility without fully restoring clarity.

const BANDS = [
  { freq: 250, type: 'lowshelf' },
  { freq: 500, type: 'peaking', Q: 1.1 },
  { freq: 1000, type: 'peaking', Q: 1.1 },
  { freq: 2000, type: 'peaking', Q: 1.1 },
  { freq: 4000, type: 'peaking', Q: 1.1 },
  { freq: 8000, type: 'highshelf' },
]

const XFADE = 0.08 // seconds

function softClipCurve(amount = 12) {
  const n = 1024
  const curve = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const x = (i / (n - 1)) * 2 - 1
    curve[i] = Math.tanh(amount * x) / Math.tanh(amount)
  }
  return curve
}

export class HearingSimulator {
  constructor() {
    this.ctx = null
    this.mode = 'normal' // 'normal' | 'patient' | 'aided'
    this.aidGains = null
    this.aidType = 'nal' // 'nal' | 'flat'
    this.snrDb = 5
    this.distortion = false
    this.playing = false
    this.sourceKind = 'sample' // 'sample' | 'file' | 'mic'
    this.buffer = null
    this._srcNode = null
    this._micStream = null
  }

  _ensureCtx() {
    if (this.ctx) return
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    this.ctx = ctx

    this.inputGain = ctx.createGain()
    this.dryGain = ctx.createGain()
    this.wetGain = ctx.createGain()
    this.master = ctx.createGain()
    this.analyser = ctx.createAnalyser()
    this.analyser.fftSize = 256
    this.analyser.smoothingTimeConstant = 0.75

    const makeBank = () =>
      BANDS.map((b) => {
        const f = ctx.createBiquadFilter()
        f.type = b.type
        f.frequency.value = b.freq
        if (b.Q) f.Q.value = b.Q
        f.gain.value = 0
        return f
      })

    this.aidFilters = makeBank() // hearing-aid insertion gain (positive)
    this.filters = makeBank() // the ear's loss (negative)

    // Wide-dynamic-range compression, as in a real hearing aid: keeps the
    // amplified signal below the wearer's discomfort level. A compressor
    // alone only ever attenuates, so — like a real device — it is paired
    // with makeup gain that restores what the compression took away.
    this.compressor = ctx.createDynamicsCompressor()
    this.compressor.threshold.value = -10
    this.compressor.knee.value = 20
    this.compressor.ratio.value = 2.5
    this.compressor.attack.value = 0.005
    this.compressor.release.value = 0.12
    this.makeup = ctx.createGain()
    this.makeup.gain.value = 1

    this.shaper = ctx.createWaveShaper()
    this.shaper.curve = null // bypass until enabled
    this.shaperWrapIn = ctx.createGain()

    // Competing babble: speech-shaped noise mixed in ahead of everything,
    // so both the normal and impaired paths hear the same restaurant.
    this.noiseGain = ctx.createGain()
    this.noiseGain.gain.value = 0
    this.noiseGain.connect(this.inputGain)

    // dry path
    this.inputGain.connect(this.dryGain)
    this.dryGain.connect(this.master)
    // wet path: aid → compression → ear's loss → distortion
    let node = this.inputGain
    for (const f of this.aidFilters) {
      node.connect(f)
      node = f
    }
    node.connect(this.compressor)
    this.compressor.connect(this.makeup)
    node = this.makeup
    for (const f of this.filters) {
      node.connect(f)
      node = f
    }
    node.connect(this.shaperWrapIn)
    this.shaperWrapIn.connect(this.shaper)
    this.shaper.connect(this.wetGain)
    this.wetGain.connect(this.master)

    this.master.connect(this.analyser)
    this.analyser.connect(ctx.destination)

    this._applyMode(true)
  }

  async loadSampleUrl(url) {
    this._ensureCtx()
    const res = await fetch(url)
    this.buffer = await this.ctx.decodeAudioData(await res.arrayBuffer())
    this.sourceKind = 'sample'
  }

  async loadFile(file) {
    this._ensureCtx()
    this.buffer = await this.ctx.decodeAudioData(await file.arrayBuffer())
    this.sourceKind = 'file'
  }

  // Fallback if the bundled WAV is missing: a speech-like tone complex.
  synthesizeFallback(seconds = 6) {
    this._ensureCtx()
    const sr = this.ctx.sampleRate
    const buf = this.ctx.createBuffer(1, sr * seconds, sr)
    const d = buf.getChannelData(0)
    const partials = [
      [220, 0.30], [440, 0.22], [880, 0.16], [1760, 0.12],
      [3520, 0.10], [5000, 0.07], [7000, 0.05],
    ]
    for (let i = 0; i < d.length; i++) {
      const t = i / sr
      const syllable = 0.55 + 0.45 * Math.sin(2 * Math.PI * 3.1 * t) // AM ~ speech rate
      let s = 0
      for (const [f, a] of partials) s += a * Math.sin(2 * Math.PI * f * t)
      s += 0.05 * (Math.random() * 2 - 1) // fricative-ish noise
      d[i] = s * syllable * 0.5
    }
    this.buffer = buf
    this.sourceKind = 'sample'
  }

  async useMic() {
    this._ensureCtx()
    this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    this.sourceKind = 'mic'
  }

  releaseMic() {
    this._micStream?.getTracks().forEach((t) => t.stop())
    this._micStream = null
  }

  start() {
    this._ensureCtx()
    if (this.ctx.state === 'suspended') this.ctx.resume()
    this.stop()
    if (this.sourceKind === 'mic') {
      if (!this._micStream) return
      this._srcNode = this.ctx.createMediaStreamSource(this._micStream)
      this._srcNode.connect(this.inputGain)
    } else {
      if (!this.buffer) return
      const src = this.ctx.createBufferSource()
      src.buffer = this.buffer
      src.loop = true
      src.connect(this.inputGain)
      src.start()
      this._srcNode = src
    }
    this.playing = true
  }

  stop() {
    if (this._srcNode) {
      try { if (this._srcNode.stop) this._srcNode.stop() } catch { /* already stopped */ }
      try { this._srcNode.disconnect() } catch { /* ignore */ }
      this._srcNode = null
    }
    this.playing = false
  }

  /**
   * Binaural mode: process each ear with its own audiogram in true stereo,
   * so asymmetric loss is heard as a lateralised world rather than an
   * averaged one. Optional head shadow attenuates the far ear above 1.5 kHz,
   * as the skull itself does — which is why speech from the bad side
   * genuinely disappears rather than merely getting quieter.
   */
  setBinaural(enabled, rightThresholds, leftThresholds, headShadow = true) {
    this._ensureCtx()
    this.binaural = enabled
    if (!enabled) {
      this._teardownBinaural()
      return
    }
    const ctx = this.ctx
    if (!this._bin) {
      const merger = ctx.createChannelMerger(2)
      const build = (pan) => {
        const split = ctx.createGain()
        const bank = BANDS.map((b) => {
          const f = ctx.createBiquadFilter()
          f.type = b.type
          f.frequency.value = b.freq
          if (b.Q) f.Q.value = b.Q
          f.gain.value = 0
          return f
        })
        const shadow = ctx.createBiquadFilter()
        shadow.type = 'highshelf'
        shadow.frequency.value = 1500
        shadow.gain.value = 0
        let n = split
        for (const f of bank) { n.connect(f); n = f }
        n.connect(shadow)
        return { split, bank, shadow }
      }
      const right = build()
      const left = build()
      right.shadow.connect(merger, 0, 0)
      left.shadow.connect(merger, 0, 1)
      this._bin = { merger, right, left }
    }
    // Re-route the wet chain output through the binaural pair.
    try { this.shaper.disconnect() } catch { /* ignore */ }
    this.shaper.connect(this._bin.right.split)
    this.shaper.connect(this._bin.left.split)
    this._bin.merger.connect(this.wetGain)

    for (const [side, thresholds] of [['right', rightThresholds], ['left', leftThresholds]]) {
      const node = this._bin[side]
      for (const [i, b] of BANDS.entries()) {
        const raw = thresholds?.[b.freq]
        const db = raw === 'NR' ? 120 : raw ?? 0
        node.bank[i].gain.setTargetAtTime(
          -Math.min(70, Math.max(0, db - 20)), ctx.currentTime, 0.03)
      }
      node.shadow.gain.setTargetAtTime(headShadow ? -6 : 0, ctx.currentTime, 0.05)
    }
    // The mono loss bank must not double-apply the attenuation.
    for (const f of this.filters) f.gain.setTargetAtTime(0, ctx.currentTime, 0.03)
  }

  _teardownBinaural() {
    if (!this._bin) return
    try { this.shaper.disconnect() } catch { /* ignore */ }
    try { this._bin.merger.disconnect() } catch { /* ignore */ }
    this.shaper.connect(this.wetGain)
    this._bin = null
    if (this._lastThresholds) this.setThresholds(this._lastThresholds)
  }

  /** thresholds: {250: dB|'NR'|undefined, ...} — attenuation per band. */
  setThresholds(thresholds) {
    this._lastThresholds = thresholds
    this._ensureCtx()
    this.bandGains = {}
    for (const [i, b] of BANDS.entries()) {
      const raw = thresholds?.[b.freq]
      const db = raw === 'NR' ? 120 : raw ?? 0
      const atten = -Math.min(70, Math.max(0, db - 20))
      this.bandGains[b.freq] = atten
      // In binaural mode the per-ear banks own the attenuation instead.
      if (!this.binaural) {
        this.filters[i].gain.setTargetAtTime(atten, this.ctx.currentTime, 0.03)
      }
    }
    return this.bandGains
  }

  /** Severity heuristic: average attenuation of the wet chain, dB. */
  severity() {
    const v = Object.values(this.bandGains || {})
    return v.length ? -v.reduce((a, b) => a + b, 0) / v.length : 0
  }

  /** gains: {250: dB, …} NAL-R insertion gain applied only in aided mode. */
  setAidGains(gains) {
    this._ensureCtx()
    this.aidGains = gains || null
    this._applyAid()
    return this.aidGains
  }

  /**
   * 'nal' = prescription-shaped gain; 'flat' = the cheap roadside amplifier
   * that raises every band equally. Same average output, very different
   * intelligibility — which is the whole argument for proper fitting.
   */
  setAidType(type) {
    this.aidType = type
    this._applyAid()
  }

  _effectiveAidGains() {
    if (!this.aidGains) return null
    if (this.aidType !== 'flat') return this.aidGains
    const values = Object.values(this.aidGains)
    const mean = values.reduce((a, b) => a + b, 0) / (values.length || 1)
    return Object.fromEntries(Object.keys(this.aidGains).map((f) => [f, mean]))
  }

  _applyAid() {
    if (!this.ctx) return
    const gains = this.mode === 'aided' ? this._effectiveAidGains() : null
    for (const [i, b] of BANDS.entries()) {
      const g = gains ? Math.min(45, Math.max(0, gains[b.freq] ?? 0)) : 0
      this.aidFilters[i].gain.setTargetAtTime(g, this.ctx.currentTime, 0.03)
    }
    this._startMakeup(Boolean(gains))
  }

  /** Track the compressor's gain reduction and give it back, as a real aid does. */
  _startMakeup(active) {
    clearInterval(this._makeupTimer)
    if (!active) {
      this.makeup.gain.setTargetAtTime(1, this.ctx.currentTime, 0.05)
      return
    }
    this._makeupTimer = setInterval(() => {
      if (!this.ctx) return
      const reductionDb = this.compressor.reduction // ≤ 0
      const target = Math.min(8, Math.pow(10, -reductionDb / 20))
      this.makeup.gain.setTargetAtTime(target, this.ctx.currentTime, 0.08)
    }, 100)
  }

  /**
   * Competing babble at a given signal-to-noise ratio, in dB.
   * Speech-shaped noise modulated at a conversational syllable rate
   * approximates a room full of other talkers.
   */
  setNoiseSNR(snrDb, enabled = true) {
    this._ensureCtx()
    this.snrDb = snrDb
    if (!enabled) {
      this.noiseGain.gain.setTargetAtTime(0, this.ctx.currentTime, 0.05)
      this._stopNoise()
      return
    }
    if (!this._noiseSrc) this._startNoise()
    // 0 dB SNR = babble at the same level as the speech.
    const level = Math.pow(10, -snrDb / 20) * 0.5
    this.noiseGain.gain.setTargetAtTime(level, this.ctx.currentTime, 0.05)
  }

  _startNoise() {
    const ctx = this.ctx
    const sr = ctx.sampleRate
    const buf = ctx.createBuffer(1, sr * 4, sr)
    const d = buf.getChannelData(0)
    for (let i = 0; i < d.length; i++) {
      const t = i / sr
      // Several independent modulations ≈ overlapping voices.
      const env = 0.6 + 0.4 * Math.sin(2 * Math.PI * 2.7 * t)
        * Math.sin(2 * Math.PI * 1.3 * t + 1.1)
      d[i] = (Math.random() * 2 - 1) * env
    }
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.loop = true

    // Shape white noise to the long-term average speech spectrum.
    const tilt = ctx.createBiquadFilter()
    tilt.type = 'lowshelf'
    tilt.frequency.value = 500
    tilt.gain.value = 6
    const roll = ctx.createBiquadFilter()
    roll.type = 'lowpass'
    roll.frequency.value = 4000
    roll.Q.value = 0.7

    src.connect(tilt)
    tilt.connect(roll)
    roll.connect(this.noiseGain)
    src.start()
    this._noiseSrc = src
  }

  _stopNoise() {
    if (this._noiseSrc) {
      try { this._noiseSrc.stop(); this._noiseSrc.disconnect() } catch { /* ignore */ }
      this._noiseSrc = null
    }
  }

  setMode(mode) {
    this.mode = mode
    this._applyAid()
    this._applyMode()
  }

  _applyMode(immediate = false) {
    const t = this.ctx.currentTime
    const dry = this.mode === 'normal' ? 1 : 0
    if (immediate) {
      this.dryGain.gain.value = dry
      this.wetGain.gain.value = 1 - dry
    } else {
      this.dryGain.gain.cancelScheduledValues(t)
      this.wetGain.gain.cancelScheduledValues(t)
      this.dryGain.gain.linearRampToValueAtTime(dry, t + XFADE)
      this.wetGain.gain.linearRampToValueAtTime(1 - dry, t + XFADE)
    }
  }

  setDistortion(on) {
    this._ensureCtx()
    this.distortion = on
    this.shaper.curve = on ? softClipCurve(10) : null
  }

  dispose() {
    this.stop()
    clearInterval(this._makeupTimer)
    this._stopNoise()
    this.releaseMic()
    this.ctx?.close()
    this.ctx = null
  }
}
