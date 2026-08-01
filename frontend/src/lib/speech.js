// Spoken counseling via the Web Speech API.
//
// Many patients with hearing loss are older or have low literacy; reading a
// printed sheet is not how the advice actually lands. Speaking it aloud (and
// in Tamil, not just English) is the accessible path — and it costs nothing,
// since speech synthesis is built into the browser.

const LANG = {
  english: 'en-IN', tamil: 'ta-IN', hindi: 'hi-IN',
  telugu: 'te-IN', kannada: 'kn-IN', malayalam: 'ml-IN',
}
const FALLBACK_LANG = {
  english: 'en-US', tamil: 'ta', hindi: 'hi',
  telugu: 'te', kannada: 'kn', malayalam: 'ml',
}

function voicesFor(lang) {
  const all = window.speechSynthesis?.getVoices?.() || []
  const want = [LANG[lang], FALLBACK_LANG[lang]].filter(Boolean)
  for (const code of want) {
    const match = all.filter((v) => v.lang?.toLowerCase().startsWith(code.toLowerCase()))
    if (match.length) return match
  }
  // Loose match on the base language tag (e.g. "ta" inside "ta-IN").
  const base = (LANG[lang] || '').split('-')[0]
  return all.filter((v) => v.lang?.toLowerCase().startsWith(base))
}

export function tamilVoiceAvailable() {
  return voicesFor('tamil').length > 0
}

/** Which of our languages this browser can actually speak. */
export function availableLanguages() {
  return Object.keys(LANG).filter((l) => voicesFor(l).length > 0)
}

/**
 * Why a language cannot be spoken, in terms the user can act on.
 *
 * Chromium enumerates legacy SAPI5 voices from the registry, while voices
 * installed through Windows Settings are OneCore voices kept somewhere else.
 * The result is that Tamil can be installed, working in Narrator, and still
 * invisible here — which looks like a bug in the app unless we say otherwise.
 */
export function voiceDiagnostic(lang) {
  const all = window.speechSynthesis?.getVoices?.() || []
  const speakable = availableLanguages()
  const name = lang.charAt(0).toUpperCase() + lang.slice(1)
  const isChromium = /Chrome|Chromium|Edg/.test(navigator.userAgent)
  const isEdge = /Edg\//.test(navigator.userAgent)

  if (!all.length) {
    return `This browser reports no speech voices at all. Try Microsoft Edge.`
  }
  return [
    `No ${name} voice is visible to this browser.`,
    speakable.length
      ? `It can currently speak: ${speakable.join(', ')}.`
      : 'It has no usable voices for this app.',
    isChromium && !isEdge
      ? 'Chrome only reads legacy SAPI5 voices, so voices added through '
        + 'Windows Settings often stay invisible to it. Opening the app in '
        + 'Microsoft Edge usually fixes this immediately.'
      : 'Install the voice under Settings → Time & language → Speech → '
        + 'Manage voices, then restart the browser.',
  ].join(' ')
}

/** Is a voice installed for this language key (or BCP-47 tag)? */
export function voiceAvailable(langOrTag) {
  if (!langOrTag) return true
  if (LANG[langOrTag]) return voicesFor(langOrTag).length > 0
  const base = String(langOrTag).split('-')[0].toLowerCase()
  const all = window.speechSynthesis?.getVoices?.() || []
  return all.some((v) => v.lang?.toLowerCase().startsWith(base))
}

export function speechSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/**
 * Speak a list of lines sequentially.
 * Returns {ok, reason} — callers surface `reason` when a language has no voice
 * installed rather than silently doing nothing.
 */
export function speak(lines, lang = 'english', { rate = 0.92, onEnd } = {}) {
  if (!speechSupported()) return { ok: false, reason: 'Speech synthesis not supported in this browser' }
  stopSpeaking()

  const voices = voicesFor(lang)
  if (!voices.length) {
    return { ok: false, reason: voiceDiagnostic(lang) }
  }

  const text = Array.isArray(lines) ? lines.join(' ') : String(lines)
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = LANG[lang] || 'en-IN'
  if (voices.length) utter.voice = voices[0]
  utter.rate = rate // slightly slow — this is patient counseling
  utter.pitch = 1
  if (onEnd) {
    utter.onend = onEnd
    utter.onerror = onEnd
  }
  window.speechSynthesis.speak(utter)
  return { ok: true }
}

export function stopSpeaking() {
  if (speechSupported()) window.speechSynthesis.cancel()
}

// Voice lists load asynchronously in Chrome; touch them early so the first
// click doesn't come back empty.
if (speechSupported()) {
  window.speechSynthesis.getVoices()
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices()
}
