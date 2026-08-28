/**
 * OpenCHAI — CHAI Release Wizard  (v6)
 *
 * v6 — replaces the old sequential Next/Back wizard with a single-page,
 * 3-tab interface per the "Modify the CHAI RELEASE WIZARD page" change
 * request. Each tab is independent — the user can jump straight to any
 * tab without clicking through unrelated screens first.
 *
 * Tab 1  OpenCHAI Packages        — auth, arch/OS, version select + install
 * Tab 2  HPC-AI Container Tools   — container image browse + download
 * Tab 3  Cluster Configuration    — edit group_vars/all.yml, gated on a
 *                                   local OpenCHAI package being installed
 *
 * Full GUI port of:
 *   configure_openchai_manager.py  (auth, OS, releases, versions, execute)
 *   container_img_selector.py      (container image download)
 *
 * Auth is genuinely validated server-side before "Auth applied" is shown.
 * "Skip auth" path: on auth failure, continue with locally-installed
 * releases only. Wizard state persists in sessionStorage so a refresh
 * doesn't lose progress.
 */

import React, { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Package, CheckCircle2, XCircle,
  AlertTriangle, Terminal, RotateCcw, Lock, Info, Loader2,
  Download, Server, Layers, HardDrive, Container, RefreshCw,
  ShieldOff, Shield, FolderOpen, CheckSquare, Square, SkipForward,
  X, Settings, Save, ArrowRight,
} from 'lucide-react'
import { chaiReleaseApi, wizardInfoApi, clusterSetupApi, createLogSocket } from '../api/api.js'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ─── Constants ────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'packages',       label: 'OpenCHAI Packages',      icon: Package  },
  { id: 'containers',     label: 'HPC-AI Container Tools', icon: Container },
  { id: 'cluster-config', label: 'Cluster Configuration',  icon: Settings },
]

// sessionStorage key for wizard-state persistence across refresh.
const WIZARD_STATE_KEY = 'openchai_chai_release_wizard_state_v2'

const JOB_POLL_MS = 2500

// Config keys that update_all_yml() (services/chai_release_service.py) writes
// after a successful install — these are exactly what the Cluster
// Configuration tab needs to check for / pre-fill.
const REQUIRED_ALL_YML_FIELDS = ['version', 'os_label', 'rhel_label', 'el_label', 'arch']

// ─── Small helpers ────────────────────────────────────────────────────────────

function Card({ children, className = '' }) {
  return <div className={`card ${className}`}>{children}</div>
}

function SectionTitle({ children }) {
  return <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-4">{children}</h2>
}

function Spinner() {
  return <div className="flex justify-center py-10"><Loader2 size={26} className="animate-spin text-sky-400" /></div>
}

function EmptyMsg({ children }) {
  return <p className="text-sm text-slate-500 dark:text-slate-400 py-4">{children}</p>
}

function Pill({ ok, label, variant }) {
  const v = variant || (ok ? 'local' : 'remote')
  const styles = {
    'local':      'bg-green-900/30 text-green-400 border-green-700/40',
    'local-only': 'bg-amber-900/30 text-amber-400 border-amber-700/40',
    'remote':     'bg-slate-100 dark:bg-slate-800    text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-700',
  }
  const icons = {
    'local':      <CheckCircle2 size={11}/>,
    'local-only': <HardDrive    size={11}/>,
    'remote':     <HardDrive    size={11}/>,
  }
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${styles[v]}`}>
      {icons[v]}
      {label}
    </span>
  )
}

function SelectList({ items, selected, onSelect, getKey, getLabel, getSub, getBadge, getSize }) {
  if (!items.length) return null
  return (
    <div className="space-y-1.5">
      {items.map(item => {
        const key = getKey(item)
        const active = selected === key
        const size = getSize ? getSize(item) : ''
        return (
          <button key={key} onClick={() => onSelect(key, item)}
            className={`w-full text-left px-4 py-3 rounded-lg border transition-all ${
              active ? 'border-sky-500 bg-sky-900/20' : 'border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-slate-500'
            }`}>
            <div className="flex items-center justify-between">
              <div>
                <p className={`font-mono text-sm ${active ? 'text-sky-300' : 'text-slate-600 dark:text-slate-300'}`}>{getLabel(item)}</p>
                {getSub && <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{getSub(item)}</p>}
              </div>
              <div className="flex items-center gap-2">
                {size && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700">
                    <HardDrive size={10}/> {size}
                  </span>
                )}
                {getBadge && getBadge(item)}
                {active && <CheckCircle2 size={15} className="text-sky-400"/>}
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}

function JobPanel({ job }) {
  const bottomRef = useRef(null)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [job?.log])

  if (!job) return null
  const isRunning = job.status === 'running'
  const isOk      = job.status === 'success' || job.status === 'partial'

  return (
    <div className="space-y-3">
      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium ${
        isOk      ? 'bg-green-900/20 border-green-700 text-green-300'
        : job.status === 'failed'
                  ? 'bg-red-900/20 border-red-700 text-red-300'
                  : 'bg-sky-900/20 border-sky-700 text-sky-300'
      }`}>
        {isRunning ? <Loader2 size={15} className="animate-spin"/> : isOk ? <CheckCircle2 size={15}/> : <XCircle size={15}/>}
        Job {job.job_id?.slice(0, 8)} — {job.status}
      </div>

      {(job.log || []).length > 0 && (
        <div className="bg-slate-100 dark:bg-slate-950 rounded-lg border border-slate-200 dark:border-slate-800 p-4 font-mono text-xs text-slate-600 dark:text-slate-300 leading-5 max-h-72 overflow-y-auto">
          {job.log.map((line, i) => (
            <div key={i} className={
              /❌|FAILED|ERROR/i.test(line) ? 'text-red-400' :
              /✅|SUCCESS/i.test(line)      ? 'text-green-400' :
              /⚠|WARNING/i.test(line)      ? 'text-yellow-400' :
              /⬇|📦|🔧/i.test(line)        ? 'text-sky-400' :
              'text-slate-600 dark:text-slate-300'
            }>{line}</div>
          ))}
          <div ref={bottomRef}/>
        </div>
      )}
    </div>
  )
}

// ─── Wizard state persistence (sessionStorage) ────────────────────────────────
const PERSIST_KEYS = [
  'activeTab', 'authType', 'username', 'verifySSL', 'authSaved', 'skipAuth',
  'selArch', 'selDist', 'selVersion', 'selRelease', 'updateConfigs',
]

function loadPersistedState() {
  try {
    const raw = sessionStorage.getItem(WIZARD_STATE_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function savePersistedState(partial) {
  try {
    const existing = loadPersistedState() || {}
    sessionStorage.setItem(WIZARD_STATE_KEY, JSON.stringify({ ...existing, ...partial }))
  } catch {
    /* sessionStorage unavailable (private mode, quota) — fail silently */
  }
}

function clearPersistedState() {
  try { sessionStorage.removeItem(WIZARD_STATE_KEY) } catch { /* ignore */ }
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ChaiReleaseWizard() {
  const persisted = loadPersistedState()

  // Active tab — replaces the old step index. Any tab is reachable at any time.
  const [activeTab, setActiveTab] = useState(persisted?.activeTab ?? 'packages')
  // Tab the user is trying to move to while an exit-confirmation is pending
  // (Cluster Configuration tab only — see handleTabChange below).
  const [pendingTab, setPendingTab] = useState(null)
  const [showExitConfirm, setShowExitConfirm] = useState(false)

  // ── Auth & OS ─────────────────────────────────────────────────────────────
  const [authType, setAuthType]   = useState(persisted?.authType ?? 'basic')
  const [username, setUsername]   = useState(persisted?.username ?? '')
  const [password, setPassword]   = useState('')   // never persisted
  const [token, setToken]         = useState('')   // never persisted
  const [verifySSL, setVerifySSL] = useState(persisted?.verifySSL ?? false)
  const [authSaved, setAuthSaved] = useState(persisted?.authSaved ?? false)
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState('')
  const [sysInfo, setSysInfo]     = useState(null)
  const [skipAuth, setSkipAuth]   = useState(persisted?.skipAuth ?? false)

  // ── Arch & Distribution ───────────────────────────────────────────────────
  const [archs, setArchs]         = useState([])
  const [selArch, setSelArch]     = useState(persisted?.selArch ?? '')
  const [dists, setDists]         = useState([])
  const [selDist, setSelDist]     = useState(persisted?.selDist ?? '')
  const [loadingArchs, setLoadingArchs] = useState(false)
  const [loadingDists, setLoadingDists] = useState(false)

  // ── Release notes (optional, informational — collapsible panel) ──────────
  const [releaseNotes, setReleaseNotes]       = useState([])
  const [loadingReleaseNotes, setLoadingReleaseNotes] = useState(false)
  const [releaseNotesOpen, setReleaseNotesOpen] = useState(false)
  const [releaseNotesLoaded, setReleaseNotesLoaded] = useState(false)
  const [selRelease, setSelRelease]           = useState(persisted?.selRelease ?? null)
  const [releaseContent, setReleaseContent]   = useState('')
  const [loadingReleaseContent, setLoadingReleaseContent] = useState(false)

  // ── OpenCHAI Version (+ per-version release assets) ──────────────────────
  const [versions, setVersions]       = useState([])
  const [selVersion, setSelVersion]   = useState(persisted?.selVersion ?? null)
  const [loadingVersions, setLoadingVersions] = useState(false)
  const [versionReleaseData, setVersionReleaseData] = useState(null)
  const [loadingVersionReleases, setLoadingVersionReleases] = useState(false)
  const [updateConfigs, setUpdateConfigs] = useState(persisted?.updateConfigs ?? true)

  // ── Install / Execute ─────────────────────────────────────────────────────
  const [execJob, setExecJob]     = useState(null)
  const [executing, setExecuting] = useState(false)
  const [execError, setExecError] = useState('')

  // ── Container images ───────────────────────────────────────────────────────
  const [ctTools, setCtTools]         = useState([])
  const [ctVersions, setCtVersions]   = useState({})
  const [ctSelVer, setCtSelVer]       = useState({})
  const [ctImages, setCtImages]       = useState({})
  const [ctSelImgs, setCtSelImgs]     = useState({})
  const [ctLoadingVer, setCtLoadingVer]   = useState({})
  const [ctLoadingImg, setCtLoadingImg]   = useState({})
  const [ctJob, setCtJob]             = useState(null)
  const [ctExecuting, setCtExecuting] = useState(false)

  // ── Cluster Configuration tab ─────────────────────────────────────────────
  const [installStatus, setInstallStatus]         = useState(null)
  const [installStatusLoading, setInstallStatusLoading] = useState(false)
  const [configLaterAck, setConfigLaterAck]       = useState(false)
  const [allYmlVars, setAllYmlVars]               = useState(null)
  const [allYmlLoading, setAllYmlLoading]         = useState(false)
  const [allYmlSaving, setAllYmlSaving]           = useState(false)
  const [configTouched, setConfigTouched]         = useState(false)
  const [configSaved, setConfigSaved]             = useState(false)

  // ── Info sidebar (per-section Markdown help) ─────────────────────────────
  const [sectionInfo, setSectionInfo] = useState({})
  const [infoOpen, setInfoOpen]       = useState(true)

  useEffect(() => {
    wizardInfoApi.all().then(setSectionInfo).catch(() => {})
  }, [])

  // ── Persist wizard state on every relevant change ────────────────────────
  useEffect(() => {
    savePersistedState({
      activeTab, authType, username, verifySSL, authSaved, skipAuth,
      selArch, selDist, selVersion, selRelease, updateConfigs,
    })
  }, [activeTab, authType, username, verifySSL, authSaved, skipAuth,
      selArch, selDist, selVersion, selRelease, updateConfigs])

  useEffect(() => {
    chaiReleaseApi.systemInfo().then(setSysInfo).catch(() => {})
  }, [])

  const didInitArchEffect    = useRef(false)
  const didInitDistEffect    = useRef(false)
  const prevSelArch          = useRef(selArch)

  useEffect(() => {
    if (!authSaved) return
    setLoadingArchs(true)
    const loader = skipAuth
      ? chaiReleaseApi.localArchitectures()
      : chaiReleaseApi.architectures(verifySSL || null)
    loader
      .then(d => {
        setArchs(d?.architectures || [])
        if (didInitArchEffect.current) {
          setSelArch('')
          setDists([])
          setSelDist('')
        }
        didInitArchEffect.current = true
      })
      .catch(e => toast.error(`Arch load: ${e.message}`))
      .finally(() => setLoadingArchs(false))
  }, [authSaved, verifySSL, skipAuth])

  useEffect(() => {
    if (!selArch) return
    const archActuallyChanged = didInitDistEffect.current && prevSelArch.current !== selArch
    prevSelArch.current = selArch

    setLoadingDists(true)
    const loader = skipAuth
      ? chaiReleaseApi.localDistributions(selArch)
      : chaiReleaseApi.distributions(selArch, verifySSL || null)
    loader
      .then(d => {
        setDists(d?.distributions || [])
        if (archActuallyChanged) setSelDist('')
        didInitDistEffect.current = true
      })
      .catch(e => toast.error(`Dist load: ${e.message}`))
      .finally(() => setLoadingDists(false))
  }, [selArch, verifySSL, skipAuth])

  useEffect(() => {
    if (!releaseNotesOpen || releaseNotesLoaded) return
    setLoadingReleaseNotes(true)
    chaiReleaseApi.releaseNotes()
      .then((d) => setReleaseNotes(d?.releases || []))
      .catch((e) => toast.error(`Release notes load: ${e.message}`))
      .finally(() => { setLoadingReleaseNotes(false); setReleaseNotesLoaded(true) })
  }, [releaseNotesOpen, releaseNotesLoaded])

  const didInitVersionEffect = useRef(false)
  useEffect(() => {
    if (!selArch || !selDist) return

    setLoadingVersions(true)

    chaiReleaseApi
      .versions(selArch, selDist, verifySSL || null)
      .then((d) => {
        let items = d?.versions || []
        if (skipAuth) items = items.filter((v) => v.installed)
        setVersions(items)
        if (didInitVersionEffect.current) setSelVersion(null)
        didInitVersionEffect.current = true
      })
      .catch((e) => toast.error(`Version load: ${e.message}`))
      .finally(() => setLoadingVersions(false))

  }, [selArch, selDist, verifySSL, skipAuth])

  useEffect(() => {
    if (!selArch || !selDist || !selVersion || skipAuth) {
      setVersionReleaseData(null)
      return
    }

    setLoadingVersionReleases(true)
    setVersionReleaseData(null)

    chaiReleaseApi
      .releases(selArch, selDist, selVersion.version, verifySSL || null)
      .then(setVersionReleaseData)
      .catch((e) => toast.error(`Release asset load: ${e.message}`))
      .finally(() => setLoadingVersionReleases(false))

  }, [selArch, selDist, selVersion, verifySSL, skipAuth])

  useEffect(() => {
    if (activeTab !== 'containers' || ctTools.length) return
    chaiReleaseApi.containerTools()
      .then(d => setCtTools(d?.tools || []))
      .catch(() => {})
  }, [activeTab, ctTools.length])

  // ─── Cluster Configuration tab: check install status on open ─────────────
  useEffect(() => {
    if (activeTab !== 'cluster-config') return

    setInstallStatusLoading(true)
    chaiReleaseApi.localInstallStatus()
      .then(async (status) => {
        setInstallStatus(status)

        const hasRequired = status?.installed && REQUIRED_ALL_YML_FIELDS.every(f => status[f])

        if (!hasRequired) {
          if (status?.installed) {
            toast.error('Installed package is missing required configuration values — switching to OpenCHAI Packages.')
          }
          setActiveTab('packages')
          return
        }

        setAllYmlLoading(true)
        try {
          const loaded = await clusterSetupApi.loadVars()
          const allYml = loaded?.files?.['all.yml']?.variables || {}
          setAllYmlVars(allYml)
        } catch (e) {
          toast.error(`all.yml load failed: ${e.message}`)
          setAllYmlVars({})
        } finally {
          setAllYmlLoading(false)
        }
      })
      .catch((e) => {
        toast.error(`Install status check failed: ${e.message}`)
        setActiveTab('packages')
      })
      .finally(() => setInstallStatusLoading(false))
  }, [activeTab])

  useJobPoll(execJob, setExecJob)
  useJobPoll(ctJob,   setCtJob)

  // ─── Handlers ─────────────────────────────────────────────────────────────

  async function handleSaveAuth() {
    if (authType === 'basic' && (!username || !password)) {
      setAuthError('Username and password are required for Basic auth.')
      return
    }
    if (authType === 'bearer' && !token) {
      setAuthError('Token is required for Bearer auth.')
      return
    }
    setAuthError('')
    setAuthLoading(true)
    try {
      const authResult = await chaiReleaseApi.persistAuth({ type: authType, username, password, token })
      if (authResult?.success === false || authResult?.error) {
        setAuthSaved(false)
        setAuthError(authResult?.error || 'Registry authentication failed. Please check your username and password.')
        toast.error('Registry authentication failed.')
        return
      }
      chaiReleaseApi.setAuth({ type: authType, username, password, token })
      setAuthSaved(true)
      setSkipAuth(false)
      toast.success('Auth applied — loading registry…')
    } catch (e) {
      setAuthSaved(false)
      setAuthError(
        e.message || 'Registry authentication failed. Please check your credentials.'
      )
      toast.error('Registry authentication failed.')
    } finally {
      setAuthLoading(false)
    }
  }

  /**
   * "Skip authentication, use local releases only" — offered after an auth
   * failure. Crucially, this NEVER logs the user out of the app or bounces
   * them to /login — a registry auth failure is scoped entirely to this
   * tab (see Issue #5 fix).
   */
  function handleSkipAuth() {
    setAuthSaved(true)
    setSkipAuth(true)
    setAuthError('')
    chaiReleaseApi.setAuth({ type: 'none', username: '', password: '', token: '' })
    toast.success('Continuing with local releases only.')
  }

  async function handleExecute() {
    if (!selVersion) return
    setExecuting(true)
    setExecError('')
    setExecJob(null)
    try {
      const res = await chaiReleaseApi.execute({
        tarball_url:      selVersion.url,
        tarball_name:     selVersion.name,
        os_dist:          selDist,
        os_arch:          selArch,
        openchai_version: selVersion.version,
        os_label:         sysInfo?.os_label || selDist,
        rhel_label:       sysInfo?.rhel_label || '',
        el_label:         sysInfo?.el_label || '',
        kernel:           sysInfo?.kernel_short || sysInfo?.kernel || '',
        verify_ssl:       verifySSL || null,
        update_configs:   updateConfigs,
      })
      setExecJob({ job_id: res.job_id, status: 'running', log: [] })
    } catch (e) {
      setExecError(e.message)
      toast.error(e.message)
    } finally {
      setExecuting(false)
    }
  }

  async function loadCtVersions(tool) {
    setCtLoadingVer(p => ({ ...p, [tool]: true }))
    try {
      const d = await chaiReleaseApi.containerVersions(tool, selDist, verifySSL || null)
      setCtVersions(p => ({ ...p, [tool]: d?.versions || [] }))
    } catch (e) {
      toast.error(`${tool} versions: ${e.message}`)
    } finally {
      setCtLoadingVer(p => ({ ...p, [tool]: false }))
    }
  }

  async function loadCtImages(tool, version) {
    setCtLoadingImg(p => ({ ...p, [tool]: true }))
    try {
      const d = await chaiReleaseApi.containerImages(tool, selDist, version, verifySSL || null)
      setCtImages(p => ({ ...p, [tool]: d?.images || [] }))
      setCtSelImgs(p => ({ ...p, [tool]: new Set() }))
    } catch (e) {
      toast.error(`${tool} images: ${e.message}`)
    } finally {
      setCtLoadingImg(p => ({ ...p, [tool]: false }))
    }
  }

  function toggleCtImage(tool, imgName) {
    setCtSelImgs(p => {
      const s = new Set(p[tool] || [])
      s.has(imgName) ? s.delete(imgName) : s.add(imgName)
      return { ...p, [tool]: s }
    })
  }

  async function handleCtExecute() {
    const downloads = []
    for (const tool of ctTools) {
      const imgs   = ctImages[tool]   || []
      const sel    = ctSelImgs[tool]  || new Set()
      const ver    = ctSelVer[tool]   || ''
      imgs.filter(img => sel.has(img.name))
          .forEach(img => downloads.push({ tool, name: img.name, url: img.url, version: ver }))
    }
    if (!downloads.length) { toast.error('No images selected.'); return }
    setCtExecuting(true)
    try {
      const res = await chaiReleaseApi.containerExecute({
        downloads, os_dist: selDist, verify_ssl: verifySSL || null,
      })
      setCtJob({ job_id: res.job_id, status: 'running', log: [] })
    } catch (e) {
      toast.error(e.message)
    } finally {
      setCtExecuting(false)
    }
  }

  function handleAllYmlFieldChange(key, value) {
    setAllYmlVars(p => ({ ...(p || {}), [key]: value }))
    setConfigTouched(true)
    setConfigSaved(false)
  }

  async function handleSaveAllYml() {
    setAllYmlSaving(true)
    try {
      await clusterSetupApi.updateVars({ file_name: 'all.yml', variables: allYmlVars || {} })
      toast.success('group_vars/all.yml updated.')
      setConfigSaved(true)
      setConfigTouched(false)
    } catch (e) {
      toast.error(`Save failed: ${e.message}`)
    } finally {
      setAllYmlSaving(false)
    }
  }

  /**
   * Exit Behavior (Cluster Configuration tab):
   * If the user tries to leave this tab before saving edits, show a
   * confirmation dialog the user must acknowledge before the tab changes.
   */
  function handleTabChange(nextTab) {
    if (activeTab === 'cluster-config' && configTouched && !configSaved) {
      setPendingTab(nextTab)
      setShowExitConfirm(true)
      return
    }
    setActiveTab(nextTab)
  }

  function acknowledgeExitAndSwitch() {
    setShowExitConfirm(false)
    setConfigTouched(false)
    if (pendingTab) setActiveTab(pendingTab)
    setPendingTab(null)
  }

  const TAB_INFO_KEY = { packages: 'version', containers: 'containers', 'cluster-config': 'execute' }
  const currentInfo = sectionInfo[TAB_INFO_KEY[activeTab]] || ''

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="w-full">
      <div className="flex gap-6 items-start">
        <div className="flex-1 min-w-0 space-y-6">

          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Package size={22} className="text-sky-400"/>
              <div>
                <h1 className="text-xl font-bold text-slate-900 dark:text-white">CHAI Release Wizard</h1>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Configure &amp; install OpenCHAI releases from the registry
                </p>
              </div>
            </div>
            <button
              onClick={() => setInfoOpen((v) => !v)}
              className={`hidden lg:flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                infoOpen ? 'bg-sky-900/30 text-sky-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:text-slate-200'
              }`}
            >
              <Info size={13}/> {infoOpen ? 'Hide info' : 'Show info'}
            </button>
          </div>

          {/* Tab bar — all three tabs are always independently reachable */}
          <div className="flex items-center gap-1 overflow-x-auto pb-1 border-b border-slate-200 dark:border-slate-800">
            {TABS.map((t) => {
              const Icon = t.icon
              const isActive = activeTab === t.id
              return (
                <button
                  key={t.id}
                  onClick={() => handleTabChange(t.id)}
                  className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-all border-b-2 -mb-px ${
                    isActive
                      ? 'border-sky-500 text-sky-500'
                      : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                  }`}
                >
                  <Icon size={14}/> {t.label}
                </button>
              )
            })}
          </div>

          {/* ══════════════════════════ TAB 1: OpenCHAI Packages ══════════════ */}
          {activeTab === 'packages' && (
            <div className="space-y-6">

              <Card>
                <SectionTitle>Registry Authentication</SectionTitle>

                {authSaved ? (
                  <div className={`p-3 rounded-lg text-sm flex items-center justify-between gap-2 ${
                    skipAuth
                      ? 'bg-amber-900/20 border border-amber-700/40 text-amber-300'
                      : 'bg-green-900/20 border border-green-700/40 text-green-300'
                  }`}>
                    <span className="flex items-center gap-2">
                      {skipAuth ? <SkipForward size={14}/> : <CheckCircle2 size={14}/>}
                      {skipAuth
                        ? 'Continuing with local releases only — registry features are unavailable for this session.'
                        : 'Auth applied — registry loaded.'}
                    </span>
                    <button
                      onClick={() => { setAuthSaved(false); setSkipAuth(false) }}
                      className="text-xs underline opacity-80 hover:opacity-100"
                    >
                      Change
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="mb-4">
                      <button type="button" onClick={() => setVerifySSL(v => !v)}
                        className="flex items-center gap-3 group">
                        <span className={`relative w-9 h-5 rounded-full transition-colors ${verifySSL ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
                          <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${verifySSL ? 'translate-x-4' : ''}`}/>
                        </span>
                        <span className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
                          {verifySSL ? <Shield size={13} className="text-sky-400"/> : <ShieldOff size={13} className="text-yellow-500"/>}
                          {verifySSL ? 'Verify SSL certificate (on)' : 'SSL verification disabled (for self-signed certs)'}
                        </span>
                      </button>
                      {!verifySSL && (
                        <p className="text-xs text-yellow-500/80 mt-1.5 ml-12">
                          ⚠ Recommended for self-signed registry certificates. Enable when a valid cert is installed.
                        </p>
                      )}
                    </div>

                    <div className="space-y-3">
                      <div>
                        <label className="label">Auth Type</label>
                        <select className="input" value={authType} onChange={e => setAuthType(e.target.value)}>
                          <option value="none">None (public registry)</option>
                          <option value="basic">Basic (username + password)</option>
                          <option value="bearer">Bearer Token</option>
                        </select>
                      </div>

                      {authType === 'basic' && (
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="label">Username</label>
                            <input className="input" value={username}
                              onChange={e => setUsername(e.target.value)} placeholder="username"/>
                          </div>
                          <div>
                            <label className="label">Password</label>
                            <input className="input" type="password" value={password}
                              onChange={e => setPassword(e.target.value)} placeholder="••••••"/>
                          </div>
                        </div>
                      )}

                      {authType === 'bearer' && (
                        <div>
                          <label className="label">Bearer Token</label>
                          <input className="input" value={token}
                            onChange={e => setToken(e.target.value)} placeholder="eyJ…"/>
                        </div>
                      )}
                    </div>

                    {authError && (
                      <div className="mt-3 space-y-2">
                        <div className="flex items-center gap-1.5 text-xs text-red-400 p-2 bg-red-900/20 rounded border border-red-800">
                          <AlertTriangle size={13}/> {authError}
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 px-1">
                          Invalid registry credentials only affect this tab — you stay signed in to
                          the application. You can retry, or continue below with local releases only.
                        </p>
                        <button
                          onClick={handleSkipAuth}
                          className="flex items-center gap-1.5 text-xs text-amber-300 hover:text-amber-200 px-2 py-1.5 rounded bg-amber-900/20 border border-amber-800/40"
                        >
                          <SkipForward size={13}/> Skip authentication — continue with local releases only
                        </button>
                      </div>
                    )}

                    <button onClick={handleSaveAuth} disabled={authLoading}
                      className="btn-primary mt-4 flex items-center gap-2">
                      {authLoading ? <Loader2 size={14} className="animate-spin"/> : <Lock size={14}/>}
                      {authLoading ? 'Connecting…' : 'Apply Auth & Load Registry'}
                    </button>
                  </>
                )}

                {sysInfo && (
                  <div className="mt-4 p-3 bg-slate-100 dark:bg-slate-800 rounded-lg text-xs text-slate-600 dark:text-slate-400 flex items-start gap-2">
                    <Info size={13} className="text-sky-400 mt-0.5 shrink-0"/>
                    <div className="space-y-0.5">
                      <div>OS: <strong className="text-slate-800 dark:text-slate-200">{sysInfo.os_name} {sysInfo.os_version}</strong> ({sysInfo.os_label})</div>
                      <div>Arch: <strong className="text-slate-800 dark:text-slate-200">{sysInfo.arch}</strong> · Kernel: {sysInfo.kernel_short || sysInfo.kernel}</div>
                      <div>Labels: <span className="font-mono">{sysInfo.rhel_label}</span> / <span className="font-mono">{sysInfo.el_label}</span></div>
                    </div>
                  </div>
                )}
              </Card>

              {authSaved && (
                <Card>
                  <SectionTitle>Architecture &amp; Distribution</SectionTitle>
                  {skipAuth && (
                    <div className="mb-3 flex items-center gap-1.5 text-xs text-amber-300 p-2 bg-amber-900/15 rounded border border-amber-800/40">
                      <SkipForward size={12}/> Showing local-only options (no registry connection).
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Architecture</label>
                      {loadingArchs ? <div className="input text-slate-500 dark:text-slate-400">Loading…</div> : (
                        <select className="input" value={selArch}
                          onChange={e => { setSelArch(e.target.value); setSelDist('') }}>
                          <option value="">— Select arch —</option>
                          {archs.map(a => <option key={a} value={a}>{a}</option>)}
                        </select>
                      )}
                    </div>
                    <div>
                      <label className="label">OS Distribution</label>
                      {loadingDists ? <div className="input text-slate-500 dark:text-slate-400">Loading…</div> : (
                        <select className="input" value={selDist}
                          onChange={e => setSelDist(e.target.value)} disabled={!selArch}>
                          <option value="">— Select OS —</option>
                          {dists.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                      )}
                    </div>
                  </div>
                  {selDist && (
                    <div className="mt-3 p-3 bg-sky-900/10 border border-sky-800/30 rounded-lg text-sm text-sky-300">
                      <CheckCircle2 size={14} className="inline mr-1.5"/>
                      Registry: <strong>{selArch} / {selDist}</strong>
                    </div>
                  )}
                </Card>
              )}

              {authSaved && (
                <Card>
                  <button
                    onClick={() => setReleaseNotesOpen(v => !v)}
                    className="w-full flex items-center justify-between text-left"
                  >
                    <SectionTitle>Release Notes</SectionTitle>
                    <span className="text-xs text-sky-400">{releaseNotesOpen ? 'Hide' : 'Browse'}</span>
                  </button>

                  {releaseNotesOpen && (
                    loadingReleaseNotes ? <Spinner/> : releaseNotes.length === 0 ? (
                      <EmptyMsg>No local release notes found.</EmptyMsg>
                    ) : (
                      <div className="space-y-4">
                        <div className="space-y-1.5">
                          {releaseNotes.map((r, i) => (
                            <button
                              type="button"
                              key={i}
                              onClick={async (e) => {
                                e.preventDefault()
                                if (selRelease?.name === r.name) {
                                  setSelRelease(null)
                                  setReleaseContent('')
                                  return
                                }
                                setSelRelease(r)
                                setLoadingReleaseContent(true)
                                try {
                                  const content = await chaiReleaseApi.releaseContent(
                                    r.path, r.type, verifySSL || null,
                                  )
                                  setReleaseContent(content || '')
                                } catch (e) {
                                  setReleaseContent(`Failed to load content:\n${e.message}`)
                                } finally {
                                  setLoadingReleaseContent(false)
                                }
                              }}
                              className={`w-full text-left px-4 py-2.5 rounded-lg border transition-all text-sm ${
                                selRelease?.name === r.name
                                  ? 'border-sky-500 bg-sky-900/20 text-sky-300'
                                  : 'border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-slate-500 text-slate-600 dark:text-slate-300'
                              }`}>
                              <div className="flex items-center justify-between">
                                <div>
                                  <span className="font-mono">{r.name}</span>
                                  <span className="ml-2 text-xs text-slate-500 dark:text-slate-400">({r.type})</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  {r.size_label && (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700">
                                      <HardDrive size={10}/> {r.size_label}
                                    </span>
                                  )}
                                  {selRelease?.name === r.name && <CheckCircle2 size={13} className="text-sky-400"/>}
                                </div>
                              </div>
                            </button>
                          ))}
                        </div>

                        {selRelease && (
                          <div className="mt-4">
                            <p className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide mb-2">
                              Preview — {selRelease.name}
                            </p>
                            <div className="bg-slate-100 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg p-4 max-h-[500px] overflow-auto">
                              {loadingReleaseContent ? (
                                <div className="flex items-center gap-2 text-sky-400 text-sm">
                                  <Loader2 size={14} className="animate-spin" />
                                  Loading content...
                                </div>
                              ) : (
                                <div className="prose dark:prose-invert prose-sm max-w-none">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                    {releaseContent || 'No content'}
                                  </ReactMarkdown>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  )}
                </Card>
              )}

              {authSaved && selDist && (
                <Card>
                  <SectionTitle>Available OpenCHAI Versions — <span className="text-sky-400 font-mono">{selDist}</span></SectionTitle>

                  {skipAuth && (
                    <div className="mb-3 flex items-center gap-1.5 text-xs text-amber-300 p-2 bg-amber-900/15 rounded border border-amber-800/40">
                      <SkipForward size={12}/> Showing locally-installed versions only (no registry connection).
                    </div>
                  )}

                  {loadingVersions ? <Spinner/> : versions.length === 0
                    ? <EmptyMsg>
                        {skipAuth
                          ? 'No locally-installed versions found for this architecture/distribution.'
                          : 'No versions found. Check registry and credentials.'}
                      </EmptyMsg>
                    : (
                      <SelectList
                        items={versions}
                        selected={selVersion?.version}
                        onSelect={(k, item) => setSelVersion(item)}
                        getKey={v => v.version}
                        getLabel={v => v.version}
                        getSub={v => {
                          if (v.name?.includes('local only')) return '📁 Local only — not in registry'
                          if (v.installed) return `📁 Already present locally at ${v.version}`
                          return v.url ? `🌐 ${v.url}` : ''
                        }}
                        getBadge={v => {
                          if (v.name?.includes('local only')) return <Pill ok={true} label='Local Only' variant='local-only'/>
                          if (v.installed)                    return <Pill ok={true} label='Local'      variant='local'/>
                          return                                     <Pill ok={false} label='Remote'    variant='remote'/>
                        }}
                        getSize={v => v.size_label || ''}
                      />
                    )
                  }

                  {selVersion && !skipAuth && (
                    <div className="mt-5 pt-4 border-t border-slate-200 dark:border-slate-800">
                      <p className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide mb-2">
                        Release Assets for {selVersion.version}
                      </p>

                      {loadingVersionReleases ? <Spinner/> : !versionReleaseData ? (
                        <EmptyMsg>No release asset data available.</EmptyMsg>
                      ) : (
                        <div className="space-y-3">
                          <div className={`flex items-center gap-2 p-3 rounded-lg border text-sm ${
                            versionReleaseData.registry_present
                              ? 'bg-green-900/20 border-green-700/40 text-green-300'
                              : 'bg-yellow-900/20 border-yellow-700/40 text-yellow-300'
                          }`}>
                            {versionReleaseData.registry_present
                              ? <><CheckCircle2 size={15}/> Registry extracted at: <code className="text-xs ml-1 text-green-200">{versionReleaseData.registry_path}</code></>
                              : <><AlertTriangle size={15}/> Registry not yet extracted — will be installed below.</>
                            }
                          </div>

                          {versionReleaseData.releases?.filter(r => r.type === 'remote_asset').length > 0 && (
                            <div className="space-y-1.5">
                              {versionReleaseData.releases.filter(r => r.type === 'remote_asset').map((r, i) => (
                                <div key={i} className="flex items-center justify-between px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-600 dark:text-slate-300">
                                  <span className="font-mono truncate">{r.name}</span>
                                  {r.size_label && (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700 shrink-0 ml-2">
                                      <HardDrive size={10}/> {r.size_label}
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  <label className="flex items-center gap-3 cursor-pointer pt-4 mt-4 border-t border-slate-200 dark:border-slate-800">
                    <button type="button" onClick={() => setUpdateConfigs(v => !v)}
                      className={`relative w-9 h-5 rounded-full transition-colors ${updateConfigs ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
                      <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${updateConfigs ? 'translate-x-4' : ''}`}/>
                    </button>
                    <span className="text-sm text-slate-600 dark:text-slate-300">
                      Update <code className="text-xs">group_vars/all.yml</code> and <code className="text-xs">ansible.cfg</code> after install
                    </span>
                  </label>

                  {selVersion && (
                    <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800">
                      {!execJob ? (
                        <>
                          {execError && (
                            <div className="mb-3 flex items-center gap-1.5 text-xs text-red-400 p-2 bg-red-900/20 rounded border border-red-800">
                              <XCircle size={13}/> {execError}
                            </div>
                          )}
                          {selVersion?.installed ? (
                            <div className="mb-3 p-3 bg-sky-900/20 border border-sky-700/40 rounded-lg text-sm text-sky-300 flex items-center gap-2">
                              <CheckCircle2 size={14}/> This version is already installed locally. Installing again will skip download and update config only.
                            </div>
                          ) : null}
                          <button onClick={handleExecute} disabled={executing} className="btn-primary flex items-center gap-2">
                            {executing ? <><Loader2 size={14} className="animate-spin"/> Starting…</> : <><Terminal size={14}/> Install {selVersion.version}</>}
                          </button>
                        </>
                      ) : (
                        <div className="space-y-4">
                          <JobPanel job={execJob}/>
                          {execJob?.status !== 'running' && (
                            <div className="flex gap-2 pt-2">
                              <button onClick={() => setExecJob(null)} className="btn-secondary flex items-center gap-1.5">
                                <RefreshCw size={13}/> Retry / Install Another
                              </button>
                              {execJob.status === 'success' && (
                                <button onClick={() => handleTabChange('cluster-config')} className="btn-primary flex items-center gap-1.5">
                                  Continue to Cluster Configuration <ArrowRight size={13}/>
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              )}
            </div>
          )}

          {/* ══════════════════════ TAB 2: HPC-AI Container Tools ═════════════ */}
          {activeTab === 'containers' && (
            <Card>
              <SectionTitle>Container Image Registry</SectionTitle>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                Browse and download HPC-AI container images for{' '}
                <strong className="text-slate-600 dark:text-slate-300">{selDist || '— select an OS distribution in OpenCHAI Packages first —'}</strong>.
                Mirrors <code>container_img_selector.py</code> with resume support.
              </p>

              {!selDist ? (
                <EmptyMsg>
                  Select an architecture &amp; OS distribution in the <strong>OpenCHAI Packages</strong> tab first.
                </EmptyMsg>
              ) : ctTools.length === 0 ? <Spinner/> : (
                <div className="space-y-4">
                  {ctTools.map(tool => (
                    <div key={tool} className="border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden">
                      <div className="flex items-center justify-between px-4 py-3 bg-slate-100 dark:bg-slate-800/50">
                        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{tool}</span>
                        {!ctVersions[tool] && (
                          <button onClick={() => loadCtVersions(tool)}
                            disabled={ctLoadingVer[tool]}
                            className="btn-secondary text-xs flex items-center gap-1">
                            {ctLoadingVer[tool]
                              ? <Loader2 size={11} className="animate-spin"/>
                              : <RefreshCw size={11}/>}
                            Load Versions
                          </button>
                        )}
                      </div>

                      {ctVersions[tool] && (
                        <div className="p-4 space-y-3">
                          <div>
                            <label className="label">Version</label>
                            <select className="input" value={ctSelVer[tool] || ''}
                              onChange={e => {
                                const ver = e.target.value
                                setCtSelVer(p => ({ ...p, [tool]: ver }))
                                if (ver) loadCtImages(tool, ver)
                              }}>
                              <option value="">— Select version —</option>
                              {ctVersions[tool].map(v => <option key={v} value={v}>{v}</option>)}
                            </select>
                          </div>

                          {ctLoadingImg[tool] && <Spinner/>}

                          {ctImages[tool]?.length > 0 && (
                            <div>
                              <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-slate-600 dark:text-slate-400">Available images</p>
                                <button onClick={() => {
                                  const allNames = new Set(ctImages[tool].map(i => i.name))
                                  setCtSelImgs(p => ({ ...p, [tool]: allNames }))
                                }} className="text-xs text-sky-400 hover:text-sky-300">Select all</button>
                              </div>
                              <div className="space-y-1">
                                {ctImages[tool].map(img => {
                                  const checked = ctSelImgs[tool]?.has(img.name)
                                  return (
                                    <button key={img.name} onClick={() => toggleCtImage(tool, img.name)}
                                      className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-left">
                                      {checked
                                        ? <CheckSquare size={14} className="text-sky-400 shrink-0"/>
                                        : <Square size={14} className="text-slate-600 shrink-0"/>}
                                      <span className="text-xs font-mono text-slate-600 dark:text-slate-300 break-all">{img.name}</span>
                                    </button>
                                  )
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {Object.values(ctSelImgs).some(s => s?.size > 0) && (
                <div className="mt-4 p-3 bg-sky-900/10 border border-sky-800/30 rounded-lg text-sm text-sky-300">
                  {Object.entries(ctSelImgs).reduce((n, [, s]) => n + (s?.size || 0), 0)} image(s) selected
                </div>
              )}

              {selDist && (
                !ctJob ? (
                  <button onClick={handleCtExecute} disabled={ctExecuting}
                    className="btn-primary mt-4 flex items-center gap-2">
                    {ctExecuting ? <><Loader2 size={14} className="animate-spin"/> Starting…</> : <><Download size={14}/> Download Selected</>}
                  </button>
                ) : (
                  <div className="mt-4 space-y-4">
                    <JobPanel job={ctJob}/>
                    {ctJob?.status !== 'running' && (
                      <button onClick={() => setCtJob(null)} className="btn-secondary flex items-center gap-1.5">
                        <RotateCcw size={13}/> Download More
                      </button>
                    )}
                  </div>
                )
              )}
            </Card>
          )}

          {/* ══════════════════════ TAB 3: Cluster Configuration ══════════════ */}
          {activeTab === 'cluster-config' && (
            <Card>
              <SectionTitle>Cluster Configuration — group_vars/all.yml</SectionTitle>

              {installStatusLoading ? <Spinner/> : !installStatus?.installed ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 p-3 rounded-lg border border-amber-700/40 bg-amber-900/20 text-amber-300 text-sm">
                    <AlertTriangle size={15}/> No OpenCHAI package is installed locally yet.
                  </div>
                  {!configLaterAck ? (
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => handleTabChange('packages')}
                        className="btn-primary flex items-center gap-1.5"
                      >
                        <Package size={14}/> Install Now
                      </button>
                      <button
                        onClick={() => setConfigLaterAck(true)}
                        className="btn-secondary flex items-center gap-1.5"
                      >
                        Later
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 p-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-sm">
                      <Info size={15} className="shrink-0"/>
                      OpenCHAI version values must be updated manually in <code className="text-xs">all.yml</code> after the package is installed.
                    </div>
                  )}
                </div>
              ) : allYmlLoading ? <Spinner/> : (
                <div className="space-y-5">
                  <div className="flex items-center gap-2 p-3 rounded-lg border border-green-700/40 bg-green-900/20 text-green-300 text-sm">
                    <CheckCircle2 size={15}/> Loaded configuration for OpenCHAI {installStatus.version} ({installStatus.arch} / {installStatus.os_dist}).
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="label">openchai_version</label>
                      <input className="input font-mono text-sm"
                        value={allYmlVars?.openchai_version ?? ''}
                        onChange={e => handleAllYmlFieldChange('openchai_version', e.target.value)} />
                    </div>
                    <div>
                      <label className="label">base_dir</label>
                      <input className="input font-mono text-sm"
                        value={allYmlVars?.base_dir ?? ''}
                        onChange={e => handleAllYmlFieldChange('base_dir', e.target.value)} />
                    </div>
                    <div>
                      <label className="label">os_version</label>
                      <input className="input font-mono text-sm"
                        value={allYmlVars?.os_version ?? ''}
                        onChange={e => handleAllYmlFieldChange('os_version', e.target.value)} />
                    </div>
                    <div>
                      <label className="label">os_arch</label>
                      <input className="input font-mono text-sm"
                        value={allYmlVars?.os_arch ?? ''}
                        onChange={e => handleAllYmlFieldChange('os_arch', e.target.value)} />
                    </div>
                    <div>
                      <label className="label">rhel_linux_label</label>
                      <input className="input font-mono text-sm"
                        value={allYmlVars?.rhel_linux_label ?? ''}
                        onChange={e => handleAllYmlFieldChange('rhel_linux_label', e.target.value)} />
                    </div>
                    <div>
                      <label className="label">enterprise_linux_label</label>
                      <input className="input font-mono text-sm"
                        value={allYmlVars?.enterprise_linux_label ?? ''}
                        onChange={e => handleAllYmlFieldChange('enterprise_linux_label', e.target.value)} />
                    </div>
                    <div className="col-span-2">
                      <label className="label">default_kernel_version</label>
                      <input className="input font-mono text-sm"
                        value={allYmlVars?.default_kernel_version ?? ''}
                        onChange={e => handleAllYmlFieldChange('default_kernel_version', e.target.value)} />
                    </div>
                  </div>

                  <div className="flex items-center gap-2 pt-2">
                    <button onClick={handleSaveAllYml} disabled={allYmlSaving || !configTouched}
                      className="btn-primary flex items-center gap-2">
                      {allYmlSaving ? <Loader2 size={14} className="animate-spin"/> : <Save size={14}/>}
                      Save all.yml
                    </button>
                    {configSaved && (
                      <span className="text-xs text-green-400 flex items-center gap-1"><CheckCircle2 size={13}/> Saved</span>
                    )}
                    {configTouched && !configSaved && (
                      <span className="text-xs text-amber-400 flex items-center gap-1"><AlertTriangle size={13}/> Unsaved changes</span>
                    )}
                  </div>
                </div>
              )}
            </Card>
          )}
        </div>

        {infoOpen && currentInfo && (
          <aside className="hidden lg:block w-72 shrink-0 sticky top-4">
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide flex items-center gap-1.5">
                  <Info size={12}/> About this tab
                </p>
                <button onClick={() => setInfoOpen(false)} className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-300">
                  <X size={14}/>
                </button>
              </div>
              <div className="prose dark:prose-invert prose-sm max-w-none text-xs [&>h1]:text-sm [&>h1]:font-semibold [&>h1]:text-slate-900 dark:text-slate-100 [&>p]:text-slate-600 dark:text-slate-400 [&>ul]:text-slate-600 dark:text-slate-400">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {currentInfo}
                </ReactMarkdown>
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* ── Exit-confirmation modal — Cluster Configuration tab only ────────── */}
      {showExitConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl shadow-2xl p-5 max-w-md w-full space-y-4">
            <div className="flex items-center gap-2 text-amber-400">
              <AlertTriangle size={18}/>
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Unsaved cluster configuration</h3>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              OpenCHAI version values must be updated manually in all.yml before deploying the cluster.
            </p>
            <div className="flex justify-end">
              <button onClick={acknowledgeExitAndSwitch} className="btn-primary">
                I Understand — Continue
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Custom hook: WebSocket live streaming + status finalisation ──────────────
function useJobPoll(job, setJob) {
  useEffect(() => {
    if (!job?.job_id || job.status !== 'running') return

    let ws          = null
    let fallbackId  = null
    let finalised   = false

    const finalise = async () => {
      if (finalised) return
      finalised = true
      try {
        const updated = await chaiReleaseApi.jobStatus(job.job_id)
        setJob(prev => ({ ...prev, ...updated }))
      } catch {}
    }

    try {
      ws = createLogSocket(
        job.job_id,
        (line) => setJob(prev => ({ ...prev, log: [...(prev.log || []), line] })),
        ()     => finalise(),
      )
    } catch {
      ws = null
    }

    const fallbackTimer = setTimeout(() => {
      if (ws && ws.readyState === WebSocket.OPEN) return
      fallbackId = setInterval(async () => {
        try {
          const updated = await chaiReleaseApi.jobStatus(job.job_id)
          setJob(prev => ({ ...prev, ...updated }))
          if (updated.status !== 'running') { clearInterval(fallbackId); finalised = true }
        } catch {}
      }, JOB_POLL_MS)
    }, 3000)

    return () => {
      clearTimeout(fallbackTimer)
      clearInterval(fallbackId)
      if (ws) try { ws.close() } catch {}
    }
  }, [job?.job_id, job?.status, setJob])
}
