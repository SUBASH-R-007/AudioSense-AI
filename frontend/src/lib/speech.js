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
  if (lang !== 'english' && !voices.length) {
    const name = lang.charAt(0).toUpperCase() + lang.slice(1)
    return {
      ok: false,
      reason: `No ${name} voice installed on this system — add one in Windows `
        + `Settings → Time & language → Speech to hear the ${name} sheet read aloud.`,
    }
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
