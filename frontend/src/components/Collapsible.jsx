// Disclosure sections — the one place the app decides what a reader sees first.
//
// THE PROBLEM THIS SOLVES. Every screen in this product grew by accretion:
// each clinically honest caveat, reference table and worked example earned its
// place on the page, and the sum of them buries the one line the clinician
// opened the page for. A results screen that prints the verdict, the evidence,
// the reference atlas and the methodology at the same visual weight has not
// told anybody anything — it has made them read everything to find the bit
// that mattered.
//
// So the rule throughout the app is: THE ANSWER IS ALWAYS VISIBLE, and
// everything that supports, qualifies or documents it is one click away.
// Collapsing is not hiding. Nothing is removed, the caveats still ship, and
// the summary line says what is inside so the reader can decide whether to
// open it.
//
// WHAT MUST NEVER BE COLLAPSED. Red flags, emergencies, validity warnings and
// anything that changes what happens to the patient today. A disclosure that
// can swallow a sudden sensorineural hearing loss is worse than a cluttered
// page. `tone="alert"` exists for sections that are allowed to be collapsible
// but must look urgent when they are; a true emergency should not use this
// component at all.
//
// LAZY CHILDREN. `children` is not mounted until the section is first opened,
// then stays mounted so its own state survives a close. The otoscopy reference
// atlas is 62 photographs: mounting it on page load cost a reader who never
// opened it every one of those requests.

import { useCallback, useId, useRef, useState } from 'react'

const TONES = {
  default: {
    card: 'border-slate-200/80 bg-white',
    title: 'text-slate-900',
    subtitle: 'text-slate-500',
    chevron: 'text-slate-400',
    hover: 'hover:bg-slate-50/70',
  },
  quiet: {
    card: 'border-slate-200/70 bg-slate-50/60',
    title: 'text-slate-700',
    subtitle: 'text-slate-500',
    chevron: 'text-slate-400',
    hover: 'hover:bg-slate-100/70',
  },
  alert: {
    card: 'border-amber-300 bg-amber-50/70',
    title: 'text-amber-900',
    subtitle: 'text-amber-800',
    chevron: 'text-amber-600',
    hover: 'hover:bg-amber-100/60',
  },
  danger: {
    card: 'border-rose-300 bg-rose-50/70',
    title: 'text-rose-900',
    subtitle: 'text-rose-800',
    chevron: 'text-rose-600',
    hover: 'hover:bg-rose-100/60',
  },
}

function Chevron({ open, className }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true"
      className={`h-4 w-4 shrink-0 transition-transform duration-150 ${
        open ? 'rotate-90' : ''} ${className}`}>
      <path d="M7 4l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/**
 * A collapsible card.
 *
 * @param title      the heading — say what is inside, not "More"
 * @param subtitle   one line of what the reader would learn by opening it
 * @param badge      short right-aligned marker (a count, "3 conflicts")
 * @param badgeTone  'default' | 'alert' | 'danger' | 'good'
 * @param defaultOpen  open on first render. Default false: the whole point.
 * @param tone       'default' | 'quiet' | 'alert' | 'danger'
 * @param as         heading level for the title, default h2
 * @param padded     false for children that manage their own padding
 */
export default function Collapsible({
  title,
  subtitle,
  badge,
  badgeTone = 'default',
  defaultOpen = false,
  tone = 'default',
  as: Heading = 'h2',
  padded = true,
  dataTour,
  children,
}) {
  const [open, setOpen] = useState(defaultOpen)
  // Once opened, keep the subtree mounted so anything the reader typed or
  // scrolled inside it survives collapsing the section again.
  const everOpened = useRef(defaultOpen)
  if (open) everOpened.current = true
  const panelId = useId()
  const t = TONES[tone] || TONES.default

  const badgeCls = {
    default: 'bg-slate-100 text-slate-600',
    alert: 'bg-amber-100 text-amber-800',
    danger: 'bg-rose-100 text-rose-700',
    good: 'bg-emerald-100 text-emerald-700',
  }[badgeTone] || 'bg-slate-100 text-slate-600'

  return (
    <section data-tour={dataTour}
      className={`overflow-hidden rounded-2xl border shadow-sm ${t.card}`}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        aria-expanded={open} aria-controls={panelId}
        className={`flex w-full items-start gap-2.5 px-5 py-3.5 text-left transition ${t.hover}`}>
        <Chevron open={open} className={`mt-0.5 ${t.chevron}`} />
        <span className="min-w-0 flex-1">
          <Heading className={`text-[14.5px] font-semibold leading-snug ${t.title}`}>
            {title}
          </Heading>
          {subtitle && (
            <span className={`mt-0.5 block text-[11.5px] leading-relaxed ${t.subtitle}`}>
              {subtitle}
            </span>
          )}
        </span>
        {badge != null && badge !== false && (
          <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide ${badgeCls}`}>
            {badge}
          </span>
        )}
      </button>
      {everOpened.current && (
        <div id={panelId} hidden={!open}
          className={padded ? 'border-t border-slate-200/70 px-5 pb-5 pt-4' : ''}>
          {children}
        </div>
      )}
    </section>
  )
}

/**
 * An inline disclosure, for a few lines inside a card that already has a
 * heading — a derived index, a formula, a methodology note. Renders as a small
 * text toggle rather than a card, so it does not compete with the card's own
 * title.
 *
 * `label` is what opening it reveals ("Show the rollover index"), never "More".
 */
export function Reveal({ label, hideLabel, defaultOpen = false, children, className = '' }) {
  const [open, setOpen] = useState(defaultOpen)
  const everOpened = useRef(defaultOpen)
  if (open) everOpened.current = true
  const panelId = useId()

  return (
    <div className={className}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        aria-expanded={open} aria-controls={panelId}
        className="inline-flex items-center gap-1 rounded text-[12px] font-medium text-teal-700 underline decoration-teal-300 underline-offset-2 transition hover:text-teal-800">
        <Chevron open={open} className="h-3.5 w-3.5 text-teal-600" />
        {open ? (hideLabel || label) : label}
      </button>
      {everOpened.current && (
        <div id={panelId} hidden={!open} className="mt-2">
          {children}
        </div>
      )}
    </div>
  )
}

/**
 * The counterpart to a collapsed page: one short paragraph, always visible,
 * that says what this screen is for. Replaces the three-sentence explanatory
 * block every page used to open with.
 */
export function PageIntro({ children }) {
  return (
    <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-slate-500">
      {children}
    </p>
  )
}

/**
 * A group of reference material at the foot of a page — the atlas, the source
 * documents, the normative tables. Visually quieter than a clinical card so
 * the eye skips it, and collapsed by default.
 */
export function ReferenceSection({ title, subtitle, children, badge, dataTour }) {
  return (
    <Collapsible title={title} subtitle={subtitle} badge={badge} tone="quiet"
      dataTour={dataTour}>
      {children}
    </Collapsible>
  )
}
