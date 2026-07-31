import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

// A self-running explanation of the interface.
//
// Anyone meeting this application has three minutes and no idea which of
// seven pages matters. The tour spotlights one thing at a time and says why
// it is there, so the software explains itself instead of depending on
// whoever is driving remembering the running order.

const STEPS = [
  {
    route: '/new-test', target: '[data-tour="demo-cases"]',
    title: 'Start with a real case',
    body: 'Five clinical presets plus two teaching cases. The 🚨 and 🔬 cases are the '
      + 'ones worth seeing first — they are the findings other tools miss.',
  },
  {
    route: '/new-test', target: '[data-tour="digitize"]',
    title: 'Paper in, data out',
    body: 'Photograph a paper audiogram and OpenCV reads the symbols off the grid. '
      + 'Extracted values land in the entry grid for a human to confirm — never '
      + 'straight into a diagnosis.',
  },
  {
    route: '/dashboard', target: '[data-tour="verdict"]',
    title: 'The answer, first',
    body: 'One sentence, the figures that carry the decision, and the single next '
      + 'step. Everything below this is the evidence behind it.',
  },
  {
    route: '/dashboard', target: '[data-tour="chart"]',
    title: 'A clinical audiogram',
    body: 'Correct notation — red O for the right ear, blue X for the left. The teal '
      + 'glow marks the frequencies that drove the AI classification.',
  },
  {
    route: '/dashboard', target: '[data-tour="norms"]',
    title: 'Hearing age',
    body: '"PTA 30 dB" means little to a patient. "Your ears are performing like a '
      + '61-year-old\'s" lands immediately — and it is the same fact.',
  },
  {
    route: '/dashboard', target: '[data-tour="battery"]',
    title: 'Do the tests agree?',
    body: 'Tympanometry, reflexes and emissions are reconciled against the audiogram. '
      + 'Agreement earns confidence; disagreement is named and explained.',
  },
  {
    route: '/simulator', target: '[data-tour="ab-toggle"]',
    title: 'Hear the diagnosis',
    body: 'Normal → this patient → with a hearing aid. The audiogram becomes a live '
      + 'filter, so the loss stops being a number.',
  },
  {
    route: '/batch', target: '[data-tour="batch-actions"]',
    title: 'Built for a queue',
    body: 'A whole shift in one upload, returned as a worklist ordered by who needs a '
      + 'clinician first — and a validation harness that scores the system against '
      + 'expert labels.',
  },
]

export default function GuidedTour({ onClose }) {
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState(null)
  const navigate = useNavigate()
  const location = useLocation()
  const current = STEPS[step]

  // Navigate first, then measure — the target may not exist until the route
  // has rendered.
  useEffect(() => {
    if (current && location.pathname !== current.route) navigate(current.route)
  }, [step, current, location.pathname, navigate])

  const measure = useCallback(() => {
    if (!current) return
    const el = document.querySelector(current.target)
    if (!el) { setRect(null); return }
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    const r = el.getBoundingClientRect()
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height })
  }, [current])

  useEffect(() => {
    const t = setTimeout(measure, 350)
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      clearTimeout(t)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [measure, location.pathname])

  const next = useCallback(() => {
    if (step >= STEPS.length - 1) onClose()
    else setStep(step + 1)
  }, [step, onClose])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight' || e.key === 'Enter') next()
      if (e.key === 'ArrowLeft') setStep((s) => Math.max(0, s - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, onClose])

  if (!current) return null
  const pad = 8
  const panelTop = rect && rect.top > 240 ? rect.top - 150 : (rect ? rect.top + rect.height + 16 : 120)

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true"
      aria-label={`Tour step ${step + 1}: ${current.title}`}>
      {/* dimmed backdrop with a hole cut over the target */}
      <div className="absolute inset-0 bg-slate-900/55" onClick={onClose} />
      {rect && (
        <div
          className="pointer-events-none absolute rounded-xl ring-4 ring-teal-400 transition-all duration-300"
          style={{
            top: rect.top - pad, left: rect.left - pad,
            width: rect.width + pad * 2, height: rect.height + pad * 2,
            boxShadow: '0 0 0 9999px rgba(15,23,42,0.55)',
            background: 'transparent',
          }}
        />
      )}

      <div
        className="absolute w-[min(26rem,calc(100vw-2rem))] rounded-2xl bg-white p-5 shadow-2xl transition-all duration-300"
        style={{
          top: Math.max(16, Math.min(panelTop, window.innerHeight - 240)),
          left: rect
            ? Math.max(16, Math.min(rect.left, window.innerWidth - 440))
            : '50%',
          transform: rect ? 'none' : 'translateX(-50%)',
        }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-widest text-teal-600">
            Step {step + 1} of {STEPS.length}
          </span>
          <button onClick={onClose} aria-label="End tour"
            className="rounded-md px-2 py-1 text-[12px] text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            Skip
          </button>
        </div>
        <h3 className="mt-1.5 text-[16px] font-semibold text-slate-900">{current.title}</h3>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-slate-600">{current.body}</p>

        <div className="mt-4 flex items-center gap-2">
          <div className="flex gap-1" aria-hidden="true">
            {STEPS.map((_, i) => (
              <span key={i} className={`h-1.5 rounded-full transition-all ${
                i === step ? 'w-5 bg-teal-600' : 'w-1.5 bg-slate-200'}`} />
            ))}
          </div>
          <button onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}
            className="ml-auto rounded-lg px-3 py-1.5 text-[13px] font-medium text-slate-500 hover:bg-slate-100 disabled:opacity-30">
            Back
          </button>
          <button onClick={next} autoFocus
            className="rounded-lg bg-teal-600 px-4 py-1.5 text-[13px] font-semibold text-white hover:bg-teal-700">
            {step === STEPS.length - 1 ? 'Finish' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  )
}
