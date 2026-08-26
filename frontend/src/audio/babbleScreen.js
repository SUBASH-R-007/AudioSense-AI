// Speech-in-babble screening: the digit-triplet test against competing talkers.
//
// The digits-in-noise test masks speech with STEADY speech-shaped noise —
// energetic masking only. Real rooms are worse than that: the masker is other
// people talking, which fluctuates at syllable rate and competes for
// attention as well as for the cochlea. This test keeps the identical
// adaptive machinery (same 1-up/1-down track, same SRT-at-50% definition, so
// results are comparable) and swaps only the masker for multi-talker babble.
//
// The babble is synthesized: several independent speech-shaped noise streams,
// each amplitude-modulated by its own syllable-rate envelope, summed. That
// reproduces the two properties that make babble babble — spectral tilt and
// asynchronous syllabic fluctuation — without shipping recordings.
//
// TODO(clinical-audio): replace both synthetic parts with recordings — a
// standard multi-talker babble track (e.g. 6-talker) dropped in as an
// AudioBuffer here, and recorded digit stimuli in place of browser TTS in the
// inherited speak(). The adaptive track and scoring need no change.

import { DigitsInNoiseTest } from './digitsInNoise.js'

//: How many synthetic "talkers" are summed. Six is the classic babble count:
//: few enough that individual voices still fluctuate audibly, many enough
//: that no single gap lets the whole triplet through.
const TALKERS = 6

//: Syllable-rate range for the per-talker envelopes, Hz. Natural speech
//: syllable rate sits around 3-5 per second.
const SYLLABLE_HZ_MIN = 2.5
const SYLLABLE_HZ_MAX = 5.5

export class BabbleScreenTest extends DigitsInNoiseTest {
  /** Multi-talker babble in place of the parent's steady shaped noise. */
  _makeSpeechShapedNoise(ctx) {
    const seconds = 4
    const n = ctx.sampleRate * seconds
    const buf = ctx.createBuffer(1, n, ctx.sampleRate)
    const out = buf.getChannelData(0)

    for (let talker = 0; talker < TALKERS; talker++) {
      // Each talker: its own speech-shaped stream (one-pole low-pass tilt,
      // as in the parent) under its own syllable-rate envelope with a random
      // rate and phase, so the talkers never pause in unison.
      const rate = SYLLABLE_HZ_MIN + Math.random() * (SYLLABLE_HZ_MAX - SYLLABLE_HZ_MIN)
      const phase = Math.random() * 2 * Math.PI
      // A second, slower drift makes the envelope irregular rather than a
      // metronomic tremolo — babble surges, it does not pulse.
      const driftRate = 0.3 + Math.random() * 0.5
      const driftPhase = Math.random() * 2 * Math.PI
      let last = 0
      for (let i = 0; i < n; i++) {
        const white = Math.random() * 2 - 1
        last = 0.85 * last + 0.15 * white
        const tSec = i / ctx.sampleRate
        const syllable = 0.55 + 0.45 * Math.sin(2 * Math.PI * rate * tSec + phase)
        const drift = 0.7 + 0.3 * Math.sin(2 * Math.PI * driftRate * tSec + driftPhase)
        out[i] += last * syllable * drift
      }
    }

    // Normalise the sum back to roughly the parent's single-stream level, so
    // the SNR the adaptive track reports means the same thing in both tests.
    let peak = 0
    for (let i = 0; i < n; i++) peak = Math.max(peak, Math.abs(out[i]))
    const norm = peak > 0 ? 2.2 / peak : 1
    for (let i = 0; i < n; i++) out[i] *= norm

    return buf
  }
}
