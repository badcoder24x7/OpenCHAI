/**
 * ClusterHealthWidget — Dashboard widget showing overall cluster health.
 * Fix vs original: uses nodesApi.health() from the shared api.js
 * instead of dynamic import of the non-existent healthApi.all().
 */
import React, { useEffect, useState } from 'react'
import { CheckCircle2, XCircle, AlertTriangle, Activity, RefreshCw } from 'lucide-react'
import { nodesApi } from '../api/api.js'

const STATUS_CFG = {
  healthy:     { Icon: CheckCircle2,  color: 'text-green-400',  bg: 'bg-green-900/20',  label: 'Healthy'     },
  degraded:    { Icon: AlertTriangle, color: 'text-yellow-400', bg: 'bg-yellow-900/20', label: 'Degraded'    },
  unreachable: { Icon: XCircle,       color: 'text-red-400',    bg: 'bg-red-900/20',    label: 'Unreachable' },
}

function MiniBar({ value, total, color }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-600 dark:text-slate-400 w-8 text-right">{pct}%</span>
    </div>
  )
}

export default function ClusterHealthWidget({ refreshMs = 30_000 }) {
  const [data, setData]           = useState(null)
  const [loading, setLoading]     = useState(true)
  const [lastCheck, setLastCheck] = useState(null)

  async function load() {
    setLoading(true)
    try {
      const result = await nodesApi.health()
      setData(result)
      setLastCheck(new Date().toLocaleTimeString())
    } catch {
      // Silently fail — dashboard should not crash
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, refreshMs)
    return () => clearInterval(id)
  }, [refreshMs])

  const healthy     = data?.healthy     ?? 0
  const degraded    = data?.degraded    ?? 0
  const unreachable = data?.unreachable ?? 0
  const total       = data?.total       ?? 0

  const overallStatus =
    unreachable > 0 ? 'unreachable'
    : degraded  > 0 ? 'degraded'
    : total     > 0 ? 'healthy'
    : null

  const cfg = overallStatus ? STATUS_CFG[overallStatus] : null

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-sky-400" />
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Cluster Health</h3>
        </div>
        <div className="flex items-center gap-2">
          {lastCheck && <span className="text-xs text-slate-500 dark:text-slate-400">{lastCheck}</span>}
          <button onClick={load} className="text-slate-500 dark:text-slate-400 hover:text-slate-600 dark:text-slate-300 transition-colors">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && !data ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">Checking nodes…</p>
      ) : total === 0 ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">No nodes configured.</p>
      ) : (
        <>
          {cfg && (
            <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${cfg.bg}`}>
              <cfg.Icon size={15} className={cfg.color} />
              <span className={`text-sm font-medium ${cfg.color}`}>{cfg.label}</span>
              <span className="text-xs text-slate-600 dark:text-slate-400 ml-auto">{total} nodes</span>
            </div>
          )}

          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between text-slate-600 dark:text-slate-400">
              <span>Healthy ({healthy})</span>
              <span>Degraded ({degraded})</span>
              <span>Down ({unreachable})</span>
            </div>
            <MiniBar value={healthy}     total={total} color="bg-green-500" />
            <MiniBar value={degraded}    total={total} color="bg-yellow-500" />
            <MiniBar value={unreachable} total={total} color="bg-red-500" />
          </div>
        </>
      )}
    </div>
  )
}
