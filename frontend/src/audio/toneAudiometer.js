// In-browser pure-tone screening — Web Audio tone generator.
//
// Produces pulsed pure tones at a requested dB HL, panned to one ear, for
// the modified Hughson-Westlake procedure on the Screening page.
//
// CALIBRATION HONESTY: a browser + consumer headphones is not a calibrated
// audiometer. Two corrections make the result *useful as a screening*:
//   1. A user calibration step anchors 40 dB HL to a "just comfortable"
//      level at 1 kHz, absorbing system volume and headphone sensitivity.
//   2. Per-frequency RETSPL offsets (ISO 389-1 / TDH-39 reference
//      equivalent threshold SPLs) correct for the fact that 0 dB HL is a
//      different sound pressure at every frequency.
// Results are labelled a screening, never a diagnostic audiogram.

//: RETSPL for supra-aural earphones, dB SPL for 0 dB HL (ISO 389-1).
const RETSPL = { 250: 25.5, 500: 11.5, 1000: 7, 2000: 9, 4000: 9.5, 8000: 13 }
const REF_FREQ = 1000
const ANCHOR_HL = 40 // the level the calibration step sets

export const SCREEN_FREQS = [1000, 2000, 4000, 8000, 500, 250] // clinical order

export class ToneAudiometer {
  constructor() {
    this.ctx = null
    // Linear gain that renders ANCHOR_HL at 1 kHz. Adjusted by the user.
    this.anchorGain = 0.05
  }

  _ensureCtx() {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)()
      this.master = this.ctx.createGain()
      this.master.gain.value = 1
      this.master.connect(this.ctx.destination)
    }
    if (this.ctx.state === 'suspended') this.ctx.resume()
    return this.ctx
  }

  setAnchorGain(g) {
    this.anchorGain = Math.min(0.6, Math.max(0.0005, g))
  }

  /** Linear amplitude for a level in dB HL at a given frequency. */
  amplitudeFor(freq, dbHL) {
    const retsplOffset = (RETSPL[freq] ?? RETSPL[REF_FREQ]) - RETSPL[REF_FREQ]
    const db = dbHL - ANCHOR_HL + retsplOffset
    return Math.min(0.95, this.anchorGain * Math.pow(10, db / 20))
  }

  /** Play a pulsed tone. ear: 'right' | 'left'. Resolves when finished. */
  playTone(freq, dbHL, ear = 'right', { pulses = 3, pulseMs = 220, gapMs = 130 } = {}) {
    const ctx = this._ensureCtx()
    const amp = this.amplitudeFor(freq, dbHL)

    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = freq

    const env = ctx.createGain()
    env.gain.value = 0

    const panner = ctx.createStereoPanner()
    panner.pan.value = ear === 'right' ? 1 : -1

    osc.connect(env)
    env.connect(panner)
    panner.connect(this.master)

    const t0 = ctx.currentTime + 0.05
    const ramp = 0.02 // click-free rise/fall
    let t = t0
    for (let i = 0; i < pulses; i++) {
      env.gain.setValueAtTime(0.0001, t)
      env.gain.exponentialRampToValueAtTime(Math.max(0.0002, amp), t + ramp)
      env.gain.setValueAtTime(Math.max(0.0002, amp), t + pulseMs / 1000 - ramp)
      env.gain.exponentialRampToValueAtTime(0.0001, t + pulseMs / 1000)
      t += (pulseMs + gapMs) / 1000
    }
    osc.start(t0)
    osc.stop(t + 0.05)
    this._current = { osc, env }

    return new Promise((resolve) => {
      osc.onended = () => {
        try { osc.disconnect(); env.disconnect(); panner.disconnect() } catch { /* ignore */ }
        this._current = null
        resolve()
      }
    })
  }

  /** Continuous reference tone for the calibration step. */
  startCalibrationTone(freq = REF_FREQ) {
    const ctx = this._ensureCtx()
    this.stopCalibrationTone()
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = freq
    const g = ctx.createGain()
    g.gain.value = this.anchorGain
    osc.connect(g)
    g.connect(this.master)
    osc.start()
    this._cal = { osc, g }
  }

  updateCalibrationTone() {
    if (this._cal) {
      this._cal.g.gain.setTargetAtTime(this.anchorGain, this.ctx.currentTime, 0.02)
    }
  }

  stopCalibrationTone() {
    if (this._cal) {
      try { this._cal.osc.stop(); this._cal.osc.disconnect(); this._cal.g.disconnect() } catch { /* ignore */ }
      this._cal = null
    }
  }

  dispose() {
    this.stopCalibrationTone()
    try { this.ctx?.close() } catch { /* ignore */ }
    this.ctx = null
  }
}

/**
 * Modified Hughson-Westlake (ASHA 2005) staircase state machine.
 *
 * Start at 40 dB HL. After a response: down 10 dB. After no response:
 * up 5 dB. Threshold = the lowest level with responses on at least 2 of 3
 * ascending presentations.
 */
export class Staircase {
  constructor(start = 40, min = -10, max = 90) {
    this.level = start
    this.min = min
    this.max = max
    this.ascending = false // true once we've had a first no-response
    this.responsesAt = new Map() // level -> {heard, total} on ascending runs
    this.done = false
    this.threshold = null
    this.presentations = 0
  }

  record(heard) {
    this.presentations += 1
    if (this.ascending) {
      const e = this.responsesAt.get(this.level) || { heard: 0, total: 0 }
      e.total += 1
      if (heard) e.heard += 1
      this.responsesAt.set(this.level, e)
      if (heard && e.heard >= 2) {
        this.done = true
        this.threshold = this.level
        return this.threshold
      }
    }

    if (heard) {
      this.level = Math.max(this.min, this.level - 10)
    } else {
      this.ascending = true
      this.level = Math.min(this.max, this.level + 5)
      if (this.level >= this.max && this.presentations > 4) {
        // No response at the output ceiling.
        this.done = true
        this.threshold = 'NR'
        return this.threshold
      }
    }

    if (this.presentations > 30) { // safety stop
      this.done = true
      this.threshold = this.level
    }
    return null
  }
}
