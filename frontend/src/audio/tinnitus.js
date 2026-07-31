// Tinnitus matching and notched sound therapy.
//
// Tinnitus cannot be measured, only matched: the patient adjusts a tone
// until it resembles what they hear. The matched pitch almost always falls
// inside their region of hearing loss, and the matched loudness is almost
// always only a few decibels above their own threshold — which is the most
// useful thing a clinician can tell a distressed patient, because it
// separates how loud the sound is from how much it intrudes.
//
// Notched sound therapy removes a half-octave band centred on the matched
// pitch from a noise carrier. The reasoning is lateral inhibition: stimulate
// the neighbours of the tinnitus frequency while starving the frequency
// itself. The evidence is mixed and it is not a cure; it is offered
// alongside counselling and amplification.

export class TinnitusTool {
  constructor() {
    this.ctx = null
    this.pitch = 4000
    this.levelDb = 20
  }

  _ensureCtx() {
    if (this.ctx) return this.ctx
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    this.ctx = ctx
    this.master = ctx.createGain()
    this.master.gain.value = 0.6
    this.master.connect(ctx.destination)
    return ctx
  }

  _resume() {
    const ctx = this._ensureCtx()
    if (ctx.state === 'suspended') ctx.resume()
    return ctx
  }

  /** Continuous tone the patient tunes to match their tinnitus. */
  startMatchTone(pitchHz = this.pitch, levelDb = this.levelDb, ear = 'both') {
    const ctx = this._resume()
    this.stopMatchTone()
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = pitchHz

    const gain = ctx.createGain()
    gain.gain.value = this._amplitude(levelDb)

    const panner = ctx.createStereoPanner()
    panner.pan.value = ear === 'right' ? 1 : ear === 'left' ? -1 : 0

    osc.connect(gain); gain.connect(panner); panner.connect(this.master)
    osc.start()
    this._match = { osc, gain, panner }
    this.pitch = pitchHz
    this.levelDb = levelDb
  }

  setPitch(hz) {
    this.pitch = hz
    if (this._match) {
      this._match.osc.frequency.setTargetAtTime(hz, this.ctx.currentTime, 0.02)
    }
  }

  setLevel(db) {
    this.levelDb = db
    if (this._match) {
      this._match.gain.gain.setTargetAtTime(
        this._amplitude(db), this.ctx.currentTime, 0.02)
    }
  }

  /** Sensation level mapped to amplitude; 0 dB SL is near-inaudible. */
  _amplitude(db) {
    return Math.min(0.5, 0.0006 * Math.pow(10, Math.max(0, db) / 20))
  }

  stopMatchTone() {
    if (this._match) {
      try {
        this._match.osc.stop()
        this._match.osc.disconnect()
        this._match.gain.disconnect()
        this._match.panner.disconnect()
      } catch { /* ignore */ }
      this._match = null
    }
  }

  /**
   * Notched noise: broadband carrier with a half-octave band removed around
   * the matched pitch. Two cascaded high-Q notch filters make the gap deep
   * enough to matter.
   */
  startNotchedMasker(pitchHz = this.pitch, gain = 0.25) {
    const ctx = this._resume()
    this.stopMasker()

    const seconds = 4
    const buf = ctx.createBuffer(1, ctx.sampleRate * seconds, ctx.sampleRate)
    const d = buf.getChannelData(0)
    let last = 0
    for (let i = 0; i < d.length; i++) {
      const white = Math.random() * 2 - 1
      last = 0.7 * last + 0.3 * white     // gentle pink-ish tilt
      d[i] = last * 1.6
    }
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.loop = true

    const notch1 = ctx.createBiquadFilter()
    notch1.type = 'notch'
    notch1.frequency.value = pitchHz
    notch1.Q.value = 2.8
    const notch2 = ctx.createBiquadFilter()
    notch2.type = 'notch'
    notch2.frequency.value = pitchHz
    notch2.Q.value = 2.8

    const out = ctx.createGain()
    out.gain.value = gain

    src.connect(notch1); notch1.connect(notch2); notch2.connect(out)
    out.connect(this.master)
    src.start()
    this._masker = { src, out, notch1, notch2 }
    return {
      centre: Math.round(pitchHz),
      low: Math.round(pitchHz / Math.SQRT2 ** 0.5),
      high: Math.round(pitchHz * Math.SQRT2 ** 0.5),
    }
  }

  /** Plain broadband noise, for the minimum-masking-level measurement. */
  startPlainMasker(gain = 0.25) {
    const ctx = this._resume()
    this.stopMasker()
    const buf = ctx.createBuffer(1, ctx.sampleRate * 3, ctx.sampleRate)
    const d = buf.getChannelData(0)
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * 0.7
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.loop = true
    const out = ctx.createGain()
    out.gain.value = gain
    src.connect(out); out.connect(this.master)
    src.start()
    this._masker = { src, out }
  }

  setMaskerLevel(gain) {
    if (this._masker) {
      this._masker.out.gain.setTargetAtTime(gain, this.ctx.currentTime, 0.03)
    }
  }

  stopMasker() {
    if (this._masker) {
      try {
        this._masker.src.stop()
        this._masker.src.disconnect()
        this._masker.out.disconnect()
      } catch { /* ignore */ }
      this._masker = null
    }
  }

  dispose() {
    this.stopMatchTone()
    this.stopMasker()
    try { this.ctx?.close() } catch { /* ignore */ }
    this.ctx = null
  }
}
