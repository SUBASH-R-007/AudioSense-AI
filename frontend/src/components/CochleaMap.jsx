// Tonotopic cochlea map — where on the basilar membrane the loss sits.
//
// Position is derived from the Greenwood function (Greenwood 1990,
// JASA 87:2592), the standard frequency-to-place map of the human cochlea:
//     F = A (10^(a x) − k),  A = 165.4, a = 2.1, k = 0.88
// solved for x, the fractional distance from the apex. High frequencies map
// to the base (outer turn), low frequencies to the apex (centre) — which is
// why noise and age damage the base first and take the high notes with it.

const A = 165.4
const ALPHA = 2.1
const K = 0.88

const AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]

/** Fractional distance from apex (0) to base (1) for a frequency in Hz. */
export function greenwoodPosition(freqHz) {
  return Math.log10(freqHz / A + K) / ALPHA
}

// Spiral geometry: 2.5 turns, base at the outside, apex at the centre.
const TURNS = 2.5
const CX = 130
const CY = 118
const R_OUTER = 96
const R_INNER = 13

function spiralPoint(t) {
  // t: 0 = base (outer), 1 = apex (centre)
  const angle = t * TURNS * 2 * Math.PI - Math.PI / 2
  const r = R_OUTER - t * (R_OUTER - R_INNER)
  return [CX + r * Math.cos(angle), CY + r * Math.sin(angle)]
}

function spiralPath(steps = 260) {
  let d = ''
  for (let i = 0; i <= steps; i++) {
    const [x, y] = spiralPoint(i / steps)
    d += `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`
  }
  return d
}

const severityColor = (db) => {
  if (db == null) return '#cbd5e1'
  if (db < 20) return '#10b981'
  if (db < 35) return '#facc15'
  if (db < 50) return '#fb923c'
  if (db < 65) return '#f43f5e'
  return '#9f1239'
}

const toNum = (v) => (v === 'NR' ? 120 : typeof v === 'number' ? v : null)

export default function CochleaMap({ thresholds, ear = 'right' }) {
  const ac = thresholds?.[ear]?.ac || {}

  // Greenwood x runs apex→base; our spiral t runs base→apex, so invert.
  // Normalize across the audiometric range so the drawn region is the part
  // of the cochlea that audiometry actually probes.
  const xMin = greenwoodPosition(250)
  const xMax = greenwoodPosition(8000)
  const tOf = (f) => {
    const x = (greenwoodPosition(f) - xMin) / (xMax - xMin)
    return 1 - x // 1 = apex (low freq), 0 = base (high freq)
  }

  const points = AC_FREQS.map((f) => {
    const db = toNum(ac[f])
    const t = tOf(f)
    const [x, y] = spiralPoint(t)
    return { f, db, x, y, color: severityColor(db) }
  })

  const damaged = points.filter((p) => p.db != null && p.db >= 35)

  return (
    <div>
      <svg viewBox="0 0 260 236" className="w-full">
        <defs>
          <filter id="cochlea-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* the membrane */}
        <path d={spiralPath()} fill="none" stroke="#e2e8f0" strokeWidth="13"
          strokeLinecap="round" />
        <path d={spiralPath()} fill="none" stroke="#f8fafc" strokeWidth="7"
          strokeLinecap="round" />

        {/* lesion glow on damaged regions */}
        {damaged.map((p) => (
          <circle key={`glow-${p.f}`} cx={p.x} cy={p.y} r={13} fill={p.color}
            opacity={0.35} filter="url(#cochlea-glow)" className="animate-pulse-soft" />
        ))}

        {/* hair-cell region markers */}
        {points.map((p) => (
          <g key={p.f}>
            <circle cx={p.x} cy={p.y} r={7.5} fill={p.color} stroke="white" strokeWidth="2" />
            <title>{`${p.f} Hz — ${p.db == null ? 'not tested' : p.db + ' dB HL'}`}</title>
          </g>
        ))}

        {/* labels for the extremes */}
        <text x={spiralPoint(tOf(8000))[0]} y={spiralPoint(tOf(8000))[1] - 13}
          textAnchor="middle" fontSize="9.5" fontWeight="700" fill="#64748b">8k</text>
        <text x={spiralPoint(tOf(250))[0]} y={spiralPoint(tOf(250))[1] - 12}
          textAnchor="middle" fontSize="9.5" fontWeight="700" fill="#64748b">250</text>

        <text x={CX} y={222} textAnchor="middle" fontSize="10" fill="#94a3b8">
          base (high frequency) → apex (low frequency)
        </text>
      </svg>

      <div className="mt-1 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[10.5px] text-slate-500">
        {[['#10b981', 'normal'], ['#facc15', 'mild'], ['#fb923c', 'moderate'],
          ['#f43f5e', 'severe'], ['#9f1239', 'profound']].map(([c, l]) => (
          <span key={l} className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ background: c }} />{l}
          </span>
        ))}
      </div>
    </div>
  )
}
