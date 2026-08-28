/**
 * LiveLogTail — streams a named log file via the /logtail WebSocket endpoint.
 *
 * Fix vs original:
 *   The original computed WS_BASE by stripping /api from VITE_API_BASE and
 *   replacing http → ws. That produced a wrong URL like "ws://localhost:8000"
 *   without the /logtail path. We now use createLogtailSocket() from api.js
 *   which mirrors the same logic as createLogSocket() and works correctly
 *   behind the Vite dev-proxy as well as in production behind nginx.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react'
import { Terminal, Pause, Play, Trash2, Download } from 'lucide-react'
import { createLogtailSocket } from '../api/api.js'

export default function LiveLogTail({
  logName   = 'app',
  lines     = 100,
  maxBuffer = 2000,
  height    = 'h-80',
}) {
  const [buffer, setBuffer]         = useState([])
  const [paused, setPaused]         = useState(false)
  const [connected, setConnected]   = useState(false)
  const wsRef    = useRef(null)
  const endRef   = useRef(null)
  const pausedRef = useRef(false)
  pausedRef.current = paused

  const connect = useCallback(() => {
    wsRef.current?.close()
    const ws = createLogtailSocket(
      logName,
      lines,
      (msg) => {
        if (pausedRef.current) return
        setConnected(true)
        setBuffer((prev) => {
          const next = [...prev, msg]
          return next.length > maxBuffer ? next.slice(-maxBuffer) : next
        })
      },
      () => { setConnected(false); wsRef.current = null },
    )
    ws.onopen = () => setConnected(true)
    ws.onerror = () => setConnected(false)
    wsRef.current = ws
  }, [logName, lines, maxBuffer])

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  // Auto-scroll
  useEffect(() => {
    if (!paused) endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [buffer, paused])

  function handleDownload() {
    const blob = new Blob([buffer.join('')], { type: 'text/plain' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${logName}-tail.log`
    a.click()
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <Terminal size={14} className="text-sky-400" />
        <span className="text-xs font-mono text-slate-600 dark:text-slate-400">{logName}</span>
        <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${
          connected
            ? 'bg-green-900/30 text-green-400 border-green-700/40'
            : 'bg-red-900/30 text-red-400 border-red-700/40'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
          {connected ? 'Live' : 'Disconnected'}
        </span>

        <div className="ml-auto flex items-center gap-1.5">
          <button className="btn-secondary text-xs flex items-center gap-1"
            onClick={() => setPaused((p) => !p)}>
            {paused ? <Play size={11} /> : <Pause size={11} />}
            {paused ? 'Resume' : 'Pause'}
          </button>
          <button className="btn-secondary text-xs flex items-center gap-1"
            onClick={() => setBuffer([])}>
            <Trash2 size={11} /> Clear
          </button>
          <button className="btn-secondary text-xs flex items-center gap-1"
            onClick={handleDownload}>
            <Download size={11} /> Download
          </button>
        </div>
      </div>

      {/* Log window */}
      <div
        className={`${height} overflow-y-auto bg-slate-100 dark:bg-slate-950 rounded-lg border border-slate-200 dark:border-slate-800 p-3 font-mono text-xs text-slate-600 dark:text-slate-300 leading-5`}
      >
        {buffer.length === 0
          ? <span className="text-slate-600">Waiting for log output…</span>
          : buffer.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">{line}</div>
          ))
        }
        <div ref={endRef} />
      </div>
    </div>
  )
}
