import {
  CartesianGrid,
  ComposedChart,
  Customized,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AC_FREQS, FREQ_LABELS } from '../lib/api.js'

const RED = '#dc2626'
const BLUE = '#2563eb'

const toNum = (v) => (v === 'NR' ? 120 : v === undefined || v === null ? null : v)
const isNR = (v) => v === 'NR'

export function buildChartData(thresholds, mlPerEar) {
  return AC_FREQS.map((f) => {
    const glowR = mlPerEar?.right?.freq_importance?.[f] ?? 0
    const glowL = mlPerEar?.left?.freq_importance?.[f] ?? 0
    return {
      freq: String(f),
      rAC: toNum(thresholds.right.ac[f]),
      rAC_nr: isNR(thresholds.right.ac[f]),
      lAC: toNum(thresholds.left.ac[f]),
      lAC_nr: isNR(thresholds.left.ac[f]),
      rBC: toNum(thresholds.right.bc[f]),
      rBC_nr: isNR(thresholds.right.bc[f]),
      lBC: toNum(thresholds.left.bc[f]),
      lBC_nr: isNR(thresholds.left.bc[f]),
      glow: Math.max(glowR, glowL),
    }
  })
}

/* ------- clinical symbol dots ------- */

const nrArrow = (cx, cy, color) => (
  <path
    d={`M${cx + 7} ${cy + 5} l0 8 m0 0 l-4 -4 m4 4 l4 -4`}
    stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round"
  />
)

const DotO = ({ cx, cy, payload, dataKey, index }) =>
  payload[dataKey] == null ? null : (
    <g key={`o-${index}`}>
      <circle cx={cx} cy={cy} r={7} stroke={RED} strokeWidth={2.4} fill="none" />
      {payload[`${dataKey}_nr`] && nrArrow(cx, cy, RED)}
    </g>
  )

const DotX = ({ cx, cy, payload, dataKey, index }) =>
  payload[dataKey] == null ? null : (
    <g key={`x-${index}`}>
      <path
        d={`M${cx - 6} ${cy - 6} L${cx + 6} ${cy + 6} M${cx + 6} ${cy - 6} L${cx - 6} ${cy + 6}`}
        stroke={BLUE} strokeWidth={2.4} strokeLinecap="round"
      />
      {payload[`${dataKey}_nr`] && nrArrow(cx, cy, BLUE)}
    </g>
  )

const bracket = (color, open) => ({ cx, cy, payload, dataKey, index }) =>
  payload[dataKey] == null ? null : (
    <g key={`b-${index}`}>
      <text
        x={cx + (open ? -13 : 13)} y={cy + 5.5}
        textAnchor="middle" fontSize="16" fontWeight="700" fill={color}
      >
        {open ? '[' : ']'}
      </text>
      {payload[`${dataKey}_nr`] && nrArrow(cx + (open ? -13 : 13), cy, color)}
    </g>
  )

/* ------- speech banana + phonemes + glow (drawn with axis scales) ------- */

const BANANA_UPPER = [[250, 22], [500, 17], [1000, 15], [2000, 13], [4000, 13], [8000, 18]]
const BANANA_LOWER = [[250, 52], [500, 57], [1000, 60], [2000, 55], [4000, 48], [8000, 42]]

function makeScales(props) {
  const xMap = Object.values(props.xAxisMap)[0]
  const yMap = Object.values(props.yAxisMap)[0]
  const band = xMap.bandSize || 0
  const xOf = (freqHz) => {
    // octave position between category centers (log-frequency axis)
    const t = Math.log2(freqHz / 250)
    const i = Math.min(Math.floor(t), AC_FREQS.length - 2)
    const frac = t - i
    const x0 = xMap.scale(String(AC_FREQS[i])) + band / 2
    const x1 = xMap.scale(String(AC_FREQS[i + 1])) + band / 2
    return x0 + frac * (x1 - x0)
  }
  return { xOf, yOf: (db) => yMap.scale(db), band, xMap, yMap }
}

const BananaLayer = (props) => {
  const { xOf, yOf } = makeScales(props)
  const path =
    BANANA_UPPER.map(([f, d], i) => `${i ? 'L' : 'M'}${xOf(f)},${yOf(d)}`).join(' ') +
    ' ' +
    [...BANANA_LOWER].reverse().map(([f, d]) => `L${xOf(f)},${yOf(d)}`).join(' ') +
    ' Z'
  return (
    <g pointerEvents="none">
      <path d={path} fill="#f59e0b" fillOpacity="0.10" stroke="#f59e0b"
        strokeOpacity="0.45" strokeDasharray="5 4" strokeWidth="1.2" />
      <text x={xOf(700)} y={yOf(38)} fontSize="11" fill="#b45309" fontWeight="600"
        opacity="0.7">speech banana</text>
    </g>
  )
}

const PhonemeLayer = (phonemes) => (props) => {
  const { xOf, yOf } = makeScales(props)
  const fill = { audible: '#64748b', borderline: '#d97706', inaudible: '#dc2626' }
  return (
    <g pointerEvents="none">
      {phonemes.map((p) => (
        <g key={p.symbol} opacity={p.status === 'audible' ? 0.75 : 1}>
          <circle cx={xOf(p.freq)} cy={yOf(p.db)} r={9}
            fill={p.status === 'inaudible' ? '#fee2e2' : p.status === 'borderline' ? '#fef3c7' : '#f1f5f9'}
            stroke={fill[p.status] || '#94a3b8'} strokeWidth={p.status === 'inaudible' ? 1.8 : 1} />
          <text x={xOf(p.freq)} y={yOf(p.db) + 3.5} textAnchor="middle" fontSize="9.5"
            fontWeight="700" fill={fill[p.status] || '#64748b'}>{p.symbol}</text>
        </g>
      ))}
    </g>
  )
}

/**
 * Plain-language callouts placed on the chart itself.
 *
 * The audiogram is a specialist instrument — it assumes you already know
 * that a dip at 4 kHz means noise. These annotations say it in words, at
 * the place on the chart where it is true.
 */
export function deriveAnnotations(data) {
  const out = []
  const at = (f) => data.find((d) => Number(d.freq) === f)
  const worst = (d) => Math.max(d?.rAC ?? -99, d?.lAC ?? -99)

  const k2 = worst(at(2000))
  const k4 = worst(at(4000))
  const k8 = worst(at(8000))
  const low = Math.max(worst(at(250)), worst(at(500)))

  // A 4 kHz notch: worse than both neighbours by a clear margin.
  if (k4 > 0 && k4 - k2 >= 15 && k4 - k8 >= 10) {
    out.push({ freq: 4000, db: k4, text: 'noise notch', tone: '#b45309' })
  } else if (k8 > 0 && k8 - low >= 30) {
    out.push({ freq: 6000, db: (k4 + k8) / 2, text: 'high-frequency loss', tone: '#b45309' })
  }
  if (low >= 40 && low - k4 >= 15) {
    out.push({ freq: 350, db: low, text: 'low-frequency loss', tone: '#b45309' })
  }
  return out
}

const AnnotationLayer = (annotations) => (props) => {
  const { xOf, yOf } = makeScales(props)
  return (
    <g pointerEvents="none">
      {annotations.map((a) => {
        const x = xOf(a.freq)
        const y = yOf(a.db)
        const labelY = y + 34
        return (
          <g key={a.text}>
            <path d={`M${x},${y + 12} L${x},${labelY - 10}`} stroke={a.tone}
              strokeWidth="1.2" strokeDasharray="3 2" opacity="0.8" />
            <rect x={x - a.text.length * 3.3 - 6} y={labelY - 9} rx="4"
              width={a.text.length * 6.6 + 12} height="17"
              fill="#fffbeb" stroke={a.tone} strokeOpacity="0.4" />
            <text x={x} y={labelY + 3} textAnchor="middle" fontSize="10.5"
              fontWeight="600" fill={a.tone}>{a.text}</text>
          </g>
        )
      })}
    </g>
  )
}

const GlowLayer = (data) => (props) => {
  const { xOf, xMap, yMap } = makeScales(props)
  return (
    <g pointerEvents="none">
      {data.filter((d) => d.glow >= 0.45).map((d) => (
        <rect
          key={d.freq}
          x={xOf(Number(d.freq)) - 24}
          y={yMap.y}
          width={48}
          height={yMap.height}
          rx={22}
          fill="#14b8a6"
          opacity={0.10 + 0.16 * d.glow}
          className="glow-blur animate-pulse-soft"
        />
      ))}
    </g>
  )
}

/* ------- main chart ------- */

export default function AudiogramChart({
  data,
  phonemes = null,
  showBanana = false,
  showPhonemes = false,
  // Overlays default off and the grid defaults square, so a chart rendered
  // without options is the plain clinical audiogram a clinician is trained to
  // read rather than a decorated one.
  showGlow = false,
  showAnnotations = true,
  height = 440,
  square = true,
}) {
  const annotations = showAnnotations ? deriveAnnotations(data) : []
  // A clinical audiogram is conventionally drawn on a square grid, one octave
  // occupying the same distance as 20 dB. Recharts' `aspect` keeps that true
  // at any container width, which a fixed pixel height cannot.
  const sizing = square
    ? { width: '100%', aspect: 1 }
    : { width: '100%', height }
  return (
    <ResponsiveContainer {...sizing}>
      <ComposedChart data={data} margin={{ top: 12, right: 24, bottom: 8, left: 4 }}>
        <CartesianGrid stroke="#e2e8f0" />
        <XAxis
          dataKey="freq"
          tickFormatter={(f) => FREQ_LABELS[f] || f}
          tick={{ fontSize: 12, fill: '#475569' }}
          axisLine={{ stroke: '#cbd5e1' }}
          tickLine={false}
          label={{ value: 'Frequency (Hz)', position: 'insideBottom', offset: -4, fontSize: 11, fill: '#94a3b8' }}
        />
        <YAxis
          domain={[-10, 120]}
          reversed
          ticks={[-10, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]}
          tick={{ fontSize: 11, fill: '#475569' }}
          axisLine={{ stroke: '#cbd5e1' }}
          tickLine={false}
          label={{ value: 'Hearing Level (dB HL)', angle: -90, position: 'insideLeft', fontSize: 11, fill: '#94a3b8' }}
        />
        {/* shaded normal-hearing band */}
        <ReferenceArea y1={-10} y2={20} fill="#10b981" fillOpacity={0.07} />
        {showGlow && <Customized component={GlowLayer(data)} />}
        {showBanana && <Customized component={BananaLayer} />}
        {showPhonemes && phonemes && <Customized component={PhonemeLayer(phonemes)} />}
        {annotations.length > 0 && <Customized component={AnnotationLayer(annotations)} />}

        <Tooltip
          formatter={(v, name) => [`${v} dB HL`, name]}
          labelFormatter={(f) => `${f} Hz`}
          contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 12 }}
        />

        <Line name="Right AC (O)" dataKey="rAC" stroke={RED} strokeWidth={1.6}
          dot={<DotO dataKey="rAC" />} activeDot={false} isAnimationActive={false} connectNulls={false} />
        <Line name="Left AC (X)" dataKey="lAC" stroke={BLUE} strokeWidth={1.6}
          dot={<DotX dataKey="lAC" />} activeDot={false} isAnimationActive={false} connectNulls={false} />
        <Line name="Right BC ([)" dataKey="rBC" stroke={RED} strokeWidth={1.1}
          strokeDasharray="4 4" strokeOpacity={0.55}
          dot={bracket(RED, true)}
          activeDot={false} isAnimationActive={false} connectNulls={false} />
        <Line name="Left BC (])" dataKey="lBC" stroke={BLUE} strokeWidth={1.1}
          strokeDasharray="4 4" strokeOpacity={0.55}
          dot={bracket(BLUE, false)} activeDot={false} isAnimationActive={false} connectNulls={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
