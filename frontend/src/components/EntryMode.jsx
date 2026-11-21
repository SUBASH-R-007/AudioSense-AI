// How a test gets into the record — and the admission that most of the time
// it is not as numbers.
//
// THE PROBLEM. Every instrument panel in this app was built to accept full
// measurements: a pressure sweep, a DP-gram with amplitudes and noise floors,
// wave latencies to the tenth of a millisecond. That is the right design for a
// diagnostic booth and the wrong one for most of the places this software is
// meant to run. A newborn screener prints PASS. A camp tablet prints REFER. A
// referral letter says "Type B, left". A tympanometer prints four numbers and
// no sweep. Demanding values that were never recorded does not produce better
// data — it produces an empty field, and an empty field is indistinguishable
// from a test that was never done.
//
// So each instrument offers up to three ways in, and the right one is whatever
// the clinic actually has:
//
//   VALUES    the full measurement. Supports every inference.
//   OUTCOME   pass / refer / incomplete, or a bare type letter. A valid
//             record, and far less than the values support.
//   EXAMPLE   a worked preset, for learning the instrument. Never a patient.
//
// THE ORDER MATTERS AND IS DELIBERATE. "Enter values" is first and is the
// default everywhere. Examples used to be the default, which meant a page
// opened showing fabricated findings beside a real patient's name — and a
// clinician who typed nothing could attach an example to a record. Examples
// now sit last, are never pre-selected, and are labelled as examples
// wherever their output is shown.
//
// WHAT AN OUTCOME CANNOT DO is stated by the backend, per test, in the result
// itself (see dpoae.from_outcome and immittance.from_recorded_type). The UI
// does not paraphrase those limits — it prints them.

import { useId } from 'react'

export const ENTRY_MODES = {
  values: { key: 'values', label: 'Enter values' },
  outcome: { key: 'outcome', label: 'Pass / refer only' },
  preset: { key: 'preset', label: 'Example traces' },
}

/**
 * Segmented control over the entry modes an instrument supports.
 *
 * @param modes  ordered keys, e.g. ['values', 'outcome', 'preset']
 * @param labels optional per-key label override
 */
export function EntryModeTabs({ mode, onMode, modes = ['values', 'outcome', 'preset'],
                                labels = {}, className = 'mt-3' }) {
  return (
    <div role="tablist" aria-label="How this test was recorded"
      className={`flex rounded-lg bg-slate-100 p-0.5 text-[12px] ${className}`}>
      {modes.map((key) => {
        const active = mode === key
        return (
          <button key={key} type="button" role="tab" aria-selected={active}
            onClick={() => onMode(key)}
            className={`flex-1 rounded-md px-3 py-1 font-medium transition ${
              active ? 'bg-white text-teal-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            {labels[key] || ENTRY_MODES[key]?.label || key}
          </button>
        )
      })}
    </div>
  )
}

//: The screening vocabulary. "Fail" is offered because clinics say it, and is
//: normalised to "refer" by the backend — the distinction is not cosmetic: a
//: refer is a referral for diagnostic testing, never a diagnosis of hearing
//: loss, and the wording is what keeps that straight on a report.
export const OUTCOMES = [
  { key: 'pass', label: 'Pass', hint: 'met the criterion',
    cls: 'border-emerald-500 bg-emerald-50 text-emerald-900',
    idle: 'border-slate-200 bg-white text-slate-600 hover:border-emerald-300' },
  { key: 'refer', label: 'Refer', hint: 'did not meet it — needs diagnostic testing',
    cls: 'border-rose-500 bg-rose-50 text-rose-900',
    idle: 'border-slate-200 bg-white text-slate-600 hover:border-rose-300' },
  { key: 'incomplete', label: 'Incomplete', hint: 'no decision reached — repeat it',
    cls: 'border-amber-500 bg-amber-50 text-amber-900',
    idle: 'border-slate-200 bg-white text-slate-600 hover:border-amber-300' },
]

/**
 * Record a screening result as one word.
 *
 * `note` is free text for what the instrument printed alongside it — the
 * device name, the ear tip size, "settled after feeding". It is kept with the
 * outcome because an outcome with no provenance is hard to defend later.
 */
export function OutcomePicker({ value, onChange, note, onNote, label,
                               noteplaceholder = 'instrument, conditions, anything printed alongside' }) {
  const noteId = useId()
  return (
    <div className="mt-3">
      {label && (
        <span className="mb-1.5 block text-[12px] font-medium text-slate-600">
          {label}
        </span>
      )}
      <div className="flex flex-wrap gap-2">
        {OUTCOMES.map((o) => {
          const active = value === o.key
          return (
            <button key={o.key} type="button" aria-pressed={active}
              onClick={() => onChange(active ? null : o.key)}
              className={`rounded-lg border px-3 py-1.5 text-[12.5px] transition ${
                active ? `${o.cls} font-semibold ring-1 ring-current/20` : o.idle}`}>
              {o.label}
              <span className={`ml-1.5 text-[10.5px] font-normal ${
                active ? 'opacity-75' : 'text-slate-400'}`}>
                {o.hint}
              </span>
            </button>
          )
        })}
      </div>
      {onNote && (
        <label htmlFor={noteId} className="mt-2 block text-[11.5px]">
          <span className="mb-1 block font-medium text-slate-500">
            What was it recorded on? (optional)
          </span>
          <input id={noteId} type="text" value={note || ''} maxLength={500}
            onChange={(e) => onNote(e.target.value)}
            placeholder={noteplaceholderSafe(noteplaceholder)}
            className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-[12.5px]" />
        </label>
      )}
    </div>
  )
}

// Defensive: an older caller passing the misspelled prop should not render
// `undefined` into the placeholder attribute.
function noteplaceholderSafe(v) {
  return typeof v === 'string' ? v : ''
}

/**
 * An editable list of test frequencies.
 *
 * WHY THIS EXISTS. The standard DP-gram set is seven frequencies, and a
 * fixed set is wrong in both directions: an occupational programme may test
 * only 3, 4 and 6 kHz, and a clinic chasing a noise notch may want 5 kHz,
 * which no preset offered. Scoring a clinic against frequencies it did not
 * test, or silently dropping the ones it added, both produce a decision that
 * does not describe the test that was run.
 *
 * Every frequency added here gets a real cochlear place from the Greenwood
 * map server-side, so the interpretation is complete for any set — not just
 * the seven.
 */
export function FrequencyEditor({ freqs, onChange, suggestions = [], min = 125,
                                  max = 16000, label = 'Frequencies tested' }) {
  const inputId = useId()
  const add = (value) => {
    const f = Math.round(Number(value))
    if (!Number.isFinite(f) || f < min || f > max) return false
    if (freqs.includes(f)) return false
    onChange([...freqs, f].sort((a, b) => a - b))
    return true
  }
  const remove = (f) => onChange(freqs.filter((x) => x !== f))

  const fmt = (f) => (f >= 1000
    ? `${(f / 1000).toString().replace(/\.0$/, '')}k` : `${f}`)

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[12px] font-medium text-slate-600">{label}</span>
        <span className="text-[11px] text-slate-400">
          {freqs.length} tested — only these are scored
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {freqs.map((f) => (
          <span key={f}
            className="inline-flex items-center gap-1 rounded-lg border border-teal-300 bg-teal-50 pl-2.5 pr-1 py-1 text-[12px] font-medium text-teal-900">
            {fmt(f)} Hz
            <button type="button" onClick={() => remove(f)}
              aria-label={`Remove ${f} Hz`}
              className="rounded px-1 text-[13px] leading-none text-teal-600 transition hover:bg-teal-200 hover:text-teal-900">
              ×
            </button>
          </span>
        ))}
        {freqs.length === 0 && (
          <span className="text-[12px] text-amber-700">
            No frequencies — add at least one to get a result.
          </span>
        )}
      </div>

      {suggestions.filter((s) => !freqs.includes(s)).length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-slate-400">Add:</span>
          {suggestions.filter((s) => !freqs.includes(s)).map((s) => (
            <button key={s} type="button" onClick={() => add(s)}
              className="rounded-lg border border-slate-200 bg-white px-2 py-0.5 text-[11.5px] text-slate-600 transition hover:border-teal-400 hover:text-teal-700">
              + {fmt(s)}
            </button>
          ))}
        </div>
      )}

      <form className="mt-2 flex items-center gap-1.5"
        onSubmit={(e) => {
          e.preventDefault()
          const el = e.currentTarget.elements[inputId]
          if (add(el.value)) el.value = ''
        }}>
        <input id={inputId} name={inputId} type="number" step="1"
          min={min} max={max} placeholder="other Hz"
          className="w-28 rounded-lg border border-slate-300 px-2 py-1 text-[12px]" />
        <button type="submit"
          className="rounded-lg border border-slate-300 px-2.5 py-1 text-[12px] font-medium text-slate-600 transition hover:border-teal-400 hover:text-teal-700">
          Add
        </button>
      </form>
    </div>
  )
}

/**
 * What an outcome-only record cannot support, printed from the backend's own
 * `limits` list rather than paraphrased here. If the server grows a limit, it
 * appears; if it drops one, it disappears.
 */
export function OutcomeLimits({ limits, className = 'mt-3' }) {
  if (!limits?.length) return null
  return (
    <div className={`rounded-xl border border-slate-300 bg-slate-50 px-3 py-2.5 ${className}`}>
      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Recorded as an outcome — what it does not give
      </span>
      <ul className="mt-1 space-y-0.5 text-[11.5px] leading-relaxed text-slate-600">
        {limits.map((l) => <li key={l}>· {l}</li>)}
      </ul>
    </div>
  )
}
