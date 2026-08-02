import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, FREQ_LABELS } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import BOAPanel from '../components/BOAPanel.jsx'
import ThresholdGrid from '../components/ThresholdGrid.jsx'

const EMPTY = () => ({ right: { ac: {}, bc: {} }, left: { ac: {}, bc: {} } })

export default function NewTest() {
  const navigate = useNavigate()
  const { setAnalysis, showToast } = useApp()
  const [patient, setPatient] = useState({
    name: '', age: 40, sex: 'male', occupation: '',
    test_date: new Date().toISOString().slice(0, 10),
    onset: 'unknown', symptoms: [],
  })
  const [thresholds, setThresholds] = useState(EMPTY())
  const [speech, setSpeech] = useState({
    right: { sdt: '', srt: '', wrs: '', wrsLevel: '', nWords: '25' },
    left: { sdt: '', srt: '', wrs: '', wrsLevel: '', nWords: '25' },
  })
  const [masked, setMasked] = useState({ right: false, left: false })
  // The transducer sets interaural attenuation, and therefore decides at
  // which frequencies masking is required at all.
  const [transducer, setTransducer] = useState('supra_aural')
  const EMPTY_BATTERY = () => ({
    tymp_pressure: '', tymp_compliance: '', tymp_ecv: '',
    reflex_ipsi: '', reflex_contra: '', reflex_tested: false,
    oae: { 1000: '', 2000: '', 4000: '', 8000: '' },
  })
  const [battery, setBattery] = useState({
    right: EMPTY_BATTERY(), left: EMPTY_BATTERY(),
  })
  const [confidence, setConfidence] = useState(null)
  const [demoCases, setDemoCases] = useState([])
  const [digitizing, setDigitizing] = useState(false)
  const [digitizeInfo, setDigitizeInfo] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    api.demoCases().then((d) => setDemoCases(d.cases)).catch(() =>
      showToast('Backend not reachable — start the FastAPI server on :8000', 'error'))
  }, [showToast])

  const loadDemo = (c) => {
    setPatient({ onset: 'unknown', symptoms: [], ...c.record.patient })
    setThresholds({
      right: { ac: c.record.right.ac || {}, bc: c.record.right.bc || {} },
      left: { ac: c.record.left.ac || {}, bc: c.record.left.bc || {} },
    })
    // Demo cases carry speech audiometry and masking status too — load the
    // whole record, not just the thresholds, or the form silently overrides it.
    const speechOf = (ear) => ({
      sdt: ear.sdt ?? '',
      srt: ear.srt ?? '',
      wrs: ear.wrs?.length ? ear.wrs[0].score : '',
      wrsLevel: ear.wrs?.length ? ear.wrs[0].level : '',
      nWords: ear.wrs?.length ? (ear.wrs[0].n_words ?? 25) : '25',
    })
    setSpeech({ right: speechOf(c.record.right), left: speechOf(c.record.left) })
    setMasked({
      right: !!c.record.right.masked,
      left: !!c.record.left.masked,
    })
    const batteryOf = (ear) => ({
      tymp_pressure: ear.tymp_pressure ?? '',
      tymp_compliance: ear.tymp_compliance ?? '',
      tymp_ecv: ear.tymp_ecv ?? '',
      reflex_ipsi: ear.reflexes?.ipsi ?? '',
      reflex_contra: ear.reflexes?.contra ?? '',
      reflex_tested: !!ear.reflexes,
      oae: [1000, 2000, 4000, 8000].reduce((acc, f) => {
        const point = (ear.oae || []).find((p) => p.freq === f)
        acc[f] = point ? point.amplitude : ''
        return acc
      }, {}),
    })
    setBattery({ right: batteryOf(c.record.right), left: batteryOf(c.record.left) })
    setConfidence(null)
    setDigitizeInfo(null)
  }

  const onPhoto = async (file) => {
    if (!file) return
    setDigitizing(true)
    setDigitizeInfo(null)
    try {
      const res = await api.digitize(file)
      if (!res.ok) {
        showToast(res.error || 'Could not read the chart', 'error')
      } else {
        setThresholds({
          right: { ac: res.right.ac || {}, bc: res.right.bc || {} },
          left: { ac: res.left.ac || {}, bc: res.left.bc || {} },
        })
        setConfidence(res.confidence)
        setDigitizeInfo(res)
      }
    } catch (e) {
      showToast(`Digitize failed: ${e.message}`, 'error')
    }
    setDigitizing(false)
  }

  const analyze = async () => {
    const hasData = Object.keys(thresholds.right.ac).length || Object.keys(thresholds.left.ac).length
    if (!hasData) return showToast('Enter at least one air-conduction threshold', 'warn')
    setAnalyzing(true)
    try {
      const num = (v) => (v === '' || v === null ? undefined : parseFloat(v))
      const built = {}
      for (const ear of ['right', 'left']) {
        const s = speech[ear]
        const b = battery[ear]
        // OAE amplitudes are entered as dB SPL against a nominal noise floor.
        const oae = Object.entries(b.oae)
          .filter(([, amp]) => amp !== '')
          .map(([freq, amp]) => ({
            freq: parseInt(freq, 10), amplitude: parseFloat(amp), noise_floor: -5,
          }))
        built[ear] = {
          ...thresholds[ear],
          masked: masked[ear],
          ...(s.srt !== '' ? { srt: parseInt(s.srt, 10) } : {}),
          ...(s.sdt !== '' && s.sdt !== undefined
            ? { sdt: parseInt(s.sdt, 10) } : {}),
          ...(s.wrs !== '' && s.wrsLevel !== ''
            ? { wrs: [{ level: parseInt(s.wrsLevel, 10), score: parseFloat(s.wrs),
                        n_words: parseInt(s.nWords || 25, 10) }] }
            : {}),
          ...(num(b.tymp_pressure) !== undefined ? { tymp_pressure: num(b.tymp_pressure) } : {}),
          ...(num(b.tymp_compliance) !== undefined ? { tymp_compliance: num(b.tymp_compliance) } : {}),
          ...(num(b.tymp_ecv) !== undefined ? { tymp_ecv: num(b.tymp_ecv) } : {}),
          // An empty box with "tested" ticked means absent at maximum output.
          ...(b.reflex_tested
            ? { reflexes: { ipsi: num(b.reflex_ipsi) ?? null, contra: num(b.reflex_contra) ?? null } }
            : {}),
          ...(oae.length ? { oae } : {}),
        }
      }
      const result = await api.analyze({ patient, transducer, ...built })
      setAnalysis(result)
      navigate('/dashboard')
    } catch (e) {
      showToast(`Analysis failed: ${e.message}`, 'error')
    }
    setAnalyzing(false)
  }

  const field = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20'
  const label = 'text-[12px] font-medium text-slate-600'

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-xl font-semibold tracking-tight">New Audiometry Test</h1>
      <p className="mt-1 text-[13.5px] text-slate-500">
        Enter thresholds manually, load a demo case, or snap-to-digitize a paper audiogram.
      </p>

      {/* demo cases */}
      <div className="mt-5 flex flex-wrap gap-2" data-tour="demo-cases">
        {demoCases.map((c) => (
          <button key={c.id} onClick={() => loadDemo(c)} title={c.description}
            className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-[12.5px] font-medium text-slate-600 shadow-sm transition hover:border-teal-400 hover:text-teal-700">
            {c.label}
          </button>
        ))}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        {/* patient details */}
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">Patient</h2>
          <div className="mt-3 space-y-3">
            <label className="block"><span className={label}>Full name</span>
              <input className={field} value={patient.name}
                onChange={(e) => setPatient({ ...patient, name: e.target.value })} placeholder="Patient name" /></label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block"><span className={label}>Age</span>
                <input type="number" min="0" max="120" className={field} value={patient.age}
                  onChange={(e) => setPatient({ ...patient, age: +e.target.value })} /></label>
              <label className="block"><span className={label}>Sex</span>
                <select className={field} value={patient.sex}
                  onChange={(e) => setPatient({ ...patient, sex: e.target.value })}>
                  <option>male</option><option>female</option><option>other</option>
                </select></label>
            </div>
            <label className="block"><span className={label}>Occupation</span>
              <input className={field} value={patient.occupation}
                onChange={(e) => setPatient({ ...patient, occupation: e.target.value })}
                placeholder="e.g. Factory worker" /></label>
            <label className="block"><span className={label}>Test date</span>
              <input type="date" className={field} value={patient.test_date || ''}
                onChange={(e) => setPatient({ ...patient, test_date: e.target.value })} /></label>
            <label className="block">
              <span className={label}>Onset of hearing loss</span>
              <select className={field} value={patient.onset}
                onChange={(e) => setPatient({ ...patient, onset: e.target.value })}>
                <option value="unknown">Not recorded</option>
                <option value="gradual">Gradual (months / years)</option>
                <option value="sudden">Sudden (within 72 hours)</option>
              </select>
              {patient.onset === 'sudden' && (
                <span className="mt-1 block text-[11px] font-medium text-rose-600">
                  Sudden sensorineural loss is an emergency — steroids are time-critical.
                </span>
              )}
            </label>
          </div>
        </div>

        {/* digitize */}
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm lg:col-span-2"
          data-tour="digitize">
          <div className="flex items-center justify-between">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Snap-to-Digitize
            </h2>
            {digitizeInfo && (
              <span className="rounded-full bg-teal-50 px-2.5 py-1 text-[11px] font-semibold text-teal-700">
                {digitizeInfo.method}
              </span>
            )}
          </div>
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); onPhoto(e.dataTransfer.files?.[0]) }}
            className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 px-6 py-8 text-center transition hover:border-teal-400 hover:bg-teal-50/30"
          >
            <svg viewBox="0 0 24 24" className="h-8 w-8 text-slate-400" fill="none"
              stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
            <div className="mt-2 text-sm font-medium text-slate-700">
              {digitizing ? 'Reading chart…' : 'Drop a photo of a paper audiogram, or click to browse'}
            </div>
            <div className="mt-1 text-[12px] text-slate-400">
              Try the bundled samples: <code className="rounded bg-slate-100 px-1">samples/audiogram_photo_1.png</code>
            </div>
            <input ref={fileRef} type="file" accept="image/*" className="hidden"
              onChange={(e) => onPhoto(e.target.files?.[0])} />
          </div>
          {digitizeInfo && (
            <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[12.5px] text-amber-800">
              <b>Human-in-the-loop:</b> extracted values (with per-value confidence badges)
              are suggestions — review and correct them below before analysis.
              {digitizeInfo.warnings?.length > 0 && (
                <ul className="mt-1 list-inside list-disc">
                  {digitizeInfo.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      {/* thresholds */}
      <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
            Thresholds (dB HL) — AC &amp; BC per ear
          </h2>
          <button onClick={() => { setThresholds(EMPTY()); setConfidence(null) }}
            className="text-[12px] font-medium text-slate-400 hover:text-rose-600">Clear all</button>
        </div>
        <div className="mt-3">
          <ThresholdGrid thresholds={thresholds} onChange={setThresholds} confidence={confidence} />
        </div>
        <div className="mt-2 text-[11.5px] text-slate-400">
          NR = No Response at audiometer limits. Leave blank if untested — analysis
          proceeds cautiously and flags provisional results.
        </div>
      </div>

      {/* speech audiometry — the cross-check on the pure tones */}
      <details className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <summary className="cursor-pointer text-[13px] font-semibold uppercase tracking-wider text-slate-400">
          Speech audiometry &amp; masking <span className="ml-1 normal-case text-slate-400">(optional)</span>
        </summary>
        <p className="mt-2 text-[12.5px] text-slate-500">
          Speech thresholds cross-check the pure tones: an SRT much better than the
          PTA points to exaggerated thresholds, and word scores that fall at higher
          levels (rollover) point to retrocochlear pathology.
        </p>

        <label className="mt-3 flex flex-wrap items-center gap-2 text-[12.5px]">
          <span className="font-medium text-slate-600">Transducer</span>
          <select value={transducer} onChange={(e) => setTransducer(e.target.value)}
            className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px]">
            <option value="supra_aural">Supra-aural — 40 dB interaural attenuation</option>
            <option value="insert">Insert — 50–60 dB</option>
            <option value="circumaural">Circumaural — 45 dB</option>
          </select>
          <span className="text-[11.5px] text-slate-500">
            Sets the level at which sound crosses the skull, and therefore where
            masking becomes necessary.
          </span>
        </label>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          {['right', 'left'].map((ear) => (
            <div key={ear} className="rounded-xl border border-slate-200 p-3">
              <div className={`text-[12px] font-bold uppercase ${
                ear === 'right' ? 'text-red-600' : 'text-blue-600'}`}>{ear} ear</div>
              <div className="mt-2 grid grid-cols-3 gap-2">
                <label className="block"><span className="text-[11px] text-slate-500">SDT (dB)</span>
                  <input type="number" className={field} value={speech[ear].sdt}
                    onChange={(e) => setSpeech({ ...speech, [ear]: { ...speech[ear], sdt: e.target.value } })}
                    placeholder="—" /></label>
                <label className="block"><span className="text-[11px] text-slate-500">SRT (dB)</span>
                  <input type="number" className={field} value={speech[ear].srt}
                    onChange={(e) => setSpeech({ ...speech, [ear]: { ...speech[ear], srt: e.target.value } })}
                    placeholder="—" /></label>
                <label className="block"><span className="text-[11px] text-slate-500">WRS (%)</span>
                  <input type="number" min="0" max="100" className={field} value={speech[ear].wrs}
                    onChange={(e) => setSpeech({ ...speech, [ear]: { ...speech[ear], wrs: e.target.value } })}
                    placeholder="—" /></label>
                <label className="block"><span className="text-[11px] text-slate-500">at (dB)</span>
                  <input type="number" className={field} value={speech[ear].wrsLevel}
                    onChange={(e) => setSpeech({ ...speech, [ear]: { ...speech[ear], wrsLevel: e.target.value } })}
                    placeholder="—" /></label>
                <label className="block"><span className="text-[11px] text-slate-500">list size</span>
                  <select className={field} value={speech[ear].nWords}
                    onChange={(e) => setSpeech({ ...speech, [ear]: { ...speech[ear], nWords: e.target.value } })}>
                    <option value="10">10</option>
                    <option value="25">25</option>
                    <option value="50">50</option>
                  </select></label>
              </div>
              <label className="mt-2 flex cursor-pointer items-center gap-1.5 text-[12px] text-slate-600">
                <input type="checkbox" checked={masked[ear]} className="h-3.5 w-3.5 accent-teal-600"
                  onChange={(e) => setMasked({ ...masked, [ear]: e.target.checked })} />
                Masked thresholds were obtained
              </label>
            </div>
          ))}
        </div>
      </details>

      {/* Behavioural observation sits under the pure-tone form because that
          is where paediatric audiometry starts — and because the mistake it
          invites is writing its levels into the threshold grid above. */}
      <details className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <summary className="cursor-pointer text-[13px] font-semibold uppercase tracking-wider text-slate-400">
          Behavioural observation (BOA) <span className="ml-1 normal-case text-slate-400">(infants under 6 months)</span>
        </summary>
        <div className="mt-3">
          <BOAPanel />
        </div>
      </details>

      {/* immittance + OAE — the rest of the battery */}
      <details className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <summary className="cursor-pointer text-[13px] font-semibold uppercase tracking-wider text-slate-400">
          Tympanometry, reflexes &amp; OAE <span className="ml-1 normal-case text-slate-400">(optional)</span>
        </summary>
        <p className="mt-2 text-[12.5px] text-slate-500">
          These are objective — they need no response from the patient. Entering them
          lets AudioSense cross-check the audiogram: confirming a conductive loss,
          catching exaggerated thresholds, or finding cochlear damage
          <b> before the audiogram moves</b>.
        </p>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          {['right', 'left'].map((ear) => {
            const b = battery[ear]
            const set = (patch) => setBattery({ ...battery, [ear]: { ...b, ...patch } })
            return (
              <div key={ear} className="rounded-xl border border-slate-200 p-3">
                <div className={`text-[12px] font-bold uppercase ${
                  ear === 'right' ? 'text-red-600' : 'text-blue-600'}`}>{ear} ear</div>

                <div className="mt-2 text-[11px] font-semibold text-slate-500">Tympanometry</div>
                <div className="grid grid-cols-3 gap-2">
                  <label className="block"><span className="text-[10.5px] text-slate-500">Peak (daPa)</span>
                    <input type="number" className={field} value={b.tymp_pressure}
                      onChange={(e) => set({ tymp_pressure: e.target.value })} placeholder="—" /></label>
                  <label className="block"><span className="text-[10.5px] text-slate-500">Compliance</span>
                    <input type="number" step="0.1" className={field} value={b.tymp_compliance}
                      onChange={(e) => set({ tymp_compliance: e.target.value })} placeholder="mmho" /></label>
                  <label className="block"><span className="text-[10.5px] text-slate-500">ECV (cm³)</span>
                    <input type="number" step="0.1" className={field} value={b.tymp_ecv}
                      onChange={(e) => set({ tymp_ecv: e.target.value })} placeholder="—" /></label>
                </div>

                <div className="mt-3 flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-500">Acoustic reflexes</span>
                  <label className="flex cursor-pointer items-center gap-1 text-[11px] text-slate-500">
                    <input type="checkbox" checked={b.reflex_tested} className="h-3 w-3 accent-teal-600"
                      onChange={(e) => set({ reflex_tested: e.target.checked })} />
                    tested
                  </label>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[['reflex_ipsi', 'Ipsi (dB)'], ['reflex_contra', 'Contra (dB)']].map(([k, l]) => (
                    <label key={k} className="block"><span className="text-[10.5px] text-slate-500">{l}</span>
                      <input type="number" className={field} value={b[k]} disabled={!b.reflex_tested}
                        onChange={(e) => set({ [k]: e.target.value })} placeholder="absent" /></label>
                  ))}
                </div>
                {b.reflex_tested && (
                  <div className="mt-1 text-[10.5px] text-slate-400">
                    Leave blank = absent at maximum output.
                  </div>
                )}

                <div className="mt-3 text-[11px] font-semibold text-slate-500">
                  DPOAE amplitude (dB SPL)
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {[1000, 2000, 4000, 8000].map((f) => (
                    <label key={f} className="block">
                      <span className="text-[10.5px] text-slate-500">{FREQ_LABELS[f]}</span>
                      <input type="number" className={field} value={b.oae[f]}
                        onChange={(e) => set({ oae: { ...b.oae, [f]: e.target.value } })}
                        placeholder="—" /></label>
                  ))}
                </div>
                <div className="mt-1 text-[10.5px] text-slate-400">
                  Present when ≥ 6 dB above the noise floor (taken as −5 dB SPL).
                </div>
              </div>
            )
          })}
        </div>
      </details>

      <div className="mt-6 flex justify-end">
        <button onClick={analyze} disabled={analyzing}
          className="rounded-xl bg-teal-600 px-8 py-3 text-[15px] font-semibold text-white shadow-md shadow-teal-600/25 transition hover:bg-teal-700 disabled:opacity-50">
          {analyzing ? 'Analyzing…' : 'Analyze →'}
        </button>
      </div>
    </div>
  )
}
