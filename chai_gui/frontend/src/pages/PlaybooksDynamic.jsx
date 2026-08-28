import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { playbooksApi } from '../api/api.js'
import LogViewer from '../components/LogViewer.jsx'
import {
  ChevronRight, ChevronDown, Play, Zap, RefreshCw,
  BookOpen, Terminal, Eye, EyeOff, Loader2, X,
} from 'lucide-react'

// ── Category sidebar ──────────────────────────────────────────────────────────
function CategorySidebar({ categories, selected, onSelect }) {
  return (
    <div className="w-52 shrink-0 space-y-1">
      <p className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold px-2 mb-2">
        Playbook Library
      </p>
      {categories.map((cat) => (
        <button key={cat.name} onClick={() => onSelect(cat.name)}
          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
            selected === cat.name
              ? 'bg-sky-600/20 text-sky-400 border border-sky-600/30'
              : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}>
          <div className="flex items-center gap-2">
            <BookOpen size={13} />
            <span className="capitalize">{cat.name}</span>
          </div>
          <span className="text-[10px] text-slate-600">{cat.count}</span>
        </button>
      ))}
    </div>
  )
}

// ── Dynamic form for playbook vars ────────────────────────────────────────────
function VarsForm({ fields, values, onChange }) {
  const [showPwd, setShowPwd] = useState({})
  if (!fields || fields.length === 0) return (
    <p className="text-xs text-slate-600 italic">No configurable variables found in this playbook.</p>
  )
  return (
    <div className="grid grid-cols-2 gap-3">
      {fields.map((f) => (
        <div key={f.name}>
          <label className="label">{f.label}</label>
          {f.type === 'boolean' ? (
            <select className="input" value={String(values[f.name] ?? f.default)}
              onChange={(e) => onChange(f.name, e.target.value === 'true')}>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : f.type === 'password' ? (
            <div className="relative">
              <input className="input pr-9" type={showPwd[f.name] ? 'text' : 'password'}
                value={values[f.name] ?? ''}
                onChange={(e) => onChange(f.name, e.target.value)}
                placeholder={f.sensitive ? '••••••' : String(f.default ?? '')} />
              <button type="button" onClick={() => setShowPwd((s) => ({ ...s, [f.name]: !s[f.name] }))}
                className="absolute right-2 top-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-300">
                {showPwd[f.name] ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>
          ) : (
            <input className="input" type={f.type === 'number' ? 'number' : 'text'}
              value={values[f.name] ?? ''}
              onChange={(e) => onChange(f.name, e.target.value)}
              placeholder={String(f.default ?? '')} />
          )}
        </div>
      ))}
    </div>
  )
}

// ── Playbook execution panel ──────────────────────────────────────────────────
function PlaybookRunner({ playbook, category, onClose }) {
  const navigate = useNavigate()
  const [detail, setDetail]       = useState(null)
  const [loading, setLoading]     = useState(true)
  const [varVals, setVarVals]     = useState({})
  const [groups, setGroups]       = useState({ groups: [], hostnames: [] })
  const [limit, setLimit]         = useState('')
  const [dryRun, setDryRun]       = useState(false)
  const [verbosity, setVerbosity] = useState(0)
  const [jobId, setJobId]         = useState(null)
  const [launching, setLaunching] = useState(false)

  useEffect(() => {
    let cancelled = false   // FIX 11: guard against a stale response after the user switches away

    async function load() {
      setLoading(true)
      try {
        const [det, grp] = await Promise.all([
          playbooksApi.detail(category, playbook.rel_path.split('/').slice(1).join('/')),
          playbooksApi.groups(),
        ])
        if (cancelled) return
        setDetail(det)
        setGroups(grp)
        // Pre-fill defaults
        const defaults = {}
        for (const f of det.form_fields || []) {
          defaults[f.name] = f.type !== 'password' ? (f.default ?? '') : ''
        }
        setVarVals(defaults)
      } catch (e) {
        if (!cancelled) toast.error(e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()

    return () => { cancelled = true }
  }, [playbook, category])

  const setVar = (k, v) => setVarVals((prev) => ({ ...prev, [k]: v }))

  const handleRun = async () => {
    setLaunching(true)
    try {
      // Filter out empty values
      const extra = Object.fromEntries(
        Object.entries(varVals).filter(([, v]) => v !== '' && v !== null && v !== undefined)
      )
      const res = await playbooksApi.execute({
        playbook_rel_path: playbook.rel_path,
        extra_vars: Object.keys(extra).length ? extra : null,
        limit: limit || null,
        dry_run: dryRun,
        verbosity,
      })
      toast.success(`Job started: ${res.job_id.slice(0, 8)}…`)
      setJobId(res.job_id)
    } catch (e) { toast.error(e.message) }
    finally { setLaunching(false) }
  }

  if (loading) return (
    <div className="flex-1 flex items-center justify-center">
      <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-sky-500" />
    </div>
  )

  return (
    <div className="flex-1 overflow-y-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">{detail?.name || playbook.name}</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-0.5">{playbook.rel_path}</p>
        </div>
        <button onClick={onClose} className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"><X size={16} /></button>
      </div>

      {/* If already launched, show log */}
      {jobId ? (
        <div className="h-96">
          <LogViewer jobId={jobId} />
        </div>
      ) : (
        <>
          {/* Variables form */}
          {(detail?.form_fields?.length > 0) && (
            <div className="card">
              <h3 className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide mb-3">Playbook Variables</h3>
              <VarsForm fields={detail.form_fields} values={varVals} onChange={setVar} />
            </div>
          )}

          {/* Execution options */}
          <div className="card space-y-4">
            <h3 className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide">Execution Options</h3>

            {/* Node / group selection */}
            <div>
              <label className="label">Target (--limit)  — leave blank to run on all hosts</label>
              <div className="flex gap-2">
                <input className="input flex-1" value={limit}
                  onChange={(e) => setLimit(e.target.value)}
                  placeholder="hostname or group name" />
                <select className="input w-48" value={limit} onChange={(e) => setLimit(e.target.value)}>
                  <option value="">— Select group —</option>
                  {groups.groups.map((g) => (
                    <option key={g} value={g}>{g} (group)</option>
                  ))}
                  {groups.hostnames.map((h) => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center gap-6">
              {/* Dry run */}
              <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-slate-600 dark:text-slate-400">
                <button type="button" onClick={() => setDryRun((d) => !d)}
                  className={`relative w-9 h-5 rounded-full transition-colors ${dryRun ? 'bg-yellow-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
                  <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${dryRun ? 'translate-x-4' : ''}`} />
                </button>
                <Zap size={13} className={dryRun ? 'text-yellow-400' : 'text-slate-600'} />
                Dry Run
              </label>

              {/* Verbosity */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 dark:text-slate-400">Verbosity:</span>
                {[0,1,2,3,4].map((v) => (
                  <button key={v} onClick={() => setVerbosity(v)}
                    className={`w-7 h-6 text-xs rounded ${verbosity === v ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 dark:hover:bg-slate-700'}`}>
                    {v === 0 ? 'off' : `${v}v`}
                  </button>
                ))}
              </div>
            </div>

            {dryRun && (
              <p className="text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800 rounded px-3 py-2">
                ⚡ Dry run mode — Ansible will run with <code>--check</code>. No changes will be applied.
              </p>
            )}

            {/* Run button */}
            <div className="flex gap-3 pt-2">
              <button onClick={handleRun} disabled={launching}
                className={`btn-primary ${dryRun ? 'bg-yellow-600 hover:bg-yellow-500' : ''}`}>
                {launching ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                {launching ? 'Launching…' : dryRun ? 'Dry Run' : 'Run Playbook'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function PlaybooksDynamic() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [categories, setCategories] = useState([])
  const [playbooks, setPlaybooks]   = useState([])
  const [loading, setLoading]       = useState(true)
  const [loadingPbs, setLoadingPbs] = useState(false)
  const [selected, setSelected]     = useState(searchParams.get('cat') || '')
  const [activePlaybook, setActivePlaybook] = useState(null)

  const fetchCategories = async () => {
    setLoading(true)
    try {
      const res = await playbooksApi.categories()
      setCategories(res.categories || [])
      // Auto-select first category
      if (!selected && res.categories?.length > 0) {
        setSelected(res.categories[0].name)
      }
    } catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchCategories() }, [])

  useEffect(() => {
    if (!selected) return
    let cancelled = false   // FIX 11: guard against a stale response after a rapid category switch
    setActivePlaybook(null)
    setLoadingPbs(true)
    playbooksApi.category(selected)
      .then((res) => { if (!cancelled) setPlaybooks(res.playbooks || []) })
      .catch((e) => { if (!cancelled) toast.error(e.message) })
      .finally(() => { if (!cancelled) setLoadingPbs(false) })
    setSearchParams({ cat: selected })
    return () => { cancelled = true }
  }, [selected])

  return (
    <div className="flex gap-5 h-[calc(100vh-8rem)]">
      {/* Sidebar */}
      <div className="w-52 shrink-0 overflow-y-auto">
        <div className="flex items-center justify-between mb-2">
          <p className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold px-1">Playbook Library</p>
          <button onClick={fetchCategories} className="text-slate-600 hover:text-slate-900 dark:hover:text-slate-300">
            <RefreshCw size={11} />
          </button>
        </div>
        {loading ? (
          <div className="flex justify-center py-8"><div className="animate-spin rounded-full h-5 w-5 border-b-2 border-sky-500" /></div>
        ) : categories.length === 0 ? (
          <p className="text-xs text-slate-600 text-center mt-4">No playbook directories found.</p>
        ) : (
          categories.map((cat) => (
            <button key={cat.name} onClick={() => setSelected(cat.name)}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors mb-1 ${
                selected === cat.name
                  ? 'bg-sky-600/20 text-sky-400 border border-sky-600/30'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}>
              <div className="flex items-center gap-2 min-w-0">
                <BookOpen size={12} className="shrink-0" />
                <span className="capitalize truncate">{cat.name}</span>
              </div>
              <span className="text-[10px] text-slate-600 shrink-0 ml-1">{cat.count}</span>
            </button>
          ))
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {activePlaybook ? (
          <PlaybookRunner
            playbook={activePlaybook}
            category={selected}
            onClose={() => setActivePlaybook(null)}
          />
        ) : (
          <>
            <div className="flex items-center gap-2 mb-4">
              <h2 className="text-base font-semibold capitalize text-slate-900 dark:text-slate-100">{selected || 'Select a category'}</h2>
              {selected && <span className="text-xs text-slate-600">({playbooks.length} playbooks)</span>}
            </div>
            {loadingPbs ? (
              <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-sky-500" />
              </div>
            ) : playbooks.length === 0 ? (
              <div className="card flex flex-col items-center py-16 text-slate-600">
                <BookOpen size={36} className="mb-3 opacity-30" />
                <p className="text-sm">{selected ? `No playbooks in '${selected}'` : 'Select a category from the sidebar.'}</p>
              </div>
            ) : (
              <div className="overflow-y-auto space-y-1">
                {playbooks.map((pb) => (
                  <button key={pb.rel_path} onClick={() => setActivePlaybook(pb)}
                    className="w-full flex items-center justify-between px-4 py-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-sky-700/50 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors group text-left">
                    <div>
                      <p className="text-sm font-mono text-slate-800 dark:text-slate-200">{pb.name}</p>
                      <p className="text-[11px] text-slate-600 mt-0.5">{pb.display_path}</p>
                    </div>
                    <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <span className="text-xs text-sky-400 flex items-center gap-1">
                        <Terminal size={12} /> Configure & Run
                      </span>
                      <ChevronRight size={14} className="text-sky-400" />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}