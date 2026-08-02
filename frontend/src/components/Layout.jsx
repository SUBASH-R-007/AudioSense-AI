import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useApp } from '../lib/store.jsx'
import AISettingsPanel from './AISettingsPanel.jsx'
import GuidedTour from './GuidedTour.jsx'

// Ordered the way a consultation runs: history first, then look in the ear,
// then measure, then interpret.
const NAV = [
  { to: '/symptoms', label: 'Signs & Symptoms', icon: 'M9 12h6m-3-3v6M4.5 8.5A7.5 7.5 0 0119 12v6a2 2 0 01-2 2H7a2 2 0 01-2-2v-4' },
  { to: '/otoscopy', label: 'Otoscopy', icon: 'M12 20a8 8 0 100-16 8 8 0 000 16zm0-4a4 4 0 100-8 4 4 0 000 8z' },
  { to: '/new-test', label: 'New Test', icon: 'M12 4v16m8-8H4' },
  { to: '/screening', label: 'Screening Test', icon: 'M12 18.5a6.5 6.5 0 100-13 6.5 6.5 0 000 13zm0-9.5a3 3 0 100 6 3 3 0 000-6z' },
  { to: '/immittance', label: 'Immittance, OAE & Speech', icon: 'M3 12c2-6 4-6 6 0s4 6 6 0 4-6 6 0' },
  { to: '/evoked-potentials', label: 'Evoked Potentials', icon: 'M2 12h3l2-6 3 12 3-9 2 3h7' },
  { to: '/dashboard', label: 'Results Dashboard', icon: 'M3 13h4v8H3zm7-9h4v17h-4zm7 5h4v12h-4z' },
  { to: '/simulator', label: 'Hearing Simulator', icon: 'M3 10v4m4-8v12m4-15v18m4-14v10m4-7v4' },
  { to: '/listening-lab', label: 'Listening Lab', icon: 'M12 3v18M8 7v10M4 10v4M16 6v12M20 9v6' },
  { to: '/progression', label: 'Progression', icon: 'M3 17l6-6 4 4 8-8m0 0v5m0-5h-5' },
  { to: '/batch', label: 'Batch Analysis', icon: 'M4 6h16M4 12h16M4 18h10' },
  { to: '/records', label: 'Patient Records', icon: 'M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2zM8 9h4m-4 4h8m-8 4h8' },
]

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

export default function Layout({ children }) {
  const { aiStatus, toast } = useApp()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [navOpen, setNavOpen] = useState(false)
  const [tourOpen, setTourOpen] = useState(false)
  const location = useLocation()
  const apiMode = aiStatus?.config?.mode === 'api'

  // On a phone the drawer must close when you navigate, or it covers the page.
  useEffect(() => { setNavOpen(false) }, [location.pathname])
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
        <nav className="mt-8 flex flex-1 flex-col gap-1" aria-label="Main">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13.5px] font-medium transition ${
                  isActive
                    ? 'bg-teal-50 text-teal-700 shadow-[inset_0_0_0_1px_rgba(13,148,136,0.15)]'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`
              }
            >
              <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none"
                stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d={n.icon} />
              </svg>
              {n.label}
            </NavLink>
          ))}
        </nav>

        <button
          onClick={() => setTourOpen(true)}
          className="mb-2 flex items-center gap-2 rounded-xl border border-teal-200 bg-teal-50/60 px-3 py-2.5 text-left text-[13px] font-semibold text-teal-800 transition hover:bg-teal-100/60"
        >
          <span aria-hidden="true">🧭</span> Show me around
        </button>

        <button
          onClick={() => setSettingsOpen(true)}
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
