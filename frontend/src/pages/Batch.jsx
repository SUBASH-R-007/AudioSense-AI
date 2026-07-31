import { useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

const PRIORITY_STYLE = {
  critical: { chip: 'bg-rose-600 text-white', row: 'bg-rose-50/60', label: 'Critical' },
  urgent: { chip: 'bg-orange-500 text-white', row: 'bg-orange-50/50', label: 'Urgent' },
  review: { chip: 'bg-amber-400 text-amber-950', row: '', label: 'Review' },
  routine: { chip: 'bg-slate-200 text-slate-600', row: '', label: 'Routine' },
}

export default function Batch() {
  const { showToast } = useApp()
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [validation, setValidation] = useState(null)
  const [onlyReview, setOnlyReview] = useState(false)
  const fileRef = useRef(null)
  const photoRef = useRef(null)
  const validateRef = useRef(null)

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

  const onPhotos = async (files) => {
    if (!files?.length) return
    setBusy(true)
    try {
      const res = await api.batchPhotos(files)
      setData(res)
      if (res.failed?.length) {
        showToast(`${res.failed.length} photo(s) could not be read`, 'warn')
      }
    } catch (e) {
      showToast(`Photo batch failed: ${e.message}`, 'error')
    }
    setBusy(false)
  }

  const onValidate = async (file) => {
    if (!file) return
    setBusy(true)
    try {
      setValidation(await api.validate(file))
    } catch (e) {
      showToast(`Validation failed: ${e.message}`, 'error')
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
      <h1 className="text-xl font-semibold tracking-tight">Batch Analysis &amp; Worklist</h1>
      <p className="mt-1 text-[13.5px] text-slate-500">
        Screen an entire camp or factory shift in one upload, and get back a queue
        ordered by who needs a clinician first.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3" data-tour="batch-actions">
        <button onClick={() => fileRef.current?.click()} disabled={busy}
          className="rounded-lg bg-teal-600 px-4 py-2 text-[13px] font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-50">
          {busy ? 'Analyzing…' : 'Upload CSV'}
        </button>
        <input ref={fileRef} type="file" accept=".csv" className="hidden"
          onChange={(e) => onFile(e.target.files?.[0])} />

        <button onClick={() => photoRef.current?.click()} disabled={busy}
          className="rounded-lg border border-slate-300 px-4 py-2 text-[13px] font-semibold text-slate-700 hover:border-teal-400 hover:text-teal-700 disabled:opacity-50">
          📷 Upload paper audiograms
        </button>
        <input ref={photoRef} type="file" accept="image/*" multiple className="hidden"
          onChange={(e) => onPhotos([...(e.target.files || [])])} />

        <button onClick={() => validateRef.current?.click()} disabled={busy}
          className="rounded-lg border border-slate-300 px-4 py-2 text-[13px] font-semibold text-slate-700 hover:border-teal-400 hover:text-teal-700 disabled:opacity-50">
          🔬 Validate vs expert labels
        </button>
        <input ref={validateRef} type="file" accept=".csv" className="hidden"
          onChange={(e) => onValidate(e.target.files?.[0])} />

        <a href="/samples/batch_sample.csv" download
          className="text-[13px] font-medium text-teal-700 underline decoration-teal-300 underline-offset-2 hover:decoration-teal-600">
          sample CSV
        </a>
        <a href="/samples/validation_labelled.csv" download
          className="text-[13px] font-medium text-teal-700 underline decoration-teal-300 underline-offset-2 hover:decoration-teal-600">
          labelled sample
        </a>
        {data && (
          <button onClick={exportCsv}
            className="ml-auto rounded-lg border border-slate-300 px-4 py-2 text-[13px] font-semibold text-slate-700 hover:border-teal-400 hover:text-teal-700">
            ⬇ Export results CSV
          </button>
        )}
      </div>

      {/* validation report */}
      {validation && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Agreement with expert labels
            </h2>
            <button onClick={() => setValidation(null)}
              className="text-[12px] text-slate-400 hover:text-slate-700">dismiss</button>
          </div>
          <p className="mt-1 text-[13.5px] font-medium text-slate-800">{validation.summary}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.values(validation.metrics).map((m) => (
              <div key={m.field} className="rounded-xl bg-slate-50 p-3">
                <div className="text-[10.5px] font-semibold uppercase tracking-wider text-slate-400">
                  {m.field}
                </div>
                {m.agreement !== undefined ? (
                  <>
                    <div className="mt-1 text-2xl font-bold text-slate-800">{m.agreement}%</div>
                    <div className="text-[11.5px] text-slate-500">
                      κ = {m.cohens_kappa} ({m.kappa_interpretation}), n = {m.n}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="mt-1 text-2xl font-bold text-slate-800">
                      ±{m.mean_absolute_error_pct}
                    </div>
                    <div className="text-[11.5px] text-slate-500">
                      mean error, {m.within_1_pct}% within 1 point
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
            {validation.caveat}
          </p>
        </div>
      )}

      {/* triage worklist — who gets seen first */}
      {data?.worklist?.total > 0 && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Triage worklist
            </h2>
            {data.performance && (
              <span className="text-[12px] text-slate-500">
                {data.performance.cases ?? data.performance.digitized} case(s) in{' '}
                <b>{data.performance.total_seconds}s</b>
                {data.performance.mean_ms
                  ? ` · ${data.performance.mean_ms} ms each · ${data.performance.cases_per_minute}/min`
                  : ''}
              </span>
            )}
          </div>
          <p className="mt-1 text-[14px] font-semibold text-slate-800">
            {data.worklist.headline}
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {['critical', 'urgent', 'review', 'routine'].map((k) => (
              <div key={k} className={`rounded-xl p-3 ${
                k === 'critical' ? 'bg-rose-50' : k === 'urgent' ? 'bg-orange-50'
                  : k === 'review' ? 'bg-amber-50' : 'bg-slate-50'}`}>
                <div className="text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">
                  {PRIORITY_STYLE[k].label}
                </div>
                <div className={`mt-1 text-2xl font-bold ${
                  k === 'critical' ? 'text-rose-700' : k === 'urgent' ? 'text-orange-700'
                    : k === 'review' ? 'text-amber-700' : 'text-slate-700'}`}>
                  {data.worklist.by_priority[k]}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 px-3 py-2">
            <span className="text-[12.5px] text-slate-600">
              <b className="text-teal-700">{data.worklist.auto_releasable}</b> draft(s)
              auto-releasable ({data.worklist.auto_release_pct}%) ·{' '}
              <b className="text-amber-700">{data.worklist.review_required}</b> need an
              audiologist
            </span>
            <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-[12.5px] text-slate-600">
              <input type="checkbox" checked={onlyReview} className="h-3.5 w-3.5 accent-teal-600"
                onChange={(e) => setOnlyReview(e.target.checked)} />
              show only cases needing review
            </label>
          </div>
        </div>
      )}

      {data?.failed?.length > 0 && (
        <div className="mt-3 rounded-xl bg-amber-50 px-4 py-2.5 text-[12.5px] text-amber-900">
          <b>{data.failed.length} photo(s) could not be read:</b>{' '}
          {data.failed.map((f) => f.file).join(', ')} — enter these manually.
        </div>
      )}

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
                <th className="px-3 py-2.5 font-semibold">Priority</th>
                <th className="px-3 py-2.5 font-semibold">Patient</th>
                <th className="px-3 py-2.5 font-semibold text-red-600">Right ear</th>
                <th className="px-3 py-2.5 font-semibold text-blue-600">Left ear</th>
                <th className="px-3 py-2.5 font-semibold">Disability</th>
              </tr>
            </thead>
            <tbody>
              {data.results
                .filter((r) => !onlyReview || r.triage?.review_required)
                .map((r, i) => (
                <tr key={r.row ?? r.file ?? i}
                  className={`border-b border-slate-50 hover:bg-slate-50/50 ${
                    PRIORITY_STYLE[r.triage?.level]?.row || ''}`}>
                  <td className="px-3 py-2.5">
                    {r.triage && (
                      <>
                        <span className={`rounded-md px-2 py-1 text-[10.5px] font-bold uppercase ${
                          PRIORITY_STYLE[r.triage.level].chip}`}
                          title={r.triage.reasons.map((x) => x.detail).join('; ')}>
                          {PRIORITY_STYLE[r.triage.level].label}
                        </span>
                        <div className="mt-1 text-[10.5px] text-slate-500">
                          {r.triage.auto_releasable ? 'auto-release' : r.triage.sla}
                        </div>
                      </>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[13px] font-semibold text-slate-800">{r.name}</span>
                      {r.urgent && (
                        <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[9.5px] font-bold uppercase text-rose-700"
                          title={(r.alerts || []).join('; ')}>refer</span>
                      )}
                    </div>
                    <div className="text-[11.5px] text-slate-500">
                      {[r.age && `${r.age} y`, r.occupation, r.method].filter(Boolean).join(' · ')}
                    </div>
                    {r.triage?.reasons?.length > 0 && (
                      <div className="mt-0.5 text-[10.5px] leading-snug text-amber-700">
                        {r.triage.reasons.map((x) => x.detail).slice(0, 2).join('; ')}
                      </div>
                    )}
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
            * = type provisional (BC incomplete) · OOD = atypical pattern, priority human
            review · rows are ordered by clinical priority, not upload order
          </div>
        </div>
      )}
    </div>
  )
}
