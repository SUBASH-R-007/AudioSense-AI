import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, FREQ_LABELS } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import BOAPanel from '../components/BOAPanel.jsx'
import TuningForkPanel from '../components/TuningForkPanel.jsx'
import ThresholdGrid from '../components/ThresholdGrid.jsx'
import ScreeningRunner from '../components/ScreeningRunner.jsx'
import StepNav from '../components/StepNav.jsx'

const EMPTY = () => ({ right: { ac: {}, bc: {} }, left: { ac: {}, bc: {} } })

const ONSET_LABELS = {
  unknown: 'Not recorded',
  gradual: 'Gradual',
  sudden: 'Sudden (within 72 h)',
  congenital: 'Present since birth',
}

const PROCEDURE_LABELS = {
  bayesian: 'Bayesian adaptive procedure',
  staircase: 'modified Hughson-Westlake staircase',
}

/**
 * Per-cell confidence for a screening run, in the shape ThresholdGrid reads:
 * confidence[ear][cond][freq] as a number in 0–1, badged on the cell and drawn
 * amber below 0.7.
 *
 * A badge answers "how far should this number be trusted before it is used",
 * which for a screening run has two separate limits — and only one of them can
 * be expressed per cell at all.
 *
 * What varies per cell is how well the procedure pinned each threshold, and the
 * two procedures differ: the Bayesian estimator stops on a credible interval and
 * so knows when it is done, while the staircase returns a bare number with no
 * error bar. A run the catch trials flagged unreliable is worse than either,
 * because the patient was responding to silence.
 *
 * What cannot be expressed per cell is the calibration: the whole scale was
 * anchored by ear on consumer headphones, so every value may share the same
 * 10–15 dB offset from ISO 389. A systematic offset is invisible in a per-cell
 * number, which is why no screening cell is allowed above the grid's 0.7
 * review-this line, and why the banner states the limit in words as well.
 */
const screeningConfidence = (right, left, procedure, reliability) => {
  const per = reliability && !reliability.reliable
    ? 0.3
    : procedure === 'bayesian' ? 0.6 : 0.5
  const mark = (ac) => Object.fromEntries(Object.keys(ac).map((f) => [f, per]))
  // Bone conduction is left unbadged because it is left unmeasured — a badge on
  // an empty cell would suggest the screening had an opinion about it.
  return {
    right: { ac: mark(right), bc: {} },
    left: { ac: mark(left), bc: {} },
  }
}

/** One read-only fact in the patient strip. */
function Fact({ label, value }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-0.5 text-[13px] text-slate-800">{value || '—'}</div>
    </div>
  )
}

export default function NewTest() {
  const navigate = useNavigate()
  // The patient is captured once on /patient and read from the store here. It
  // used to be typed into this form, halfway through the battery, so the
  // screens before it could not see the age — and the age is what selects the
  // normative bands every other test is judged against.
  const { patient, setPatient, setAnalysis, showToast } = useApp()
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
  // screeningOpen is the run in progress; screeningInfo is the provenance of the
  // values now sitting in the grid, and outlives the run because the operator
  // has to keep seeing what these thresholds are.
  const [screeningOpen, setScreeningOpen] = useState(false)
  const [screeningInfo, setScreeningInfo] = useState(null)
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
    // Where the numbers came from has to be replaced along with the numbers, or
    // a demo case inherits the last run's screening warning.
    setScreeningInfo(null)
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
        setScreeningInfo(null)
      }
    } catch (e) {
      showToast(`Digitize failed: ${e.message}`, 'error')
    }
    setDigitizing(false)
  }

  // The measured run lands in the AC rows and nowhere else. Bone conduction is
  // cleared rather than carried over, because a screening cannot measure it: a
  // BC row left over from a demo case or an earlier photo, sitting under freshly
  // screened AC values, would read as an air-bone gap that nobody tested for.
  // The analysis then reports the type as provisional, which is the truth.
  const onScreeningComplete = ({ right, left, reliability, procedure }) => {
    setThresholds({
      right: { ac: { ...right }, bc: {} },
      left: { ac: { ...left }, bc: {} },
    })
    setConfidence(screeningConfidence(right, left, procedure, reliability))
    setScreeningInfo({ procedure, reliability })
    setDigitizeInfo(null)
    setScreeningOpen(false)
  }

  const analyze = async () => {
    // Analysing without demographics loses the age for good, and the age is what
    // selects the normative bands downstream — so this refuses rather than
    // quietly assuming an adult.
    if (!patient) {
      return showToast('Enter the patient first — the age selects the normative bands', 'warn')
    }
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
      // The backend's PatientInfo takes exactly these fields; the store keeps
      // no symptoms list, so it is sent empty rather than omitted.
      const patientInfo = {
        name: patient.name || '',
        age: Number(patient.age),
        sex: patient.sex || 'unspecified',
        occupation: patient.occupation || '',
        test_date: patient.test_date || null,
        onset: patient.onset || 'unknown',
        symptoms: patient.symptoms || [],
      }
      const result = await api.analyze({ patient: patientInfo, transducer, ...built })
      setAnalysis(result)
      navigate('/dashboard')
    } catch (e) {
      showToast(`Analysis failed: ${e.message}`, 'error')
    }
    setAnalyzing(false)
  }

  const field = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20'

  // A screening run needs the operator watching the patient's hand, not a form.
  // The rest of the page is taken off screen for the duration — an editable
  // threshold grid beside a live run is an invitation to type into the row the
  // run is about to overwrite, and the tone presentations are being timed by eye.
  if (screeningOpen) {
    return (
      <div className="mx-auto max-w-3xl">
        <h1 className="text-xl font-semibold tracking-tight">Screening audiometry</h1>
        <p className="mt-1 text-[13.5px] text-slate-500">
          The rest of the form is hidden until this finishes. Accepting the run writes
          the measured levels into the air-conduction rows and marks them as screening
          values; cancelling leaves the form exactly as you left it.
        </p>
        <ScreeningRunner
          onComplete={onScreeningComplete}
          onCancel={() => setScreeningOpen(false)}
          subjectLabel={patient?.name || undefined}
          acceptLabel="Use these thresholds →"
          busyLabel="Filling the grid…"
        />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-xl font-semibold tracking-tight">New Audiometry Test</h1>
      <p className="mt-1 text-[13.5px] text-slate-500">
        Type the thresholds in, snap-to-digitize a paper audiogram, or measure them
        here on headphones. Or load a demo case.
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

      {/* Who this audiogram belongs to — read-only. The details are captured
          once on /patient, and duplicating the inputs here is exactly how the
          age used to end up recorded in two places and disagreeing. */}
      {patient && (
        <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="grid flex-1 grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
              <Fact label="Name" value={patient.name} />
              <Fact label="Age" value={patient.age != null && patient.age !== '' ? `${patient.age} yr` : ''} />
              <Fact label="Sex" value={patient.sex} />
              <Fact label="Occupation" value={patient.occupation} />
              <Fact label="Test date" value={patient.test_date} />
              <Fact label="Onset" value={ONSET_LABELS[patient.onset] || patient.onset} />
            </div>
            <Link to="/patient"
              className="rounded-lg border border-slate-200 px-2.5 py-1 text-[12px] font-medium text-slate-600 transition hover:border-teal-400 hover:text-teal-700">
              Edit
            </Link>
          </div>
          {patient.onset === 'sudden' && (
            <p className="mt-3 text-[11px] font-medium text-rose-600">
              Sudden sensorineural loss is an emergency — steroids are time-critical.
            </p>
          )}
        </div>
      )}

      <div className="mt-5">
        {/* digitize */}
        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
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

        {/* Measure them here — the third way in, for a room with no audiometer.
            It sits beside Snap-to-Digitize because both are ways of filling the
            same grid from something other than a keyboard, and both hand back
            values the operator is expected to review rather than trust. */}
        <div className="mt-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
          data-tour="screening-launch">
          <div className="flex items-center justify-between">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
              Measure thresholds here
            </h2>
            {screeningInfo && (
              <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-semibold text-amber-800">
                screening values in grid
              </span>
            )}
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-slate-500">
            No audiometer in the room? Run the browser screening on headphones — six
            frequencies per ear, with silent catch trials — and the measured levels drop
            straight into the air-conduction rows below, ready to be corrected and carried
            through the rest of the battery.
          </p>
          {patient ? (
            <button
              onClick={() => setScreeningOpen(true)}
              className="mt-3 rounded-xl bg-teal-600 px-5 py-2.5 text-[13.5px] font-semibold text-white shadow-sm shadow-teal-600/25 transition hover:bg-teal-700"
            >
              {screeningInfo ? 'Screen again →' : 'Start screening run →'}
            </button>
          ) : (
            // Thresholds live in this page's state only. Sending the operator to
            // /patient after a run would unmount the form and throw the whole
            // measurement away, so the patient is captured before a tone is played.
            <div className="mt-3 rounded-xl border border-dashed border-slate-300 bg-slate-50/70 px-4 py-3 text-[12.5px] text-slate-600">
              Enter the patient first — a run started now would be lost on the way to
              recording who it belonged to.{' '}
              <Link to="/patient" className="font-semibold text-teal-700 hover:underline">
                Enter patient details →
              </Link>
            </div>
          )}

          {/* THE LIMIT, stated where the values are and left there. A toast would
              be gone by the time anyone reads the audiogram. */}
          {screeningInfo && (
            <div className="mt-3 space-y-2">
              <div className="rounded-lg bg-amber-50 px-3 py-2 text-[12.5px] leading-relaxed text-amber-800">
                <b>Screening thresholds — not a diagnostic audiogram.</b> These were
                measured on uncalibrated consumer headphones against an anchor the
                operator set by ear at 1 kHz, so the whole scale may sit 10–15 dB away
                from ISO 389 dB HL: the <i>shape</i> of the loss is far more trustworthy
                than its depth. Air conduction only and unmasked — the air-bone gap was
                never measured, so conductive and sensorineural loss cannot be told
                apart, and a threshold close to the other ear's may be that ear
                responding. Confirm on a calibrated audiometer before diagnosing,
                certifying, or fitting anything.
                <div className="mt-1.5">
                  Recorded by the {PROCEDURE_LABELS[screeningInfo.procedure]
                    || screeningInfo.procedure}. Every screening-derived cell carries a
                  confidence badge in the grid below — no screening value is badged above
                  the review-this line, however cleanly it measured. Correct any of them
                  by hand; the grid is what gets analysed.
                </div>
              </div>
              {screeningInfo.reliability && (
                <div className={`rounded-lg border px-3 py-2 text-[12.5px] ${
                  screeningInfo.reliability.reliable
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                    : 'border-rose-300 bg-rose-50 text-rose-900'
                }`}>
                  <b>{screeningInfo.reliability.reliable
                    ? 'Responses reliable' : 'Results unreliable'}</b>
                  {' — '}{screeningInfo.reliability.message}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* thresholds */}
      <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
        data-tour="threshold-grid">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400">
            Thresholds (dB HL) — AC &amp; BC per ear
          </h2>
          {patient && (
            <button onClick={() => {
              setThresholds(EMPTY()); setConfidence(null)
              setScreeningInfo(null); setDigitizeInfo(null)
            }}
              className="text-[12px] font-medium text-slate-400 hover:text-rose-600">Clear all</button>
          )}
        </div>
        {patient ? (
          <>
            <div className="mt-3">
              <ThresholdGrid thresholds={thresholds} onChange={setThresholds} confidence={confidence} />
            </div>
            <div className="mt-2 text-[11.5px] text-slate-400">
              NR = No Response at audiometer limits. Leave blank if untested — analysis
              proceeds cautiously and flags provisional results.
            </div>
          </>
        ) : (
          // Thresholds recorded against nobody cannot be given an age later —
          // the record is filed without the one field the norms depend on.
          <div className="mt-3 rounded-xl border border-dashed border-slate-300 bg-slate-50/70 px-4 py-7 text-center">
            <p className="text-[13px] font-medium text-slate-700">
              No patient has been entered for this consultation yet.
            </p>
            <p className="mx-auto mt-1 max-w-md text-[12px] leading-relaxed text-slate-500">
              The age decides which normative bands this audiogram and the rest of
              the battery are judged against, so it is captured before any
              thresholds are taken.
            </p>
            <Link to="/patient"
              className="mt-4 inline-block rounded-lg bg-teal-600 px-4 py-1.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-teal-700">
              Enter patient details →
            </Link>
          </div>
        )}
      </div>

      {/* speech audiometry — the cross-check on the pure tones */}
      <details className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
        data-tour="speech-masking">
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

      {/* Tuning forks come before audiometry at the bedside, and their value
          here is that the audiogram entered above can judge them: the gap the
          forks imply is drawn against the gap actually measured. */}
      <details className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
        data-tour="tuning-fork">
        <summary className="cursor-pointer text-[13px] font-semibold uppercase tracking-wider text-slate-400">
          Tuning fork tests <span className="ml-1 normal-case text-slate-400">(Rinne, Weber, Bing, Schwabach)</span>
        </summary>
        <div className="mt-3">
          <TuningForkPanel thresholds={thresholds} />
        </div>
      </details>

      {/* Behavioural observation sits under the pure-tone form because that
          is where paediatric audiometry starts — and because the mistake it
          invites is writing its levels into the threshold grid above. */}
      <details className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
        data-tour="boa">
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

      <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
        {!patient && (
          <span className="text-[12px] text-slate-500">
            Enter the patient before analysing — the age selects the normative bands.
          </span>
        )}
        <button onClick={analyze} disabled={analyzing || !patient}
          className="rounded-xl bg-teal-600 px-8 py-3 text-[15px] font-semibold text-white shadow-md shadow-teal-600/25 transition hover:bg-teal-700 disabled:opacity-50">
          {analyzing ? 'Analyzing…' : 'Analyze →'}
        </button>
      </div>

      <StepNav stepKey="pure_tone" />
    </div>
  )
}
