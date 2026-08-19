// Step 1 — who the patient is.
//
// This screen exists because these details are not paperwork; they change what
// every later test means. The age selects the normative band a tympanogram is
// judged against, decides whether behavioural audiometry is even obtainable,
// and reorders the whole battery under six months. Onset is the difference
// between a routine fitting and a steroid emergency.
//
// They used to be typed into the middle of the pure-tone form, which meant the
// two screens before it could not see them.

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../lib/store.jsx'
import StepNav from '../components/StepNav.jsx'

const field = 'mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-[13px] ' +
  'focus-visible:outline-2 focus-visible:outline-teal-600'

const EMPTY = () => ({
  name: '', age: '', sex: 'male', occupation: '',
  test_date: new Date().toISOString().slice(0, 10),
  onset: 'unknown',
})

export default function Patient() {
  const navigate = useNavigate()
  const { patient, setPatient, resetCase, analysis, showToast } = useApp()
  const [form, setForm] = useState(() => patient || EMPTY())

  useEffect(() => { if (patient) setForm({ ...EMPTY(), ...patient }) }, [patient])

  const set = (patch) => setForm((f) => ({ ...f, ...patch }))
  const ageNum = form.age === '' ? null : Number(form.age)
  const ready = (form.name || '').trim().length > 0 && ageNum != null && !Number.isNaN(ageNum)

  const save = () => {
    if (!ready) {
      showToast('A name and an age are needed before the battery can start', 'warn')
      return
    }
    setPatient({ ...form, age: ageNum })
    return true
  }

  const saveAndGo = () => { if (save()) navigate('/symptoms') }

  const startNew = () => {
    if (!window.confirm(
      'Clear this patient and every result recorded for them — history, otoscopy, '
      + 'thresholds, tuning forks, evoked potentials?')) return
    resetCase()
    setForm(EMPTY())
    showToast('Started a new patient')
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">
            Patient details
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            Entered once, and carried through every test in this consultation.
          </p>
        </div>
        {(patient || analysis) && (
          <button onClick={startNew}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-[12.5px] font-medium text-slate-600 transition hover:border-rose-300 hover:text-rose-700">
            Start a new patient
          </button>
        )}
      </header>

      <div className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
        data-tour="patient-form">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block sm:col-span-2">
            <span className="text-[12px] font-medium text-slate-600">Name</span>
            <input className={field} value={form.name} autoFocus
              onChange={(e) => set({ name: e.target.value })}
              placeholder="Patient name" />
          </label>

          <label className="block">
            <span className="text-[12px] font-medium text-slate-600">Age (years)</span>
            <input type="number" min="0" max="120" className={field} value={form.age}
              onChange={(e) => set({ age: e.target.value })} placeholder="—" />
            <span className="mt-1 block text-[11px] leading-relaxed text-slate-400">
              Selects the normative bands for tympanometry and emissions, and
              decides which paediatric tests apply.
            </span>
          </label>

          <label className="block">
            <span className="text-[12px] font-medium text-slate-600">Sex</span>
            <select className={field} value={form.sex}
              onChange={(e) => set({ sex: e.target.value })}>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </label>

          <label className="block">
            <span className="text-[12px] font-medium text-slate-600">Occupation</span>
            <input className={field} value={form.occupation}
              onChange={(e) => set({ occupation: e.target.value })}
              placeholder="e.g. factory worker" />
          </label>

          <label className="block">
            <span className="text-[12px] font-medium text-slate-600">Test date</span>
            <input type="date" className={field} value={form.test_date || ''}
              onChange={(e) => set({ test_date: e.target.value })} />
          </label>

          <label className="block sm:col-span-2">
            <span className="text-[12px] font-medium text-slate-600">Onset of the loss</span>
            <select className={field} value={form.onset}
              onChange={(e) => set({ onset: e.target.value })}>
              <option value="unknown">Unknown / not reported</option>
              <option value="sudden">Sudden — within the last 72 hours</option>
              <option value="gradual">Gradual</option>
              <option value="congenital">Present since birth</option>
            </select>
          </label>
        </div>

        {form.onset === 'sudden' && (
          <p className="mt-4 rounded-xl border border-rose-300 bg-rose-50 px-3 py-2.5 text-[12.5px] font-medium leading-relaxed text-rose-900">
            Sudden sensorineural hearing loss is a medical emergency. Corticosteroids
            work, and the window is days — this needs an ENT opinion today, not after
            the rest of the battery.
          </p>
        )}

        {ageNum != null && ageNum < 0.5 && (
          <p className="mt-4 rounded-xl border border-sky-300 bg-sky-50 px-3 py-2.5 text-[12.5px] leading-relaxed text-sky-900">
            Under six months there is no conditioned response to shape, so pure
            tones are not the reference test. Behavioural observation is a screen
            only, and an objective threshold estimate — ABR or ASSR — is what
            sizes the loss.
          </p>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
          <button onClick={save} disabled={!ready}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-[13px] font-medium text-slate-700 transition hover:border-teal-400 disabled:opacity-40">
            Save
          </button>
          <button onClick={saveAndGo} disabled={!ready}
            className="rounded-lg bg-teal-600 px-4 py-1.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-teal-700 disabled:opacity-40">
            Save and start the battery →
          </button>
        </div>
        {!ready && (
          <p className="mt-2 text-right text-[11.5px] text-slate-400">
            A name and an age are needed before the battery can start.
          </p>
        )}
      </div>

      <StepNav stepKey="patient" />
    </div>
  )
}
