// Spatial hearing — 3D sound placed around the listener with HRTF.
//
// The audiogram cannot express "I can't tell where sounds come from", yet
// that is what makes a road dangerous and a name called across a room
// impossible to answer. Localization depends on comparing the two ears, so
// asymmetric loss destroys it even when the better ear tests well.
//
// A PannerNode in 'HRTF' mode applies a real head-related transfer
// function, so a source genuinely sounds like it is behind or to the left.
// Each ear then passes through its own loss filters, which is what turns
// this from a demo into a measurement: with asymmetric hearing the cues
// stop working and localization error grows.
//
// The same scene drives immersive WebXR when a headset is present. Without
// one it is a top-down 2D scene, and nothing is lost but the head tracking.

const BANDS = [250, 500, 1000, 2000, 4000, 8000]

export class SpatialScene {
  constructor() {
    this.ctx = null
    this.impaired = false
  }

  _ensureCtx() {
    if (this.ctx) return this.ctx
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    this.ctx = ctx

    // Listener at the origin, facing -z (the Web Audio convention).
    const l = ctx.listener
    if (l.forwardZ) {
      l.forwardX.value = 0; l.forwardY.value = 0; l.forwardZ.value = -1
      l.upX.value = 0; l.upY.value = 1; l.upZ.value = 0
      l.positionX.value = 0; l.positionY.value = 0; l.positionZ.value = 0
    } else if (l.setOrientation) {
      l.setOrientation(0, 0, -1, 0, 1, 0)
      l.setPosition(0, 0, 0)
    }

    this.panner = ctx.createPanner()
    this.panner.panningModel = 'HRTF'
    this.panner.distanceModel = 'inverse'
    this.panner.refDistance = 1
    this.panner.maxDistance = 20

    // Split into ears so each can carry its own hearing loss.
    this.splitter = ctx.createChannelSplitter(2)
    this.merger = ctx.createChannelMerger(2)
    this.earChains = { left: this._buildEar(ctx), right: this._buildEar(ctx) }

    this.panner.connect(this.splitter)
    this.splitter.connect(this.earChains.left.input, 0)
    this.splitter.connect(this.earChains.right.input, 1)
    this.earChains.left.output.connect(this.merger, 0, 0)
    this.earChains.right.output.connect(this.merger, 0, 1)

    this.master = ctx.createGain()
    this.master.gain.value = 0.9
    this.merger.connect(this.master)
    this.master.connect(ctx.destination)
    return ctx
  }

  _buildEar(ctx) {
    const input = ctx.createGain()
    let node = input
    const filters = BANDS.map((freq, i) => {
      const f = ctx.createBiquadFilter()
      f.type = i === 0 ? 'lowshelf' : i === BANDS.length - 1 ? 'highshelf' : 'peaking'
      f.frequency.value = freq
      if (f.type === 'peaking') f.Q.value = 1.1
      f.gain.value = 0
      node.connect(f)
      node = f
      return f
    })
    return { input, output: node, filters }
  }

  /** Apply each ear's audiogram. Pass null to hear it with normal ears. */
  setHearing(rightAc, leftAc) {
    this._ensureCtx()
    this.impaired = Boolean(rightAc || leftAc)
    for (const [ear, ac] of [['right', rightAc], ['left', leftAc]]) {
      const chain = this.earChains[ear]
      BANDS.forEach((freq, i) => {
        const raw = ac?.[freq]
        const db = raw === 'NR' ? 120 : raw ?? 0
        const atten = this.impaired ? -Math.min(70, Math.max(0, db - 20)) : 0
        chain.filters[i].gain.setTargetAtTime(atten, this.ctx.currentTime, 0.02)
      })
    }
  }

  /** Move the source to an angle in degrees (0 ahead, +90 right). */
  setAngle(deg, distance = 2) {
    this._ensureCtx()
    const rad = (deg * Math.PI) / 180
    const x = Math.sin(rad) * distance
    const z = -Math.cos(rad) * distance
    const t = this.ctx.currentTime
    if (this.panner.positionX) {
      this.panner.positionX.setTargetAtTime(x, t, 0.02)
      this.panner.positionY.setTargetAtTime(0, t, 0.02)
      this.panner.positionZ.setTargetAtTime(z, t, 0.02)
    } else {
      this.panner.setPosition(x, 0, z)
    }
    this.angle = deg
  }

  /**
   * Play a burst from the current position. Broadband noise bursts are used
   * because they carry both the time and level cues localization needs — a
   * pure tone deliberately does not, and would make the test unfair.
   */
  playBurst(durationMs = 700) {
    const ctx = this._ensureCtx()
    if (ctx.state === 'suspended') ctx.resume()
    const sr = ctx.sampleRate
    const length = Math.floor((sr * durationMs) / 1000)
    const buf = ctx.createBuffer(1, length, sr)
    const d = buf.getChannelData(0)
    for (let i = 0; i < length; i++) {
      const env = Math.min(1, i / (sr * 0.005)) *
        Math.min(1, (length - i) / (sr * 0.05))
      d[i] = (Math.random() * 2 - 1) * env * 0.6
    }
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.connect(this.panner)
    src.start()
    return new Promise((resolve) => { src.onended = resolve })
  }

  /** True if this browser can enter an immersive VR session. */
  static async xrSupported() {
    try {
      return Boolean(navigator.xr && await navigator.xr.isSessionSupported('immersive-vr'))
    } catch {
      return false
    }
  }

  dispose() {
    try { this.ctx?.close() } catch { /* ignore */ }
    this.ctx = null
  }
}

/** A random angle at least `minSeparation` from the previous one. */
export function nextAngle(previous, minSeparation = 40) {
  for (let i = 0; i < 30; i++) {
    const angle = Math.round((Math.random() * 360 - 180) / 15) * 15
    if (previous == null || Math.abs(angle - previous) >= minSeparation) return angle
  }
  return Math.round((Math.random() * 360 - 180) / 15) * 15
}
