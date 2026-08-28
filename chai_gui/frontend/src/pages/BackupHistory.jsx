import React, { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { backupApi } from '../api/api.js'
import { History, RotateCcw, Trash2, Eye, RefreshCw, X } from 'lucide-react'

export default function BackupHistory() {
  const [backups, setBackups]   = useState([])
  const [loading, setLoading]   = useState(true)
  const [preview, setPreview]   = useState(null)   // { path, content }
  const [working, setWorking]   = useState(null)

  const fetchBackups = async () => {
    setLoading(true)
    try { setBackups(await backupApi.list()) }
    catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchBackups() }, [])

  const handleRestore = async (bak) => {
    if (!window.confirm(`Restore this backup?\n\n${bak.backup_path}\n→ ${bak.original_path}`)) return
    setWorking(bak.backup_path)
    try {
      await backupApi.restore(bak.backup_path)
      toast.success('Restored successfully.')
      fetchBackups()
    } catch (e) { toast.error(e.message) }
    finally { setWorking(null) }
  }

  const handleDelete = async (bak) => {
    if (!window.confirm('Delete this backup entry?')) return
    setWorking(bak.backup_path)
    try {
      await backupApi.delete(bak.backup_path)
      toast.success('Backup deleted.')
      fetchBackups()
    } catch (e) { toast.error(e.message) }
    finally { setWorking(null) }
  }

  const handlePreview = async (bak) => {
    try {
      const res = await backupApi.read(bak.backup_path)
      setPreview({ path: bak.backup_path, content: res.content })
    } catch (e) { toast.error(e.message) }
  }

  // Group by timestamp
  const grouped = backups.reduce((acc, b) => {
    acc[b.timestamp] = acc[b.timestamp] || []
    acc[b.timestamp].push(b)
    return acc
  }, {})

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Backup History</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{backups.length} backup entries across {Object.keys(grouped).length} snapshots</p>
        </div>
        <button onClick={fetchBackups} className="btn-secondary"><RefreshCw size={13} /> Refresh</button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-sky-500" /></div>
      ) : backups.length === 0 ? (
        <div className="card flex flex-col items-center py-16 text-slate-600">
          <History size={40} className="mb-3 opacity-30" />
          <p className="text-sm">No backups yet.</p>
          <p className="text-xs mt-1">Backups are created automatically when files are modified with "Backup before save" enabled.</p>
        </div>
      ) : (
        Object.entries(grouped).sort(([a], [b]) => b.localeCompare(a)).map(([ts, entries]) => (
          <div key={ts} className="card">
            <div className="flex items-center gap-2 mb-3">
              <History size={13} className="text-sky-400" />
              <span className="text-xs font-mono font-semibold text-sky-400">{ts.replace('_', ' ').replace('_', '.')}</span>
              <span className="text-xs text-slate-600">({entries.length} file{entries.length !== 1 ? 's' : ''})</span>
            </div>
            <div className="space-y-1">
              {entries.map((bak) => (
                <div key={bak.backup_path}
                  className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-800/40 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors group">
                  <div>
                    <p className="text-xs font-mono text-slate-600 dark:text-slate-300">{bak.original_path}</p>
                    <p className="text-[10px] text-slate-600 mt-0.5">{(bak.size_bytes / 1024).toFixed(1)} KB</p>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => handlePreview(bak)}
                      className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-sky-400 transition-colors" title="Preview">
                      <Eye size={13} />
                    </button>
                    <button onClick={() => handleRestore(bak)} disabled={working === bak.backup_path}
                      className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-green-400 transition-colors" title="Restore">
                      <RotateCcw size={13} />
                    </button>
                    <button onClick={() => handleDelete(bak)} disabled={working === bak.backup_path}
                      className="p-1.5 text-slate-600 dark:text-slate-400 hover:text-red-400 transition-colors" title="Delete backup">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl w-full max-w-2xl p-6">
            <div className="flex justify-between mb-3">
              <h2 className="text-xs font-mono text-slate-600 dark:text-slate-400 truncate max-w-md">{preview.path}</h2>
              <button onClick={() => setPreview(null)}><X size={16} className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white" /></button>
            </div>
            <pre className="bg-slate-100 dark:bg-slate-950 rounded-lg p-4 text-xs font-mono text-green-400 overflow-auto max-h-[60vh] whitespace-pre-wrap">
              {preview.content || '(empty)'}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
