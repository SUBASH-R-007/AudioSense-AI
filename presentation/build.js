// AudioSense AI — pilot presentation deck.
//
// Palette is the product's own: the teal the app ships in, its amber warning
// tone, and slate for text. Swapping these into another deck would look wrong,
// which is the point.

const pptxgen = require('pptxgenjs')

const TEAL = '0D9488'   // the app's brand teal
const DEEP = '134E4A'   // dark teal — title and closing slides
const INK = '0F172A'    // slate-900, body text
const MUTE = '64748B'   // slate-500, captions
const PAPER = 'F8FAFC'  // slate-50, light slide ground
const LINE = 'E2E8F0'   // slate-200, card edges
const AMBER = 'F59E0B'  // the app's warning tone
const ROSE = 'E11D48'   // used only for the emergency/problem framing
const WHITE = 'FFFFFF'

const HEAD = 'Cambria'  // safe-list serif
const BODY = 'Calibri'  // safe-list sans

const W = 13.333
const H = 7.5

const pres = new pptxgen()
pres.layout = 'LAYOUT_WIDE'
pres.author = 'AudioSense AI'
pres.title = 'AudioSense AI — Pilot Review'

// A fresh object every call: pptxgenjs converts options to EMU in place.
const shadow = (blur = 12, opacity = 0.10) => ({
  type: 'outer', angle: 90, blur, offset: 2, color: '94A3B8', opacity,
})

/** Rounded card. Never an edge stripe — a tint and a soft shadow instead. */
function card(slide, x, y, w, h, fill = WHITE) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.10,
    fill: { color: fill }, line: { color: LINE, width: 1 },
    shadow: shadow(),
  })
}

/** The repeated motif: a numeral or glyph inside a filled circle. */
function bubble(slide, x, y, d, text, fillColor = TEAL, textColor = WHITE) {
  slide.addShape(pres.ShapeType.ellipse, {
    x, y, w: d, h: d, fill: { color: fillColor }, line: { color: fillColor },
  })
  slide.addText(text, {
    x, y, w: d, h: d, align: 'center', valign: 'middle',
    fontFace: BODY, fontSize: d > 0.5 ? 15 : 12, bold: true, color: textColor,
    margin: 0,
  })
}

/** A clearly-marked drop zone for artwork the user supplies. */
function imageSlot(slide, x, y, w, h, label, hint) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08,
    fill: { color: 'F1F5F9' },
    line: { color: '94A3B8', width: 1.5, dashType: 'dash' },
  })
  slide.addText(
    [
      { text: label, options: { fontSize: 13, bold: true, color: '475569', breakLine: true } },
      { text: hint, options: { fontSize: 10.5, color: MUTE } },
    ],
    { x: x + 0.15, y, w: w - 0.3, h, align: 'center', valign: 'middle',
      fontFace: BODY, margin: 0 },
  )
}

function slideTitle(slide, text, kicker) {
  if (kicker) {
    slide.addText(kicker.toUpperCase(), {
      x: 0.7, y: 0.52, w: 9, h: 0.28, fontFace: BODY, fontSize: 11.5,
      bold: true, color: TEAL, charSpacing: 2, margin: 0,
    })
  }
  slide.addText(text, {
    x: 0.7, y: kicker ? 0.82 : 0.62, w: 11.9, h: 0.78,
    fontFace: HEAD, fontSize: 34, bold: true, color: INK, margin: 0,
  })
}

// ===========================================================================
// 1 — Title
// ===========================================================================
{
  const s = pres.addSlide()
  s.background = { color: DEEP }

  // Quiet audiogram motif: a descending curve of dots, the shape of the
  // noise-notch case the product is built around.
  const pts = [[0, 0.10], [1, 0.16], [2, 0.30], [3, 0.46], [4, 0.86], [5, 0.40]]
  pts.forEach(([i, v]) => {
    s.addShape(pres.ShapeType.ellipse, {
      x: 8.55 + i * 0.72, y: 2.5 + v * 2.4, w: 0.20, h: 0.20,
      fill: { color: i === 4 ? AMBER : '2DD4BF' },
      line: { color: i === 4 ? AMBER : '2DD4BF' },
    })
  })
  s.addText('4 kHz notch', {
    x: 10.5, y: 5.05, w: 2.2, h: 0.3, fontFace: BODY, fontSize: 10,
    italic: true, color: '5EEAD4', align: 'center', margin: 0,
  })

  s.addText('AudioSense AI', {
    x: 0.85, y: 1.95, w: 8.0, h: 1.0,
    fontFace: HEAD, fontSize: 52, bold: true, color: WHITE, margin: 0,
  })
  s.addText('Automated Pure-Tone Audiometry Interpretation', {
    x: 0.85, y: 2.95, w: 7.6, h: 0.45,
    fontFace: BODY, fontSize: 19, color: '5EEAD4', margin: 0,
  })
  s.addText(
    'A clinical decision-support platform for hearing assessment — offline-first, '
    + 'guideline-based, and built for high-volume screening.',
    { x: 0.85, y: 3.5, w: 7.3, h: 0.8, fontFace: BODY, fontSize: 13.5,
      color: 'CBD5E1', lineSpacing: 20, margin: 0 },
  )

  s.addText('PILOT REVIEW  ·  NIEPMD  ×  RAJALAKSHMI ENGINEERING COLLEGE', {
    x: 0.85, y: 4.45, w: 8.5, h: 0.3, fontFace: BODY, fontSize: 11,
    bold: true, color: '99F6E4', charSpacing: 1.2, margin: 0,
  })

  // Team block
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.85, y: 5.05, w: 7.3, h: 1.5, rectRadius: 0.10,
    fill: { color: '0F3E3A' }, line: { color: '155E56', width: 1 },
  })
  s.addText('PROJECT TEAM', {
    x: 1.1, y: 5.2, w: 3, h: 0.25, fontFace: BODY, fontSize: 9.5,
    bold: true, color: '5EEAD4', charSpacing: 1.5, margin: 0,
  })
  s.addText(
    [
      { text: 'Subash R', options: { bold: true, color: WHITE, breakLine: true } },
      { text: '[ Team member 2 ]', options: { color: '94A3B8', breakLine: true } },
      { text: '[ Team member 3 ]', options: { color: '94A3B8' } },
    ],
    { x: 1.1, y: 5.5, w: 3.2, h: 0.95, fontFace: BODY, fontSize: 12.5,
      lineSpacing: 17, margin: 0 },
  )
  s.addText(
    [
      { text: 'Guide / Mentor', options: { fontSize: 9.5, color: '5EEAD4', bold: true, breakLine: true } },
      { text: '[ Faculty guide name ]', options: { fontSize: 12.5, color: WHITE, breakLine: true } },
      { text: '[ Department ]', options: { fontSize: 11, color: '94A3B8' } },
    ],
    { x: 4.8, y: 5.2, w: 3.1, h: 1.2, fontFace: BODY, lineSpacing: 17, margin: 0 },
  )

  imageSlot(s, 9.1, 5.6, 1.6, 0.95, 'NIEPMD logo', '')
  imageSlot(s, 10.95, 5.6, 1.75, 0.95, 'REC logo', '')

  s.addNotes(
    'AudioSense AI interprets pure-tone audiograms automatically. '
    + 'It is live and in pilot at https://audio-sense-ai.vercel.app. '
    + 'Fill in the remaining team member and guide names before presenting.',
  )
}

// ===========================================================================
// 2 — Problem statement
// ===========================================================================
{
  const s = pres.addSlide()
  s.background = { color: PAPER }
  slideTitle(s, 'Interpretation is the bottleneck — not the test', 'The problem')

  const stats = [
    ['1 in 5', 'people live with hearing loss\nworldwide (WHO, 2021)', ROSE],
    ['Minutes', 'of expert time to interpret\none audiogram by hand', AMBER],
    ['< 1 second', 'AudioSense, measured across\nthe bundled demo cases', TEAL],
  ]
  stats.forEach(([big, small, col], i) => {
    const x = 0.7 + i * 4.07
    card(s, x, 1.75, 3.75, 1.85)
    s.addText(big, {
      x: x + 0.28, y: 1.95, w: 3.3, h: 0.62, fontFace: HEAD, fontSize: 32,
      bold: true, color: col, margin: 0,
    })
    s.addText(small, {
      x: x + 0.28, y: 2.62, w: 3.2, h: 0.8, fontFace: BODY, fontSize: 12.5,
      color: MUTE, lineSpacing: 16, margin: 0,
    })
  })

  card(s, 0.7, 3.9, 7.7, 2.85)
  s.addText('Why this matters clinically', {
    x: 1.0, y: 4.12, w: 6.9, h: 0.35, fontFace: HEAD, fontSize: 19,
    bold: true, color: INK, margin: 0,
  })
  const points = [
    ['Expertise-dependent', 'The same audiogram is graded differently by different readers. Consistency is not guaranteed.'],
    ['Time-consuming', 'Degree, type, configuration, disability percentage and red flags are each computed by hand.'],
    ['Delays diagnosis', 'In camps and high-volume clinics, reports queue for days behind a scarce specialist.'],
    ['Emergencies get missed', 'Sudden sensorineural loss is steroid-treatable within days — and reads like an ordinary loss.'],
  ]
  points.forEach(([h, d], i) => {
    const y = 4.6 + i * 0.53
    bubble(s, 1.0, y + 0.02, 0.26, String(i + 1), TEAL, WHITE)
    s.addText(
      [
        { text: h + ' — ', options: { bold: true, color: INK } },
        { text: d, options: { color: MUTE } },
      ],
      { x: 1.38, y, w: 6.75, h: 0.45, fontFace: BODY, fontSize: 11.5, margin: 0 },
    )
  })

  card(s, 8.75, 3.9, 3.85, 2.85, DEEP)
  s.addText('The one that must not be missed', {
    x: 9.05, y: 4.12, w: 3.25, h: 0.6, fontFace: HEAD, fontSize: 16,
    bold: true, color: WHITE, margin: 0,
  })
  s.addText(
    'A sudden asymmetric loss is a medical emergency with a treatment window '
    + 'of days. Most audiogram tools report it as "moderate sensorineural loss" '
    + 'and book a hearing-aid fitting.',
    { x: 9.05, y: 4.78, w: 3.25, h: 1.35, fontFace: BODY, fontSize: 12,
      color: 'CBD5E1', lineSpacing: 17, margin: 0 },
  )
  s.addText('AudioSense flags it above everything else.', {
    x: 9.05, y: 6.15, w: 3.25, h: 0.45, fontFace: BODY, fontSize: 11.5,
    bold: true, italic: true, color: '5EEAD4', margin: 0,
  })

  s.addNotes('The brief names three problems: time-consuming, expertise-dependent, '
    + 'delays diagnosis in high-volume settings. The fourth point — missed '
    + 'emergencies — is the one that justifies a decision-support tool rather '
    + 'than a calculator.')
}

// ===========================================================================
// 3 — Solution / technical approach
// ===========================================================================
{
  const s = pres.addSlide()
  s.background = { color: PAPER }
  slideTitle(s, 'Rules first, ML second — every claim auditable',
    'Solution · technical approach')

  // Pipeline
  const steps = [
    ['Capture', 'Type, photograph or\nmeasure in-browser'],
    ['Rules engine', 'WHO 2021 grade, type,\nconfiguration, RPwD %'],
    ['Cross-check', 'Immittance, OAE, speech,\nforks, history reconciled'],
    ['Decide', 'Red flags, masking review,\nnext test to run'],
    ['Explain', 'Report, counselling sheet,\npatient anatomy video'],
  ]
  steps.forEach(([t, d], i) => {
    const x = 0.7 + i * 2.44
    card(s, x, 1.72, 2.2, 1.5)
    bubble(s, x + 0.18, 1.9, 0.34, String(i + 1))
    s.addText(t, {
      x: x + 0.6, y: 1.92, w: 1.5, h: 0.3, fontFace: BODY, fontSize: 13,
      bold: true, color: INK, margin: 0,
    })
    s.addText(d, {
      x: x + 0.18, y: 2.32, w: 1.88, h: 0.8, fontFace: BODY, fontSize: 10,
      color: MUTE, lineSpacing: 13, margin: 0,
    })
    if (i < steps.length - 1) {
      s.addText('▶', {
        x: x + 2.2, y: 2.25, w: 0.24, h: 0.3, fontFace: BODY, fontSize: 11,
        color: '94A3B8', align: 'center', margin: 0,
      })
    }
  })

  // Left: principles
  card(s, 0.7, 3.5, 6.15, 3.25)
  s.addText('Design principles', {
    x: 1.0, y: 3.72, w: 5.5, h: 0.35, fontFace: HEAD, fontSize: 19,
    bold: true, color: INK, margin: 0,
  })
  const princ = [
    ['Guidelines, not guesses', 'WHO 2021 grading and the RPwD Act are deterministic — validated by conformance, κ = 1.0 against expert labels.'],
    ['ML is advisory only', 'The classifier ranks and flags; it never sets the diagnosis. Atypical inputs route to a human.'],
    ['Findings cross-check each other', 'Immittance, emissions, speech and forks are reconciled against the audiogram. Conflicts sort first.'],
    ['Offline-first', 'No API key and no network required. An LLM key only improves the narrative.'],
  ]
  princ.forEach(([h, d], i) => {
    const y = 4.24 + i * 0.62
    bubble(s, 1.0, y + 0.03, 0.24, '✓', TEAL, WHITE)
    s.addText(
      [
        { text: h + '  ', options: { bold: true, color: INK, breakLine: true } },
        { text: d, options: { color: MUTE, fontSize: 10.5 } },
      ],
      { x: 1.35, y, w: 5.35, h: 0.58, fontFace: BODY, fontSize: 11,
        lineSpacing: 12.5, margin: 0 },
    )
  })

  // Right: stack + scale
  card(s, 7.1, 3.5, 5.5, 3.25, DEEP)
  s.addText('Built and measured', {
    x: 7.4, y: 3.72, w: 4.9, h: 0.35, fontFace: HEAD, fontSize: 19,
    bold: true, color: WHITE, margin: 0,
  })

  const metrics = [
    ['2,093', 'automated tests, all passing'],
    ['74', 'API endpoints · 22 routers'],
    ['33.8k', 'lines of code (BE + FE)'],
    ['< 1 s', 'per audiogram interpretation'],
  ]
  metrics.forEach(([v, l], i) => {
    const x = 7.4 + (i % 2) * 2.55
    const y = 4.22 + Math.floor(i / 2) * 0.92
    s.addText(v, {
      x, y, w: 2.4, h: 0.42, fontFace: HEAD, fontSize: 25, bold: true,
      color: '5EEAD4', margin: 0,
    })
    s.addText(l, {
      x, y: y + 0.42, w: 2.4, h: 0.4, fontFace: BODY, fontSize: 10,
      color: 'CBD5E1', lineSpacing: 12, margin: 0,
    })
  })

  s.addText('FastAPI · scikit-learn · OpenCV · React + Vite · SQLite · Docker', {
    x: 7.4, y: 6.15, w: 4.9, h: 0.4, fontFace: BODY, fontSize: 10.5,
    color: '99F6E4', italic: true, margin: 0,
  })

  s.addNotes('The key architectural claim: clinical decisions are deterministic '
    + 'and cite their guideline, so they are auditable. Machine learning is '
    + 'confined to pattern suggestion and image retrieval, where being wrong '
    + 'is recoverable.')
}

// ===========================================================================
// 4 — What is to be developed
// ===========================================================================
{
  const s = pres.addSlide()
  s.background = { color: PAPER }
  slideTitle(s, 'What we build next — and why each one matters',
    'Development roadmap')

  const items = [
    ['Otoscopy model — larger dataset',
     '62 images from 22 source photographs. Measured holding out every view of a source photograph: 27% top-1 (17/62, 95% CI 15–42%), 52% top-3 (chance 12.5%). Three classes — marginal perforation, retraction and mass — score 0% recall.',
     'Train on 2,000+ clinician-labelled images across the 8 patterns; target > 85% top-3 and no class below 50% recall.'],
    ['Clinical validation study',
     'Rules validated by conformance (κ = 1.0). The ML pattern classifier is validated on a small bundled labelled set.',
     'Prospective study against audiologist ground truth at NIEPMD; publish sensitivity and specificity per finding.'],
    ['Role-based access & audit trail',
     'Every signed-in user can see every patient record. No roles, no per-action audit log.',
     'Clinician / admin roles, per-clinic record ownership, and an append-only audit trail for DPDP compliance.'],
    ['Tamil-script clinical reports',
     'The counselling sheet reads and speaks in 6 languages; the PDF cannot embed Tamil script.',
     'Bundle Noto fonts so the printed report matches the on-screen sheet in all six languages.'],
  ]

  items.forEach(([title, now, next], i) => {
    const y = 1.78 + i * 1.22
    card(s, 0.7, y, 11.9, 1.10)
    bubble(s, 0.95, y + 0.42, 0.32, String(i + 1))
    s.addText(title, {
      x: 1.42, y: y + 0.16, w: 3.7, h: 0.55, fontFace: BODY, fontSize: 13.5,
      bold: true, color: INK, valign: 'middle', margin: 0,
    })
    s.addText(
      [{ text: 'NOW   ', options: { bold: true, color: AMBER, fontSize: 9 } },
       { text: now, options: { color: MUTE, fontSize: 10.5 } }],
      { x: 5.25, y: y + 0.14, w: 3.55, h: 0.9, fontFace: BODY,
        lineSpacing: 13, valign: 'middle', margin: 0 },
    )
    s.addText(
      [{ text: 'NEXT   ', options: { bold: true, color: TEAL, fontSize: 9 } },
       { text: next, options: { color: INK, fontSize: 10.5 } }],
      { x: 8.95, y: y + 0.14, w: 3.45, h: 0.9, fontFace: BODY,
        lineSpacing: 13, valign: 'middle', margin: 0 },
    )
  })

  s.addText(
    'The otoscopy accuracy is printed inside the product itself, on the page that uses it — '
    + 'the tool states its own limits rather than hiding them.',
    { x: 0.7, y: 6.68, w: 11.9, h: 0.32, fontFace: BODY, fontSize: 11,
      italic: true, color: MUTE, margin: 0 },
  )

  s.addNotes('Every "NOW" figure here is measured from the shipped model card, '
    + 'not estimated. Retraction scoring 0% recall is the clearest single '
    + 'argument for a larger dataset.')
}

// ===========================================================================
// 5 — Deliverables
// ===========================================================================
{
  const s = pres.addSlide()
  s.background = { color: PAPER }
  slideTitle(s, 'Live and in pilot today', 'Deliverables')

  imageSlot(s, 0.7, 1.72, 7.0, 3.95, 'Website screenshot',
    'Results dashboard — paste screenshot here')

  card(s, 7.95, 1.72, 4.65, 1.95, DEEP)
  s.addText('PILOT TESTING URL', {
    x: 8.25, y: 1.92, w: 4.05, h: 0.25, fontFace: BODY, fontSize: 9.5,
    bold: true, color: '5EEAD4', charSpacing: 1.5, margin: 0,
  })
  s.addText('audio-sense-ai\n.vercel.app', {
    x: 8.25, y: 2.2, w: 4.05, h: 0.85, fontFace: HEAD, fontSize: 21,
    bold: true, color: WHITE, lineSpacing: 24, margin: 0,
    hyperlink: { url: 'https://audio-sense-ai.vercel.app' },
  })
  s.addText('Access is credential-protected — no patient data is public.', {
    x: 8.25, y: 3.08, w: 4.05, h: 0.45, fontFace: BODY, fontSize: 10.5,
    color: 'CBD5E1', lineSpacing: 13, margin: 0,
  })

  imageSlot(s, 7.95, 3.9, 2.15, 1.77, 'QR code', 'scan to open')

  card(s, 10.35, 3.9, 2.25, 1.77)
  s.addText(
    [
      { text: 'Deployed on', options: { fontSize: 9.5, color: MUTE, breakLine: true } },
      { text: 'Railway', options: { fontSize: 14, bold: true, color: INK, breakLine: true } },
      { text: 'backend + volume', options: { fontSize: 9.5, color: MUTE, breakLine: true } },
      { text: 'Vercel', options: { fontSize: 14, bold: true, color: INK, breakLine: true } },
      { text: 'frontend (CDN)', options: { fontSize: 9.5, color: MUTE } },
    ],
    { x: 10.6, y: 4.05, w: 1.85, h: 1.5, fontFace: BODY, lineSpacing: 14,
      valign: 'middle', margin: 0 },
  )

  // What ships
  const ships = [
    ['Clinical report', 'PDF with a verification hash and QR'],
    ['Patient counselling', '6 languages, read aloud, or scanned to phone'],
    ['Anatomy animations', '11 clips — the mechanism, shown to the patient'],
    ['Batch worklist', 'CSV of a whole camp, triaged by priority'],
  ]
  ships.forEach(([t, d], i) => {
    const x = 0.7 + i * 3.02
    card(s, x, 5.9, 2.82, 1.05)
    bubble(s, x + 0.2, 6.12, 0.26, '●', TEAL, WHITE)
    s.addText(t, {
      x: x + 0.55, y: 6.06, w: 2.15, h: 0.3, fontFace: BODY, fontSize: 11.5,
      bold: true, color: INK, margin: 0,
    })
    s.addText(d, {
      x: x + 0.2, y: 6.4, w: 2.5, h: 0.45, fontFace: BODY, fontSize: 9.5,
      color: MUTE, lineSpacing: 11, margin: 0,
    })
  })

  s.addNotes('Live URL: https://audio-sense-ai.vercel.app — protected by a '
    + 'username and password, so nothing is publicly reachable. '
    + 'Paste the dashboard screenshot and the QR code into the marked slots.')
}

// ===========================================================================
// 6 — Requirements and budget
// ===========================================================================
{
  const s = pres.addSlide()
  s.background = { color: PAPER }
  slideTitle(s, 'What development and deployment require', 'Requirements · budget')

  const rows = [
    ['Backend hosting', 'Always-on server with a persistent volume for patient records', 'Railway Hobby', '₹5,000 / yr'],
    ['Frontend hosting', 'Global CDN for the clinician-facing app', 'Vercel Pro *', '₹21,000 / yr'],
    ['Domain + TLS', 'A clinic-owned address; HTTPS is required for microphone access', 'Registrar', '₹1,500 / yr'],
    ['Otoscopy dataset', '2,000+ otoscope images, labelled by a clinician — the single largest cost', 'Annotation effort', '₹1.5–3.0 L'],
    ['Clinical validation', 'Prospective study against audiologist ground truth', 'NIEPMD collaboration', 'In kind'],
    ['LLM credits (optional)', 'Narrative report generation; the app works fully without it', 'Any provider', '₹5,000 / yr'],
  ]

  s.addTable(
    [
      [
        { text: 'Requirement', options: { bold: true, color: WHITE, fill: { color: DEEP } } },
        { text: 'Why it is needed', options: { bold: true, color: WHITE, fill: { color: DEEP } } },
        { text: 'Provider', options: { bold: true, color: WHITE, fill: { color: DEEP } } },
        { text: 'Estimated cost', options: { bold: true, color: WHITE, fill: { color: DEEP }, align: 'right' } },
      ],
      ...rows.map(([a, b, c, d], i) => {
        const bg = i % 2 ? 'F1F5F9' : WHITE
        return [
          { text: a, options: { bold: true, color: INK, fill: { color: bg } } },
          { text: b, options: { color: MUTE, fill: { color: bg } } },
          { text: c, options: { color: MUTE, fill: { color: bg } } },
          { text: d, options: { bold: true, color: TEAL, fill: { color: bg }, align: 'right' } },
        ]
      }),
    ],
    {
      x: 0.7, y: 1.75, w: 11.9, colW: [2.5, 5.3, 2.0, 2.1],
      rowH: 0.5, fontFace: BODY, fontSize: 11, valign: 'middle',
      border: { type: 'solid', color: LINE, pt: 1 },
      margin: [4, 8, 4, 8],
    },
  )

  card(s, 0.7, 5.35, 5.85, 1.6)
  s.addText('Recurring infrastructure', {
    x: 1.0, y: 5.52, w: 5.2, h: 0.3, fontFace: BODY, fontSize: 11,
    bold: true, color: MUTE, margin: 0,
  })
  s.addText('₹32,500', {
    x: 1.0, y: 5.82, w: 2.5, h: 0.6, fontFace: HEAD, fontSize: 32,
    bold: true, color: INK, margin: 0,
  })
  s.addText('per year, all subscriptions', {
    x: 1.0, y: 6.44, w: 2.5, h: 0.3, fontFace: BODY, fontSize: 11,
    color: MUTE, margin: 0,
  })
  s.addText(
    [{ text: '* ', options: { color: AMBER, bold: true } },
     { text: 'A free path exists — Oracle Cloud Always Free reduces hosting to ₹0, at the cost of self-administration.',
       options: { color: MUTE } }],
    { x: 3.65, y: 5.72, w: 2.7, h: 1.05, fontFace: BODY, fontSize: 9.5,
      lineSpacing: 12, valign: 'middle', margin: 0 },
  )

  card(s, 6.8, 5.35, 5.8, 1.6, DEEP)
  s.addText('One-time development investment', {
    x: 7.1, y: 5.52, w: 5.2, h: 0.3, fontFace: BODY, fontSize: 11,
    bold: true, color: '5EEAD4', margin: 0,
  })
  s.addText('₹1.5 – 3.0 L', {
    x: 7.1, y: 5.82, w: 3.4, h: 0.6, fontFace: HEAD, fontSize: 32,
    bold: true, color: WHITE, margin: 0,
  })
  s.addText('dataset annotation — buys the accuracy gain', {
    x: 7.1, y: 6.44, w: 5.2, h: 0.3, fontFace: BODY, fontSize: 11,
    color: 'CBD5E1', margin: 0,
  })

  s.addNotes('Costs are estimates in Indian rupees at current published list '
    + 'prices and should be re-checked before commitment. The dataset line is '
    + 'the one that actually changes clinical performance; the hosting lines '
    + 'are small and can be reduced to zero on Oracle Always Free.')
}

// ===========================================================================
// 7 — Timeline
// ===========================================================================
{
  const s = pres.addSlide()
  s.background = { color: PAPER }
  slideTitle(s, 'Module status', 'Timeline')

  const DONE = { label: 'Delivered', bg: 'D1FAE5', fg: '065F46' }
  const PILOT = { label: 'In pilot', bg: 'CCFBF1', fg: '115E59' }
  const PROG = { label: 'In progress', bg: 'FEF3C7', fg: '92400E' }
  const PLAN = { label: 'Planned', bg: 'E2E8F0', fg: '475569' }

  const mods = [
    ['Pure-tone rules engine — WHO 2021 grade, type, configuration', DONE],
    ['RPwD Act 2016 disability computation, with formula shown', DONE],
    ['ML pattern classification + out-of-distribution flagging', DONE],
    ['Red-flag safety review and masking adequacy check', DONE],
    ['Immittance, otoacoustic emissions and speech audiometry', DONE],
    ['Tuning-fork battery and evoked potentials (ABR / MLR / LLR)', DONE],
    ['Snap-to-digitize — paper audiogram photo to thresholds', DONE],
    ['Patient counselling in six languages + QR handout', DONE],
    ['Ear-anatomy animations for patient explanation', DONE],
    ['Authentication, session control and patient records', PILOT],
    ['Deployment — Railway + Vercel with persistent storage', PILOT],
    ['Otoscopy classifier — retrain on a larger labelled dataset', PROG],
    ['Prospective clinical validation at NIEPMD', PLAN],
    ['Role-based access, per-clinic ownership and audit trail', PLAN],
  ]

  const head = [
    { text: 'S.No', options: { bold: true, color: WHITE, fill: { color: DEEP }, align: 'center' } },
    { text: 'Module', options: { bold: true, color: WHITE, fill: { color: DEEP } } },
    { text: 'Status', options: { bold: true, color: WHITE, fill: { color: DEEP }, align: 'center' } },
  ]
  const body = mods.map(([name, st], i) => {
    const bg = i % 2 ? 'F1F5F9' : WHITE
    return [
      { text: String(i + 1), options: { color: MUTE, fill: { color: bg }, align: 'center' } },
      { text: name, options: { color: INK, fill: { color: bg } } },
      { text: st.label, options: { bold: true, color: st.fg, fill: { color: st.bg }, align: 'center' } },
    ]
  })

  s.addTable([head, ...body], {
    x: 0.7, y: 1.72, w: 11.9, colW: [0.9, 8.6, 2.4],
    rowH: 0.325, fontFace: BODY, fontSize: 11, valign: 'middle',
    border: { type: 'solid', color: LINE, pt: 1 },
    margin: [3, 8, 3, 8],
  })

  s.addText(
    '9 of 14 modules delivered and running in the pilot build · 2,093 automated tests passing',
    { x: 0.7, y: 6.68, w: 11.9, h: 0.30, fontFace: BODY, fontSize: 11.5,
      bold: true, color: TEAL, margin: 0 },
  )

  s.addNotes('Delivered means built, tested and running in the deployed pilot. '
    + 'In pilot means shipped but still being exercised with real users. '
    + 'The two planned items are the ones that gate multi-clinic use.')
}

// ===========================================================================
// 8 — Thank you
// ===========================================================================
{
  const s = pres.addSlide()
  s.background = { color: DEEP }

  s.addText('Thank you', {
    x: 0.9, y: 2.35, w: 7.5, h: 1.05, fontFace: HEAD, fontSize: 50,
    bold: true, color: WHITE, margin: 0,
  })
  s.addText('Questions, and a live walkthrough on request.', {
    x: 0.9, y: 3.42, w: 7.5, h: 0.45, fontFace: BODY, fontSize: 17,
    color: '5EEAD4', margin: 0,
  })

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.9, y: 4.25, w: 6.4, h: 1.25, rectRadius: 0.10,
    fill: { color: '0F3E3A' }, line: { color: '155E56', width: 1 },
  })
  s.addText('TRY THE PILOT', {
    x: 1.2, y: 4.42, w: 4, h: 0.25, fontFace: BODY, fontSize: 9.5,
    bold: true, color: '5EEAD4', charSpacing: 1.5, margin: 0,
  })
  s.addText('audio-sense-ai.vercel.app', {
    x: 1.2, y: 4.7, w: 5.8, h: 0.5, fontFace: HEAD, fontSize: 23,
    bold: true, color: WHITE, margin: 0,
    hyperlink: { url: 'https://audio-sense-ai.vercel.app' },
  })

  imageSlot(s, 7.9, 4.05, 1.9, 1.65, 'QR code', '')

  s.addText('AI-assisted interpretation · final diagnosis requires a qualified audiologist',
    { x: 0.9, y: 6.35, w: 8.5, h: 0.3, fontFace: BODY, fontSize: 11,
      italic: true, color: '94A3B8', margin: 0 })

  imageSlot(s, 10.1, 4.05, 1.3, 0.85, 'NIEPMD', '')
  imageSlot(s, 11.55, 4.05, 1.35, 0.85, 'REC', '')

  s.addNotes('Close on the live URL. Offer to run a demo case end to end: '
    + 'load the sudden asymmetric loss demo and show the emergency banner.')
}

pres.writeFile({ fileName: 'AudioSense-AI-Pilot-Review.pptx' })
  .then((f) => console.log('written:', f))
