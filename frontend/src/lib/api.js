// Thin API client — all calls go through the Vite dev proxy to :8000.

async function json(res) {
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  health: () => fetch('/api/health').then(json),
  demoCases: () => fetch('/api/demo-cases').then(json),

  analyze: (record) =>
    fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(record),
    }).then(json),

  prescription: (ear) =>
    fetch('/api/prescription', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ear),
    }).then(json),

  digitize: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/digitize', { method: 'POST', body: fd }).then(json)
  },

  report: (analysis) =>
    fetch('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(analysis),
    }).then(json),

  progression: (baseline, current) =>
    fetch('/api/progression', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ baseline, current }),
    }).then(json),

  batch: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/batch', { method: 'POST', body: fd }).then(json)
  },

  validate: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/validate', { method: 'POST', body: fd }).then(json)
  },

  batchPhotos: (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    return fetch('/api/batch-photos', { method: 'POST', body: fd }).then(json)
  },

  bulkReports: async (cases) => {
    const res = await fetch('/api/bulk-reports', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cases }),
    })
    if (!res.ok) throw new Error(`Bulk export failed: ${res.status}`)
    return res.blob()
  },

  pdf: async (payload) => {
    const res = await fetch('/api/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`PDF failed: ${res.status}`)
    return res.blob()
  },

  feedback: (correction) =>
    fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(correction),
    }).then(json),

  feedbackStats: () => fetch('/api/feedback').then(json),

  handout: (payload) =>
    fetch('/api/handout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  referral: async (payload) => {
    const res = await fetch('/api/referral', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`Referral failed: ${res.status}`)
    return res.blob()
  },

  saveVisit: (analysis) =>
    fetch('/api/records/visit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(analysis),
    }).then(json),

  patients: (q = '') =>
    fetch(`/api/records/patients?q=${encodeURIComponent(q)}`).then(json),
  patientHistory: (id) => fetch(`/api/records/patients/${id}`).then(json),

  noiseDose: (payload) =>
    fetch('/api/noise-dose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  atlas: (limit = 700) => fetch(`/api/atlas?limit=${limit}`).then(json),
  atlasProject: (ear) =>
    fetch('/api/atlas/project', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ear),
    }).then(json),

  localization: (trials, right_ac, left_ac) =>
    fetch('/api/listening/localization', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trials, right_ac, left_ac }),
    }).then(json),

  predictLocalization: (right_ac, left_ac) =>
    fetch('/api/listening/predict-localization', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ right_ac, left_ac }),
    }).then(json),

  digitsInNoise: (reversals, right_ac, left_ac) =>
    fetch('/api/listening/digits-in-noise', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reversals, right_ac, left_ac }),
    }).then(json),

  tinnitus: (payload) =>
    fetch('/api/listening/tinnitus', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json),

  modelComparison: () => fetch('/api/model/comparison').then(json),

  aiSettings: () => fetch('/api/settings/ai').then(json),
  updateAiSettings: (update) =>
    fetch('/api/settings/ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    }).then(json),
  testAiSettings: (update) =>
    fetch('/api/settings/ai/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update || {}),
    }).then(json),
}

export const AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]
export const BC_FREQS = [250, 500, 1000, 2000, 4000]
export const FREQ_LABELS = { 250: '250', 500: '500', 1000: '1k', 2000: '2k', 4000: '4k', 8000: '8k' }
