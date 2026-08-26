// Otoscopy — read a tympanic membrane image against the reference atlas.
//
// The screen is built around what the model can actually support. It leads
// with a ranked differential and the most similar labelled reference views
// side by side with the patient's image, because that is a comparison the
// clinician can judge. It does not lead with a single confident label: exact
// pattern accuracy on the shipped reference set is well under half, and
// presenting that as a diagnosis would be a lie told with a progress bar.
//
// The measured accuracy is read from the model card and shown on screen —
// not hardcoded here, and not buried in a README.

import { useEffect, useRef, useState } from 'react'
import { api, apiUrl } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import LinkagePanel from '../components/LinkagePanel.jsx'
import StepNav from '../components/StepNav.jsx'

//: What the upload accepts, by MIME type. Videos are DISPLAYED, never
//: analysed — the classifier reads still images only.
const MEDIA_TYPES = {
  'image/jpeg': 'image', 'image/png': 'image', 'image/webp': 'image',
  'video/mp4': 'video', 'video/webm': 'video',
}
//: The image cap mirrors the backend's own limit (otoscopy_router MAX_BYTES),
//: so a file this page accepts is never bounced server-side for size. Video
//: stays client-side, so its cap is only about browser memory.
const MAX_IMAGE_BYTES = 12 * 1024 * 1024
const MAX_VIDEO_BYTES = 50 * 1024 * 1024

const fmtBytes = (n) => (n >= 1024 * 1024
  ? `${(n / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

const URGENCY_STYLE = {
  urgent: 'border-rose-300 bg-rose-50 text-rose-800',
  refer: 'border-amber-300 bg-amber-50 text-amber-800',
  treat: 'border-sky-300 bg-sky-50 text-sky-800',
  routine: 'border-emerald-300 bg-emerald-50 text-emerald-800',
}

const CERTAINTY_NOTE = {
  probable: 'Top class is well separated from the rest.',
  provisional: 'Leading class, but not clearly separated — read the differential.',
  uncertain: 'The model cannot separate these patterns. Treat the list as prompts.',
  unreliable: 'Image quality is too poor to interpret. Retake it.',
  'out-of-distribution': 'This does not resemble any reference view. Verify the image is an otoscope capture.',
}

// Tailwind scans source for literal class names, so the colour cannot be
// interpolated into the string — it would never be generated.
function Bar({ value, lead = false }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div className={`h-full rounded-full ${lead ? 'bg-teal-500' : 'bg-slate-300'}`}
        style={{ width: `${Math.max(2, Math.round(value * 100))}%` }} />
    </div>
  )
}

function Atlas({ atlas, onPick }) {
  if (!atlas) return null
  return (
    <div data-tour="otoscopy-atlas" className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">Reference atlas</h2>
        <span className="text-[12px] text-slate-500">
          {atlas.total_images} labelled views across {atlas.classes.length} patterns
        </span>
      </div>
      <p className="mt-1 text-[12.5px] leading-relaxed text-slate-500">{atlas.source}</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {atlas.classes.map((c) => (
          <div key={c.label} className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="text-[13px] font-semibold text-slate-800">{c.name}</div>
              <span className={`shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                URGENCY_STYLE[c.urgency] || 'border-slate-300 bg-white text-slate-600'}`}>
                {c.urgency}
              </span>
            </div>
            <div className="mt-2 flex gap-1.5">
              {c.images.slice(0, 3).map((src) => (
                <button key={src} onClick={() => onPick?.(src)} type="button"
                  className="h-14 w-14 overflow-hidden rounded-lg border border-slate-200 transition hover:ring-2 hover:ring-teal-400"
                  title="Use this reference view as a test image">
                  <img src={apiUrl(src)} alt="" className="h-full w-full object-cover" />
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11.5px] leading-relaxed text-slate-600">{c.appearance}</p>
            <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
              <span className="font-semibold text-slate-600">Expect:</span> {c.expected_hearing} Tympanogram {c.expected_tympanogram}.
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Otoscopy() {
  const { patient, analysis, assessment, otoscopy, setOtoscopy, showToast } = useApp()
  const fileRef = useRef(null)
  const [atlas, setAtlas] = useState(null)
  const [card, setCard] = useState(null)
  const [side, setSide] = useState('right')
  // What was uploaded, whatever happened to it afterwards. The preview used to
  // exist only inside the result panel, so a failed analysis showed nothing at
  // all — the clinician could not even see which file had failed.
  const [media, setMedia] = useState(null) // { url, name, size, kind }
  const [mediaError, setMediaError] = useState(null)
  // Shared, so the symptom page and the dashboard can cross-check against it.
  const result = otoscopy
  const setResult = setOtoscopy
  const [busy, setBusy] = useState(false)

  const [fromImage, setFromImage] = useState(null)

  useEffect(() => {
    api.otoscopyAtlas().then(setAtlas).catch(() => setAtlas(null))
    api.otoscopyModel().then(setCard).catch(() => setCard(null))
  }, [])

  // The image's own differential, recomputed whenever a new one is read.
  useEffect(() => {
    if (!result) { setFromImage(null); return }
    let cancelled = false
    api.diseasesFromOtoscopy(result)
      .then((r) => { if (!cancelled) setFromImage(r) })
      .catch(() => { if (!cancelled) setFromImage(null) })
    return () => { cancelled = true }
  }, [result])

  // Revoke the PREVIOUS object URL whenever the media changes, and the last
  // one on unmount — the cleanup closure holds the old value. These URLs used
  // to leak on every upload.
  useEffect(() => () => { if (media?.url) URL.revokeObjectURL(media.url) }, [media])

  async function analyse(file) {
    setBusy(true)
    setResult(null)
    try {
      // The current analysis rides along so the cross-check against the
      // audiogram and tympanogram happens in the same round trip.
      setResult(await api.otoscopy(file, side, analysis))
    } catch (e) {
      showToast(e.message || 'Could not read that image', 'error')
    } finally {
      setBusy(false)
    }
  }

  function chooseFile(file) {
    if (!file) return
    setMediaError(null)

    const kind = MEDIA_TYPES[file.type]
    if (!kind) {
      setMediaError(`"${file.name}" is ${file.type || 'an unrecognised type'} — `
        + 'use a JPG, PNG or WebP image, or an MP4 or WebM video.')
      return
    }
    const cap = kind === 'video' ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES
    if (file.size > cap) {
      setMediaError(`"${file.name}" is ${fmtBytes(file.size)} — the limit is `
        + `${fmtBytes(cap)} for ${kind === 'video' ? 'video' : 'images'}.`)
      return
    }

    setMedia({ url: URL.createObjectURL(file), name: file.name,
               size: file.size, kind })
    if (kind === 'image') {
      analyse(file)
    } else {
      // The classifier reads still images; a video is shown for viewing only,
      // so a stale differential from a previous image must not sit next to it.
      // TODO(frame-grab): capture a chosen frame from the video client-side
      // and send that still through /api/otoscopy/analyze.
      setResult(null)
    }
  }

  function removeMedia() {
    setMedia(null)
    setMediaError(null)
    setResult(null)
    // Selecting the same file again must re-fire the change event.
    if (fileRef.current) fileRef.current.value = ''
  }

  // Atlas thumbnails double as test images — the fastest way to demonstrate
  // the pipeline without a patient in the chair.
  async function runReference(src) {
    setBusy(true)
    setResult(null)
    setMediaError(null)
    try {
      const blob = await fetch(apiUrl(src)).then((r) => r.blob())
      setMedia({ url: URL.createObjectURL(blob), name: 'Reference view',
                 size: blob.size, kind: 'image' })
      setResult(await api.otoscopy(new File([blob], 'reference.png', { type: 'image/png' }),
        side, analysis))
    } catch (e) {
      showToast(e.message || 'Could not load that reference view', 'error')
    } finally {
      setBusy(false)
    }
  }

  const validation = card?.validation
  const conc = result?.concordance
  // One tympanic membrane looks much like another on screen, and this page will
  // happily read an image against whatever case happens to be open. Naming the
  // patient is the only thing that makes the mismatch visible before a finding
  // is filed under the wrong ear.
  const patientName = (patient?.name || '').trim()

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">Otoscopy</h1>
        <p className="mt-1 max-w-3xl text-[13.5px] leading-relaxed text-slate-500">
          Match a tympanic-membrane image against the labelled reference patterns, then
          check what it predicts against the audiogram and tympanogram already on file.
        </p>
      </header>

      {/* --- upload ------------------------------------------------------ */}
      <div data-tour="otoscopy-upload" className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-[13px]">
            <span className="mb-1 block font-medium text-slate-600">Ear</span>
            <select value={side} onChange={(e) => setSide(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-[13px]">
              <option value="right">Right</option>
              <option value="left">Left</option>
            </select>
          </label>
          <input ref={fileRef} type="file"
            accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"
            className="hidden" onChange={(e) => chooseFile(e.target.files?.[0])} />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={busy}
            className="rounded-lg bg-teal-600 px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:bg-teal-700 disabled:opacity-50">
            {busy ? 'Reading…' : media ? 'Replace image or video' : 'Upload image or video'}
          </button>
          <span className="text-[12px] text-slate-500">
            Will cross-check{' '}
            {patientName
              ? <><span className="font-medium text-slate-700">{patientName}</span>’s image</>
              : 'this image'}{' '}
            against{' '}
            {[analysis && 'the audiogram', assessment && 'the symptom history']
              .filter(Boolean).join(' and ') || 'nothing yet'}
            {!analysis || !assessment ? (
              <span className="text-slate-400">
                {' '}— add {[!analysis && 'a test', !assessment && 'a history']
                  .filter(Boolean).join(' and ')} for the full comparison.
              </span>
            ) : '.'}
          </span>
        </div>

        {validation && (
          <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
            <span className="font-semibold">Measured on the shipped reference set:</span>{' '}
            exact pattern correct {Math.round(validation.accuracy * 100)}% of the time
            (chance {Math.round(validation.chance_level * 100)}%), correct answer in the
            top three {Math.round(validation.top3_accuracy * 100)}%, urgency band correct{' '}
            {Math.round(validation.urgency_accuracy * 100)}%. Held out one whole image at
            a time. Use the ranked list, not the headline.
          </p>
        )}

        {/* Unconditional, unlike the measured figures above — those only render
            once the model card loads, and this caveat has to hold whether or
            not it does. */}
        <p className="mt-2 text-[11.5px] leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-600">Note:</span> these
          results are not yet reliable, because the training set is small. The
          accuracy will improve in further iterations of the software.
        </p>

        {mediaError && (
          <p role="alert"
            className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12.5px] text-rose-800">
            {mediaError}
          </p>
        )}
      </div>

      {/* --- what was uploaded ------------------------------------------- */}
      {/* Videos always render here (they never produce a result panel); an
          image shows here only until its analysis succeeds, at which point the
          result panel below takes over the same object URL. */}
      {media && (media.kind === 'video' || !result) && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-900">
            {media.kind === 'video' ? (
              <video src={media.url} controls playsInline preload="metadata"
                className="mx-auto max-h-80 w-full object-contain"
                aria-label={`Uploaded otoscope video: ${media.name}`} />
            ) : (
              <img src={media.url} alt={`Uploaded otoscope view: ${media.name}`}
                className="mx-auto max-h-72 object-contain" />
            )}
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-[12px] text-slate-600">
              <span className="font-medium text-slate-800">{media.name}</span>
              {' '}· {fmtBytes(media.size)} · {media.kind}
            </span>
            <button type="button" onClick={() => fileRef.current?.click()}
              className="rounded-lg border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-slate-600 transition hover:border-slate-300">
              Replace
            </button>
            <button type="button" onClick={removeMedia}
              className="rounded-lg border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-slate-600 transition hover:border-rose-300 hover:text-rose-700">
              Remove
            </button>
          </div>
          {media.kind === 'video' && (
            <p className="mt-2.5 rounded-lg border border-sky-300 bg-sky-50 px-3 py-2 text-[12px] leading-relaxed text-sky-900">
              Video is shown for viewing and documentation only — the AI reads
              still images. Pause on the clearest view of the drum and upload a
              screenshot of that frame to run the analysis.
            </p>
          )}
          {media.kind === 'image' && busy && (
            <p className="mt-2.5 text-[12px] text-slate-400">Analysing…</p>
          )}
          {media.kind === 'image' && !busy && !result && (
            <p className="mt-2.5 text-[12px] text-slate-500">
              The analysis did not complete — the image is kept here so you can
              see what was sent. Replace it or try again.
            </p>
          )}
        </div>
      )}

      {/* --- result ------------------------------------------------------ */}
      {result && (
        <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1.15fr]">
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-900">
              {media?.url && <img src={media.url} alt="Uploaded otoscope view"
                className="mx-auto max-h-72 object-contain" />}
            </div>
            {media && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-[12px] text-slate-600">
                  <span className="font-medium text-slate-800">{media.name}</span>
                  {' '}· {fmtBytes(media.size)}
                </span>
                <button type="button" onClick={() => fileRef.current?.click()}
                  className="rounded-lg border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-slate-600 transition hover:border-slate-300">
                  Replace
                </button>
                <button type="button" onClick={removeMedia}
                  className="rounded-lg border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-slate-600 transition hover:border-rose-300 hover:text-rose-700">
                  Remove
                </button>
              </div>
            )}

            {!result.quality.usable && (
              <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12.5px] text-rose-800">
                <div className="font-semibold">Image quality is not adequate.</div>
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  {result.quality.issues.map((i) => <li key={i}>{i}</li>)}
                </ul>
              </div>
            )}

            <dl className="mt-4 grid grid-cols-2 gap-2 text-[12px]">
              {[
                ['Erythema', result.measurements.erythema],
                ['Cone of light', result.measurements.cone_of_light],
                ['Wax fraction', result.measurements.wax_fraction],
                ['Dark defect', result.measurements.defect_size],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg bg-slate-50 px-2.5 py-2">
                  <dt className="text-[11px] font-medium text-slate-500">{label}</dt>
                  <dd className="mt-0.5 font-mono text-[13px] text-slate-800">
                    {(value ?? 0).toFixed(3)}
                  </dd>
                </div>
              ))}
            </dl>

            <h3 className="mt-4 text-[12px] font-semibold uppercase tracking-wider text-slate-400">
              What the image shows
            </h3>
            <ul className="mt-1.5 space-y-1 text-[12.5px] leading-relaxed text-slate-600">
              {result.evidence.map((e, i) => <li key={i}>· {e}</li>)}
            </ul>
          </div>

          <div data-tour="otoscopy-result" className="space-y-5">
            <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-lg border px-2.5 py-1 text-[12px] font-semibold ${
                  URGENCY_STYLE[result.urgency.key] || 'border-slate-300 bg-slate-50 text-slate-700'}`}>
                  {result.urgency.name}
                </span>
                <span className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-[12px] font-medium text-slate-700">
                  {result.category.name} · {Math.round(result.category.probability * 100)}%
                </span>
              </div>
              <p className="mt-2 text-[12px] text-slate-500">
                {CERTAINTY_NOTE[result.prediction.certainty] || ''}
              </p>
              {result.training_set_note && (
                <p className="mt-2 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-[12px] leading-relaxed text-slate-700">
                  {result.training_set_note}
                </p>
              )}

              <h3 className="mt-4 text-[12px] font-semibold uppercase tracking-wider text-slate-400">
                Differential
              </h3>
              <ul className="mt-2 space-y-2.5">
                {result.ranked.slice(0, 4).map((r, i) => (
                  <li key={r.label}>
                    <div className="flex items-baseline justify-between gap-3 text-[13px]">
                      <span className={i === 0 ? 'font-semibold text-slate-900' : 'text-slate-700'}>
                        {r.name}
                      </span>
                      <span className="font-mono text-[12px] text-slate-500">
                        {Math.round(r.probability * 100)}%
                      </span>
                    </div>
                    <div className="mt-1"><Bar value={r.probability} lead={i === 0} /></div>
                  </li>
                ))}
              </ul>
            </div>

            {/* Reference comparison — the part that stays useful even when
                the classifier is unsure. */}
            <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
              <h3 className="text-[15px] font-semibold text-slate-900">Closest reference views</h3>
              <p className="mt-1 text-[12px] text-slate-500">
                Labelled images from the reference document, ranked by visual similarity.
                Compare them against the capture yourself.
              </p>
              <div className="mt-3 grid grid-cols-3 gap-3">
                {result.reference_matches.map((m) => (
                  <figure key={m.image} className="rounded-xl border border-slate-200 p-2">
                    <img src={apiUrl(m.image)} alt={m.name}
                      className="h-24 w-full rounded-lg object-cover" />
                    <figcaption className="mt-1.5 text-[11px] leading-tight text-slate-600">
                      <span className="font-medium">{m.name}</span>
                      <span className="block text-slate-400">
                        similarity {m.similarity.toFixed(2)}
                      </span>
                    </figcaption>
                  </figure>
                ))}
              </div>
            </div>

            {/* Clinical consequence of the leading pattern. */}
            <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
              <h3 className="text-[15px] font-semibold text-slate-900">
                If this is {result.clinical.name?.toLowerCase()}
              </h3>
              <dl className="mt-3 space-y-2 text-[12.5px] leading-relaxed">
                <div>
                  <dt className="font-semibold text-slate-600">Expected hearing</dt>
                  <dd className="text-slate-700">{result.clinical.expected_hearing}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-slate-600">Expected tympanogram</dt>
                  <dd className="text-slate-700">Type {result.clinical.expected_tympanogram}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-slate-600">Next tests</dt>
                  <dd className="text-slate-700">
                    {result.clinical.recommended_tests?.join(' · ')}
                  </dd>
                </div>
                <div>
                  <dt className="font-semibold text-slate-600">Management</dt>
                  <dd className="text-slate-700">{result.clinical.referral}</dd>
                </div>
              </dl>
              {result.clinical.red_flags?.length > 0 && (
                <ul className="mt-3 space-y-1 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] leading-relaxed text-rose-800">
                  {result.clinical.red_flags.map((f) => <li key={f}>⚠ {f}</li>)}
                </ul>
              )}
              {result.clinical.note && (
                <p className="mt-3 text-[12px] italic leading-relaxed text-slate-500">
                  {result.clinical.note}
                </p>
              )}
            </div>

            {/* The differential this image produces on its own. No history and
                no audiogram — a scope goes in the ear before the patient is in
                the booth, and the appearance already narrows the list. */}
            {fromImage?.available && (
              <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-[15px] font-semibold text-slate-900">
                    Diseases this appearance points to
                  </h3>
                  <span className="text-[11.5px] text-slate-500">from the image alone</span>
                </div>
                <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-700">
                  {fromImage.headline}
                </p>

                {fromImage.differential.length > 0 && (
                  <ul className="mt-3 space-y-2">
                    {fromImage.differential.slice(0, 5).map((d, i) => (
                      <li key={d.key}>
                        <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
                          <span className={i === 0 && fromImage.separated
                            ? 'font-semibold text-slate-900' : 'text-slate-700'}>
                            {d.name}
                          </span>
                          <span className="font-mono text-[11.5px] text-slate-500">
                            {Math.round(d.score * 100)}
                          </span>
                        </div>
                        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full rounded-full bg-teal-500"
                            style={{ width: `${Math.max(3, Math.round(d.score * 100))}%` }} />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                {fromImage.other_conditions.length > 0 && (
                  <p className="mt-3 text-[12px] leading-relaxed text-slate-600">
                    <span className="font-semibold">Also consider:</span>{' '}
                    {fromImage.other_conditions.join(' · ')}
                  </p>
                )}
                {fromImage.argues_against.length > 0 && (
                  <p className="mt-1.5 text-[12px] leading-relaxed text-slate-600">
                    <span className="font-semibold text-rose-700">Argues against:</span>{' '}
                    {fromImage.argues_against.map((d) => d.name).join(' · ')}
                  </p>
                )}
                {fromImage.reasoning.map((r) => (
                  <p key={r} className="mt-2 text-[11.5px] leading-relaxed text-slate-500">
                    {r}
                  </p>
                ))}
                <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                  {fromImage.note}
                </p>
              </div>
            )}

            {/* Does the history confirm the image? This is the check the
                classifier's weakness makes most valuable — two independent
                methods reaching the same answer from different evidence. */}
            <LinkagePanel side={side} />

            {/* Cross-check: independent of whether the classifier is right. */}
            {conc && (
              <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
                <h3 className="text-[15px] font-semibold text-slate-900">
                  Against the rest of the battery
                </h3>
                {!conc.available ? (
                  <p className="mt-1.5 text-[12.5px] text-slate-500">{conc.note}</p>
                ) : (
                  <>
                    <p className="mt-1.5 text-[12.5px] font-medium text-slate-700">
                      {conc.headline}
                    </p>
                    {conc.agreements.map((a) => (
                      <div key={a.title}
                        className="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[12px] text-emerald-900">
                        <div className="font-semibold">✓ {a.title}</div>
                        <div className="mt-0.5 leading-relaxed">{a.detail}</div>
                      </div>
                    ))}
                    {conc.conflicts.map((c) => (
                      <div key={c.title}
                        className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
                        <div className="font-semibold">⚠ {c.title}</div>
                        <div className="mt-0.5 leading-relaxed">{c.detail}</div>
                        <div className="mt-1 font-medium">{c.action}</div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}

            <p className="text-[11.5px] leading-relaxed text-slate-400">{result.disclaimer}</p>
          </div>
        </div>
      )}

      <Atlas atlas={atlas} onPick={runReference} />

      {card?.limits && (
        <div data-tour="otoscopy-limits" className="mt-5 rounded-2xl border border-slate-200/80 bg-slate-50/60 p-5">
          <h2 className="text-[13px] font-semibold text-slate-800">What this model cannot do</h2>
          <ul className="mt-2 space-y-1 text-[12.5px] leading-relaxed text-slate-600">
            {card.limits.map((l) => <li key={l}>· {l}</li>)}
          </ul>
          <p className="mt-2.5 text-[12px] leading-relaxed text-slate-500">{card.improve}</p>
        </div>
      )}

      <StepNav stepKey="otoscopy" />
    </div>
  )
}
