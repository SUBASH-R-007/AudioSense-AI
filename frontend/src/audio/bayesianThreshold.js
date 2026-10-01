// Bayesian adaptive threshold estimation (QUEST/ZEST family).
//
// The classic Hughson-Westlake staircase throws away information: it only
// remembers the last reversal, needs 7-11 presentations per frequency, and
// returns a bare number with no idea how sure it is.
//
// Instead we maintain a full posterior over threshold. Every response —
// heard or not — updates the whole distribution via Bayes' rule against a
// psychometric function. We then present the level that will be most
// informative next, and stop as soon as the 95% credible interval is tight
// enough.
//
// Measured against the Staircase in toneAudiometer.js, both driven exactly as
// ScreeningRunner drives them, over 1,000 simulated listeners x 12 thresholds
// (true thresholds uniform over 0-70 dB HL in whole dB; cumulative-normal
// psychometric function with a 4 dB spread, 3% lapses, 2% false alarms).
// Each result is scored against the listener's clinical threshold — the
// lowest 5-dB step they respond to at least half the time:
//
//                          presentations   bias     mean |error|   off >10 dB
//   Bayesian (this file)        9.3        +0.0 dB     1.8 dB         0.16%
//   Hughson-Westlake           10.6        +0.3 dB     2.2 dB         0.03%
//
// (Silent catch trials add about 12% to both.) So the gain in speed and
// accuracy is modest, it misses by more than 10 dB a little more often, and
// the headline benefit is that every threshold arrives with an error bar,
// which a staircase fundamentally cannot give.
//
//   P(heard | level, threshold) = guess + (1 - guess - lapse) * Φ((L - T)/β)
//
// β is the psychometric slope, and the lapse/guess terms absorb the fact
// that real listeners occasionally miss an audible tone or respond to
// nothing.

const GUESS = 0.02   // responds with no stimulus present
const LAPSE = 0.03   // misses a clearly audible tone
const SLOPE = 4.5    // dB; spread of the psychometric function
//: dB of posterior kept beyond each end of the presentable range. Without it
//: the posterior cannot express "does not hear even the loudest tone", and a
//: dead ear would be reported as a number at a level that was never heard.
const EDGE = 20

/** Logistic approximation to the cumulative normal — cheap and adequate. */
function psi(level, threshold) {
  const z = (level - threshold) / SLOPE
  const p = 1 / (1 + Math.exp(-1.7 * z))
  return GUESS + (1 - GUESS - LAPSE) * p
}

export class BayesianThreshold {
  /**
   * @param {number} min lowest testable level, dB HL
   * @param {number} max highest testable level, dB HL
   * @param {number} prior centre of the prior, dB HL
   */
  constructor(min = -10, max = 90, prior = 30) {
    this.min = min
    this.max = max
    this.step = 1
    this.grid = []
    // Presentations stay within [min, max]; the threshold itself may lie
    // outside it, and the posterior has to be able to say so.
    for (let t = min - EDGE; t <= max + EDGE; t += this.step) this.grid.push(t)

    // Broad Gaussian prior — informative enough to start sensibly, weak
    // enough that a few responses dominate it.
    const sd = 25
    this.post = this.grid.map((t) => Math.exp(-0.5 * ((t - prior) / sd) ** 2))
    this._normalize()

    this.trials = []
    this.done = false
    this.threshold = null
  }

  _normalize() {
    const sum = this.post.reduce((a, b) => a + b, 0) || 1
    this.post = this.post.map((p) => p / sum)
  }

  get mean() {
    return this.grid.reduce((acc, t, i) => acc + t * this.post[i], 0)
  }

  get sd() {
    const m = this.mean
    return Math.sqrt(this.grid.reduce((acc, t, i) => acc + this.post[i] * (t - m) ** 2, 0))
  }

  /** Smallest grid level with at least `q` of the posterior mass at or below it. */
  _quantile(q) {
    let cum = 0
    for (let i = 0; i < this.grid.length; i++) {
      cum += this.post[i]
      if (cum >= q) return this.grid[i]
    }
    return this.grid[this.grid.length - 1]
  }

  /**
   * Equal-tailed 95% credible interval, in dB, clamped to the presentable
   * range — a bound beyond it would quote a level the procedure cannot play.
   */
  credibleInterval(mass = 0.95) {
    const tail = (1 - mass) / 2
    const clamp = (t) => Math.min(this.max, Math.max(this.min, t))
    return [clamp(this._quantile(tail)), clamp(this._quantile(1 - tail))]
  }

  /**
   * The threshold on the clinical convention, not the psychometric midpoint.
   *
   * ASHA (2005), Guidelines for Manual Pure-Tone Threshold Audiometry:
   * threshold is "the lowest decibel hearing level at which responses occur
   * in at least one half of a series of ascending trials", in 5-dB steps. The
   * posterior is over T, the level heard half the time (psi's midpoint, to
   * within 0.1 dB of the guess/lapse asymmetry). A listener with midpoint T
   * responds at least half the time at every step at or above T, so their
   * clinical threshold is the lowest 5-dB step at or above T: ceil(T / 5) * 5.
   * That mapping is monotone, so the posterior median of the clinical
   * threshold is that same step taken at the posterior median of T — the
   * estimate that minimises the expected absolute error in dB.
   *
   * Rounding the posterior mean to the NEAREST step would report the
   * midpoint instead, which sits about half a step below the lowest level
   * reliably heard: one step too good, always in the same direction.
   *
   * Beyond the presentable range: a median below `min` reports `min` (heard
   * at the softest level the procedure can play), and a median above `max`
   * reports 'NR' — no response at the highest level, as the staircase does.
   */
  clinicalThreshold() {
    const step = Math.ceil(this._quantile(0.5) / 5) * 5
    if (step > this.max) return 'NR'
    return Math.max(this.min, step)
  }

  /**
   * A result at either end of the range must rest on a presentation actually
   * made there: 'NR' on a tone at `max` that went unanswered, and `min` on a
   * tone at `min` that was heard. Otherwise it is an extrapolation past the
   * last level tested.
   */
  _edgeUnverified(threshold) {
    if (threshold === 'NR') {
      return !this.trials.some((t) => t.level === this.max && !t.heard)
    }
    if (threshold === this.min) {
      return !this.trials.some((t) => t.level === this.min && t.heard)
    }
    return false
  }

  /**
   * Next level to present: the one whose outcome we can least predict
   * (p ≈ 0.5 under the current posterior) — the most informative question.
   * Rounded to 5 dB so the procedure still looks like clinical audiometry.
   */
  nextLevel() {
    let best = this.grid[0]
    let bestGap = Infinity
    for (const level of this.grid) {
      const p = this.grid.reduce((acc, t, i) => acc + this.post[i] * psi(level, t), 0)
      const gap = Math.abs(p - 0.5)
      if (gap < bestGap) { bestGap = gap; best = level }
    }
    const snapped = Math.round(best / 5) * 5
    return Math.min(this.max, Math.max(this.min, snapped))
  }

  /** Fold one response into the posterior. Returns the running estimate. */
  record(level, heard) {
    this.trials.push({ level, heard })
    this.post = this.post.map((p, i) => {
      const lik = psi(level, this.grid[i])
      return p * (heard ? lik : 1 - lik)
    })
    this._normalize()

    const [lo, hi] = this.credibleInterval()
    // Stop when the interval is tight, or when we have spent enough trials.
    //
    // The width is judged on the interval clamped at the floor only. Every
    // threshold below `min` reports the same normal result, so uncertainty
    // down there is not worth another tone; above `max`, the difference
    // between a response at the loudest level and none at all moves the
    // grade, so that uncertainty keeps the procedure presenting at `max`.
    const top = this._quantile(0.975)
    const candidate = this.clinicalThreshold()
    const settled = top - lo <= 10 && this.trials.length >= 4
      && !this._edgeUnverified(candidate)
    if (settled || this.trials.length >= 12) {
      this.done = true
      this.threshold = candidate
    }
    return { mean: this.mean, sd: this.sd, ci: [lo, hi] }
  }

  /** Posterior as {level, p} pairs, for plotting. */
  distribution() {
    return this.grid.map((t, i) => ({ level: t, p: this.post[i] }))
  }

  summary() {
    const [lo, hi] = this.credibleInterval()
    return {
      threshold: this.threshold ?? this.clinicalThreshold(),
      mean: Math.round(this.mean * 10) / 10,
      sd: Math.round(this.sd * 10) / 10,
      ci: [lo, hi],
      ci_width: hi - lo,
      presentations: this.trials.length,
    }
  }
}

/**
 * Response reliability from silent catch trials.
 *
 * Real audiometry inserts presentations with no stimulus. A response to
 * silence is a false positive; too many and the thresholds cannot be
 * trusted, however tidy they look.
 */
export class ReliabilityMonitor {
  constructor(catchRate = 0.12) {
    this.catchRate = catchRate
    this.catchTrials = 0
    this.falsePositives = 0
  }

  /** Should the next presentation be silent? */
  shouldCatch(rng = Math.random) {
    return rng() < this.catchRate
  }

  record(responded) {
    this.catchTrials += 1
    if (responded) this.falsePositives += 1
  }

  get rate() {
    return this.catchTrials ? this.falsePositives / this.catchTrials : 0
  }

  /** Unreliable once false positives exceed a third of catch trials. */
  get reliable() {
    return !(this.catchTrials >= 3 && this.rate > 0.33)
  }

  summary() {
    return {
      catch_trials: this.catchTrials,
      false_positives: this.falsePositives,
      false_positive_rate: Math.round(this.rate * 100),
      reliable: this.reliable,
      message: this.reliable
        ? (this.catchTrials
          ? `${this.falsePositives} false positive(s) in ${this.catchTrials} silent catch trials — responses look reliable.`
          : 'No catch trials presented yet.')
        : `${this.falsePositives} of ${this.catchTrials} silent trials drew a response — `
          + 'the patient is responding to nothing. Re-instruct and repeat; these '
          + 'thresholds should not be used.',
    }
  }
}
