import { Component } from 'react'

// A single render error must never blank the screen — least of all during a
// three-minute demo. This catches it, keeps the rest of the app reachable,
// and shows what happened so it can be reported rather than guessed at.

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Keep the detail in the console for whoever is debugging.
    console.error('Caught by ErrorBoundary:', error, info?.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div role="alert" className="mx-auto mt-16 max-w-lg rounded-2xl border border-rose-200 bg-rose-50 p-6">
        <h2 className="text-[17px] font-semibold text-rose-900">
          This page hit an error
        </h2>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-rose-800">
          The rest of the application is unaffected — use the navigation to
          continue, or reload to start again.
        </p>
        <pre className="mt-3 max-h-40 overflow-auto rounded-lg bg-white/70 p-3 text-[11.5px] text-rose-900">
          {String(error?.message || error)}
        </pre>
        <div className="mt-4 flex gap-2">
          <button onClick={() => this.setState({ error: null })}
            className="rounded-lg bg-rose-600 px-4 py-2 text-[13px] font-semibold text-white hover:bg-rose-700">
            Try again
          </button>
          <button onClick={() => window.location.reload()}
            className="rounded-lg border border-rose-300 px-4 py-2 text-[13px] font-semibold text-rose-800 hover:bg-rose-100">
            Reload
          </button>
        </div>
      </div>
    )
  }
}
