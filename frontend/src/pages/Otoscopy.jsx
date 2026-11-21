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
//
// TWO EARS, TWO FINDINGS. Each ear keeps its own image, its own reading and
// its own cross-checks, and the tabs below switch between them without
// touching the other. Before this, examining the right ear and then the left
// overwrote the first: the panel showed one ear's picture while the selector
// said the other, and the linkage reconciled the wrong ear against the
// audiogram. A perforated left drum beside a normal right one is the
// commonest thing an otoscope sees, so holding one result per case was never
// enough.
//
// THE CLINICIAN OVERRULES THE MODEL. At 27% top-1 on unseen photographs, the
// person holding the scope is right about three times out of four when they
// disagree. "Not what you see?" sets the pattern by hand, and the override is
// authoritative — every panel below re-derives from it (see
// model.apply_correction) and the correction is logged as the expert label
// this model has almost none of.

import { useEffect, useMemo, useRef, useState } from 'react'
import { api, apiUrl } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import LinkagePanel from '../components/LinkagePanel.jsx'
import StepNav from '../components/StepNav.jsx'
import Collapsible, { Reveal, ReferenceSection } from '../components/Collapsible.jsx'

//: What the upload accepts, by MIME type. Videos are DISPLAYED, never
//: analysed — the classifier reads still images only.
const MEDIA_TYPES = {
  'image/jpeg': 'image', 'image/png': 'image', 'image/webp': 'image',
  'video/mp4': 'video', 'video/webm': 'video',
}
const IMAGE_EXTENSIONS = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' }
//: The image cap mirrors the backend's own limit (otoscopy_router MAX_BYTES),
//: so a file this page accepts is never bounced server-side for size. Video
//: stays client-side, so its cap is only about browser memory.
const MAX_IMAGE_BYTES = 12 * 1024 * 1024
const MAX_VIDEO_BYTES = 50 * 1024 * 1024

const EARS = ['right', 'left']
const EAR_LABEL = { right: 'Right ear', left: 'Left ear' }

const fmtBytes = (n) => (n >= 1024 * 1024
  ? `${(n / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

const URGENCY_STYLE = {
  urgent: 'border-rose-300 bg-rose-50 text-rose-800',
  refer: 'border-amber-300 bg-amber-50 text-amber-800',
  treat: 'border-sky-300 bg-sky-50 text-sky-800',
  routine: 'border-emerald-300 bg-emerald-50 text-emerald-800',
}

const CERTAINTY_NOTE = {
  // "Well separated" describes the model's own scores, not its accuracy: on
  // unseen photographs most "probable" calls were wrong (the held-out count
  // is shown beside it when the server provides it).
  probable: 'Top class is well separated from the rest — which is not the same as being right.',
  provisional: 'Leading class, but not clearly separated — read the differential.',
  uncertain: 'The model cannot separate these patterns. Treat the list as prompts.',
  unreliable: 'Image quality is too poor to interpret. Retake it.',
  'out-of-distribution': 'This does not resemble any reference view. Verify the image is an otoscope capture.',
  clinician_confirmed: 'Pattern set by you on direct examination — the model’s accuracy does not apply to it.',
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

// Every reference image is requested under this versioned URL. Browsers that
// opened the atlas before the API sent CORS and caching headers hold copies
// stored without Access-Control-Allow-Origin, and with no Cache-Control they
// treat those as fresh for days — so a crossOrigin <img> on the old URL would
// fail and show a broken thumbnail. A URL they have never cached cannot hit
// that copy. Change the version if the image headers ever change again.
const REFERENCE_IMAGE_VERSION = 'cors1'
const referenceUrl = (src) =>
  `${apiUrl(src)}${src.includes('?') ? '&' : '?'}v=${REFERENCE_IMAGE_VERSION}`

// Collapsed by default, and lazily mounted with it: the atlas is 62
// photographs across eight patterns, and a reader who never opens it should
// not pay for a single one of those requests. It is reference material — the
// patient's own reading is what the page is for.
function Atlas({ atlas, onPick }) {
  if (!atlas) return null
  return (
    <div className="mt-5">
      <ReferenceSection dataTour="otoscopy-atlas" title="Reference atlas"
        badge={`${atlas.total_images} views`}
        subtitle={`${atlas.total_images} labelled views across ${atlas.classes.length} patterns — what the classifier was trained on, and what to compare against. Tap a thumbnail to run it as a test image.`}>
        <p className="text-[12.5px] leading-relaxed text-slate-500">{atlas.source}</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {atlas.classes.map((c) => (
            <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="text-[13px] font-semibold text-slate-800">{c.name}</div>
                <span className={`shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  URGENCY_STYLE[c.urgency] || 'border-slate-300 bg-white text-slate-600'}`}>
                  {c.urgency}
                </span>
              </div>
              {/* crossOrigin on every reference <img>: the API is another
                  origin in deployment, and a plain <img> request (no Origin
                  header) is answered without Access-Control-Allow-Origin or
                  Vary: Origin. The browser caches that response and hands it to
                  the fetch() in runReference for the same URL, which then fails
                  CORS ("Failed to fetch"). */}
              <div className="mt-2 flex gap-1.5">
                {c.images.slice(0, 3).map((src) => (
                  <button key={src} onClick={() => onPick?.(src)} type="button"
                    className="h-14 w-14 overflow-hidden rounded-lg border border-slate-200 transition hover:ring-2 hover:ring-teal-400"
                    title="Use this reference view as a test image">
                    <img src={referenceUrl(src)} alt="" crossOrigin="anonymous"
                      className="h-full w-full object-cover" />
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
      </ReferenceSection>
    </div>
  )
}

/**
 * Set the pattern by hand.
 *
 * Deliberately not a "report a bug" affordance. The clinician's examination is
 * better evidence than this classifier, so this is the normal way to finish
 * reading an image — and the corrected pattern, not the predicted one, is what
 * every cross-check below then uses.
 */
function CorrectionPanel({ result, classes, analysis, onCorrected, onUndo, canUndo }) {
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const corrected = result?.correction?.corrected
  const predicted = result?.prediction?.label

  // Reopening for a different image must not keep the previous choice.
  useEffect(() => { setChoice(''); setNote(''); setError(null); setOpen(false) },
    [result?.filename, predicted])

  async function submit() {
    if (!choice) return
    setBusy(true)
    setError(null)
    try {
      onCorrected(await api.otoscopyCorrect({
        result, corrected: choice, note: note.trim(), analysis,
      }))
      setOpen(false)
    } catch (e) {
      setError(e.message || 'Could not record that correction')
    } finally {
      setBusy(false)
    }
  }

  if (corrected) {
    const c = result.correction
    return (
      <div className="mt-3 rounded-xl border border-teal-300 bg-teal-50 px-3 py-2.5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-teal-700">
            Pattern set by you
          </span>
          {canUndo && (
            <button type="button" onClick={onUndo}
              className="text-[11.5px] font-medium text-teal-700 underline decoration-teal-300 underline-offset-2 hover:text-teal-900">
              Undo — go back to the model’s reading
            </button>
          )}
        </div>
        <p className="mt-1 text-[13px] font-medium leading-relaxed text-teal-900">
          {c.name}
          {!c.agreed_with_model && c.model_name && (
            <span className="font-normal text-teal-800">
              {' '}— the model read it as {String(c.model_name).toLowerCase()}
              {c.model_confidence != null
                && ` (${Math.round(c.model_confidence * 100)}%)`}.
            </span>
          )}
          {c.agreed_with_model && (
            <span className="font-normal text-teal-800">
              {' '}— confirming what the model read.
            </span>
          )}
        </p>
        <p className="mt-1 text-[11.5px] leading-relaxed text-teal-800">
          Everything below now follows your pattern, not the model’s.
          {c.stored === false
            ? ' It could not be saved for retraining.'
            : ' It has been saved as an expert label for retraining.'}
        </p>
        {c.note && (
          <p className="mt-1 text-[11.5px] italic leading-relaxed text-teal-800">
            “{c.note}”
          </p>
        )}
      </div>
    )
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}
        className="mt-3 rounded-lg border border-slate-300 px-3 py-1.5 text-[12px] font-medium text-slate-700 transition hover:border-teal-400 hover:text-teal-700">
        Not what you see? Set the pattern yourself
      </button>
    )
  }

  return (
    <div className="mt-3 rounded-xl border border-slate-300 bg-slate-50 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[12.5px] font-semibold text-slate-800">
          What do you see down the scope?
        </span>
        <button type="button" onClick={() => setOpen(false)}
          className="text-[11.5px] font-medium text-slate-500 hover:text-slate-700">
          Cancel
        </button>
      </div>
      <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
        Your reading replaces the model’s everywhere on this page, and is kept
        as a training label.
      </p>
      <div className="mt-2.5 grid gap-1.5 sm:grid-cols-2">
        {classes.map((c) => (
          <label key={c.label}
            className={`flex cursor-pointer items-start gap-2 rounded-lg border px-2.5 py-2 text-[12px] transition ${
              choice === c.label
                ? 'border-teal-500 bg-white font-medium text-teal-900 ring-1 ring-teal-400'
                : 'border-slate-200 bg-white text-slate-700 hover:border-teal-300'}`}>
            <input type="radio" name="otoscopy-correction" value={c.label}
              checked={choice === c.label}
              onChange={() => setChoice(c.label)} className="mt-0.5" />
            <span>
              {c.name}
              {c.label === predicted && (
                <span className="ml-1 text-[10px] uppercase tracking-wide text-slate-400">
                  model’s pick
                </span>
              )}
            </span>
          </label>
        ))}
      </div>
      <label className="mt-2.5 block text-[12px]">
        <span className="mb-1 block font-medium text-slate-600">
          Note (optional) — what made it clear
        </span>
        <input type="text" value={note} maxLength={1000}
          onChange={(e) => setNote(e.target.value)}
          placeholder="central perforation, anterior half, no discharge"
          className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-[12.5px]" />
      </label>
      {error && (
        <p role="alert" className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[12px] text-rose-800">
          {error}
        </p>
      )}
      <button type="button" onClick={submit} disabled={!choice || busy}
        className="mt-2.5 rounded-lg bg-teal-600 px-3.5 py-1.5 text-[12.5px] font-semibold text-white shadow-sm transition hover:bg-teal-700 disabled:opacity-40">
        {busy ? 'Setting…' : 'Set this pattern'}
      </button>
    </div>
  )
}

export default function Otoscopy() {
  const { patient, analysis, assessment, otoscopyEars, setOtoscopyEar,
          showToast } = useApp()
  const fileRef = useRef(null)
  const [atlas, setAtlas] = useState(null)
  const [card, setCard] = useState(null)
  const [side, setSide] = useState('right')
  // Per ear, like the results: replacing the right ear's capture must not
  // wipe the left ear's.  { url, name, size, kind }
  const [mediaByEar, setMediaByEar] = useState({ right: null, left: null })
  const [mediaError, setMediaError] = useState(null)
  const [busyEar, setBusyEar] = useState(null)
  const [fromImageByEar, setFromImageByEar] = useState({ right: null, left: null })
  // The model's own result, kept so an override can be undone within the
  // session. Not persisted: after a reload the correction stands on its own,
  // and the model's ranking is still recorded inside it.
  const [preCorrection, setPreCorrection] = useState({ right: null, left: null })

  const result = otoscopyEars?.[side] || null
  const media = mediaByEar[side]
  const busy = busyEar === side
  const fromImage = fromImageByEar[side]

  useEffect(() => {
    api.otoscopyAtlas().then(setAtlas).catch(() => setAtlas(null))
    api.otoscopyModel().then(setCard).catch(() => setCard(null))
  }, [])

  const classes = useMemo(
    () => (atlas?.classes || []).map((c) => ({ label: c.label, name: c.name })),
    [atlas])

  // The image's own differential, per ear, recomputed whenever that ear's
  // reading changes — including when a clinician overrides the pattern, since
  // the differential is drawn from the pattern.
  useEffect(() => {
    const current = otoscopyEars?.[side] || null
    if (!current) {
      setFromImageByEar((prev) => (prev[side] ? { ...prev, [side]: null } : prev))
      return
    }
    let cancelled = false
    api.diseasesFromOtoscopy(current)
      .then((r) => { if (!cancelled) setFromImageByEar((p) => ({ ...p, [side]: r })) })
      .catch(() => { if (!cancelled) setFromImageByEar((p) => ({ ...p, [side]: null })) })
    return () => { cancelled = true }
  }, [otoscopyEars, side])

  // Revoke every object URL this page created, on unmount. Per-ear media means
  // two can be live at once, and each replacement revokes its predecessor in
  // `putMedia` below.
  const mediaRef = useRef(mediaByEar)
  mediaRef.current = mediaByEar
  useEffect(() => () => {
    for (const m of Object.values(mediaRef.current)) {
      if (m?.url) URL.revokeObjectURL(m.url)
    }
  }, [])

  function putMedia(ear, next) {
    setMediaByEar((prev) => {
      if (prev[ear]?.url && prev[ear].url !== next?.url) {
        URL.revokeObjectURL(prev[ear].url)
      }
      return { ...prev, [ear]: next }
    })
  }

  async function analyse(file, ear) {
    setBusyEar(ear)
    setOtoscopyEar(ear, null)
    setPreCorrection((p) => ({ ...p, [ear]: null }))
    try {
      // The current analysis rides along so the cross-check against the
      // audiogram and tympanogram happens in the same round trip.
      setOtoscopyEar(ear, await api.otoscopy(file, ear, analysis))
    } catch (e) {
      showToast(e.message || 'Could not read that image', 'error')
    } finally {
      setBusyEar((b) => (b === ear ? null : b))
    }
  }

  function chooseFile(file) {
    if (!file) return
    setMediaError(null)
    const ear = side

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

    putMedia(ear, { url: URL.createObjectURL(file), name: file.name,
                    size: file.size, kind })
    if (kind === 'image') {
      analyse(file, ear)
    } else {
      // The classifier reads still images; a video is shown for viewing only,
      // so a stale differential from a previous image must not sit next to it.
      // TODO(frame-grab): capture a chosen frame from the video client-side
      // and send that still through /api/otoscopy/analyze.
      setOtoscopyEar(ear, null)
    }
  }

  function removeMedia() {
    putMedia(side, null)
    setMediaError(null)
    setOtoscopyEar(side, null)
    setPreCorrection((p) => ({ ...p, [side]: null }))
    // Selecting the same file again must re-fire the change event.
    if (fileRef.current) fileRef.current.value = ''
  }

  function applyCorrection(corrected) {
    setPreCorrection((p) => ({ ...p, [side]: p[side] || result }))
    setOtoscopyEar(side, corrected)
  }

  function undoCorrection() {
    const original = preCorrection[side]
    if (!original) return
    setOtoscopyEar(side, original)
    setPreCorrection((p) => ({ ...p, [side]: null }))
  }

  // Atlas thumbnails double as test images — the fastest way to demonstrate
  // the pipeline without a patient in the chair.
  async function runReference(src) {
    const ear = side
    setBusyEar(ear)
    setOtoscopyEar(ear, null)
    setMediaError(null)
    try {
      // no-store: a cached copy of this URL may come from a request made
      // without CORS (any plain <img>) and so lack Access-Control-Allow-Origin;
      // reusing it would fail this fetch.
      const res = await fetch(referenceUrl(src), { cache: 'no-store' })
      if (!res.ok) throw new Error(`Reference view unavailable (HTTP ${res.status})`)
      const blob = await res.blob()
      // The upload is labelled with the type the server actually sent, and a
      // filename whose extension agrees with it — the shipped atlas is JPEG,
      // and a JPEG declared as PNG is a mislabelled clinical upload.
      const type = blob.type.split(';')[0].trim().toLowerCase()
      const ext = IMAGE_EXTENSIONS[type]
      if (!ext) {
        throw new Error(`Reference view is ${type || 'an unknown type'}, not an image`)
      }
      const stem = (src.split('/').pop() || '').replace(/\.[^.]*$/, '') || 'reference'
      const filename = `${stem}.${ext}`
      putMedia(ear, { url: URL.createObjectURL(blob), name: 'Reference view',
                      size: blob.size, kind: 'image' })
      setOtoscopyEar(ear, await api.otoscopy(
        new File([blob], filename, { type }), ear, analysis))
    } catch (e) {
      showToast(e.message || 'Could not load that reference view', 'error')
    } finally {
      setBusyEar((b) => (b === ear ? null : b))
    }
  }

  const validation = card?.validation
  const conc = result?.concordance
  const isCorrected = Boolean(result?.correction?.corrected)
  // One tympanic membrane looks much like another on screen, and this page will
  // happily read an image against whatever case happens to be open. Naming the
  // patient is the only thing that makes the mismatch visible before a finding
  // is filed under the wrong ear.
  const patientName = (patient?.name || '').trim()

  // Both ears at a glance, so "I have only done one" is visible without
  // switching tabs.
  const earSummary = (ear) => {
    const r = otoscopyEars?.[ear]
    if (busyEar === ear) return 'reading…'
    if (!r) return mediaByEar[ear]?.kind === 'video' ? 'video only' : 'not examined'
    return r.prediction?.name || 'read'
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">Otoscopy</h1>
        <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-slate-500">
          Match a tympanic-membrane image against the labelled reference patterns, then
          check what it predicts against the audiogram and tympanogram already on file.
          Each ear is examined and recorded separately.
        </p>
      </header>

      {/* --- ear tabs ---------------------------------------------------- */}
      <div role="tablist" aria-label="Which ear"
        className="mt-4 flex gap-2">
        {EARS.map((ear) => {
          const active = side === ear
          return (
            <button key={ear} type="button" role="tab" aria-selected={active}
              onClick={() => setSide(ear)}
              className={`flex-1 rounded-xl border px-3.5 py-2.5 text-left transition ${
                active
                  ? ear === 'right'
                    ? 'border-red-300 bg-red-50 ring-1 ring-red-200'
                    : 'border-blue-300 bg-blue-50 ring-1 ring-blue-200'
                  : 'border-slate-200 bg-white hover:border-slate-300'}`}>
              <span className={`block text-[13px] font-semibold ${
                active ? (ear === 'right' ? 'text-red-800' : 'text-blue-800')
                  : 'text-slate-700'}`}>
                {EAR_LABEL[ear]}
              </span>
              <span className={`mt-0.5 block truncate text-[11.5px] ${
                otoscopyEars?.[ear] ? 'text-slate-600' : 'text-slate-400'}`}>
                {earSummary(ear)}
                {otoscopyEars?.[ear]?.correction?.corrected && ' · set by you'}
              </span>
            </button>
          )
        })}
      </div>

      {/* --- upload ------------------------------------------------------ */}
      <div data-tour="otoscopy-upload" className="mt-3 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file"
            accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"
            className="hidden" onChange={(e) => chooseFile(e.target.files?.[0])} />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={busy}
            className="rounded-lg bg-teal-600 px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:bg-teal-700 disabled:opacity-50">
            {busy ? 'Reading…'
              : media ? `Replace ${EAR_LABEL[side].toLowerCase()} capture`
                : `Upload ${EAR_LABEL[side].toLowerCase()} image or video`}
          </button>
          <span className="text-[12px] text-slate-500">
            Will cross-check{' '}
            {patientName
              ? <><span className="font-medium text-slate-700">{patientName}</span>’s {side} ear</>
              : `this ${side} ear`}{' '}
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

        {/* Unconditional, unlike the measured figures below — those only render
            once the model card loads, and this caveat has to hold whether or
            not it does. */}
        <p className="mt-3 text-[11.5px] leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-600">Note:</span> these
          results are not yet reliable, because the training set is small. Set
          the pattern yourself whenever you disagree — your reading is better
          evidence than the model’s, and it is what the rest of the page will use.
        </p>

        {validation && (
          <Reveal className="mt-2" label="Measured accuracy of this classifier">
            <p className="rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
              <span className="font-semibold">On the shipped reference set:</span>{' '}
              exact pattern correct {Math.round(validation.accuracy * 100)}% of the time
              (chance {Math.round(validation.chance_level * 100)}%), correct answer in the
              top three {Math.round(validation.top3_accuracy * 100)}%, urgency band correct{' '}
              {Math.round(validation.urgency_accuracy * 100)}%
              {validation.no_information_rate?.urgency != null && (
                <> (always answering the commonest band scores{' '}
                  {Math.round(validation.no_information_rate.urgency * 100)}%)</>
              )}
              . {validation.protocol === 'source_photograph'
                ? `Held out every view cut from the same source photograph${
                  validation.source_photographs ? ` (${validation.source_photographs} pictures)` : ''}.`
                : 'Measured view by view, which flatters the model.'}{' '}
              Use the ranked list, not the headline.
            </p>
          </Reveal>
        )}

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
              {' '}· {fmtBytes(media.size)} · {media.kind} · {EAR_LABEL[side].toLowerCase()}
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

      {!media && !result && !busy && (
        <p className="mt-5 rounded-2xl border border-dashed border-slate-300 p-8 text-center text-[13px] text-slate-400">
          No capture for the {side} ear yet.
          {otoscopyEars?.[side === 'right' ? 'left' : 'right']
            && ` The ${side === 'right' ? 'left' : 'right'} ear has been read — switch tabs above to see it.`}
        </p>
      )}

      {/* --- result ------------------------------------------------------ */}
      {result && (
        <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1.15fr]">
          <div className="space-y-5">
            <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-900">
                {media?.url && <img src={media.url}
                  alt={`Uploaded otoscope view, ${side} ear`}
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
            </div>

            {/* The descriptors the classifier measured. Evidence for the
                reading, not the reading itself — so it is one click away. */}
            <Collapsible title="What the image shows"
              subtitle="The measurements the classifier actually read, in plain language."
              badge={result.evidence.length}>
              <ul className="space-y-1 text-[12.5px] leading-relaxed text-slate-600">
                {result.evidence.map((e, i) => <li key={i}>· {e}</li>)}
              </ul>
              <Reveal className="mt-3" label="Raw descriptors">
                <dl className="grid grid-cols-2 gap-2 text-[12px]">
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
              </Reveal>
            </Collapsible>
          </div>

          <div data-tour="otoscopy-result" className="space-y-5">
            <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-lg border px-2.5 py-1 text-[12px] font-semibold ${
                  URGENCY_STYLE[result.urgency.key] || 'border-slate-300 bg-slate-50 text-slate-700'}`}>
                  {result.urgency.name}
                </span>
                <span className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-[12px] font-medium text-slate-700">
                  {result.category.name}
                  {result.category.probability != null
                    && ` · ${Math.round(result.category.probability * 100)}%`}
                </span>
                <span className={`rounded-lg border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${
                  side === 'right' ? 'border-red-200 bg-red-50 text-red-700'
                    : 'border-blue-200 bg-blue-50 text-blue-700'}`}>
                  {side}
                </span>
              </div>

              {result.prediction.statement && (
                <p className="mt-2 text-[13.5px] font-semibold leading-relaxed text-slate-900">
                  {result.prediction.statement}
                </p>
              )}
              <p className="mt-1 text-[12px] text-slate-500">
                {CERTAINTY_NOTE[result.prediction.certainty] || ''}
                {result.prediction.certainty_held_out?.n > 0 && (
                  <> On unseen photographs, {result.prediction.certainty_held_out.correct} of{' '}
                    {result.prediction.certainty_held_out.n} calls at this certainty were right.</>
                )}
              </p>

              <CorrectionPanel result={result} classes={classes} analysis={analysis}
                onCorrected={applyCorrection} onUndo={undoCorrection}
                canUndo={Boolean(preCorrection[side])} />

              {!isCorrected && result.reliable === false && result.reliability_note && (
                <Reveal className="mt-3" label="How reliable is this reading?">
                  <p className="text-[11.5px] leading-snug text-amber-800">
                    {result.reliability_note}
                  </p>
                </Reveal>
              )}
              {result.training_set_note && (
                <p className="mt-2 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-[12px] leading-relaxed text-slate-700">
                  {result.training_set_note}
                </p>
              )}

              <Collapsible
                title={isCorrected ? 'What the model ranked' : 'Other patterns considered'}
                subtitle={isCorrected
                  ? 'Kept for the record — it is not driving anything on this page.'
                  : 'The model’s weights across the eight reference patterns.'}
                badge={result.ranked.length}>
                <ul className="space-y-2.5">
                  {result.ranked.slice(0, 4).map((r, i) => (
                    <li key={r.label}>
                      <div className="flex items-baseline justify-between gap-3 text-[13px]">
                        <span className={r.corrected ? 'font-semibold text-teal-800'
                          : i === 0 ? 'font-medium text-slate-900' : 'text-slate-700'}>
                          {r.name}
                          {r.corrected && (
                            <span className="ml-1 text-[10px] uppercase tracking-wide text-teal-600">
                              your reading
                            </span>
                          )}
                        </span>
                        <span className="font-mono text-[12px] text-slate-500">
                          {Math.round(r.probability * 100)}%
                        </span>
                      </div>
                      <div className="mt-1"><Bar value={r.probability} lead={i === 0} /></div>
                    </li>
                  ))}
                </ul>
                <p className="mt-2.5 text-[11px] leading-relaxed text-slate-400">
                  These are the model’s weights, not chances of being right — on
                  held-out photographs it is about as confident when wrong as
                  when right.
                </p>
              </Collapsible>
            </div>

            {/* Reference comparison — the part that stays useful even when
                the classifier is unsure, and the fastest way for a clinician
                to confirm or overrule the pattern. */}
            <Collapsible title="Closest reference views" defaultOpen
              subtitle="Labelled images ranked by visual similarity — compare them against the capture yourself."
              badge={result.reference_matches.length}>
              <div className="grid grid-cols-3 gap-3">
                {result.reference_matches.map((m) => (
                  <figure key={m.image} className="rounded-xl border border-slate-200 p-2">
                    <img src={referenceUrl(m.image)} alt={m.name} crossOrigin="anonymous"
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
            </Collapsible>

            {/* Clinical consequence of the leading pattern. */}
            <Collapsible defaultOpen
              title={isCorrected
                ? `${result.clinical.name} — what to expect`
                : `If this is ${result.clinical.name?.toLowerCase()}`}
              subtitle={result.clinical.referral}>
              <dl className="space-y-2 text-[12.5px] leading-relaxed">
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
            </Collapsible>

            {/* The differential this image produces on its own. No history and
                no audiogram — a scope goes in the ear before the patient is in
                the booth, and the appearance already narrows the list. */}
            {fromImage?.available && (
              <Collapsible title="Diseases this appearance points to"
                subtitle={fromImage.headline}
                badge={fromImage.differential.length || null}>
                {fromImage.differential.length > 0 && (
                  <ul className="space-y-2">
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
                <Reveal className="mt-2.5" label="Why these">
                  <>
                    {fromImage.reasoning.map((r) => (
                      <p key={r} className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
                        {r}
                      </p>
                    ))}
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                      {fromImage.note}
                    </p>
                  </>
                </Reveal>
              </Collapsible>
            )}

            {/* Cross-check: independent of whether the classifier is right.
                Conflicts are never collapsed — two tests that cannot both be
                true is the finding. */}
            {conc && (
              conc.available && conc.conflicts.length > 0 ? (
                <div className="rounded-2xl border border-amber-300 bg-white p-5 shadow-sm">
                  <h3 className="text-[15px] font-semibold text-amber-900">
                    Against the rest of the battery
                  </h3>
                  <p className="mt-1.5 text-[12.5px] font-medium text-slate-700">
                    {conc.headline}
                  </p>
                  {conc.conflicts.map((c) => (
                    <div key={c.title}
                      className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
                      <div className="font-semibold">⚠ {c.title}</div>
                      <div className="mt-0.5 leading-relaxed">{c.detail}</div>
                      <div className="mt-1 font-medium">{c.action}</div>
                    </div>
                  ))}
                  {conc.agreements.length > 0 && (
                    <Reveal className="mt-2.5"
                      label={`${conc.agreements.length} check${conc.agreements.length === 1 ? '' : 's'} that do agree`}>
                      {conc.agreements.map((a) => (
                        <div key={a.title}
                          className="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[12px] text-emerald-900">
                          <div className="font-semibold">✓ {a.title}</div>
                          <div className="mt-0.5 leading-relaxed">{a.detail}</div>
                        </div>
                      ))}
                    </Reveal>
                  )}
                </div>
              ) : (
                <Collapsible title="Against the rest of the battery"
                  subtitle={conc.available ? conc.headline : conc.note}
                  badge={conc.available ? 'agrees' : null}
                  badgeTone="good">
                  {!conc.available ? (
                    <p className="text-[12.5px] text-slate-500">{conc.note}</p>
                  ) : (
                    conc.agreements.map((a) => (
                      <div key={a.title}
                        className="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[12px] text-emerald-900 first:mt-0">
                        <div className="font-semibold">✓ {a.title}</div>
                        <div className="mt-0.5 leading-relaxed">{a.detail}</div>
                      </div>
                    ))
                  )}
                </Collapsible>
              )
            )}

            {/* Does the history confirm the image? This is the check the
                classifier's weakness makes most valuable — two independent
                methods reaching the same answer from different evidence. */}
            <LinkagePanel side={side} />

            <p className="text-[11.5px] leading-relaxed text-slate-400">{result.disclaimer}</p>
          </div>
        </div>
      )}

      <Atlas atlas={atlas} onPick={runReference} />

      {card?.limits && (
        <div className="mt-5">
          <ReferenceSection dataTour="otoscopy-limits"
            title="What this model cannot do"
            subtitle="Read once before relying on any reading from it."
            badge={card.limits.length}>
            <ul className="space-y-1 text-[12.5px] leading-relaxed text-slate-600">
              {card.limits.map((l) => <li key={l}>· {l}</li>)}
            </ul>
            <p className="mt-2.5 text-[12px] leading-relaxed text-slate-500">{card.improve}</p>
          </ReferenceSection>
        </div>
      )}

      <StepNav stepKey="otoscopy" />
    </div>
  )
}
