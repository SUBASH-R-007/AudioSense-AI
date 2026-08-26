import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import { useApp } from '../lib/store.jsx'
import ScreeningRunner from '../components/ScreeningRunner.jsx'

export default function Screening() {
  const navigate = useNavigate()
  const { analysis, setAnalysis, setBabbleScreen, showToast, patient: recorded, setPatient: setRecorded } = useApp()
  // Screening is a tool, not a step of the consultation — a judge tries it on
  // themselves, a camp screens a queue of walk-ins. So it keeps its own subject
  // rather than editing the recorded patient. But when a patient IS on file it
  // seeds from them, because otherwise a screening run would overwrite the
  // dashboard's analysis with a 30-year-old called nobody.
  const [patient, setPatient] = useState(() => ({
    name: recorded?.name || '', age: recorded?.age ?? 30,
    sex: recorded?.sex || 'other', occupation: recorded?.occupation || '',
    test_date: new Date().toISOString().slice(0, 10),
  }))

  useEffect(() => {
    if (!recorded) return
    setPatient((p) => ({
      ...p,
      name: recorded.name || p.name,
      age: recorded.age ?? p.age,
      sex: recorded.sex || p.sex,
      occupation: recorded.occupation || p.occupation,
    }))
  }, [recorded])

  // The runner measures; this page decides what the measurement means for the
  // record. Bone conduction is left empty because a screening never establishes
  // it, and the analysis must not be able to infer an air-bone gap from silence.
  const analyze = async (run) => {
    // A babble run measures a speech reception threshold, not tone
    // thresholds, so there is nothing for /api/analyze to grade. It is scored
    // against the (provisional) bands server-side and stored as its own
    // instrument result, which the dashboard shows beside the audiogram.
    if (run.procedure === 'babble') {
      try {
        const scored = await api.speechBabble(
          run.babble.reversals,
          analysis?.thresholds?.right?.ac || {},
          analysis?.thresholds?.left?.ac || {})
        setBabbleScreen({ ...scored, trials: run.babble.trials,
                          reversals: run.babble.reversals,
                          when: new Date().toISOString() })
        showToast(`Speech-in-babble SRT ${scored.result.srt_db_snr} dB SNR — ${scored.result.band}`)
        navigate('/dashboard')
      } catch (e) {
        showToast(`Scoring failed: ${e.message}`, 'error')
      }
      return
    }
    const { right, left } = run
    try {
      const subject = { ...patient, name: patient.name || 'Screening subject' }
      const record = {
        patient: subject,
        right: { ac: right, bc: {} },
        left: { ac: left, bc: {} },
      }
      setAnalysis(await api.analyze(record))
      // The dashboard reads the patient from the analysis, but every other
      // screen reads it from the store. Publishing it here keeps them agreeing
      // about whose result is on screen.
      setRecorded({ ...(recorded || {}), ...subject, onset: recorded?.onset || 'unknown' })
      navigate('/dashboard')
    } catch (e) {
      showToast(`Analysis failed: ${e.message}`, 'error')
    }
  }

  const field = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20'

  return (
    <div data-tour="screening-runner" className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold tracking-tight">Hearing Screening</h1>
      <p className="mt-1 text-[13.5px] text-slate-500">
        A modified Hughson-Westlake pure-tone screening, run in the browser — the
        result flows straight into the full AudioSense analysis.
      </p>

      <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800">
        <b>Screening, not a diagnostic audiogram.</b> Consumer headphones and browser
        audio are not calibrated to ISO 389 reference levels. Absolute dB HL values are
        approximate; use this to detect and demonstrate hearing loss, never to certify it.
        Run it in a quiet room with wired headphones.
      </div>

      {/* Who the thresholds belong to. Age and occupation are not decoration:
          the analysis reads them when it separates presbycusis from noise
          exposure, so a blank form makes a weaker report. */}
      <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Subject
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <label className="block"><span className="text-[12px] font-medium text-slate-600">Name</span>
            <input className={field} value={patient.name}
              onChange={(e) => setPatient({ ...patient, name: e.target.value })}
              placeholder="Screening subject" /></label>
          <label className="block"><span className="text-[12px] font-medium text-slate-600">Age</span>
            <input type="number" className={field} value={patient.age}
              onChange={(e) => setPatient({ ...patient, age: +e.target.value })} /></label>
          <label className="block"><span className="text-[12px] font-medium text-slate-600">Occupation</span>
            <input className={field} value={patient.occupation}
              onChange={(e) => setPatient({ ...patient, occupation: e.target.value })} /></label>
        </div>
      </div>

      <ScreeningRunner onComplete={analyze} subjectLabel={patient.name} />
    </div>
  )
}
