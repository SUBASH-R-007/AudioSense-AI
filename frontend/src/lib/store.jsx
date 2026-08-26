import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, clearToken, getToken, onUnauthorized, setToken } from './api.js'

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
  // The symptom history and the otoscope reading for the case in progress.
  //
  // These live here rather than on their own pages because the whole point of
  // them is that they constrain each other: the image is checked against what
  // the patient reported, the differential against the thresholds. A finding
  // that only exists inside one page's local state cannot be cross-checked
  // from another.
  const [assessment, setAssessmentRaw] = useState(() => load('as_assessment', null))
  const [otoscopy, setOtoscopyRaw] = useState(() => load('as_otoscopy', null))
  // Evoked potentials, tuning forks and behavioural observation used to live
  // only on their own screens, so a case could be fully worked up and the
  // dashboard would still show three of its modalities as never performed.
  const [aep, setAepRaw] = useState(() => load('as_aep', null))
  const [tuningFork, setTuningForkRaw] = useState(() => load('as_tuning_fork', null))
  const [boa, setBoaRaw] = useState(() => load('as_boa', null))
  // The exact request last sent to /api/analyze. Kept so a test performed
  // AFTER the audiogram — a tympanogram on the immittance page, emissions —
  // can be merged in and the analysis re-run over everything collected,
  // instead of silently interpreting on a subset.
  const [record, setRecordRaw] = useState(() => load('as_record', null))
  // Speech-in-babble screening — an instrument result like the fork battery,
  // stored so the dashboard can show it beside the audiogram it complements.
  const [babbleScreen, setBabbleScreenRaw] = useState(() => load('as_babble', null))
  // The patient, captured once at the start of the consultation.
  //
  // This used to live inside the pure-tone form's local state, which put it
  // halfway through the flow: the two screens that come BEFORE it — history and
  // otoscopy — could not see it and asked for the age again, and immittance
  // defaulted to a 30-year-old, so a child's tympanogram was judged against
  // adult norms unless somebody noticed.
  const [patient, setPatientRaw] = useState(() => load('as_patient', null))
  // Steps deliberately not performed, mapped to the reason given. A skip is a
  // clinical fact worth recording and it must never be confused with a normal
  // result — nothing here is fed to the interpretation, it only stops the app
  // asking again.
  const [skipped, setSkippedRaw] = useState(() => load('as_skipped', {}))
  const [aiStatus, setAiStatus] = useState(null)
  const [toast, setToast] = useState(null)
  // Who is signed in, or null. Nothing but the login screen renders while this
  // is null, so it is the single fact the whole app is gated on.
  const [session, setSession] = useState(null)
  // Whether this instance wants a login. null while we have not asked yet —
  // distinct from false, which is the real and alarming answer "this instance
  // has no accounts configured".
  const [authRequired, setAuthRequired] = useState(null)
  // The server's own word for which of three states it is in: "protected"
  // (accounts configured), "locked" (none configured — nothing works), or
  // "anonymous" (authentication deliberately disabled). `authRequired` is
  // false for BOTH of the last two, which is why they used to be confused.
  const [authMode, setAuthMode] = useState(null)
  // True until the stored token has been checked. Without it the first paint
  // shows the login screen to somebody who is already signed in, which looks
  // exactly like being logged out and provokes a needless second sign-in.
  const [booting, setBooting] = useState(true)

  const persist = useCallback((key, value, setter) => {
    setter(value)
    try {
      if (value === null) sessionStorage.removeItem(key)
      else sessionStorage.setItem(key, JSON.stringify(value))
    } catch { /* quota or private mode — in-memory state still works */ }
  }, [])

  const setAssessment = useCallback(
    (a) => persist('as_assessment', a, setAssessmentRaw), [persist])
  const setOtoscopy = useCallback(
    (o) => persist('as_otoscopy', o, setOtoscopyRaw), [persist])
  const setAep = useCallback(
    (v) => persist('as_aep', v, setAepRaw), [persist])
  const setTuningFork = useCallback(
    (v) => persist('as_tuning_fork', v, setTuningForkRaw), [persist])
  const setBoa = useCallback(
    (v) => persist('as_boa', v, setBoaRaw), [persist])
  const setBabbleScreen = useCallback(
    (v) => persist('as_babble', v, setBabbleScreenRaw), [persist])
  const setRecord = useCallback(
    (v) => persist('as_record', v, setRecordRaw), [persist])
  const setPatient = useCallback(
    (p) => persist('as_patient', p, setPatientRaw), [persist])

  const skipStep = useCallback((key, reason) => {
    setSkippedRaw((prev) => {
      const next = { ...prev, [key]: reason || 'Skipped' }
      try { sessionStorage.setItem('as_skipped', JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
  }, [])

  const unskipStep = useCallback((key) => {
    setSkippedRaw((prev) => {
      const next = { ...prev }
      delete next[key]
      try { sessionStorage.setItem('as_skipped', JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
  }, [])

  // Starting a new patient must clear every modality, or the next case inherits
  // the last one's otoscopy image and tuning-fork battery and the dashboard
  // reports findings that belong to somebody else.
  const resetCase = useCallback(() => {
    for (const k of ['as_analysis', 'as_assessment', 'as_otoscopy', 'as_aep',
                     'as_tuning_fork', 'as_boa', 'as_babble', 'as_record', 'as_patient', 'as_skipped']) {
      try { sessionStorage.removeItem(k) } catch { /* ignore */ }
    }
    setAnalysisRaw(null); setAssessmentRaw(null); setOtoscopyRaw(null)
    setAepRaw(null); setTuningForkRaw(null); setBoaRaw(null); setBabbleScreenRaw(null); setRecordRaw(null)
    setPatientRaw(null); setSkippedRaw({})
  }, [])

  // ---------------------------------------------------------------------
  // The session
  // ---------------------------------------------------------------------

  // Ending a session has to take the case with it. Every modality lives in
  // sessionStorage, so a clinician who signs out and hands the machine over
  // would otherwise leave the previous patient's name, thresholds, symptom
  // history and otoscopy image on screen for whoever signs in next. That is a
  // data-protection incident, not a cosmetic bug, so it happens on the way out
  // rather than being left to the next person to notice.
  const endSession = useCallback(() => {
    clearToken()
    setSession(null)
    resetCase()
    // resetCase deliberately keeps the visit history, because starting a new
    // patient should not throw away the comparisons the progression screen is
    // built on. A different clinician signing in is a different matter: those
    // entries are labelled with patient names.
    try { sessionStorage.removeItem('as_history') } catch { /* ignore */ }
    setHistory([])
  }, [resetCase])

  useEffect(() => {
    // Subscribe before the first request goes out, so a token that expired
    // while the tab was closed is handled by the same path as one that expires
    // mid-consultation.
    const unsubscribe = onUnauthorized(endSession)
    let cancelled = false

    ;(async () => {
      let mode = 'protected'
      try {
        const status = await api.authStatus()
        mode = status.mode || (status.auth_required ? 'protected' : 'locked')
        if (!cancelled) { setAuthRequired(status.auth_required); setAuthMode(mode) }
      } catch {
        // Unreachable backend, or one too old to have the route. Assume a login
        // is wanted: showing a login screen to an instance that did not need
        // one is an inconvenience, and skipping it on one that did is not.
        if (!cancelled) { setAuthRequired(true); setAuthMode('protected') }
      }

      // A token in storage proves nothing — it may have expired, or the account
      // may have been removed from the environment since. Only the server can
      // say, so ask it before restoring anything.
      if (getToken()) {
        try {
          const who = await api.me()
          if (!cancelled) setSession({ username: who.username })
        } catch {
          if (!cancelled) endSession()
        }
      } else if (mode === 'anonymous' && !cancelled) {
        // The backend has declared that it is serving every route without a
        // token. There is then no credential that can work — /api/auth/login
        // returns 503 and /api/auth/me returns 401 — so gating on `session`
        // left the local-development path staring at a login screen forever.
        //
        // Failing closed is preserved: only the server's own self-declared
        // "anonymous" opens this, never a missing or false `auth_required`.
        setSession({ username: 'local', anonymous: true })
      }

      if (!cancelled) setBooting(false)
    })()

    return () => { cancelled = true; unsubscribe() }
  }, [endSession])

  const signIn = useCallback(async (username, password) => {
    // Errors are left to propagate: the login screen is the only place that can
    // tell the operator apart from the typist, and it needs the status code to
    // do it. The password is used here and nowhere else — never stored, never
    // put in state that outlives the attempt, never logged.
    const result = await api.login(username, password)
    setToken(result.token)
    setSession({ username: result.username })
  }, [])

  const signOut = useCallback(() => { endSession() }, [endSession])

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

  // Gated on the session because /api/settings/ai now requires a token: asking
  // before sign-in would spend a request to be told 401, and asking again the
  // moment someone signs in is exactly when the answer becomes available.
  useEffect(() => {
    if (session) refreshAiStatus()
    else setAiStatus(null)
  }, [session, refreshAiStatus])

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
      value={{
        analysis, setAnalysis, history,
        assessment, setAssessment, otoscopy, setOtoscopy,
        aep, setAep, tuningFork, setTuningFork, boa, setBoa, babbleScreen, setBabbleScreen, record, setRecord,
        patient, setPatient, skipped, skipStep, unskipStep, resetCase,
        aiStatus, refreshAiStatus, toast, showToast,
        session, authRequired, authMode, booting, signIn, signOut,
      }}
    >
      {children}
    </AppContext.Provider>
  )
}

export const useApp = () => useContext(AppContext)
