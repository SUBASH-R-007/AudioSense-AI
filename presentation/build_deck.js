// AudioSense AI — pilot review deck.
//
// Re-run after dropping assets/niepmd_logo.png and assets/dashboard.png in:
//   node presentation/build_deck.js
// Missing images render as a labelled placeholder rather than breaking the build.

const fs = require('fs')
const path = require('path')
const pptxgen = require('pptxgenjs')

const DIR = path.join(__dirname, 'assets')
const A = (n) => path.join(DIR, n)
const has = (n) => fs.existsSync(A(n))

// REC purple + the product's own teal. Gold is the REC torch.
const PURPLE = '4A1D73'
const PURPLE_DK = '2E1049'
const TEAL = '0D9488'
const TEAL_LT = 'E6F4F2'
const GOLD = 'F2A900'
const INK = '1E293B'
const BODY = '475569'
const MUTED = '94A3B8'
const LINE = 'E2E8F0'
const WHITE = 'FFFFFF'

const HEAD = 'Cambria'
const TEXT = 'Calibri'

const pres = new pptxgen()
pres.layout = 'LAYOUT_WIDE'          // 13.3 x 7.5
pres.author = 'Kutty Koncepts'
pres.title = 'AudioSense AI — Pilot Review'
const W = 13.333, H = 7.5

// ---------------------------------------------------------------- helpers --

function darkSlide () {
  const s = pres.addSlide()
  s.background = { color: PURPLE_DK }
  if (has('bg_purple.png')) {
    s.addImage({ path: A('bg_purple.png'), x: 0, y: 0, w: W, h: H })
  }
  return s
}

function lightSlide (title, kicker) {
  const s = pres.addSlide()
  s.background = { color: WHITE }
  if (kicker) {
    s.addText(kicker.toUpperCase(), {
      x: 0.6, y: 0.5, w: 8, h: 0.26, margin: 0,
      fontFace: TEXT, fontSize: 11, bold: true, color: TEAL, charSpacing: 2,
    })
  }
  s.addText(title, {
    x: 0.6, y: 0.78, w: 11.2, h: 0.62, margin: 0,
    fontFace: HEAD, fontSize: 32, bold: true, color: INK,
  })
  return s
}

// One motif, repeated: soft rounded card, no edge stripes.
function card (s, { x, y, w, h, fill = WHITE, line = LINE }) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.09,
    fill: { color: fill },
    line: { color: line, width: 1 },
    shadow: { type: 'outer', color: '94A3B8', blur: 10, offset: 2, angle: 90, opacity: 0.16 },
  })
}

// The second motif: a small filled circle holding a glyph.
function bead (s, { x, y, ch, fill = TEAL, color = WHITE, d = 0.4, size = 15 }) {
  s.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color }, line: { color: fill, width: 0 } })
  s.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color: fill } })
  s.addText(ch, {
    x, y, w: d, h: d, margin: 0, align: 'center', valign: 'middle',
    fontFace: TEXT, fontSize: size, bold: true, color,
  })
}

function picture (s, { file, x, y, w, h, label }) {
  if (has(file)) {
    s.addImage({ path: A(file), x, y, w, h, sizing: { type: 'contain', w, h } })
    return true
  }
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08,
    fill: { color: 'F8FAFC' }, line: { color: TEAL, width: 1, dashType: 'dash' },
  })
  s.addText(`${label}\n\nDrop  presentation/assets/${file}\nthen re-run build_deck.js`, {
    x, y, w, h, margin: 0, align: 'center', valign: 'middle',
    fontFace: TEXT, fontSize: 11, color: TEAL, lineSpacing: 16,
  })
  return false
}

function footer (s, n) {
  s.addText('AudioSense AI  ·  Kutty Koncepts  ·  REC × NIEPMD', {
    x: 0.6, y: H - 0.46, w: 8, h: 0.26, margin: 0,
    fontFace: TEXT, fontSize: 9, color: MUTED,
  })
  s.addText(String(n), {
    x: W - 1.0, y: H - 0.46, w: 0.4, h: 0.26, margin: 0, align: 'right',
    fontFace: TEXT, fontSize: 9, color: MUTED,
  })
}

// ============================================================ 1 · TITLE ====
{
  const s = darkSlide()

  if (has('rec_logo.png')) s.addImage({ path: A('rec_logo.png'), x: 0.6, y: 0.5, w: 1.9, h: 0.94, sizing: { type: 'contain', w: 1.9, h: 0.94 } })
  picture(s, { file: 'niepmd_logo.png', x: 2.75, y: 0.5, w: 0.95, h: 0.94, label: 'NIEPMD' })

  s.addText('PROBLEM STATEMENT 8', {
    x: 0.6, y: 2.05, w: 8, h: 0.28, margin: 0,
    fontFace: TEXT, fontSize: 12, bold: true, color: GOLD, charSpacing: 3,
  })
  s.addText('AudioSense AI', {
    x: 0.6, y: 2.42, w: 9.2, h: 1.0, margin: 0,
    fontFace: HEAD, fontSize: 52, bold: true, color: WHITE,
  })
  s.addText('AI-assisted Pure Tone Audiometry interpretation — offline-first,\nclinically rigorous, and running in pilot today.', {
    x: 0.62, y: 3.45, w: 8.6, h: 0.8, margin: 0,
    fontFace: TEXT, fontSize: 16, color: 'D9CBE9', lineSpacing: 24,
  })

  const stats = [
    ['2,093', 'automated tests'],
    ['~670 ms', 'full interpretation'],
    ['6', 'counselling languages'],
    ['0', 'API keys required'],
  ]
  stats.forEach(([big, small], i) => {
    const x = 0.6 + i * 2.3
    s.addText(big, { x, y: 4.62, w: 2.1, h: 0.46, margin: 0, fontFace: HEAD, fontSize: 26, bold: true, color: GOLD })
    s.addText(small, { x, y: 5.06, w: 2.1, h: 0.3, margin: 0, fontFace: TEXT, fontSize: 11, color: 'BFAFD4' })
  })

  card(s, { x: 9.5, y: 2.35, w: 3.2, h: 3.15, fill: 'FFFFFF', line: 'FFFFFF' })
  s.addText('TEAM  ·  KUTTY KONCEPTS', {
    x: 9.75, y: 2.58, w: 2.8, h: 0.26, margin: 0,
    fontFace: TEXT, fontSize: 10, bold: true, color: TEAL, charSpacing: 1.5,
  })
  const team = ['Trishanth G', 'Subash R', 'Vaishnavi Thiruvengadam', 'Varsha S']
  team.forEach((m, i) => {
    s.addText(m, {
      x: 9.75, y: 2.98 + i * 0.42, w: 2.8, h: 0.34, margin: 0,
      fontFace: TEXT, fontSize: 13, bold: true, color: INK,
    })
  })
  s.addText('Rajalakshmi Engineering College, Chennai\nIn collaboration with NIEPMD', {
    x: 9.75, y: 4.76, w: 2.8, h: 0.62, margin: 0,
    fontFace: TEXT, fontSize: 10.5, color: BODY, lineSpacing: 15,
  })

  s.addText('audio-sense-ai.vercel.app', {
    x: 0.6, y: H - 0.92, w: 6, h: 0.3, margin: 0,
    fontFace: TEXT, fontSize: 12, bold: true, color: WHITE,
  })
  s.addNotes('Problem Statement 8. Team Kutty Koncepts, Rajalakshmi Engineering College, with NIEPMD. The platform is already deployed and in pilot.')
}

// ========================================================== 2 · PROBLEM ====
{
  const s = lightSlide('Interpretation is the bottleneck — and so is the queue', '01 · The problem')

  card(s, { x: 0.6, y: 1.62, w: 3.9, h: 2.0, fill: PURPLE, line: PURPLE })
  s.addText('1 : 500,000', { x: 0.9, y: 1.95, w: 3.3, h: 0.7, margin: 0, fontFace: HEAD, fontSize: 40, bold: true, color: GOLD })
  s.addText('audiologists to people in India. One screening camp produces hundreds of audiograms in a single day.', {
    x: 0.9, y: 2.68, w: 3.3, h: 0.8, margin: 0, fontFace: TEXT, fontSize: 12, color: 'E5DAF2', lineSpacing: 16,
  })

  const problems = [
    ['1', 'Slow by construction',
      'Classify the pattern, grade degree and type, compute the statutory disability percentage, write the report — every case, by hand.'],
    ['2', 'Dependent on one scarce specialist',
      'Diagnosis, hearing-aid fitting and rehabilitation all wait on the same person being in the room.'],
    ['3', 'Order is the real risk',
      'Two hundred audiograms look alike in a folder. The one with sudden asymmetric loss — a steroid emergency measured in days — is not marked.'],
  ]
  problems.forEach(([n, head, bodyText], i) => {
    const y = 1.62 + i * 1.32
    card(s, { x: 4.75, y, w: 7.95, h: 1.16 })
    bead(s, { x: 5.0, y: y + 0.36, ch: n, fill: TEAL })
    s.addText(head, { x: 5.58, y: y + 0.2, w: 6.9, h: 0.3, margin: 0, fontFace: TEXT, fontSize: 14.5, bold: true, color: INK })
    s.addText(bodyText, { x: 5.58, y: y + 0.52, w: 6.95, h: 0.56, margin: 0, fontFace: TEXT, fontSize: 11.5, color: BODY, lineSpacing: 15 })
  })

  card(s, { x: 0.6, y: 3.78, w: 3.9, h: 1.72, fill: TEAL_LT, line: 'CCE7E3' })
  s.addText('At NIEPMD', { x: 0.9, y: 3.98, w: 3.3, h: 0.28, margin: 0, fontFace: TEXT, fontSize: 11, bold: true, color: TEAL, charSpacing: 1 })
  s.addText('Assessment feeds disability certification and rehabilitation planning, so consistency between assessors matters as much as speed.', {
    x: 0.9, y: 4.3, w: 3.3, h: 1.0, margin: 0, fontFace: TEXT, fontSize: 11.5, color: '14685F', lineSpacing: 16,
  })
  footer(s, 2)
  s.addNotes('The bottleneck is not measuring hearing — it is interpreting and prioritising at volume.')
}

// ============================================= 3 · SOLUTION / TECHNICAL ====
{
  const s = lightSlide('One request in, the whole clinical picture out', '02 · Solution & technical approach')

  // Diagram drawn natively rather than placed as an image: it stays crisp at
  // any zoom, matches the deck palette, and can be edited in PowerPoint.
  const chip = (x, y, w, t, fill, color, size = 9) => {
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w, h: 0.3, rectRadius: 0.06,
      fill: { color: fill }, line: { color: fill, width: 0 },
    })
    s.addText(t, {
      x, y, w, h: 0.3, margin: 0, align: 'center', valign: 'middle',
      fontFace: TEXT, fontSize: size, bold: true, color,
    })
  }
  const bandLabel = (x, y, t, color, w = 3.0) => s.addText(t, {
    x, y, w, h: 0.24, margin: 0,
    fontFace: TEXT, fontSize: 9, bold: true, color, charSpacing: 1.6,
  })
  const flow = (x, y) => s.addShape(pres.ShapeType.downArrow, {
    x, y, w: 0.26, h: 0.26, fill: { color: 'CBD5E1' }, line: { color: 'CBD5E1', width: 0 },
  })

  // ---- Band 1 · browser -------------------------------------------------
  card(s, { x: 0.6, y: 1.5, w: 12.13, h: 1.16 })
  bandLabel(0.85, 1.63, 'BROWSER · REACT + VITE · INSTALLABLE PWA', TEAL)
  const steps = ['1 Patient', '2 Symptoms', '3 Otoscopy', '4 Pure tone', '5 Immittance', '6 Evoked', '7 Results']
  steps.forEach((t, i) => chip(0.85 + i * 1.67, 1.90, 1.59, t, TEAL_LT, '11655D'))
  s.addText('Clinic tools, outside the per-patient flow:  Screening  ·  Hearing Simulator  ·  Listening Lab  ·  Progression  ·  Batch worklist  ·  Patient Records', {
    x: 0.85, y: 2.28, w: 11.63, h: 0.24, margin: 0,
    fontFace: TEXT, fontSize: 9, color: MUTED,
  })

  flow(6.6, 2.72)

  // ---- Band 2 · the gate ------------------------------------------------
  card(s, { x: 0.6, y: 3.04, w: 12.13, h: 0.62, fill: 'FEF6E7', line: 'F5D9A0' })
  s.addText('ACCESS GATE', {
    x: 0.85, y: 3.17, w: 1.5, h: 0.36, margin: 0, valign: 'middle',
    fontFace: TEXT, fontSize: 9, bold: true, color: '7A4C00', charSpacing: 1.4,
  })
  s.addText('Bearer-token middleware — default closed, so a new route is protected the moment it is registered. PBKDF2 accounts · HMAC sessions · login throttle. Seven public paths (health, login, QR, patient handout).', {
    x: 2.35, y: 3.14, w: 10.15, h: 0.42, margin: 0, valign: 'middle',
    fontFace: TEXT, fontSize: 9.5, color: '6B4A12',
  })

  flow(6.6, 3.72)

  // ---- Band 3 · API -----------------------------------------------------
  card(s, { x: 0.6, y: 4.04, w: 12.13, h: 1.0 })
  bandLabel(0.85, 4.15, 'FASTAPI · 23 ROUTERS · 72 ENDPOINTS', PURPLE)
  const api = [
    'analyze', 'otoscopy', 'symptoms', 'tympanometry', 'oae', 'speech',
    'masking', 'tuning-fork', 'aep + boa', 'diagnosis', 'anatomy', 'linkage',
    'report + pdf', 'records', 'batch', 'progression', 'prescription', 'validate',
  ]
  api.forEach((t, i) => {
    const col = i % 9, row = Math.floor(i / 9)
    chip(0.85 + col * 1.32, 4.42 + row * 0.32, 1.24, t, 'EDE9F5', PURPLE, 8)
  })

  flow(6.6, 5.1)

  // ---- Band 4 · engine, ML, state --------------------------------------
  card(s, { x: 0.6, y: 5.42, w: 6.3, h: 1.35, fill: '1E293B', line: '1E293B' })
  bandLabel(0.85, 5.54, 'DETERMINISTIC CLINICAL ENGINE · 24 MODULES', '7DD3C0')
  s.addText('WHO 2021 grading · air-bone-gap typing · RPwD 2016 disability · masking rules · Jerger 8-type immittance · ABR/MLR/LLR normatives · Rinne–Weber grid · red-flag safety',
    { x: 0.85, y: 5.82, w: 5.85, h: 0.62, margin: 0, fontFace: TEXT, fontSize: 9, color: 'CBD5E1', lineSpacing: 12 })
  s.addText('Same input → same answer. No model decides a diagnosis.', {
    x: 0.85, y: 6.44, w: 5.85, h: 0.24, margin: 0, fontFace: TEXT, fontSize: 9, bold: true, italic: true, color: GOLD,
  })

  card(s, { x: 7.1, y: 5.42, w: 2.7, h: 1.35, fill: TEAL_LT, line: 'CCE7E3' })
  bandLabel(7.32, 5.54, 'ML — ADVISORY ONLY', TEAL, 2.3)
  s.addText('RandomForest pattern + calibration · out-of-distribution flag · deep ensemble second opinion · OpenCV audiogram digitiser · otoscopy retrieval',
    { x: 7.32, y: 5.82, w: 2.3, h: 0.86, margin: 0, fontFace: TEXT, fontSize: 8.5, color: '14685F', lineSpacing: 11.5 })

  card(s, { x: 10.0, y: 5.42, w: 2.73, h: 1.35, fill: 'EDE9F5', line: 'D9CEEA' })
  bandLabel(10.22, 5.54, 'STATE & ARTIFACTS', PURPLE, 2.3)
  s.addText('Volume: records.db + handouts, verification, feedback, config\nImage: 12 MB trained models + 62-view atlas (never retrained on deploy)',
    { x: 10.22, y: 5.82, w: 2.3, h: 0.86, margin: 0, fontFace: TEXT, fontSize: 8.5, color: '4A1D73', lineSpacing: 11.5 })

  footer(s, 3)
  s.addNotes('The load-bearing claim: every clinical judgement is a deterministic rule implementation. ML is confined to pattern recognition and always reports its own confidence. Nothing retrains on deploy — the model that ships is the model that was tested.')
}

// ================================================ 4 · WHAT TO DEVELOP ======
{
  const s = lightSlide('What we build next, and why', '03 · Development roadmap')

  card(s, { x: 0.6, y: 1.5, w: 6.05, h: 2.35, fill: 'FEF6E7', line: 'F5D9A0' })
  bead(s, { x: 0.9, y: 1.78, ch: '!', fill: GOLD, color: '3A2500' })
  s.addText('Priority 1 — Otoscopy model accuracy', {
    x: 1.45, y: 1.8, w: 5.0, h: 0.3, margin: 0, fontFace: TEXT, fontSize: 14, bold: true, color: '7A4C00',
  })
  s.addText([
    { text: 'Trained today on 62 labelled images across 8 patterns — crops from only 22 source photographs.', options: { bullet: true, breakLine: true } },
    { text: 'Measured holding out every view of a source photograph: 27% top-1 (17/62, 95% CI 15–42%), 52% top-3, against 12.5% chance.', options: { bullet: true, breakLine: true } },
    { text: 'Target: a 2,000+ image annotated dataset, clinician-labelled, to make the differential dependable.', options: { bullet: true } },
  ], { x: 1.45, y: 2.2, w: 4.95, h: 1.5, margin: 0, fontFace: TEXT, fontSize: 11.5, color: '6B4A12', lineSpacing: 15, paraSpaceAfter: 6 })

  const items = [
    ['Clinical validation study', 'Prospective agreement against audiologist ground truth. The rules score kappa 1.0 by construction; the ML needs real-world numbers.'],
    ['Roles and audit trail', 'Today every signed-in user sees every patient. Multi-clinic use needs per-user roles, record ownership and an audit actor.'],
    ['Paediatric expansion', 'Wider ABR/ASSR coverage and VRA, so children under six months are sized objectively rather than screened.'],
    ['Field hardening', 'Tamil font embedding in the PDF, tablet layouts for the camp setting, and offline sync for intermittent connectivity.'],
  ]
  items.forEach(([h2, b], i) => {
    const y = 1.5 + i * 1.06
    card(s, { x: 6.85, y, w: 5.85, h: 0.96 })
    bead(s, { x: 7.08, y: y + 0.26, ch: String(i + 2), fill: PURPLE, d: 0.36, size: 13 })
    s.addText(h2, { x: 7.58, y: y + 0.13, w: 5.0, h: 0.28, margin: 0, fontFace: TEXT, fontSize: 13, bold: true, color: INK })
    s.addText(b, { x: 7.58, y: y + 0.41, w: 5.0, h: 0.5, margin: 0, fontFace: TEXT, fontSize: 10.5, color: BODY, lineSpacing: 13.5 })
  })

  card(s, { x: 0.6, y: 4.02, w: 6.05, h: 1.5, fill: TEAL_LT, line: 'CCE7E3' })
  s.addText('Already shipped in this cycle', { x: 0.9, y: 4.2, w: 5.4, h: 0.28, margin: 0, fontFace: TEXT, fontSize: 12, bold: true, color: TEAL })
  s.addText('Patient-facing ear anatomy animations · access control with hashed accounts · persistent patient records · complete diagnostic-picture panel · 84 defects found and fixed by adversarial review.', {
    x: 0.9, y: 4.5, w: 5.4, h: 0.9, margin: 0, fontFace: TEXT, fontSize: 11, color: '14685F', lineSpacing: 15,
  })
  footer(s, 4)
  s.addNotes('We state the otoscopy accuracy honestly on screen in the product itself; it is a retrieval aid today, not a diagnosis.')
}

// ================================================== 5 · DELIVERABLES ======
{
  const s = lightSlide('Live, and open for pilot testing', '04 · Deliverables')

  picture(s, { file: 'dashboard.png', x: 0.6, y: 1.5, w: 7.85, h: 4.4, label: 'Results dashboard screenshot' })
  s.addText('Results dashboard — audiogram, AI pattern classification, WHO degree, air-bone-gap type and speech intelligibility index, on one screen.', {
    x: 0.6, y: 5.96, w: 7.85, h: 0.42, margin: 0, fontFace: TEXT, fontSize: 10, color: MUTED, lineSpacing: 13,
  })

  card(s, { x: 8.75, y: 1.5, w: 3.95, h: 2.62, fill: WHITE })
  picture(s, { file: 'qr_pilot.png', x: 9.62, y: 1.72, w: 2.2, h: 2.2, label: 'QR' })

  card(s, { x: 8.75, y: 4.28, w: 3.95, h: 1.62, fill: PURPLE, line: PURPLE })
  s.addText('PILOT URL', { x: 9.0, y: 4.46, w: 3.45, h: 0.24, margin: 0, fontFace: TEXT, fontSize: 10, bold: true, color: GOLD, charSpacing: 2 })
  s.addText('audio-sense-ai.vercel.app', {
    x: 9.0, y: 4.72, w: 3.5, h: 0.34, margin: 0, fontFace: TEXT, fontSize: 14, bold: true, color: WHITE,
  })
  s.addText('Scan or open in any browser. Credentials are issued per clinic — the instance refuses every request without one.', {
    x: 9.0, y: 5.1, w: 3.45, h: 0.72, margin: 0, fontFace: TEXT, fontSize: 10, color: 'D9CBE9', lineSpacing: 13.5,
  })

  // Four deliverables across one row — each in its own column, so they cannot
  // collide with the caption above.
  const outs = ['Web app, offline-capable PWA', 'Verified PDF report + QR hash',
    'Counselling sheet in 6 languages', 'Batch CSV camp worklist']
  outs.forEach((t, i) => {
    const x = 0.6 + i * 3.05
    bead(s, { x, y: 6.5, ch: '✓', fill: TEAL, d: 0.28, size: 11 })
    s.addText(t, {
      x: x + 0.36, y: 6.5, w: 2.6, h: 0.28, margin: 0, valign: 'middle',
      fontFace: TEXT, fontSize: 10.5, color: BODY,
    })
  })
  footer(s, 5)
  s.addNotes('The pilot URL is live now. Ask NIEPMD staff to try a real case end to end and report anything that reads wrong.')
}

// ================================= 6 · REQUIREMENTS & BUDGET (FUNDED) ====
{
  const s = lightSlide('What it takes to make this clinically dependable', '05 · Requirements & budget')

  s.addText('12-month programme.  The engineering is largely done — the spend is on the two things that turn a working platform into a trustworthy one: labelled clinical data, and independent validation.', {
    x: 0.6, y: 1.44, w: 12.13, h: 0.32, margin: 0,
    fontFace: TEXT, fontSize: 11.5, color: BODY,
  })

  const R = (cat, detail, amt, why) => ([
    { text: cat, options: { bold: true, color: INK } },
    { text: detail, options: { color: BODY } },
    { text: why, options: { color: MUTED, fontSize: 9 } },
    { text: amt, options: { align: 'right', bold: true, color: INK } },
  ])

  s.addTable([
    [
      { text: 'Category', options: { bold: true, color: WHITE, fill: { color: PURPLE } } },
      { text: 'What it covers', options: { bold: true, color: WHITE, fill: { color: PURPLE } } },
      { text: 'Why it is needed', options: { bold: true, color: WHITE, fill: { color: PURPLE } } },
      { text: '₹', options: { bold: true, align: 'right', color: WHITE, fill: { color: PURPLE } } },
    ],
    R('Clinical data & validation', '2,500 otoscopy images annotated by two clinicians; 200-patient prospective agreement study; biostatistics support',
      '8,60,000', 'The 62-image model is the single weakest link'),
    R('Hardware', '3 USB video otoscopes · 4 clinic tablets · audiometer interface + annual calibration · 2 on-site servers with UPS',
      '3,75,000', 'Capture quality decides dataset quality'),
    R('Infrastructure — 12 months', 'Production cloud (HA, Indian region) · block storage · backups · monitoring · domain and TLS',
      '1,50,000', 'Uptime a clinic can schedule around'),
    R('AI tooling & compute', 'LLM API for report narratives · GPU hours to retrain otoscopy · generative video for the anatomy library · vision API fallback · 2 AI coding-assistant seats',
      '3,90,000', 'Every clinical rule still runs offline'),
    R('Compliance & security', 'DPDP Act 2023 readiness review · independent penetration test · CDSCO SaMD classification pathway',
      '3,50,000', 'Required before scaling past one site'),
    R('Team — 12 months', '2 engineers (full-time) · clinical advisor (part-time) · audiologist time for labelling and review',
      '9,60,000', 'Sustains the work past the student cycle'),
    [
      { text: 'Total', options: { bold: true, color: WHITE, fill: { color: '1E293B' } } },
      { text: '12-month programme, inclusive of hardware and one year of running cost', options: { color: 'CBD5E1', fill: { color: '1E293B' } } },
      { text: '', options: { fill: { color: '1E293B' } } },
      { text: '₹ 30,85,000', options: { align: 'right', bold: true, color: GOLD, fill: { color: '1E293B' }, fontSize: 13 } },
    ],
  ], {
    x: 0.6, y: 1.9, w: 12.13, colW: [2.35, 5.15, 3.13, 1.5],
    fontFace: TEXT, fontSize: 9.5, color: BODY, rowH: 0.42, valign: 'middle',
    border: { type: 'solid', color: LINE, pt: 0.5 }, fill: { color: WHITE },
  })

  // Where it can be phased, and what the floor actually is.
  const notes = [
    ['Phase 1 · ₹12,35,000', 'Dataset, annotation and capture hardware. Lifts otoscopy from 27% top-1 to a usable differential — the highest-value spend.'],
    ['Phase 2 · ₹5,40,000', 'AI tooling, GPU compute and production infrastructure. Retrains the model and puts it somewhere a clinic can rely on.'],
    ['Phase 3 · ₹13,10,000', 'Team and compliance for the full year — validation, DPDP readiness, and maintenance past the student cycle.'],
  ]
  notes.forEach(([h2, b], i) => {
    const x = 0.6 + i * 4.07
    card(s, { x, y: 5.4, w: 3.84, h: 1.22, fill: i === 0 ? 'FEF6E7' : WHITE, line: i === 0 ? 'F5D9A0' : LINE })
    s.addText(h2, { x: x + 0.24, y: 5.54, w: 3.4, h: 0.26, margin: 0, fontFace: TEXT, fontSize: 12, bold: true, color: i === 0 ? '7A4C00' : PURPLE })
    s.addText(b, { x: x + 0.24, y: 5.82, w: 3.4, h: 0.68, margin: 0, fontFace: TEXT, fontSize: 9.5, color: i === 0 ? '6B4A12' : BODY, lineSpacing: 12.5 })
  })

  footer(s, 6)
  s.addNotes('The platform itself is built and deployed. This budget buys the two things it cannot buy itself: a real annotated dataset and independent clinical validation. Phase 1 alone addresses the weakest link.')
}

// ==================================================== 7 · TIMELINE ========
{
  const s = lightSlide('Module status', '06 · Timeline')

  const rows = [
    ['1', 'Pure-tone audiometry · WHO 2021 grading · ABG typing', 'Completed'],
    ['2', 'Disability estimation (RPwD Act 2016)', 'Completed'],
    ['3', 'ML pattern classification + confidence & OOD flagging', 'Completed'],
    ['4', 'Snap-to-digitize (OpenCV paper audiogram reader)', 'Completed'],
    ['5', 'Immittance — 8 Jerger types · OAE · speech audiometry', 'Completed'],
    ['6', 'Masking engine · tuning-fork battery', 'Completed'],
    ['7', 'Evoked potentials (ABR / MLR / LLR) · BOA', 'Completed'],
    ['8', 'Symptom triage · cross-modal linkage · diagnostic picture', 'Completed'],
    ['9', 'Reports · 6-language counselling · QR verification', 'Completed'],
    ['10', 'Hearing simulator · Listening Lab · patient records', 'Completed'],
    ['11', 'Patient ear-anatomy animations', 'Completed'],
    ['12', 'Access control · persistent records · pilot deployment', 'Completed'],
    ['13', 'Otoscopy model — retrain on 2,000+ labelled images', 'In progress'],
    ['14', 'Prospective clinical validation at NIEPMD', 'Planned'],
    ['15', 'Roles, record ownership and audit trail', 'Planned'],
    ['16', 'Tablet layouts · Tamil PDF font · offline sync', 'Planned'],
  ]

  const STATUS = {
    Completed: { fill: 'E7F6EF', color: '0F7B4F' },
    'In progress': { fill: 'FEF3DC', color: '9A6400' },
    Planned: { fill: 'EDE9F5', color: PURPLE },
  }

  const body = rows.map(([n, m, st]) => ([
    { text: n, options: { align: 'center', color: MUTED } },
    { text: m, options: { color: INK } },
    { text: st, options: { align: 'center', bold: true, color: STATUS[st].color, fill: { color: STATUS[st].fill } } },
  ]))

  s.addTable([
    [
      { text: 'S.No', options: { bold: true, align: 'center', color: WHITE, fill: { color: PURPLE } } },
      { text: 'Module', options: { bold: true, color: WHITE, fill: { color: PURPLE } } },
      { text: 'Status', options: { bold: true, align: 'center', color: WHITE, fill: { color: PURPLE } } },
    ],
    ...body,
  ], {
    x: 0.6, y: 1.46, w: 12.1, colW: [0.85, 9.15, 2.1],
    fontFace: TEXT, fontSize: 10.5, rowH: 0.265, valign: 'middle',
    border: { type: 'solid', color: LINE, pt: 0.5 },
    fill: { color: WHITE },
  })

  s.addText('12 of 16 modules complete and in pilot. The remaining four are accuracy and governance work, not new capability.', {
    x: 0.6, y: 6.42, w: 12.1, h: 0.3, margin: 0,
    fontFace: TEXT, fontSize: 11, italic: true, color: TEAL,
  })
  footer(s, 7)
  s.addNotes('Everything marked Completed is running in the deployed pilot today, not on a branch.')
}

// =================================================== 8 · THANK YOU ========
{
  const s = darkSlide()

  s.addText('Thank you', {
    x: 0.6, y: 2.3, w: 8, h: 1.0, margin: 0,
    fontFace: HEAD, fontSize: 54, bold: true, color: WHITE,
  })
  s.addText('We would value NIEPMD clinicians testing the pilot on real cases —\nespecially anything the system reports that reads wrong to an expert eye.', {
    x: 0.62, y: 3.32, w: 8.0, h: 0.8, margin: 0,
    fontFace: TEXT, fontSize: 15, color: 'D9CBE9', lineSpacing: 23,
  })

  card(s, { x: 0.6, y: 4.42, w: 8.0, h: 1.15, fill: 'FFFFFF', line: 'FFFFFF' })
  s.addText('audio-sense-ai.vercel.app', {
    x: 0.9, y: 4.62, w: 5.0, h: 0.34, margin: 0, fontFace: TEXT, fontSize: 16, bold: true, color: PURPLE,
  })
  s.addText('Kutty Koncepts · Rajalakshmi Engineering College, Chennai', {
    x: 0.9, y: 4.98, w: 6.6, h: 0.3, margin: 0, fontFace: TEXT, fontSize: 11.5, color: BODY,
  })

  if (has('rec_logo.png')) s.addImage({ path: A('rec_logo.png'), x: 9.5, y: 4.55, w: 1.7, h: 0.84, sizing: { type: 'contain', w: 1.7, h: 0.84 } })
  picture(s, { file: 'niepmd_logo.png', x: 11.45, y: 4.55, w: 0.85, h: 0.84, label: 'NIEPMD' })

  s.addText('AI-assisted interpretation; final diagnosis requires a qualified audiologist.', {
    x: 0.6, y: H - 0.68, w: 9, h: 0.28, margin: 0,
    fontFace: TEXT, fontSize: 10, italic: true, color: 'A996C4',
  })
  s.addNotes('Close on the ask: clinician testing and honest feedback on anything that reads wrong.')
}

const out = path.join(__dirname, 'AudioSense-AI-Pilot-Review-v2.pptx')
pres.writeFile({ fileName: out }).then(() => console.log('wrote', out))
