/**
 * NodeHealthBadge — inline health pill for a single node.
 * Fix vs original: uses nodesApi.nodeHealth() from the shared api.js
 * instead of a dynamic import that referenced the non-existent healthApi export.
 */
import React, { useEffect, useState, useCallback } from 'react'
import { Activity, Wifi, WifiOff, AlertTriangle } from 'lucide-react'
import { nodesApi } from '../api/api.js'

const STATUS_CFG = {
  healthy:     { icon: Wifi,          color: 'text-green-400',  bg: 'bg-green-900/30 border-green-700/40',   label: 'Healthy'     },
  degraded:    { icon: AlertTriangle, color: 'text-yellow-400', bg: 'bg-yellow-900/30 border-yellow-700/40', label: 'Degraded'    },
  unreachable: { icon: WifiOff,       color: 'text-red-400',    bg: 'bg-red-900/30 border-red-700/40',       label: 'Unreachable' },
  checking:    { icon: Activity,      color: 'text-slate-600 dark:text-slate-400',  bg: 'bg-slate-100 dark:bg-slate-800/50 border-slate-300 dark:border-slate-700/40',   label: 'Checking…'   },
}

export default function NodeHealthBadge({ nodeId, refreshMs = 30_000 }) {
  const [status, setStatus] = useState('checking')

  const check = useCallback(async () => {
    try {
      const data = await nodesApi.nodeHealth(nodeId)
      setStatus(data.status ?? 'unreachable')
    } catch {
      setStatus('unreachable')
    }
  }, [nodeId])

  useEffect(() => {
    check()
    const id = setInterval(check, refreshMs)
    return () => clearInterval(id)
  }, [check, refreshMs])

  const cfg  = STATUS_CFG[status] ?? STATUS_CFG.checking
  const Icon = cfg.icon

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.bg} ${cfg.color}`}
      title={`Health: ${cfg.label}`}
    >
      <Icon size={11} />
      {cfg.label}
    </span>
  )
}
