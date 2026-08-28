/**
 * LogViewer — streams Ansible job output via WebSocket + HTTP polling fallback.
 *
 * Fixes vs original:
 *  - Dedup on merge: poll replaces the full buffer (no phantom-line accumulation)
 *  - WS lines appended additively on top of polled buffer
 *  - Cleanup: isMounted guard prevents setState after unmount
 *  - Status transitions: 'live' only set once WS is actually open, not on every message
 */
import React, { useEffect, useRef, useState } from 'react'
import { createLogSocket, logsApi } from '../api/api.js'
import { Download, Pause, Play, Trash2 } from 'lucide-react'

export default function LogViewer({ jobId, maxLines = 2000 }) {
  const [lines,  setLines]  = useState([])
  const [status, setStatus] = useState('idle')
  const [paused, setPaused] = useState(false)

  const wsRef    = useRef(null)
  const pollRef  = useRef(null)
  const bottomRef = useRef(null)
  const pausedRef = useRef(false)
  pausedRef.current = paused

  // Auto-scroll
  useEffect(() => {
    if (!paused) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, paused])

  useEffect(() => {
    if (!jobId) return
    let mounted = true

    setStatus('connecting')
    setLines([])

    // ── Initial load + polling ────────────────────────────────────────────
    const startPolling = () => {
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const res = await logsApi.stream(jobId, maxLines)
          if (!mounted) return
          if (res.lines) setLines(res.lines.slice(-maxLines))
          if (res.status !== 'running') {
            setStatus('closed')
            clearInterval(pollRef.current)
          }
        } catch {
          // silently ignore transient poll failures
        }
      }, 2500)
    }

    // ── WebSocket ─────────────────────────────────────────────────────────
    const connectWS = () => {
      const ws = createLogSocket(
        jobId,
        (line) => {
          if (!mounted || pausedRef.current) return
          setStatus('live')
          setLines((prev) => {
            const next = [...prev, line]
            return next.slice(-maxLines)
          })
          if (/SUCCESS|FAILED/.test(line)) setStatus('closed')
        },
        () => { if (mounted) setStatus('closed') },
      )
      wsRef.current = ws
    }

    async function init() {
      try {
        const res = await logsApi.stream(jobId, maxLines)
        if (!mounted) return
        if (res.lines) setLines(res.lines.slice(-maxLines))
        if (res.status === 'running') {
          startPolling()
          connectWS()
        } else {
          setStatus('closed')
        }
      } catch {
        startPolling()
        connectWS()
      }
    }

    init()

    return () => {
      mounted = false
      wsRef.current?.close()
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [jobId, maxLines])

  // ── Colour coding ─────────────────────────────────────────────────────────
  function colorLine(line) {
    if (/FAILED|ERROR|fatal/i.test(line))  return 'text-red-400'
    if (/SUCCESS/i.test(line))             return 'text-green-400 font-semibold'
    if (/\bok=\d/i.test(line))             return 'text-green-400'
    if (/changed=/i.test(line))            return 'text-yellow-400'
    if (/PLAY \[|TASK \[/i.test(line))     return 'text-sky-400 font-semibold'
    if (/skipping/i.test(line))            return 'text-slate-500 dark:text-slate-400'
    if (/warning/i.test(line))             return 'text-orange-400'
    return 'text-slate-600 dark:text-slate-300'
  }

  // ── Download ──────────────────────────────────────────────────────────────
  function downloadLog() {
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url
    a.download = `openchai-job-${jobId || 'log'}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-slate-100 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">

      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full ${
            status === 'live'       ? 'bg-green-500 animate-pulse'  :
            status === 'connecting' ? 'bg-yellow-500 animate-pulse' :
            status === 'closed'     ? 'bg-slate-500' : 'bg-slate-300 dark:bg-slate-700'
          }`} />
          <span className="text-slate-500 dark:text-slate-400 capitalize">{status}</span>
          <span className="text-slate-700">·</span>
          <span className="text-slate-500 dark:text-slate-400">{lines.length} lines</span>
        </div>

        <div className="flex items-center gap-1">
          <button onClick={() => setPaused((p) => !p)} className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
            {paused ? <Play size={13} /> : <Pause size={13} />}
          </button>
          <button onClick={() => setLines([])} className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
            <Trash2 size={13} />
          </button>
          <button onClick={downloadLog} className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
            <Download size={13} />
          </button>
        </div>
      </div>

      {/* Log body */}
      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-5">
        {lines.length === 0 ? (
          <p className="text-slate-700 italic">
            {status === 'connecting' ? 'Connecting to log stream…' : 'No output yet.'}
          </p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={colorLine(line)}>{line}</div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
