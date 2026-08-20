// Live conversation mode — speech recognition + word-level audibility.
//
// The bundled sentence proves the point in the abstract. This makes it
// personal: a judge speaks their own words, and sees them appear with the
// parts this patient would miss struck out, as they say them.
//
// Recognition runs entirely in the browser's Web Speech API. Each interim
// transcript is scored against the patient's thresholds by the same
// backend word-audibility engine used everywhere else, so the captions and
// the clinical report can never disagree.

export function recognitionSupported() {
  return typeof window !== 'undefined'
    && !!(window.SpeechRecognition || window.webkitSpeechRecognition)
}

//: Errors that cannot resolve by trying again. Everything else — a dropped
//: network, a long silence — is worth a restart; these are a standing refusal,
//: and restarting on them is an infinite loop.
const FATAL_ERRORS = new Set(['not-allowed', 'service-not-allowed', 'audio-capture'])

export class ConversationListener {
  /**
   * @param {(text: string, isFinal: boolean) => void} onTranscript
   * @param {(err: string) => void} onError
   */
  constructor(onTranscript, onError, lang = 'en-IN') {
    this.onTranscript = onTranscript
    this.onError = onError
    this.lang = lang
    this.recognition = null
    this.listening = false
    this._stopping = false
  }

  start() {
    if (!recognitionSupported()) {
      this.onError?.('Speech recognition is not supported in this browser — '
        + 'Chrome or Edge are needed for live conversation mode.')
      return false
    }
    const Impl = window.SpeechRecognition || window.webkitSpeechRecognition
    const rec = new Impl()
    rec.lang = this.lang
    rec.continuous = true
    rec.interimResults = true
    rec.maxAlternatives = 1

    rec.onresult = (event) => {
      let text = ''
      let isFinal = false
      for (let i = event.resultIndex; i < event.results.length; i++) {
        text += event.results[i][0].transcript
        if (event.results[i].isFinal) isFinal = true
      }
      const trimmed = text.trim()
      if (trimmed) this.onTranscript?.(trimmed, isFinal)
    }
    rec.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return
      // Retrying a denied microphone just gets it denied again. Tear the
      // listener down BEFORE onend fires, or the restart below spins forever:
      // a permanent error toast per iteration and a recogniser that only stops
      // when the page is left. Stopping first also means the consumer's error
      // callback observes an already-stopped listener.
      if (FATAL_ERRORS.has(e.error)) this.stop()
      this.onError?.(
        e.error === 'not-allowed'
          ? 'Microphone permission denied — allow it to use conversation mode.'
          : `Speech recognition error: ${e.error}`,
      )
    }
    // continuous mode still stops on long silences; restart unless we asked it to stop
    rec.onend = () => {
      if (this.listening && !this._stopping) {
        try { rec.start() } catch { /* already restarting */ }
      }
    }

    this.recognition = rec
    this.listening = true
    this._stopping = false
    try {
      rec.start()
    } catch {
      this.onError?.('Could not start the microphone.')
      this.listening = false
      return false
    }
    return true
  }

  stop() {
    this._stopping = true
    this.listening = false
    try { this.recognition?.stop() } catch { /* ignore */ }
    this.recognition = null
  }
}
