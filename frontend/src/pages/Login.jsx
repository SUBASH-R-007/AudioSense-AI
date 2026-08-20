import { useState } from 'react'
import { useApp } from '../lib/store.jsx'

/** The same mark the sidebar uses, so signing in does not feel like a different product. */
function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-600 shadow-sm shadow-teal-600/30">
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none"
          stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 12h3l2-5 3 10 3-8 2 3h7" />
        </svg>
      </div>
      <div>
        <div className="text-[17px] font-semibold tracking-tight text-slate-900">
          AudioSense <span className="text-teal-600">AI</span>
        </div>
        <div className="text-[10px] font-medium uppercase tracking-widest text-slate-400">
          Audiometry Intelligence
        </div>
      </div>
    </div>
  )
}

/** "187 seconds" reads as a number to count; "about 3 minutes" reads as a decision. */
function humaniseWait(seconds) {
  if (seconds < 90) return `about ${seconds} seconds`
  return `about ${Math.ceil(seconds / 60)} minutes`
}

// What went wrong decides who has to fix it, and the screen is useless if it
// blames the person typing for a problem only the operator can solve. The
// status code is the only reliable signal — the message text is not something
// to switch on — which is why api.js attaches it.
function describeFailure(err) {
  const status = err?.status

  if (status === 401) {
    return {
      tone: 'error',
      title: 'Incorrect username or password',
      detail: 'The instance does not say which of the two was wrong, by design. '
        + 'Check for caps lock and for a trailing space in the username.',
    }
  }

  if (status === 429) {
    const match = /(\d+)\s*second/.exec(err?.message || '')
    const wait = match ? humaniseWait(Number(match[1])) : 'a few minutes'
    return {
      tone: 'error',
      title: 'Too many failed attempts',
      detail: `Sign-in from this address is paused for ${wait}. `
        + 'The wait restarts on every further failure, so it is worth confirming '
        + 'the credentials before trying again.',
    }
  }

  if (status === 503) {
    return {
      tone: 'config',
      title: 'No accounts are configured on this instance',
      detail: 'Nothing is wrong with the password — there is nobody to sign in as. '
        + 'Whoever deployed this needs to set AUDIOSENSE_USERS in the backend '
        + 'environment (username:hash entries, produced by scripts/make_user.py) '
        + 'and restart it. Until then every request is refused.',
    }
  }

  return {
    tone: 'error',
    title: 'Could not sign in',
    detail: err?.message
      || 'The server did not answer. Check that the backend is running and reachable.',
  }
}

export default function Login() {
  const { signIn, authMode } = useApp()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState(null)

  // The instance already told us at boot that it has no accounts, so say so
  // before anyone types a password that was never going to work.
  //
  // Keyed on the mode, not on `authRequired === false`, which is also false for
  // an instance running deliberately without authentication — so this banner
  // used to accuse a working anonymous instance of having no accounts.
  const unconfigured = authMode === 'locked'

  const submit = async (event) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setFailure(null)
    try {
      await signIn(username.trim(), password)
    } catch (err) {
      setFailure(describeFailure(err))
      // Clear the attempt rather than leave it sitting in a form field for the
      // next person at the machine to reveal. The username stays, because
      // retyping it is friction with no benefit.
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  const field = 'mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-[14px] '
    + 'text-slate-900 outline-none transition placeholder:text-slate-300 '
    + 'focus:border-teal-400 focus:ring-2 focus:ring-teal-100 disabled:bg-slate-50'

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-sm">
        <Logo />

        <form onSubmit={submit}
          className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
          <h1 className="text-[15px] font-semibold text-slate-900">Sign in</h1>
          <p className="mt-1 text-[12px] leading-relaxed text-slate-500">
            This instance holds patient records. Use the credentials issued for it.
          </p>

          {unconfigured && (
            <div className="mt-4 rounded-xl bg-amber-50 px-3 py-2.5 text-[12px] leading-relaxed text-amber-900">
              <div className="font-semibold">This instance has no accounts</div>
              <div className="mt-0.5">
                Nobody can sign in until <code className="font-mono">AUDIOSENSE_USERS</code> is
                set in the backend environment.
              </div>
            </div>
          )}

          <label className="mt-4 block">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Username
            </span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              autoComplete="username"
              autoCapitalize="none"
              spellCheck="false"
              required
              disabled={busy}
              className={field}
            />
          </label>

          <label className="mt-3 block">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Password
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              disabled={busy}
              className={field}
            />
          </label>

          {failure && (
            <div role="alert"
              className={`mt-4 rounded-xl px-3 py-2.5 text-[12px] leading-relaxed ${
                failure.tone === 'config'
                  ? 'bg-amber-50 text-amber-900'
                  : 'bg-rose-50 text-rose-800'
              }`}>
              <div className="font-semibold">{failure.title}</div>
              <div className="mt-0.5">{failure.detail}</div>
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="mt-5 w-full rounded-xl bg-teal-600 px-4 py-2.5 text-[14px] font-semibold text-white shadow-sm transition hover:bg-teal-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="mt-4 px-1 text-[10px] leading-relaxed text-slate-400">
          AI-assisted interpretation; final diagnosis requires a qualified audiologist.
        </p>
      </div>
    </div>
  )
}

/**
 * Who is signed in, and the way out.
 *
 * It lives here rather than in Layout so the sidebar stays untouched; the app
 * renders it at the top of the main column. Signing out clears the case as well
 * as the token, so the control is a deliberate one — hence the confirmation.
 */
export function SessionBar() {
  const { session, signOut } = useApp()
  if (!session) return null

  const confirmSignOut = () => {
    const ok = window.confirm(
      'Sign out? The patient, thresholds and every other finding in this '
      + 'consultation will be cleared from this machine.')
    if (ok) signOut()
  }

  // No authentication at all. Say so plainly and permanently — an instance in
  // this mode serves patient records to anyone who can reach it, and the one
  // thing worse than running it locally is running it without noticing. There
  // is no Sign out here because there is nothing to end.
  if (session.anonymous) {
    return (
      <div className="mb-4 flex items-center justify-end print:hidden">
        <span className="rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-900">
          Running without authentication — local development only. This instance
          serves records to anyone who can reach it.
        </span>
      </div>
    )
  }

  return (
    <div className="mb-4 flex items-center justify-end gap-3 print:hidden">
      <span className="text-[11px] text-slate-400">
        Signed in as <span className="font-semibold text-slate-600">{session.username}</span>
      </span>
      <button
        onClick={confirmSignOut}
        className="rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 transition hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
      >
        Sign out
      </button>
    </div>
  )
}
