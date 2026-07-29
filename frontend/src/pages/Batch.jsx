import { useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

export default function Batch() {
  const { showToast } = useApp()
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)

  const onFile = async (file) => {
    if (!file) return
    setBusy(true)
    try {
      setData(await api.batch(file))
    } catch (e) {
      showToast(`Batch failed: ${e.message}`, 'error')
    }
    setBusy(false)
  }

  const exportCsv = () => {
    if (!data) return
    const head = ['name', 'age', 'occupation',
      'right_pta', 'right_grade', 'right_type', 'right_pattern',
      'left_pta', 'left_grade', 'left_type', 'left_pattern',
      'binaural_disability_pct', 'benchmark_disability']
    const rows = data.results.map((r) => [
      r.name, r.age, r.occupation,
      r.right.pta, r.right.grade, r.right.type, r.right.pattern,
      r.left.pta, r.left.grade, r.left.type, r.left.pattern,
      r.binaural_disability_pct, r.benchmark_disability,
    ].map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))
    const blob = new Blob([[head.join(','), ...rows].join('\n')], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'audiosense_batch_results.csv'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const EarCell = ({ ear }) => (
    <td className="px-3 py-2.5 text-[12.5px]">
      {ear.pta != null ? (
        <>
          <div className="font-semibold text-slate-800">{ear.grade}</div>
          <div className="text-slate-500">
            PTA {ear.pta} · {ear.type}{ear.provisional ? '*' : ''}
            {ear.pattern && <> · {ear.pattern}</>}
            {ear.ood && <span className="ml-1 rounded bg-rose-100 px-1 py-0.5 text-[10px] font-bold text-rose-700">OOD</span>}
          </div>
        </>
      ) : <span className="text-slate-300">—</span>}
    </td>
  )

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-xl font-semibold tracking-tight">Batch Analysis</h1>
      <p className="mt-1 text-[13.5px] text-slate-500">
        Screen an entire camp or factory shift in one upload — CSV in, classified results out.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button onClick={() => fileRef.current?.click()}
          className="rounded-lg bg-teal-600 px-4 py-2 text-[13px] font-semibold text-white shadow-sm hover:bg-teal-700">
          {busy ? 'Analyzing…' : 'Upload CSV'}
        </button>
        <input ref={fileRef} type="file" accept=".csv" className="hidden"
          onChange={(e) => onFile(e.target.files?.[0])} />
        <a href="/samples/batch_sample.csv" download
          className="text-[13px] font-medium text-teal-700 underline decoration-teal-300 underline-offset-2 hover:decoration-teal-600">
          Download sample CSV (8 patients)
        </a>
        {data && (
          <button onClick={exportCsv}
            className="ml-auto rounded-lg border border-slate-300 px-4 py-2 text-[13px] font-semibold text-slate-700 hover:border-teal-400 hover:text-teal-700">
            ⬇ Export results CSV
          </button>
        )}
      </div>

      {data?.summary?.total > 0 && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Camp overview — {data.summary.total} people screened
            </h2>
            {data.summary.urgent_referrals > 0 && (
              <span className="rounded-full bg-rose-100 px-2.5 py-1 text-[11.5px] font-bold text-rose-700">
                {data.summary.urgent_referrals} urgent referral
                {data.summary.urgent_referrals === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <p className="mt-1 text-[14px] font-semibold text-slate-800">
            {data.summary.headline}
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ['Hearing loss', `${data.summary.impaired_pct}%`, `${data.summary.impaired} of ${data.summary.total}`, 'text-slate-800'],
              ['4 kHz noise notch', `${data.summary.noise_notch_pct}%`, `${data.summary.noise_notch} workers`, 'text-amber-600'],
              ['Benchmark disability', `${data.summary.benchmark_pct}%`, `${data.summary.benchmark_disability} eligible (RPwD ≥40%)`, 'text-rose-600'],
              ['Needs human review', data.summary.needs_review, 'atypical patterns', 'text-teal-700'],
            ].map(([label, value, sub, color]) => (
              <div key={label} className="rounded-xl bg-slate-50 p-3">
                <div className="text-[10.5px] font-semibold uppercase tracking-wider text-slate-400">
                  {label}
                </div>
                <div className={`mt-1 text-2xl font-bold ${color}`}>{value}</div>
                <div className="text-[11px] text-slate-500">{sub}</div>
              </div>
            ))}
          </div>

          {Object.keys(data.summary.by_age_band || {}).length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Prevalence by age band
              </div>
              <div className="mt-2 space-y-1.5">
                {Object.entries(data.summary.by_age_band).map(([band, s]) => (
                  <div key={band} className="flex items-center gap-3">
                    <span className="w-14 text-[12px] font-medium text-slate-600">{band}</span>
                    <div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-teal-500 transition-all duration-500"
                        style={{ width: `${s.impaired_pct}%` }} />
                    </div>
                    <span className="w-24 text-right text-[11.5px] text-slate-500">
                      {s.impaired_pct}% of {s.n}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <p className="mt-3 text-[11px] text-slate-400">
            A per-patient tool answers "does this person need help?" — these numbers
            answer "does this workforce need a hearing-conservation programme?"
          </p>
        </div>
      )}

      {data && (
        <div className="mt-5 overflow-x-auto rounded-2xl border border-slate-200/80 bg-white shadow-sm">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                <th className="px-3 py-2.5 font-semibold">Patient</th>
                <th className="px-3 py-2.5 font-semibold text-red-600">Right ear</th>
                <th className="px-3 py-2.5 font-semibold text-blue-600">Left ear</th>
                <th className="px-3 py-2.5 font-semibold">Disability</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.row} className="border-b border-slate-50 hover:bg-slate-50/50">
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[13px] font-semibold text-slate-800">{r.name}</span>
                      {r.urgent && (
                        <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[9.5px] font-bold uppercase text-rose-700"
                          title={(r.alerts || []).join('; ')}>refer</span>
                      )}
                    </div>
                    <div className="text-[11.5px] text-slate-500">{r.age} y · {r.occupation}</div>
                  </td>
                  <EarCell ear={r.right} />
                  <EarCell ear={r.left} />
                  <td className="px-3 py-2.5">
                    {r.binaural_disability_pct != null ? (
                      <div className="flex items-center gap-2">
                        <span className="text-[14px] font-bold text-slate-800">{r.binaural_disability_pct}%</span>
                        {r.benchmark_disability && (
                          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold uppercase text-rose-700">
                            benchmark
                          </span>
                        )}
                      </div>
                    ) : <span className="text-slate-300">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-3 py-2 text-[11px] text-slate-400">
            * = type provisional (BC incomplete) · OOD = atypical pattern, priority human review
          </div>
        </div>
      )}
    </div>
  )
}
