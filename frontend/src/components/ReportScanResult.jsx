// What came off a scanned audiometry report, and what still needs a human.
//
// GUIDED TRANSCRIPTION IS THE POINT. With no OCR engine and no vision
// provider configured — the default for this app, which ships needing zero
// keys — the printed fields on a report page cannot be read automatically.
// The useless answer is to say so and leave the clinician retyping a page
// from scratch. The useful one is to show them the exact crop of the page
// that holds each field, next to the box it goes in. Reading a value off a
// 60-pixel-tall strip and typing it is seconds of work and carries no risk of
// a transcription the software invented.
//
// The crops are cut HERE, in the browser, from the file that was uploaded.
// The server sends coordinates — a few hundred bytes — rather than twenty
// base64 thumbnails, and the original page never has to come back down.
//
// WHERE A VALUE WAS READ, it is shown as a suggestion in an editable box with
// the line it came from underneath, so it can be checked against the page
// without hunting for it. Nothing here is written into the patient record
// until the clinician presses the button that says so.

import { useEffect, useMemo, useRef, useState } from 'react'
import { Reveal } from './Collapsible.jsx'

const SEX_OPTIONS = ['', 'female', 'male', 'unspecified']

/** One region of the uploaded page, drawn to a canvas at a readable height. */
function Crop({ pageUrl, region, maxHeight = 46 }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!pageUrl || !region || !ref.current) return
    const canvas = ref.current
    const img = new Image()
    let cancelled = false
    img.onload = () => {
      if (cancelled) return
      // The scan was analysed at a bounded size, so the coordinates are in
      // that frame. Scale them onto the original file's pixels.
      const sx = img.naturalWidth / (region.pageW || img.naturalWidth)
      const sy = img.naturalHeight / (region.pageH || img.naturalHeight)
      const pad = 4
      const x = Math.max(0, (region.x - pad) * sx)
      const y = Math.max(0, (region.y - pad) * sy)
      const w = Math.min(img.naturalWidth - x, (region.w + pad * 2) * sx)
      const h = Math.min(img.naturalHeight - y, (region.h + pad * 2) * sy)
      if (w <= 0 || h <= 0) return
      const scale = Math.min(maxHeight / h, 3)
      canvas.width = Math.round(w * scale)
      canvas.height = Math.round(h * scale)
      const ctx = canvas.getContext('2d')
      ctx.imageSmoothingQuality = 'high'
      ctx.drawImage(img, x, y, w, h, 0, 0, canvas.width, canvas.height)
    }
    img.src = pageUrl
    return () => { cancelled = true }
  }, [pageUrl, region, maxHeight])

  if (!pageUrl || !region) return null
  return (
    <canvas ref={ref} aria-label="Crop of the uploaded page"
      className="max-w-full rounded border border-slate-200 bg-white" />
  )
}

export default function ReportScanResult({ scan, pageUrl, fields, onField,
                                           onApplyPatient }) {
  const [regionIndex, setRegionIndex] = useState(0)
  const read = scan.fields || {}
  const page = scan.page || {}

  const regions = useMemo(
    () => (scan.text_regions || []).map((r) => ({ ...r, pageW: page.w, pageH: page.h })),
    [scan.text_regions, page.w, page.h])

  const thresholds = scan.thresholds
  const chartOk = Boolean(thresholds?.ok)
  const countRead = Object.keys(read).length

  return (
    <div className="mt-4 space-y-4">
      {/* --- what happened to the audiogram ---------------------------- */}
      <div className={`rounded-xl border px-3 py-2.5 ${
        chartOk ? 'border-emerald-300 bg-emerald-50' : 'border-amber-300 bg-amber-50'}`}>
        <span className={`text-[11px] font-semibold uppercase tracking-wide ${
          chartOk ? 'text-emerald-700' : 'text-amber-700'}`}>
          {chartOk ? 'Audiogram read from the page' : 'Audiogram not read'}
        </span>
        <p className={`mt-1 text-[12.5px] leading-relaxed ${
          chartOk ? 'text-emerald-900' : 'text-amber-900'}`}>
          {chartOk ? (
            <>
              The values are in the threshold grid below with their confidence
              badges — check them against the chart before analysing.
              {thresholds.detection?.greyscale && (
                <> This page carries no usable colour, so each ear was decided
                  from the symbol shape alone.</>
              )}
            </>
          ) : (
            <>Nothing has been written into the grid. See the notes below, or
              crop to the chart and use Snap-to-Digitize.</>
          )}
        </p>
      </div>

      {(scan.notes || []).length > 0 && (
        <ul className="space-y-1.5">
          {scan.notes.map((n) => (
            <li key={n}
              className="rounded-lg bg-slate-50 px-3 py-2 text-[12px] leading-relaxed text-slate-600">
              {n}
            </li>
          ))}
        </ul>
      )}

      {chartOk && (thresholds.warnings || []).length > 0 && (
        <Reveal label={`${thresholds.warnings.length} note(s) on reading the chart`}>
          <ul className="space-y-1">
            {thresholds.warnings.map((w) => (
              <li key={w} className="text-[11.5px] leading-relaxed text-amber-800">
                · {w}
              </li>
            ))}
          </ul>
        </Reveal>
      )}

      {/* --- the printed fields ---------------------------------------- */}
      <div className="rounded-xl border border-slate-200 p-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[12.5px] font-semibold text-slate-800">
            Printed on the report
          </span>
          <span className="text-[11px] text-slate-500">
            {scan.guided
              ? 'read them off the crops and type them in'
              : `${countRead} of ${(scan.expected_fields || []).length} read automatically`}
          </span>
        </div>

        {scan.guided && regions.length > 0 && (
          <div className="mt-2.5 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] font-medium text-slate-500">
                Page block {regionIndex + 1} of {regions.length}
              </span>
              <span className="flex gap-1">
                <button type="button"
                  onClick={() => setRegionIndex((i) => Math.max(0, i - 1))}
                  disabled={regionIndex === 0}
                  className="rounded border border-slate-300 px-2 py-0.5 text-[11.5px] text-slate-600 disabled:opacity-40">
                  Previous
                </button>
                <button type="button"
                  onClick={() => setRegionIndex((i) => Math.min(regions.length - 1, i + 1))}
                  disabled={regionIndex >= regions.length - 1}
                  className="rounded border border-slate-300 px-2 py-0.5 text-[11.5px] text-slate-600 disabled:opacity-40">
                  Next
                </button>
              </span>
            </div>
            <div className="mt-2 overflow-x-auto">
              <Crop pageUrl={pageUrl} region={regions[regionIndex]} maxHeight={54} />
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
              Step through the blocks of the page and type what each one says
              into the fields below. Nothing here is guessed from the image.
            </p>
          </div>
        )}

        <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
          {(scan.expected_fields || []).map((field) => {
            const hit = read[field.key]
            const value = fields[field.key] ?? ''
            return (
              <label key={field.key} className="text-[12px]">
                <span className="mb-1 flex items-baseline justify-between gap-2">
                  <span className="font-medium text-slate-600">{field.label}</span>
                  {hit && (
                    <span className="rounded bg-teal-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-teal-700">
                      read
                    </span>
                  )}
                </span>
                {field.kind === 'sex' ? (
                  <select value={value}
                    onChange={(e) => onField(field.key, e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]">
                    {SEX_OPTIONS.map((o) => (
                      <option key={o} value={o}>{o || '—'}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={['int', 'float', 'percent'].includes(field.kind) ? 'number' : 'text'}
                    value={value}
                    onChange={(e) => onField(field.key, e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-[13px]" />
                )}
                {hit?.source_line && (
                  <span className="mt-0.5 block truncate text-[10.5px] text-slate-400"
                    title={hit.source_line}>
                    from “{hit.source_line}”
                  </span>
                )}
              </label>
            )
          })}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" onClick={onApplyPatient}
            className="rounded-lg bg-teal-600 px-3.5 py-1.5 text-[12.5px] font-semibold text-white transition hover:bg-teal-700">
            Use these patient details
          </button>
          <span className="text-[11px] text-slate-400">
            Name, age and sex only — the age selects the normative bands every
            later test is judged against.
          </span>
        </div>

        {/* The printed PTA/SRT/word scores are kept for comparison, not fed
            into the analysis: this app recomputes them from the thresholds,
            and silently preferring a scanned number over its own arithmetic
            would make the two disagree with no way to tell which was which. */}
        <Reveal className="mt-3" label="What happens to the printed results">
          <p className="text-[11px] leading-relaxed text-slate-500">
            The pure-tone averages, speech scores, impression and
            recommendation are recorded here for comparison only. Everything
            this app reports is recomputed from the thresholds in the grid, so
            the two can be held against each other — a printed PTA that
            disagrees with the one computed from the same chart means a value
            was transcribed wrongly, and that is worth seeing rather than
            hiding.
          </p>
        </Reveal>
      </div>
    </div>
  )
}
