import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'

export default function AISettingsPanel({ onClose }) {
  const { refreshAiStatus, showToast } = useApp()
  const [data, setData] = useState(null)
  const [mode, setMode] = useState('offline')
  const [provider, setProvider] = useState('gemini')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [baseUrl, setBaseUrl] = useState('http://localhost:11434')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.aiSettings().then((d) => {
      setData(d)
      setMode(d.config.mode)
      setProvider(d.config.provider)
      setModel('')
      setBaseUrl(d.config.base_url || 'http://localhost:11434')
    }).catch(() => showToast('Backend not reachable', 'error'))
  }, [showToast])

  if (!data) return null
  const providers = data.providers
  const p = providers[provider]

  const overlay = () => {
    const u = { mode, provider }
    if (apiKey) u.api_key = apiKey
    if (model) u.model = model
    if (provider === 'ollama') u.base_url = baseUrl
    return u
  }

  const runTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await api.testAiSettings(overlay()))
    } catch (e) {
      setTestResult({ ok: false, message: String(e.message || e) })
    }
    setTesting(false)
  }

  const save = async () => {
    setSaving(true)
    try {
      await api.updateAiSettings(overlay())
      await refreshAiStatus()
      showToast(mode === 'api'
        ? `AI mode enabled — ${providers[provider].label}`
        : 'Offline mode enabled — deterministic engines active')
      onClose()
    } catch (e) {
      showToast(`Save failed: ${e.message}`, 'error')
    }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm"
      onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">AI Engine Settings</h2>
            <p className="mt-0.5 text-[13px] text-slate-500">
              Offline mode is fully functional (deterministic template reports + OpenCV
              digitization). API mode adds LLM-written narratives and vision extraction.
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Mode toggle */}
        <div className="mt-5 grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1.5">
          {[['offline', 'Offline Mode', 'Rules + templates + OpenCV — zero dependencies'],
            ['api', 'API Mode', 'LLM reports + AI vision via your chosen provider']].map(([m, label, desc]) => (
            <button key={m} onClick={() => setMode(m)}
              className={`rounded-lg px-4 py-3 text-left transition ${
                mode === m ? 'bg-white shadow-sm ring-1 ring-slate-200' : 'hover:bg-white/50'
              }`}>
              <div className={`text-sm font-semibold ${mode === m ? 'text-teal-700' : 'text-slate-600'}`}>{label}</div>
              <div className="mt-0.5 text-[11.5px] leading-snug text-slate-500">{desc}</div>
            </button>
          ))}
        </div>

        {mode === 'api' && (
          <>
            <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(providers).map(([key, prov]) => (
                <button key={key} onClick={() => { setProvider(key); setTestResult(null) }}
                  className={`rounded-xl border px-3 py-2.5 text-left transition ${
                    provider === key
                      ? 'border-teal-500 bg-teal-50/60 ring-1 ring-teal-500'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold text-slate-800">{prov.label}</span>
                    {prov.free_tier && (
                      <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9.5px] font-bold uppercase text-emerald-700">free</span>
                    )}
                  </div>
                  <div className="mt-1 text-[11px] leading-snug text-slate-500">{prov.key_hint}</div>
                </button>
              ))}
            </div>

            <div className="mt-4 space-y-3">
              {p.needs_key && (
                <label className="block">
                  <span className="text-[12px] font-medium text-slate-600">API key
                    {data.config.provider === provider && data.config.api_key &&
                      <span className="ml-2 text-slate-400">(saved: {data.config.api_key} — leave blank to keep)</span>}
                  </span>
                  <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Paste your key"
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20" />
                </label>
              )}
              {provider === 'ollama' && (
                <label className="block">
                  <span className="text-[12px] font-medium text-slate-600">Ollama base URL</span>
                  <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20" />
                </label>
              )}
              <label className="block">
                <span className="text-[12px] font-medium text-slate-600">Model
                  <span className="ml-2 text-slate-400">(default: {p.default_model})</span></span>
                <input value={model} onChange={(e) => setModel(e.target.value)}
                  placeholder={p.default_model}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20" />
              </label>

              <div className="flex items-center gap-3">
                <button onClick={runTest} disabled={testing}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-teal-400 hover:text-teal-700 disabled:opacity-50">
                  {testing ? 'Testing…' : 'Test connection'}
                </button>
                {testResult && (
                  <span className={`text-[13px] font-medium ${testResult.ok ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {testResult.ok ? `✓ ${testResult.message}` : `✗ ${testResult.message}`}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400">
                If an API call fails during use, AudioSense automatically falls back to the
                offline engine — the demo never stalls.
              </p>
            </div>
          </>
        )}

        <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4">
          <button onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100">Cancel</button>
          <button onClick={save} disabled={saving}
            className="rounded-lg bg-teal-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-700 disabled:opacity-50">
            {saving ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      </div>
    </div>
  )
}
