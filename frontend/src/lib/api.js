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

const http = (path, options) => fetch(apiUrl(path), options)

async function json(res) {
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  health: () => http('/api/health').then(json),
  demoCases: () => http('/api/demo-cases').then(json),

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
