import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

const AppContext = createContext(null)

const load = (key, fallback) => {
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

export function AppProvider({ children }) {
  // Current analysis shown on the dashboard (survives refresh via sessionStorage).
  const [analysis, setAnalysisRaw] = useState(() => load('as_analysis', null))
  // History of analyzed tests in this session — feeds the Progression page.
  const [history, setHistory] = useState(() => load('as_history', []))
  const [aiStatus, setAiStatus] = useState(null)
  const [toast, setToast] = useState(null)

  const setAnalysis = useCallback((a) => {
    setAnalysisRaw(a)
    try { sessionStorage.setItem('as_analysis', JSON.stringify(a)) } catch { /* ignore */ }
    if (a) {
      setHistory((h) => {
        const entry = {
          id: Date.now(),
          label: `${a.patient?.name || 'Unknown'} — ${a.patient?.test_date || 'undated'}`,
          record: {
            patient: a.patient,
            right: a.thresholds.right,
            left: a.thresholds.left,
          },
        }
        const next = [...h, entry].slice(-12)
        try { sessionStorage.setItem('as_history', JSON.stringify(next)) } catch { /* ignore */ }
        return next
      })
    }
  }, [])

  const refreshAiStatus = useCallback(async () => {
    try {
      setAiStatus(await api.aiSettings())
    } catch {
      setAiStatus(null)
    }
  }, [])

  useEffect(() => { refreshAiStatus() }, [refreshAiStatus])

  const showToast = useCallback((message, kind = 'info') => {
    setToast({ message, kind, id: Date.now() })
  }, [])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  return (
    <AppContext.Provider
      value={{ analysis, setAnalysis, history, aiStatus, refreshAiStatus, toast, showToast }}
    >
      {children}
    </AppContext.Provider>
  )
}

export const useApp = () => useContext(AppContext)
