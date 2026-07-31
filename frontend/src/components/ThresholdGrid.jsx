import { AC_FREQS, BC_FREQS, FREQ_LABELS } from '../lib/api.js'

const DB_OPTIONS = []
for (let db = -10; db <= 120; db += 5) DB_OPTIONS.push(db)

const ROWS = [
  { ear: 'right', cond: 'ac', label: 'Right AC', symbol: 'O', color: 'text-red-600' },
  { ear: 'right', cond: 'bc', label: 'Right BC', symbol: '[', color: 'text-red-600' },
  { ear: 'left', cond: 'ac', label: 'Left AC', symbol: 'X', color: 'text-blue-600' },
  { ear: 'left', cond: 'bc', label: 'Left BC', symbol: ']', color: 'text-blue-600' },
]

// thresholds shape: {right: {ac: {250: 10|'NR'|undefined}, bc: {...}}, left: {...}}
export default function ThresholdGrid({ thresholds, onChange, confidence }) {
  const set = (ear, cond, freq, raw) => {
    const next = structuredClone(thresholds)
    if (raw === '') delete next[ear][cond][freq]
    else next[ear][cond][freq] = raw === 'NR' ? 'NR' : parseInt(raw, 10)
    onChange(next)
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-center text-[13px]">
        <thead>
          <tr className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
            <th className="px-3 py-2.5 text-left font-semibold">Ear / Hz</th>
            {AC_FREQS.map((f) => (
              <th key={f} className="px-2 py-2.5 font-semibold">{FREQ_LABELS[f]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.label} className="border-t border-slate-100">
              <td className="whitespace-nowrap px-3 py-2 text-left font-medium text-slate-700">
                <span className={`mr-1.5 inline-block w-3 font-bold ${row.color}`}>{row.symbol}</span>
                {row.label}
              </td>
              {AC_FREQS.map((f) => {
                const disabled = row.cond === 'bc' && !BC_FREQS.includes(f)
                const value = thresholds[row.ear][row.cond][f]
                const conf = confidence?.[row.ear]?.[row.cond]?.[f]
                return (
                  <td key={f} className={`px-1.5 py-1.5 ${disabled ? 'bg-slate-50' : ''}`}>
                    {disabled ? (
                      <span className="text-slate-300">—</span>
                    ) : (
                      <div className="relative inline-block">
                        <select
                          value={value === undefined ? '' : String(value)}
                          onChange={(e) => set(row.ear, row.cond, f, e.target.value)}
                          className={`w-[4.6rem] appearance-none rounded-md border py-1.5 pl-2 pr-5 text-center text-[13px] transition focus:outline-none focus:ring-2 focus:ring-teal-500/30 ${
                            value === undefined
                              ? 'border-slate-200 bg-white text-slate-400'
                              : 'border-slate-300 bg-white font-medium text-slate-800'
                          } ${conf !== undefined && conf < 0.7 ? 'border-amber-400 bg-amber-50' : ''}`}
                        >
                          <option value="">–</option>
                          {DB_OPTIONS.map((db) => (
                            <option key={db} value={db}>{db}</option>
                          ))}
                          <option value="NR">NR</option>
                        </select>
                        {conf !== undefined && (
                          <span className={`absolute -top-1.5 -right-1 rounded-full px-1 text-[8.5px] font-bold ${
                            conf >= 0.7 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                          }`}>
                            {Math.round(conf * 100)}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
