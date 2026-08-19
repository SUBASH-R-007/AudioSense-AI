// The short animation a clinician plays while explaining the result.
//
// A patient does not picture a 40 dB air-bone gap; they picture their ear. The
// backend picks which clip of the eardrum-to-cochlea journey matches THIS ear
// and supplies the plain sentences that go with it — this component only
// renders that choice.
//
// Two things it is careful about.
//
// It never claims the clip is the patient. The clips are generic anatomy, and
// somebody who leaves believing they watched footage of their own eardrum has
// been misled by the thing that was meant to inform them. The disclaimer is
// rendered from the payload, above the video, not tucked underneath it.
//
// It never shows a broken player. The clips are large binaries added out of
// band, so on any given deployment they may simply not be there yet. A missing
// file degrades to the same explanation in words, which is the part that
// actually does the counselling — the video is the illustration, not the
// content.

import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api.js'

// Module scope: a fresh object here would give the fetch effect a new
// dependency identity on every render and loop it.
const SIDES = ['right', 'left']

const DIR = '/anatomy'

export default function EarAnatomyVideo({ analysis, otoscopy, side, onSideChange }) {
  const [internalSide, setInternalSide] = useState(side || 'right')
  const ear = side || internalSide
  const setEar = onSideChange || setInternalSide

  const [selection, setSelection] = useState(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  // 'probing' | 'ready' | 'missing' — whether the clip file actually exists.
  const [asset, setAsset] = useState('probing')

  useEffect(() => {
    if (!analysis) { setSelection(null); setFailed(false); return }
    let cancelled = false
    setBusy(true)
    setFailed(false)
    api.anatomyVideo({ analysis, otoscopy, side: ear })
      .then((r) => { if (!cancelled) setSelection(r) })
      .catch(() => { if (!cancelled) { setSelection(null); setFailed(true) } })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [analysis, otoscopy, ear])

  const key = selection?.available ? selection.key : null
  const src = key ? `${DIR}/${key}.mp4` : null
  // Only set once the poster is known to be a real image — see below.
  const [poster, setPoster] = useState(null)

  // Probe before rendering a player, and check the CONTENT TYPE rather than
  // just the status. Both static hosts this app runs on answer an unknown path
  // with the SPA fallback — `200 OK, Content-Type: text/html` — so a status
  // check alone would call a missing clip present and hand an HTML document to
  // a <video> element. The poster is probed the same way for the same reason:
  // an <img>-style attribute pointed at HTML renders as a broken frame over an
  // otherwise working video.
  useEffect(() => {
    if (!src) { setAsset('probing'); setPoster(null); return }
    let cancelled = false
    setAsset('probing')
    setPoster(null)

    const probe = (url, prefix) => fetch(url, { method: 'HEAD' })
      .then((r) => r.ok
        && (r.headers.get('content-type') || '').toLowerCase().startsWith(prefix))
      .catch(() => false)

    probe(src, 'video/').then((ok) => {
      if (cancelled) return
      setAsset(ok ? 'ready' : 'missing')
      // A poster is optional; its absence costs a thumbnail and nothing else,
      // so it is only worth asking about once the clip itself is there.
      if (!ok) return
      const jpg = `${DIR}/${key}.jpg`
      probe(jpg, 'image/').then((imageOk) => {
        if (!cancelled && imageOk) setPoster(jpg)
      })
    })

    return () => { cancelled = true }
  }, [src, key])

  const earToggle = useMemo(() => (
    <div className="flex rounded-lg bg-slate-100 p-0.5">
      {SIDES.map((e) => (
        <button key={e} onClick={() => setEar(e)}
          aria-pressed={ear === e}
          className={`rounded-md px-2 py-0.5 text-[10.5px] font-semibold capitalize transition ${
            ear === e
              ? e === 'right' ? 'bg-white text-red-600 shadow-sm' : 'bg-white text-blue-600 shadow-sm'
              : 'text-slate-500'
          }`}>{e}</button>
      ))}
    </div>
  ), [ear, setEar])

  if (!analysis) return null

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
      data-tour="anatomy-video">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-[15px] font-semibold text-slate-900">
            Show the patient what is happening
          </h2>
          <p className="mt-0.5 text-[12px] text-slate-500">
            {selection?.journey
              || 'Ear canal and eardrum, through the middle-ear bones, into the cochlea.'}
          </p>
        </div>
        {earToggle}
      </div>

      {busy && (
        <p className="mt-4 text-[12.5px] text-slate-400">Choosing the clip…</p>
      )}

      {!busy && failed && (
        <p className="mt-4 rounded-xl border border-dashed border-amber-300 bg-amber-50/60 p-4 text-[12.5px] leading-relaxed text-amber-900">
          The clip could not be chosen. Nothing recorded in this case has
          changed — this panel simply has not been able to reach the server.
        </p>
      )}

      {!busy && !failed && selection && !selection.available && (
        <p className="mt-4 rounded-xl border border-dashed border-slate-300 p-4 text-[12.5px] leading-relaxed text-slate-500">
          {selection.reason}
        </p>
      )}

      {!busy && !failed && selection?.available && (
        <div className="mt-4">
          {/* Above the video, deliberately. Somebody who watches first and
              reads afterwards has already formed the wrong belief. */}
          <p className="rounded-xl border border-sky-300 bg-sky-50 px-3 py-2 text-[12px] font-medium leading-relaxed text-sky-900">
            {selection.note}
          </p>

          <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
            <div>
              {asset === 'ready' ? (
                <video
                  key={src}
                  className="w-full rounded-xl border border-slate-200 bg-slate-900"
                  src={src}
                  {...(poster ? { poster } : {})}
                  controls
                  loop
                  muted
                  playsInline
                  preload="metadata"
                  onError={() => setAsset('missing')}
                  aria-label={`Animation: ${selection.title}`}
                />
              ) : (
                <div className="flex min-h-[190px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-center">
                  {asset === 'probing' ? (
                    <span className="text-[12.5px] text-slate-400">
                      Looking for the animation…
                    </span>
                  ) : (
                    <>
                      <span className="text-[12.5px] font-medium text-slate-600">
                        Animation not installed on this instance
                      </span>
                      <span className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
                        The explanation beside this is the counselling; the clip
                        is the illustration. Drop{' '}
                        <code className="rounded bg-slate-200 px-1 py-0.5 text-[10.5px]">
                          {selection.file}
                        </code>{' '}
                        into <code className="rounded bg-slate-200 px-1 py-0.5 text-[10.5px]">frontend/public/anatomy/</code>{' '}
                        to enable it.
                      </span>
                    </>
                  )}
                </div>
              )}
              <p className="mt-1.5 text-[11px] leading-snug text-slate-400">
                <b className="text-slate-500">Shows:</b> {selection.shows}
              </p>
            </div>

            <div>
              <h3 className="text-[14px] font-semibold text-slate-900">
                {selection.patient_title}
              </h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-slate-700">
                {selection.plain}
              </p>

              {selection.plus_sensorineural && (
                <p className="mt-2.5 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] leading-relaxed text-amber-900">
                  This clip shows the blockage only. There is <b>also</b> damage
                  in the hearing organ itself in this ear, which no picture of
                  the middle ear can show — treating the blockage will not
                  recover that part.
                </p>
              )}

              <details className="mt-3 text-[12px] text-slate-600">
                <summary className="cursor-pointer font-medium text-teal-700">
                  Why this clip and not another
                </summary>
                <div className="mt-1.5 rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[11.5px] text-slate-500">
                    Chosen for the <b className="capitalize">{selection.side}</b> ear
                    from:
                  </p>
                  <ul className="mt-1 space-y-0.5">
                    {(selection.because || []).map((b, i) => (
                      <li key={i} className="text-[11.5px] text-slate-700">· {b}</li>
                    ))}
                  </ul>
                  <p className="mt-1.5 text-[11px] text-slate-500">
                    <b>Mechanism:</b> {selection.mechanism}
                  </p>
                </div>
              </details>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
