// The conclusion, above the evidence.
//
// Everything else on the dashboard is supporting detail. This is the
// answer: what is wrong, the figures that carry the decision, and the one
// thing to do next. If a reader looks at nothing else, this must be enough.

const TONE = {
  emergency: {
    wrap: 'border-rose-300 bg-gradient-to-br from-rose-50 to-white',
    accent: 'text-rose-700', chip: 'bg-rose-600 text-white', icon: '⚠',
  },
  warning: {
    wrap: 'border-amber-300 bg-gradient-to-br from-amber-50 to-white',
    accent: 'text-amber-700', chip: 'bg-amber-500 text-white', icon: '⏳',
  },
  loss: {
    wrap: 'border-slate-200 bg-gradient-to-br from-teal-50/60 to-white',
    accent: 'text-teal-800', chip: 'bg-teal-600 text-white', icon: '📋',
  },
  normal: {
    wrap: 'border-emerald-200 bg-gradient-to-br from-emerald-50 to-white',
    accent: 'text-emerald-800', chip: 'bg-emerald-600 text-white', icon: '✓',
  },
  unknown: {
    wrap: 'border-slate-200 bg-white', accent: 'text-slate-700',
    chip: 'bg-slate-400 text-white', icon: '?',
  },
}

const ACTION_STYLE = {
  emergency: 'bg-rose-600 text-white',
  urgent: 'bg-orange-500 text-white',
  validity: 'bg-amber-500 text-white',
  routine: 'bg-slate-900 text-white',
}

export default function VerdictBanner({ verdict }) {
  if (!verdict) return null
  const tone = TONE[verdict.tone] || TONE.unknown

  return (
    <section
      aria-label="Interpretation summary"
      data-tour="verdict"
      className={`rounded-2xl border p-5 shadow-sm ${tone.wrap}`}
    >
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className={`mt-0.5 flex h-9 w-9 shrink-0 items-center
          justify-center rounded-xl text-[17px] ${tone.chip}`}>
          {tone.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            Interpretation
          </div>
          <h2 className={`mt-0.5 text-[19px] font-semibold leading-snug ${tone.accent}`}>
            {verdict.headline}
          </h2>
          <p className="mt-1 text-[12.5px] text-slate-500">{verdict.confidence_note}</p>
        </div>
      </div>

      {verdict.numbers?.length > 0 && (
        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {verdict.numbers.map((n) => (
            <div key={n.label}
              className={`rounded-xl px-3 py-2.5 ${
                n.emphasis ? 'bg-white ring-1 ring-rose-200' : 'bg-white/70'}`}>
              <dt className="text-[10.5px] font-semibold uppercase tracking-wider text-slate-400">
                {n.label}
              </dt>
              <dd className="mt-0.5">
                <span className={`text-2xl font-bold ${
                  n.emphasis ? 'text-rose-700' : 'text-slate-800'}`}>{n.value}</span>
                {n.unit && <span className="ml-1 text-[12px] text-slate-500">{n.unit}</span>}
                {n.hint && (
                  <div className="mt-0.5 text-[11px] leading-snug text-slate-500">{n.hint}</div>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        <span className={`rounded-lg px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-wider ${
          ACTION_STYLE[verdict.action_level] || ACTION_STYLE.routine}`}>
          Next step
        </span>
        <span className="text-[14px] font-medium text-slate-800">{verdict.action}</span>
      </div>

      <p className="mt-3 border-t border-slate-200/70 pt-2 text-[11px] italic text-slate-400">
        {verdict.disclaimer}
      </p>
    </section>
  )
}
