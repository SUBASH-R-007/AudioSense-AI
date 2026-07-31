// Everyday sounds, synthesized in the browser.
//
// Speech proves the communication problem; these prove the safety and
// quality-of-life problem. A patient who cannot hear a smoke alarm or a
// reversing truck has a different conversation with their family than one
// who "just needs the TV louder".
//
// Everything is generated procedurally into an AudioBuffer — no asset
// downloads, so the whole app still works offline.

const TAU = Math.PI * 2

function makeBuffer(ctx, seconds, fill) {
  const sr = ctx.sampleRate
  const buf = ctx.createBuffer(1, Math.floor(sr * seconds), sr)
  fill(buf.getChannelData(0), sr)
  return buf
}

/** Smoke alarm: ~3.1 kHz square-ish beeps in the classic T3 pattern. */
function smokeAlarm(ctx) {
  return makeBuffer(ctx, 4, (d, sr) => {
    const beep = 0.5, gap = 0.5, cycle = 4
    for (let i = 0; i < d.length; i++) {
      const t = i / sr
      const inCycle = t % cycle
      const slot = Math.floor(inCycle / (beep + gap))
      const phase = inCycle - slot * (beep + gap)
      const on = slot < 3 && phase < beep
      if (!on) { d[i] = 0; continue }
      const env = Math.min(1, phase / 0.01) * Math.min(1, (beep - phase) / 0.02)
      // Square-ish: fundamental plus odd harmonics, as real piezo alarms are.
      d[i] = env * 0.42 * (
        Math.sin(TAU * 3100 * t)
        + 0.34 * Math.sin(TAU * 9300 * t)
        + 0.2 * Math.sin(TAU * 15500 * t)
      )
    }
  })
}

/** Doorbell: two-tone chime, low-frequency and easy to hear. */
function doorbell(ctx) {
  return makeBuffer(ctx, 3, (d, sr) => {
    const strikes = [{ t: 0.05, f: 660 }, { t: 0.75, f: 520 }]
    for (let i = 0; i < d.length; i++) {
      const t = i / sr
      let s = 0
      for (const k of strikes) {
        if (t < k.t) continue
        const age = t - k.t
        const env = Math.exp(-age * 2.2)
        s += env * 0.4 * (Math.sin(TAU * k.f * t) + 0.35 * Math.sin(TAU * k.f * 2.7 * t))
      }
      d[i] = s
    }
  })
}

/** Birdsong: fast FM chirps in the 4–7 kHz band — first thing lost. */
function birdsong(ctx) {
  return makeBuffer(ctx, 4, (d, sr) => {
    const chirps = [0.2, 0.55, 0.9, 1.7, 2.05, 2.4, 3.1, 3.45]
    for (let i = 0; i < d.length; i++) {
      const t = i / sr
      let s = 0
      for (const start of chirps) {
        const age = t - start
        if (age < 0 || age > 0.22) continue
        const env = Math.sin((age / 0.22) * Math.PI) ** 2
        // Sweep 4.2 kHz -> 6.8 kHz and back.
        const f = 4200 + 2600 * Math.sin((age / 0.22) * Math.PI)
        s += env * 0.36 * Math.sin(TAU * f * age)
      }
      d[i] = s
    }
  })
}

/** Reversing-vehicle alarm: 1 kHz pulses, a workplace safety signal. */
function reversingTruck(ctx) {
  return makeBuffer(ctx, 4, (d, sr) => {
    for (let i = 0; i < d.length; i++) {
      const t = i / sr
      const phase = t % 0.85
      const on = phase < 0.35
      const env = on ? Math.min(1, phase / 0.008) * Math.min(1, (0.35 - phase) / 0.02) : 0
      d[i] = env * 0.4 * (Math.sin(TAU * 1000 * t) + 0.3 * Math.sin(TAU * 2000 * t))
    }
  })
}

/** Telephone ring: 400 Hz modulated at 25 Hz, UK/India style double ring. */
function phoneRing(ctx) {
  return makeBuffer(ctx, 4, (d, sr) => {
    for (let i = 0; i < d.length; i++) {
      const t = i / sr
      const inCycle = t % 2.0
      const on = inCycle < 0.4 || (inCycle > 0.6 && inCycle < 1.0)
      const env = on ? 1 : 0
      d[i] = env * 0.34 * Math.sin(TAU * 400 * t) * (0.6 + 0.4 * Math.sin(TAU * 25 * t))
    }
  })
}

export const SOUNDSCAPES = [
  { id: 'alarm', label: 'Smoke alarm', icon: '🚨', band: '3.1 kHz',
    why: 'Life-safety signal — sits exactly where noise damage bites.', make: smokeAlarm },
  { id: 'bird', label: 'Birdsong', icon: '🐦', band: '4–7 kHz',
    why: 'Usually the first everyday sound patients notice is gone.', make: birdsong },
  { id: 'truck', label: 'Reversing vehicle', icon: '🚚', band: '1 kHz',
    why: 'Workplace safety alarm — matters on a factory floor.', make: reversingTruck },
  { id: 'phone', label: 'Telephone ring', icon: '📞', band: '400 Hz',
    why: 'Low-frequency: often still audible even with high-frequency loss.', make: phoneRing },
  { id: 'doorbell', label: 'Doorbell', icon: '🔔', band: '520–660 Hz',
    why: 'Low-frequency chime — a useful contrast with the alarm.', make: doorbell },
]

export function buildSoundscape(ctx, id) {
  const entry = SOUNDSCAPES.find((s) => s.id === id)
  return entry ? entry.make(ctx) : null
}
