import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useApp } from '../lib/store.jsx'
import AISettingsPanel from './AISettingsPanel.jsx'

const NAV = [
  { to: '/new-test', label: 'New Test', icon: 'M12 4v16m8-8H4' },
  { to: '/screening', label: 'Screening Test', icon: 'M12 18.5a6.5 6.5 0 100-13 6.5 6.5 0 000 13zm0-9.5a3 3 0 100 6 3 3 0 000-6z' },
  { to: '/dashboard', label: 'Results Dashboard', icon: 'M3 13h4v8H3zm7-9h4v17h-4zm7 5h4v12h-4z' },
  { to: '/simulator', label: 'Hearing Simulator', icon: 'M3 10v4m4-8v12m4-15v18m4-14v10m4-7v4' },
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
  const apiMode = aiStatus?.config?.mode === 'api'
  const providerLabel = apiMode
    ? aiStatus?.providers?.[aiStatus.config.provider]?.label || aiStatus.config.provider
    : null

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-20 flex w-60 flex-col border-r border-slate-200/80 bg-white px-4 py-5">
        <Logo />
        <nav className="mt-8 flex flex-1 flex-col gap-1">
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

      <main className="ml-60 flex-1 px-8 py-7">{children}</main>

      {settingsOpen && <AISettingsPanel onClose={() => setSettingsOpen(false)} />}

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
