// The eight tympanogram types, each drawn from the criteria that define it.
//
// The reference document illustrates every type with a screenshot, but those
// come from several sources and disagree on axes, scales and even units —
// some plot mm H2O rather than daPa. Generating the curves from the numeric
// table instead gives one consistent set on one pair of axes, and every shape
// can be traced back to the row that produced it. Each curve is also fed back
// through the classifier, so the picture and the label provably agree.

import {
  CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

const TYPE_TONE = {
  A: '#0d9488', As: '#d97706', Ad: '#d97706', Add: '#dc2626',
  B: '#dc2626', C: '#0284c7', D: '#7c3aed', E: '#dc2626',
}

function Curve({ entry, normative }) {
  const tone = TYPE_TONE[entry.type] || '#0d9488'
  const peak = Math.max(...entry.points.map((p) => p.admittance))
  return (
    <div className="h-36 w-full">
      <ResponsiveContainer>
        <LineChart data={entry.points} margin={{ top: 6, right: 6, bottom: 2, left: -18 }}>
          <CartesianGrid stroke="#eef2f7" strokeDasharray="3 3" />
          {normative && (
            <ReferenceArea x1={normative.pressure[0]} x2={normative.pressure[1]}
              fill={tone} fillOpacity={0.06} />
          )}
          <ReferenceLine x={0} stroke="#cbd5e1" strokeDasharray="4 4" />
          <XAxis dataKey="pressure" type="number" domain={[-400, 200]}
            ticks={[-400, -200, 0, 200]} tick={{ fontSize: 9, fill: '#94a3b8' }} />
          <YAxis domain={[0, Math.max(2, Math.ceil(peak * 1.15))]}
            tick={{ fontSize: 9, fill: '#94a3b8' }} width={34} />
          <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }}
            formatter={(v) => [`${v} mmho`, 'Admittance']}
            labelFormatter={(l) => `${l} daPa`} />
          <Line type="monotone" dataKey="admittance" stroke={tone} strokeWidth={2}
            dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function TympanogramAtlas({ reference, activeType = null }) {
  if (!reference?.curves?.length) return null
  const { criteria, citations } = reference

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">
          The eight tympanogram types
        </h2>
        <span className="text-[11.5px] text-slate-500">
          curves generated from the criteria, not traced from figures
        </span>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {reference.curves.map((entry) => {
          const active = activeType === entry.type
          return (
            <figure key={entry.type}
              className={`rounded-xl border p-3 transition ${
                active ? 'border-teal-500 bg-teal-50/40 ring-1 ring-teal-500/30'
                  : 'border-slate-200'}`}>
              <figcaption className="flex items-baseline justify-between gap-2">
                <span className="text-[13px] font-semibold text-slate-800">
                  Type {entry.type}
                </span>
                {active && (
                  <span className="rounded bg-teal-600 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-white">
                    this ear
                  </span>
                )}
              </figcaption>
              <p className="mt-0.5 text-[11px] text-slate-500">{entry.shape}</p>
              <Curve entry={entry} normative={reference.normative} />
              <dl className="mt-1 space-y-0.5 text-[10.5px] leading-snug">
                <div>
                  <dt className="inline font-semibold text-slate-600">Peak: </dt>
                  <dd className="inline text-slate-600">
                    {entry.peak_pressure} daPa, {entry.compliance} mmho
                  </dd>
                </div>
                <div>
                  <dt className="inline font-semibold text-slate-600">Disorders: </dt>
                  <dd className="inline text-slate-600">
                    {entry.disorders.join(', ')}
                  </dd>
                </div>
              </dl>
              {entry.volume_variants?.length > 0 && (
                <ul className="mt-1.5 space-y-1 rounded-lg bg-slate-50 p-2 text-[10.5px] leading-snug text-slate-600">
                  {entry.volume_variants.map((v) => (
                    <li key={v.band}>
                      <span className="font-semibold capitalize text-slate-700">
                        {v.band} ECV:
                      </span>{' '}
                      {v.disorders.join(', ')}
                    </li>
                  ))}
                </ul>
              )}
            </figure>
          )
        })}
      </div>

      {criteria && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-[11.5px]">
            <caption className="pb-1.5 text-left text-[11px] text-slate-500">
              Normative criteria, as the reference states them
            </caption>
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                <th className="py-1 pr-3 font-medium">Measure</th>
                <th className="py-1 pr-3 font-medium">Children</th>
                <th className="py-1 font-medium">Adults</th>
              </tr>
            </thead>
            <tbody className="text-slate-700">
              <tr className="border-t border-slate-100">
                <td className="py-1 pr-3">Ear-canal volume (ml)</td>
                <td className="py-1 pr-3">{criteria.ecv_child.join(' – ')}</td>
                <td className="py-1">{criteria.ecv_adult.join(' – ')}</td>
              </tr>
              <tr className="border-t border-slate-100">
                <td className="py-1 pr-3">Static compliance (mmho)</td>
                <td className="py-1 pr-3">{criteria.compliance_child.join(' – ')}</td>
                <td className="py-1">{criteria.compliance_adult.join(' – ')}</td>
              </tr>
              <tr className="border-t border-slate-100">
                <td className="py-1 pr-3">Peak pressure (daPa)</td>
                <td className="py-1 pr-3" colSpan={2}>
                  {criteria.pressure[1]} to {criteria.pressure[0]}
                </td>
              </tr>
              <tr className="border-t border-slate-100">
                <td className="py-1 pr-3">Tympanic gradient</td>
                <td className="py-1 pr-3" colSpan={2}>&gt; {criteria.gradient_min}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        {reference.gradient_formula}
      </p>
      {citations?.length > 0 && (
        <p className="mt-1 text-[10.5px] leading-relaxed text-slate-400">
          {citations.join(' · ')}
        </p>
      )}
    </div>
  )
}
