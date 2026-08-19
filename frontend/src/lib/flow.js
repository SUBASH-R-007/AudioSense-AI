// The consultation flow — one definition, used by the sidebar, the step
// footer, and the progress logic.
//
// Before this existed the app was twelve screens a clinician had to already
// know the order of. Demographics were typed into the pure-tone form in the
// middle of the flow, so the two screens that come BEFORE it — history and
// otoscopy — had no idea who the patient was and asked for the age again.
// Immittance defaulted to a 30-year-old, which meant a child's tympanogram was
// judged against adult norms unless someone noticed.
//
// So the flow is now explicit and the patient is captured once, first.
//
// TWO KINDS OF SCREEN. A STEP belongs to this patient's consultation and
// carries state. A TOOL is a standalone instrument that does not — the
// simulator, the batch worklist, the records browser. Mixing them in one list
// is what made the order unreadable.
//
// SKIPPING IS A FIRST-CLASS OUTCOME. Most of the battery is genuinely optional:
// a routine follow-up needs no otoscopy, a screening camp has no tympanometer.
// A skipped step records WHY, and — this is the part that matters — it never
// fabricates a result. "Not performed" and "performed and normal" are different
// clinical facts, and the interpretation must keep telling them apart. Skipping
// therefore changes nothing about the analysis; it only silences the prompt.

/** Steps of the consultation, in the order a session actually runs. */
export const STEPS = [
  {
    key: 'patient',
    to: '/patient',
    label: 'Patient details',
    short: 'Patient',
    required: true,
    icon: 'M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 7a4 4 0 108 0 4 4 0 00-8 0',
    why: 'Age decides which normative bands every later test is judged against, '
       + 'and onset decides whether this is an emergency.',
  },
  {
    key: 'symptoms',
    to: '/symptoms',
    label: 'Signs & symptoms',
    short: 'History',
    required: false,
    icon: 'M9 12h6m-3-3v6M4.5 8.5A7.5 7.5 0 0119 12v6a2 2 0 01-2 2H7a2 2 0 01-2-2v-4',
    why: 'The complaint decides which findings matter.',
    skipHint: 'Routine follow-up with no new complaint',
  },
  {
    key: 'otoscopy',
    to: '/otoscopy',
    label: 'Otoscopy',
    short: 'Otoscopy',
    required: false,
    icon: 'M12 20a8 8 0 100-16 8 8 0 000 16zm0-4a4 4 0 100-8 4 4 0 000 8z',
    why: 'A conductive loss often has a cause you can see, and wax invalidates '
       + 'everything measured through it.',
    skipHint: 'No otoscope available, or ears already examined',
  },
  {
    key: 'pure_tone',
    to: '/new-test',
    label: 'Pure-tone audiometry',
    short: 'Audiogram',
    required: true,
    icon: 'M12 4v16m8-8H4',
    why: 'The reference measurement everything else is checked against.',
  },
  {
    key: 'immittance',
    to: '/immittance',
    label: 'Immittance, OAE & speech',
    short: 'Immittance',
    required: false,
    icon: 'M3 12c2-6 4-6 6 0s4 6 6 0 4-6 6 0',
    why: 'Gives the conductive mechanism the audiogram can only infer, and '
       + 'reports outer hair cells before thresholds move.',
    skipHint: 'No tympanometer or OAE probe on site',
  },
  {
    key: 'aep',
    to: '/evoked-potentials',
    label: 'Evoked potentials',
    short: 'AEP',
    required: false,
    icon: 'M2 12h3l2-6 3 12 3-9 2 3h7',
    why: 'Objective, and the only way to localise a lesion above the cochlea.',
    skipHint: 'Not indicated, or no evoked-potential system',
  },
  {
    key: 'results',
    to: '/dashboard',
    label: 'Results',
    short: 'Results',
    required: true,
    icon: 'M3 13h4v8H3zm7-9h4v17h-4zm7 5h4v12h-4z',
    why: 'The verdict, the evidence behind it, and what is still outstanding.',
  },
]

/** Standalone instruments — not part of any one patient's consultation. */
export const TOOLS = [
  { to: '/screening', label: 'Screening Test', icon: 'M12 18.5a6.5 6.5 0 100-13 6.5 6.5 0 000 13zm0-9.5a3 3 0 100 6 3 3 0 000-6z' },
  { to: '/simulator', label: 'Hearing Simulator', icon: 'M3 10v4m4-8v12m4-15v18m4-14v10m4-7v4' },
  { to: '/listening-lab', label: 'Listening Lab', icon: 'M12 3v18M8 7v10M4 10v4M16 6v12M20 9v6' },
  { to: '/progression', label: 'Progression', icon: 'M3 17l6-6 4 4 8-8m0 0v5m0-5h-5' },
  { to: '/batch', label: 'Batch Analysis', icon: 'M4 6h16M4 12h16M4 18h10' },
  { to: '/records', label: 'Patient Records', icon: 'M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2zM8 9h4m-4 4h8m-8 4h8' },
]

export const STEP_BY_KEY = Object.fromEntries(STEPS.map((s) => [s.key, s]))
export const STEP_BY_PATH = Object.fromEntries(STEPS.map((s) => [s.to, s]))

/** A step counts as done only when it produced something real. */
function isDone(key, ctx) {
  const { patient, assessment, otoscopy, analysis, aep } = ctx
  switch (key) {
    case 'patient':
      // A name alone is not a patient record; the age is what later tests need.
      return Boolean(patient && (patient.name || '').trim() && patient.age != null)
    case 'symptoms':
      return Boolean(assessment)
    case 'otoscopy':
      return Boolean(otoscopy)
    case 'pure_tone':
      return Boolean(analysis)
    case 'immittance': {
      // Immittance is entered on two different screens, so the truth is
      // whatever actually reached the analysis rather than which page was open.
      const battery = analysis?.battery
      if (!battery) return false
      return ['right', 'left'].some((side) => {
        const t = battery[side]?.tests_available || {}
        return t.tympanometry || t.oae || t.speech || t.reflexes
      })
    }
    case 'aep':
      return Boolean(aep)
    case 'results':
      return Boolean(analysis)
    default:
      return false
  }
}

/**
 * State of one step: done | skipped | ready | blocked.
 *
 * `blocked` exists so the sidebar can say WHY a step is not available yet
 * rather than letting a clinician land on an empty screen — the results are
 * blocked until there are thresholds to interpret.
 */
export function stepState(key, ctx) {
  if (isDone(key, ctx)) return 'done'
  if (ctx.skipped?.[key]) return 'skipped'
  if ((key === 'results' || key === 'aep') && !ctx.analysis && key === 'results') {
    return 'blocked'
  }
  return 'ready'
}

/** Every step with its state, for the sidebar and the progress bar. */
export function flowState(ctx) {
  return STEPS.map((s, i) => ({ ...s, index: i + 1, state: stepState(s.key, ctx) }))
}

/** The next step worth visiting after `key` — skips over done and skipped. */
export function nextStep(key, ctx) {
  const i = STEPS.findIndex((s) => s.key === key)
  if (i === -1) return null
  for (const s of STEPS.slice(i + 1)) {
    const state = stepState(s.key, ctx)
    if (state === 'ready' || (s.key === 'results' && ctx.analysis)) return s
  }
  // Everything downstream is done or skipped: results is always the endpoint.
  return ctx.analysis ? STEP_BY_KEY.results : null
}

export function prevStep(key) {
  const i = STEPS.findIndex((s) => s.key === key)
  return i > 0 ? STEPS[i - 1] : null
}

/** Progress for the sidebar header: how much of the flow is settled. */
export function flowProgress(ctx) {
  const states = STEPS.map((s) => stepState(s.key, ctx))
  const settled = states.filter((s) => s === 'done' || s === 'skipped').length
  return {
    settled,
    total: STEPS.length,
    done: states.filter((s) => s === 'done').length,
    skipped: states.filter((s) => s === 'skipped').length,
  }
}

/** Reasons offered when a step is skipped. Free text is allowed too. */
export const SKIP_REASONS = [
  'Equipment not available',
  'Not clinically indicated',
  'Patient could not tolerate it',
  'Already done elsewhere',
  'Time — to be completed later',
]
