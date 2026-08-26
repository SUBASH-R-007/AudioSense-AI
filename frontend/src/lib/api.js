// Thin API client.
//
// Locally, VITE_API_BASE_URL is unset, so every path stays relative and the
// Vite dev proxy forwards /api to the backend on :8000 — nothing changes.
//
// In production the frontend and backend live on different hosts (Vercel and
// a container host), so the base URL is injected at build time here. This
// is the only place that needs to know, which is why every call in the app
// goes through this module.

const RAW_BASE = import.meta.env?.VITE_API_BASE_URL ?? ''
/** Normalised origin for the API, or '' for same-origin + dev proxy. */
export const API_BASE = RAW_BASE.replace(/\/+$/, '')

/** Absolute URL for an API path. Exported for the few callers outside this file. */
export const apiUrl = (path) => `${API_BASE}${path}`

// ---------------------------------------------------------------------------
// The session token
// ---------------------------------------------------------------------------
//
// Held in a module variable so the hot path never touches storage, and mirrored
// into sessionStorage so a refresh — which clinicians do constantly, mid-case —
// does not sign anyone out. sessionStorage rather than localStorage on purpose:
// the token dies with the tab, which is the behaviour you want on a shared
// clinic machine where the next person inherits the browser but must not
// inherit the session.

const TOKEN_KEY = 'as_token'

let token = (() => {
  try { return sessionStorage.getItem(TOKEN_KEY) || null } catch { return null }
})()

/** Record a freshly issued token. Pass null or '' to forget the current one. */
export function setToken(next) {
  token = next || null
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch { /* private mode — the in-memory copy still carries the session */ }
}

export const getToken = () => token
export const clearToken = () => setToken(null)

// Anyone who needs to know the session has ended. The store subscribes; nothing
// else should need to.
const expiryListeners = new Set()

/** Subscribe to "the session just died". Returns an unsubscribe function. */
export function onUnauthorized(listener) {
  expiryListeners.add(listener)
  return () => expiryListeners.delete(listener)
}

// A token that has expired takes every in-flight request down with it, and a
// consultation screen can easily have a dozen of those. Handling it here, once,
// means the app reacts a single time — it flips back to the login screen —
// instead of each caller independently deciding to shout about it. The `token`
// check is what makes it once: the first 401 to land clears it, and every
// sibling 401 then finds nothing to clear and stays quiet.
function noteUnauthorized(path) {
  // A rejected login is a wrong password, not an expired session. Treating it
  // as expiry would be harmless but confusing, since it would fire the
  // "you have been signed out" path at someone who was never signed in.
  if (path.startsWith('/api/auth/login')) return
  if (!token) return
  clearToken()
  for (const listener of expiryListeners) {
    try { listener() } catch { /* a bad listener must not break the response */ }
  }
}

async function http(path, options = {}) {
  // Headers are merged rather than replaced, and only Authorization is added.
  // Several callers post FormData and rely on the browser generating the
  // multipart Content-Type with its boundary; forcing a Content-Type here would
  // produce a request the backend cannot parse.
  const headers = new Headers(options.headers || {})
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(apiUrl(path), { ...options, headers })
  if (res.status === 401) noteUnauthorized(path)
  return res
}

async function json(res) {
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    const err = new Error(detail || `${res.status} ${res.statusText}`)
    // The login screen has to tell a wrong password (401) apart from a
    // throttled client (429) and an instance with no accounts at all (503),
    // and the message text is not a safe thing to switch on.
    err.status = res.status
    throw err
  }
  return res.json()
}

export const api = {
  health: () => http('/api/health').then(json),

  // --- authentication -----------------------------------------------------
  // status is public and answers before anyone has signed in, which is how the
  // app finds out whether this instance has any accounts at all. me() is not
  // public by design: its whole job is to say whether a stored token is still
  // good, so it has to be a request that a bad token fails.
  authStatus: () => http('/api/auth/status').then(json),
  login: (username, password) =>
    http('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }).then(json),
  me: () => http('/api/auth/me').then(json),

  demoCases: () => http('/api/demo-cases').then(json),

  // Live captions score every utterance, so this is called continuously while
  // the microphone is open — it must go through the client like everything
  // else or it loses the session token.
  speechWords: (ac, text) =>
    http('/api/speech-words', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ac, text }),
    }).then(json),

  analyze: (record) =>
    http('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(record),
    }).then(json),

  prescription: (ear) =>
    http('/api/prescription', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ear),
    }).then(json),

  digitize: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http('/api/digitize', { method: 'POST', body: fd }).then(json)
  },

  report: (analysis) =>
    http('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(analysis),
    }).then(json),

  progression: (baseline, current) =>
    http('/api/progression', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ baseline, current }),
    }).then(json),

  batch: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http('/api/batch', { method: 'POST', body: fd }).then(json)
  },

  validate: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http('/api/validate', { method: 'POST', body: fd }).then(json)
  },

  batchPhotos: (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    return http('/api/batch-photos', { method: 'POST', body: fd }).then(json)
  },

  bulkReports: async (cases) => {
    const res = await http('/api/bulk-reports', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cases }),
    })
    if (!res.ok) throw new Error(`Bulk export failed: ${res.status}`)
    return res.blob()
  },

  pdf: async (payload) => {
    const res = await http('/api/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`PDF failed: ${res.status}`)
    return res.blob()
  },

  feedback: (correction) =>
    http('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(correction),
    }).then(json),

  feedbackStats: () => http('/api/feedback').then(json),

  handout: (payload) =>
    http('/api/handout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  referral: async (payload) => {
    const res = await http('/api/referral', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`Referral failed: ${res.status}`)
    return res.blob()
  },

  saveVisit: (analysis) =>
    http('/api/records/visit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(analysis),
    }).then(json),

  patients: (q = '') =>
    http(`/api/records/patients?q=${encodeURIComponent(q)}`).then(json),
  patientHistory: (id) => http(`/api/records/patients/${id}`).then(json),

  noiseDose: (payload) =>
    http('/api/noise-dose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  atlas: (limit = 700) => http(`/api/atlas?limit=${limit}`).then(json),
  atlasProject: (ear) =>
    http('/api/atlas/project', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ear),
    }).then(json),

  localization: (trials, right_ac, left_ac) =>
    http('/api/listening/localization', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trials, right_ac, left_ac }),
    }).then(json),

  predictLocalization: (right_ac, left_ac) =>
    http('/api/listening/predict-localization', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ right_ac, left_ac }),
    }).then(json),

  speechBabble: (reversals, right_ac = {}, left_ac = {}) =>
    http('/api/listening/speech-babble', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reversals, right_ac, left_ac }),
    }).then(json),
  digitsInNoise: (reversals, right_ac, left_ac) =>
    http('/api/listening/digits-in-noise', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reversals, right_ac, left_ac }),
    }).then(json),

  tinnitus: (payload) =>
    http('/api/listening/tinnitus', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  modelComparison: () => http('/api/model/comparison').then(json),

  // --- otoscopy -----------------------------------------------------------
  otoscopyAtlas: () => http('/api/otoscopy/reference').then(json),
  otoscopyModel: () => http('/api/otoscopy/model').then(json),
  otoscopy: (file, side = 'right', analysis = null) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('side', side)
    // Sent as a form field rather than a second request so the cross-check
    // against the audiogram happens server-side, in one round trip.
    if (analysis) fd.append('analysis', JSON.stringify(analysis))
    return http('/api/otoscopy/analyze', { method: 'POST', body: fd }).then(json)
  },

  // --- signs and symptoms -------------------------------------------------
  symptomCatalog: () => http('/api/symptoms/catalog').then(json),
  symptoms: (payload) =>
    http('/api/symptoms/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),
  correlateSymptoms: (assessment, analysis) =>
    http('/api/symptoms/correlate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assessment, analysis }),
    }).then(json),

  // --- cross-modal linkage ------------------------------------------------
  linkage: (payload) =>
    http('/api/linkage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),
  linkageReference: () => http('/api/linkage/reference').then(json),
  diseasesFromOtoscopy: (otoscopy) =>
    http('/api/linkage/from-otoscopy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ otoscopy }),
    }).then(json),
  diseasesFromAudiogram: (analysis, side = 'right') =>
    http('/api/linkage/from-audiogram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis, side }),
    }).then(json),

  // --- evoked potentials and behavioural observation ----------------------
  aepReference: () => http('/api/aep/reference').then(json),
  abr: (payload) =>
    http('/api/aep/abr', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),
  abrThreshold: (series) =>
    http('/api/aep/abr/threshold', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ series }),
    }).then(json),
  mlr: (payload) =>
    http('/api/aep/mlr', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),
  llr: (payload) =>
    http('/api/aep/llr', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),
  abrAsymmetry: (right, left) =>
    http('/api/aep/abr/asymmetry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ right, left }),
    }).then(json),
  aepBattery: (payload) =>
    http('/api/aep/battery', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),
  boaReference: () => http('/api/boa/reference').then(json),
  boa: (payload) =>
    http('/api/boa/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  // --- masking as a live instrument ---------------------------------------
  // The transducer changes whether masking is required at all, so it has to be
  // switchable without re-running the whole analysis.
  maskingReference: () => http('/api/masking/reference').then(json),
  masking: (payload) =>
    http('/api/masking/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  // A second opinion from the deep ensemble, whose disagreement with the
  // forest is itself the signal worth showing.
  deepPredict: (ear) =>
    http('/api/model/deep-predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ear),
    }).then(json),

  // --- the complete diagnostic picture ------------------------------------
  diagnosisReference: () => http('/api/diagnosis/reference').then(json),
  diagnosisPicture: (payload) =>
    http('/api/diagnosis/picture', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  anatomyReference: () => http('/api/anatomy/reference').then(json),
  anatomyVideo: (payload) =>
    http('/api/anatomy/video', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  // --- tuning forks: Rinne, Weber, Bing, ABC/Schwabach, Gelle -------------
  tuningForkReference: () => http('/api/tuning-fork/reference').then(json),
  tuningFork: (payload) =>
    http('/api/tuning-fork/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  // --- speech audiometry: SDT, SRT, WRS -----------------------------------
  speechReference: () => http('/api/speech/reference').then(json),
  speech: (payload) =>
    http('/api/speech/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),
  compareWordScores: (payload) =>
    http('/api/speech/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  // --- immittance and emissions as instruments ----------------------------
  tympanometryReference: () => http('/api/tympanometry/reference').then(json),
  tympanometry: (payload) =>
    http('/api/tympanometry/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),
  oaeReference: () => http('/api/oae/reference').then(json),
  oae: (payload) =>
    http('/api/oae/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  aiSettings: () => http('/api/settings/ai').then(json),
  updateAiSettings: (update) =>
    http('/api/settings/ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    }).then(json),
  testAiSettings: (update) =>
    http('/api/settings/ai/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update || {}),
    }).then(json),
}

export const AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]
export const BC_FREQS = [250, 500, 1000, 2000, 4000]
export const FREQ_LABELS = { 250: '250', 500: '500', 1000: '1k', 2000: '2k', 4000: '4k', 8000: '8k' }
