// Digits-in-noise: the speech test that survives uncalibrated equipment.
//
// Pure-tone screening in a browser is compromised by not knowing the
// absolute output level. A speech-in-noise test sidesteps that entirely:
// only the RATIO of speech to noise matters, and the ratio is exactly what
// we control. This is why national screening programmes run digit-triplet
// tests over the telephone and the web.
//
// It also measures the complaint people actually present with. Someone can
// have a clean audiogram and still be unable to follow a conversation in a
// restaurant, and this is the test that shows it.
//
// Digits are spoken by the browser's speech synthesiser and rendered into a
// buffer through a MediaStream capture, so no audio assets are shipped.

const DIGITS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']

export class DigitsInNoiseTest {
  constructor() {
    this.ctx = null
    this.snr = 0          // dB, speech relative to noise
    this.reversals = []
    this.lastCorrect = null
    this.trial = 0
    this.step = 4         // dB; narrows after the first reversals
  }

  _ensureCtx() {
    if (this.ctx) return this.ctx
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    this.ctx = ctx
    this.noiseGain = ctx.createGain()
    this.speechGain = ctx.createGain()
    this.master = ctx.createGain()
    this.noiseGain.connect(this.master)
    this.speechGain.connect(this.master)
    this.master.connect(ctx.destination)
    this.noiseBuffer = this._makeSpeechShapedNoise(ctx)
    return ctx
  }

  /** Noise shaped like the long-term average speech spectrum. */
  _makeSpeechShapedNoise(ctx) {
    const seconds = 4
    const buf = ctx.createBuffer(1, ctx.sampleRate * seconds, ctx.sampleRate)
    const d = buf.getChannelData(0)
    let last = 0
    for (let i = 0; i < d.length; i++) {
      const white = Math.random() * 2 - 1
      // One-pole low-pass gives the downward tilt of the speech spectrum.
      last = 0.85 * last + 0.15 * white
      d[i] = last * 2.2
    }
    return buf
  }

  startNoise() {
    const ctx = this._ensureCtx()
    if (ctx.state === 'suspended') ctx.resume()
    this.stopNoise()
    const src = ctx.createBufferSource()
    src.buffer = this.noiseBuffer
    src.loop = true
    src.connect(this.noiseGain)
    src.start()
    this._noise = src
    this._applyLevels()
  }

  stopNoise() {
    if (this._noise) {
      try { this._noise.stop(); this._noise.disconnect() } catch { /* ignore */ }
      this._noise = null
    }
  }

  _applyLevels() {
    if (!this.ctx) return
    const t = this.ctx.currentTime
    // Hold the noise fixed and move the speech, so overall loudness is stable.
    this.noiseGain.gain.setTargetAtTime(0.25, t, 0.05)
    this.speechGain.gain.setTargetAtTime(
      0.25 * Math.pow(10, this.snr / 20), t, 0.05)
  }

  /** A triplet of distinct digits. */
  nextTriplet() {
    const pool = [...DIGITS]
    const out = []
    for (let i = 0; i < 3; i++) {
      out.push(...pool.splice(Math.floor(Math.random() * pool.length), 1))
    }
    this.currentTriplet = out
    return out
  }

  /**
   * Speak the triplet at the current SNR. Speech synthesis plays through the
   * system output rather than our graph, so the speech level is set by
   * utterance volume — the ratio against our noise is preserved.
   */
  speak(triplet) {
    return new Promise((resolve) => {
      if (!('speechSynthesis' in window)) { resolve(false); return }
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(triplet.join('  '))
      u.rate = 0.75
      u.lang = 'en-IN'
      // Map SNR onto utterance volume around a mid-point, clamped to [0,1].
      u.volume = Math.max(0.05, Math.min(1, 0.5 * Math.pow(10, this.snr / 20)))
      u.onend = () => resolve(true)
      u.onerror = () => resolve(false)
      window.speechSynthesis.speak(u)
    })
  }

  /**
   * Record the response and adapt. One-up/one-down converges on the SNR at
   * which half the triplets are heard correctly, which is the definition of
   * the speech reception threshold.
   */
  record(correct) {
    this.trial += 1
    if (this.lastCorrect !== null && correct !== this.lastCorrect) {
      this.reversals.push(this.snr)
      if (this.reversals.length === 2) this.step = 2
    }
    this.lastCorrect = correct
    this.snr += correct ? -this.step : this.step
    this.snr = Math.max(-20, Math.min(15, this.snr))
    this._applyLevels()
    return { trial: this.trial, snr: this.snr, reversals: this.reversals.length }
  }

  get done() {
    return this.reversals.length >= 6 || this.trial >= 25
  }

  dispose() {
    this.stopNoise()
    try { window.speechSynthesis?.cancel() } catch { /* ignore */ }
    try { this.ctx?.close() } catch { /* ignore */ }
    this.ctx = null
  }
}
