import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import { TOOLS, flowProgress, flowState } from '../lib/flow.js'
import AISettingsPanel from './AISettingsPanel.jsx'
import GuidedTour from './GuidedTour.jsx'


/** A step's number, or the mark that replaces it once the step is settled. */
function StepMark({ step }) {
  const base = 'flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[9.5px] font-bold'
  if (step.state === 'done') {
    return <span className={`${base} bg-teal-600 text-white`} aria-label="done">✓</span>
  }
  if (step.state === 'skipped') {
    return <span className={`${base} bg-slate-200 text-slate-500`} aria-label="skipped">–</span>
  }
  if (step.state === 'blocked') {
    return <span className={`${base} border border-slate-200 text-slate-300`}>{step.index}</span>
  }
  return (
    <span className={`${base} border border-slate-300 text-slate-500 group-hover:border-teal-400 group-hover:text-teal-700`}>
      {step.index}
    </span>
  )
}

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-600 shadow-sm shadow-teal-600/30">
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none"
          stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 12h3l2-5 3 10 3-8 2 3h7" />
        </svg>
      </div>
      <div>
        <div className="text-[15px] font-semibold tracking-tight text-slate-900">
          AudioSense <span className="text-teal-600">AI</span>
        </div>
        <div className="text-[10px] font-medium uppercase tracking-widest text-slate-400">
          Audiometry Intelligence
        </div>
      </div>
    </div>
  )
}

const POLL_MS = 30000

// The whole interface renders from static assets, so it looks perfectly healthy
// with the backend dead behind it — and the first sign of trouble is a failed
// analysis halfway through a consultation. Whether the model is trained matters
// separately: without it, pattern classification silently drops out and the
// interpretation falls back to the rule engine alone, which is a different
// product from the one the screen appears to be offering.
function describeBackend(health) {
  if (health === null) {
    return { dot: 'bg-slate-300', box: 'text-slate-400', label: 'Checking backend…' }
  }
  if (health === false) {
    return {
      dot: 'bg-rose-500', box: 'bg-rose-50 text-rose-800',
      label: 'Backend unreachable',
      detail: 'Nothing can be analysed until it answers. Retrying every 30 s.',
    }
  }
  if (!health.model_trained) {
    return {
      dot: 'bg-amber-500', box: 'bg-amber-50 text-amber-900',
      label: 'Model not trained',
      detail: 'Backend is up. Pattern classification is unavailable; rule-based grading and typing still run.',
    }
  }
  return { dot: 'bg-emerald-500', box: 'text-slate-400', label: 'Backend online' }
}

export default function Layout({ children }) {
  const { aiStatus, toast, patient, assessment, otoscopy, analysis, aep, skipped } = useApp()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [navOpen, setNavOpen] = useState(false)
  const [tourOpen, setTourOpen] = useState(false)
  // null while the first probe is in flight, false once it has failed.
  const [health, setHealth] = useState(null)
  const location = useLocation()
  const apiMode = aiStatus?.config?.mode === 'api'

  // On a phone the drawer must close when you navigate, or it covers the page.
  useEffect(() => { setNavOpen(false) }, [location.pathname])

  useEffect(() => {
    let cancelled = false
    const probe = () => api.health()
      .then((h) => { if (!cancelled) setHealth(h) })
      .catch(() => { if (!cancelled) setHealth(false) })
    probe()
    const timer = setInterval(probe, POLL_MS)
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  const steps = flowState({ patient, assessment, otoscopy, analysis, aep, skipped })
  const progress = flowProgress({ patient, assessment, otoscopy, analysis, aep, skipped })
  const backend = describeBackend(health)
  const providerLabel = apiMode
    ? aiStatus?.providers?.[aiStatus.config.provider]?.label || aiStatus.config.provider
    : null

  return (
    <div className="flex min-h-screen">
      {/* mobile top bar — the sidebar becomes a drawer below lg */}
      <header className="fixed inset-x-0 top-0 z-30 flex items-center gap-3 border-b border-slate-200 bg-white/95 px-4 py-2.5 backdrop-blur lg:hidden print:hidden">
        <button onClick={() => setNavOpen(true)} aria-label="Open navigation"
          aria-expanded={navOpen} aria-controls="main-nav"
          className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-teal-600">
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <Logo />
      </header>

      {navOpen && (
        <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden"
          onClick={() => setNavOpen(false)} aria-hidden="true" />
      )}

      <aside id="main-nav"
        className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-slate-200/80 bg-white px-4 py-5 transition-transform duration-200 lg:translate-x-0 print:hidden ${
          navOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center justify-between">
          <Logo />
          <button onClick={() => setNavOpen(false)} aria-label="Close navigation"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 lg:hidden">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>
        <nav className="mt-6 flex flex-1 flex-col overflow-y-auto" aria-label="Main">
          {/* The consultation, in the order it runs. The sidebar is the flow —
              a clinician should never have to already know which screen comes
              next, and a step that was deliberately skipped must look different
              from one that was simply never reached. */}
          <div className="flex items-baseline justify-between px-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
              Consultation
            </span>
            <span className="font-mono text-[10px] text-slate-400">
              {progress.settled}/{progress.total}
            </span>
          </div>
          <div className="mx-3 mt-1.5 h-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-teal-500 transition-all"
              style={{ width: `${(progress.settled / progress.total) * 100}%` }} />
          </div>

          <div className="mt-2 flex flex-col gap-0.5" data-tour="flow-nav">
            {steps.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                aria-disabled={n.state === 'blocked'}
                title={n.state === 'blocked'
                  ? 'Available once there are thresholds to interpret'
                  : n.why}
                className={({ isActive }) =>
                  `group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition ${
                    isActive
                      ? 'bg-teal-50 text-teal-700 shadow-[inset_0_0_0_1px_rgba(13,148,136,0.15)]'
                      : n.state === 'blocked'
                        ? 'text-slate-300'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`
                }
              >
                <StepMark step={n} />
                <span className="flex-1 truncate">{n.label}</span>
                {n.state === 'skipped' && (
                  <span className="text-[9.5px] font-semibold uppercase tracking-wide text-slate-400">
                    skipped
                  </span>
                )}
                {!n.required && n.state === 'ready' && (
                  <span className="text-[9.5px] uppercase tracking-wide text-slate-300">
                    optional
                  </span>
                )}
              </NavLink>
            ))}
          </div>

          <div className="mt-5 px-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
              Tools
            </span>
          </div>
          <div className="mt-1.5 flex flex-col gap-0.5" data-tour="tools-nav">
            {TOOLS.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition ${
                    isActive
                      ? 'bg-teal-50 text-teal-700 shadow-[inset_0_0_0_1px_rgba(13,148,136,0.15)]'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`
                }
              >
                <svg viewBox="0 0 24 24" className="h-[17px] w-[17px]" fill="none"
                  stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d={n.icon} />
                </svg>
                <span className="truncate">{n.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>

        <button
          onClick={() => setTourOpen(true)}
          className="mb-2 flex items-center gap-2 rounded-xl border border-teal-200 bg-teal-50/60 px-3 py-2.5 text-left text-[13px] font-semibold text-teal-800 transition hover:bg-teal-100/60"
        >
          <span aria-hidden="true">🧭</span> Show me around
        </button>

        <button
          onClick={() => setSettingsOpen(true)}
          data-tour="ai-engine"
          className="group flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5 text-left transition hover:border-teal-300 hover:bg-teal-50/40"
        >
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              AI Engine
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[13px] font-medium text-slate-700">
              <span className={`h-2 w-2 rounded-full ${apiMode ? 'bg-teal-500' : 'bg-slate-400'}`} />
              {apiMode ? `${providerLabel}` : 'Offline mode'}
            </div>
          </div>
          <svg viewBox="0 0 24 24" className="h-4.5 w-4.5 text-slate-400 transition group-hover:rotate-45 group-hover:text-teal-600"
            fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z" />
          </svg>
        </button>

        <div role="status" aria-live="polite" data-tour="backend-status"
          className={`mt-2 rounded-xl px-3 py-2 ${backend.box}`}>
          <div className="flex items-center gap-2 text-[12px] font-medium">
            <span className={`h-2 w-2 shrink-0 rounded-full ${backend.dot}`} aria-hidden="true" />
            {backend.label}
          </div>
          {backend.detail && (
            <div className="mt-1 text-[11px] leading-relaxed">{backend.detail}</div>
          )}
        </div>

        <div className="mt-3 px-1 text-[10px] leading-relaxed text-slate-400">
          AI-assisted interpretation; final diagnosis requires a qualified audiologist.
        </div>
      </aside>

      <main id="main-content"
        className="flex-1 px-4 pb-10 pt-16 sm:px-6 lg:ml-60 lg:px-8 lg:pt-7 print:ml-0 print:pt-0">
        {children}
      </main>

      {settingsOpen && <AISettingsPanel onClose={() => setSettingsOpen(false)} />}
      {tourOpen && <GuidedTour onClose={() => setTourOpen(false)} />}

      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 max-w-sm rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${
            toast.kind === 'error' ? 'bg-rose-600' : toast.kind === 'warn' ? 'bg-amber-500' : 'bg-slate-800'
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}
