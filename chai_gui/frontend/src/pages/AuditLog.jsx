import React, { useEffect, useState, useCallback } from 'react'
import { ShieldCheck, RefreshCw, Filter, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { auditApi } from '../api/api.js'

const ACTION_COLORS = {
  node:    'bg-sky-900/40 text-sky-300 border-sky-700/40',
  cluster: 'bg-purple-900/40 text-purple-300 border-purple-700/40',
  deploy:  'bg-green-900/40 text-green-300 border-green-700/40',
  backup:  'bg-yellow-900/40 text-yellow-300 border-yellow-700/40',
}

function actionColor(action = '') {
  const prefix = action.split('.')[0]
  return ACTION_COLORS[prefix] ?? 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-600'
}

function fmtTs(epoch) {
  return new Date(epoch * 1000).toLocaleString()
}

export default function AuditLog() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter]   = useState('')
  const [error, setError]     = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await auditApi.list(200, filter || undefined)
      setEntries(data.entries ?? [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => { load() }, [load])

  const handleClear = async () => {
    if (!window.confirm('Clear all audit entries? This cannot be undone.')) return
    try {
      await auditApi.clear()
      toast.success('Audit log cleared.')
      load()
    } catch (e) {
      toast.error(e.message)
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck size={20} className="text-sky-400" />
          <h1 className="text-lg font-bold text-slate-900 dark:text-white">Audit Log</h1>
          <span className="badge-gray">{entries.length} entries</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Filter size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 dark:text-slate-400" />
            <input
              className="input pl-8 text-sm w-44"
              placeholder="Filter by action…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <button className="btn-secondary flex items-center gap-1.5" onClick={load}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button className="btn-danger flex items-center gap-1.5" onClick={handleClear}>
            <Trash2 size={13} /> Clear
          </button>
        </div>
      </div>

      {error && (
        <div className="card border border-red-700/40 text-red-400 text-sm">{error}</div>
      )}

      {/* Table */}
      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400">
                <th className="px-4 py-3 text-left">Timestamp</th>
                <th className="px-4 py-3 text-left">Action</th>
                <th className="px-4 py-3 text-left">Actor</th>
                <th className="px-4 py-3 text-left">Detail</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center">
                    <div className="flex justify-center">
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-sky-500" />
                    </div>
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                    No audit entries found.
                  </td>
                </tr>
              ) : (
                entries.map((e, i) => (
                  <tr key={i} className="border-b border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-2.5 text-slate-600 dark:text-slate-400 whitespace-nowrap text-xs">
                      {fmtTs(e.ts)}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${actionColor(e.action)}`}>
                        {e.action}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{e.actor}</td>
                    <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 text-xs font-mono truncate max-w-xs">
                      {e.detail ? JSON.stringify(e.detail) : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
