import React, { useState, useEffect, useRef } from 'react'
import toast from 'react-hot-toast'
import { inventoryDefApi, backupApi } from '../api/api.js'
import PageHeader from '../components/PageHeader.jsx'
import {
  Plus, Pencil, Trash2, RefreshCw, Upload, Wifi, WifiOff,
  Loader2, Eye, EyeOff, FileText, X, CheckCircle2, XCircle,
  History, Lock, ShieldCheck, ShieldOff,
} from 'lucide-react'

const EMPTY = {
  ansible_hostname: '', ip: '', ansible_user: 'root',
  ansible_password: '',
  group: 'compute', hostname: '', ssh_port: '22',
}

// ── Node Modal ────────────────────────────────────────────────────────────────
// Sentinel: the password field shows this when editing to indicate "keep existing"
const PWD_UNCHANGED_SENTINEL = '__UNCHANGED__'

function NodeModal({ node, onClose, onSaved, backupEnabled }) {
  // When editing, initialise both password fields to the sentinel so the
  // user sees the "unchanged" placeholder and we know not to clear the
  // stored vault-encrypted credential if they don't retype it.
  const initPwd = node ? PWD_UNCHANGED_SENTINEL : ''
  const [form, setForm]       = useState(
    node
      ? { ...EMPTY, ...node, ansible_password: initPwd }
      : { ...EMPTY }
  )
  const [saving, setSaving]   = useState(false)
  const [showPwd, setShowPwd] = useState(false)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const isEdit = !!node?.ansible_hostname

  const handleSave = async () => {
    if (!form.ansible_hostname || !form.ip || !form.ansible_user) {
      toast.error('ansible_hostname, IP, and ansible_user are required.')
      return
    }
    setSaving(true)
    try {
      if (isEdit) {
        const { ansible_hostname, password_set, ...updates } = form
        // If the password field still holds the sentinel, omit it from the
        // update payload entirely so the backend preserves the existing
        // vault-encrypted credential untouched.
        if (updates.ansible_password === PWD_UNCHANGED_SENTINEL) {
          delete updates.ansible_password
        }
        await inventoryDefApi.update(node.ansible_hostname, updates, backupEnabled)
        toast.success(`Node '${node.ansible_hostname}' updated.`)
      } else {
        const payload = { ...form }
        if (payload.ansible_password === PWD_UNCHANGED_SENTINEL) payload.ansible_password = ''
        await inventoryDefApi.add(payload, backupEnabled)
        toast.success(`Node '${form.ansible_hostname}' added.`)
      }
      onSaved(); onClose()
    } catch (e) { toast.error(e.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold">{isEdit ? 'Edit Node' : 'Add Node'}</h2>
          <button onClick={onClose}><X size={18} className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white" /></button>
        </div>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">ansible_hostname *</label>
              <input className="input" value={form.ansible_hostname} disabled={isEdit}
                onChange={(e) => set('ansible_hostname', e.target.value)} placeholder="cn01" />
            </div>
            <div>
              <label className="label">IP Address *</label>
              <input className="input" value={form.ip}
                onChange={(e) => set('ip', e.target.value)} placeholder="192.168.1.101" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">ansible_user *</label>
              <input className="input" value={form.ansible_user}
                onChange={(e) => set('ansible_user', e.target.value)} placeholder="root" />
            </div>
            <div>
              <label className="label">Password (SSH + sudo)</label>
              <div className="relative">
                <input className="input pr-9" type={showPwd ? 'text' : 'password'}
                  value={form.ansible_password === PWD_UNCHANGED_SENTINEL ? '' : form.ansible_password}
                  placeholder={form.ansible_password === PWD_UNCHANGED_SENTINEL ? '(unchanged — type to change)' : '••••••'}
                  onChange={(e) => set('ansible_password', e.target.value || (isEdit ? PWD_UNCHANGED_SENTINEL : ''))} />
                <button type="button" onClick={() => setShowPwd((s) => !s)}
                  className="absolute right-2 top-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-300">
                  {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              {isEdit && (
                <p className="text-[10px] text-slate-600 mt-1">Leave blank to keep existing password</p>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Group</label>
              <input className="input" value={form.group}
                onChange={(e) => set('group', e.target.value)} placeholder="compute" />
            </div>
            <div>
              <label className="label">ssh_port</label>
              <input className="input" value={form.ssh_port}
                onChange={(e) => set('ssh_port', e.target.value)} placeholder="22" />
            </div>
          </div>
          <div className="flex items-start gap-1.5 px-2.5 py-2 bg-sky-900/15 border border-sky-800/30 rounded text-[11px] text-sky-300">
            <Lock size={12} className="mt-0.5 shrink-0"/>
            <span>One password per node, used for both SSH login and sudo — encrypted into the shared Ansible Vault (<code className="text-[10px]">inventory/group_vars/all/vault.yml</code>) by the same automation script every playbook run uses. Never shown again after saving.</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">hostname (FQDN)</label>
              <input className="input" value={form.hostname}
                onChange={(e) => set('hostname', e.target.value)} placeholder="cn01.cluster.local" />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-5 pt-4 border-t border-slate-200 dark:border-slate-800">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? 'Saving…' : isEdit ? 'Update' : 'Add Node'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Bulk CSV modal ────────────────────────────────────────────────────────────
function BulkModal({ onClose, onSaved, backupEnabled }) {
  const [csv, setCsv]         = useState('')
  const [loading, setLoading] = useState(false)
  const [fileName, setFileName] = useState('')
  const [skippedRows, setSkippedRows] = useState(null)
  const fileInputRef = useRef(null)

  // Native OS file picker — reads a .csv/.txt file straight from disk instead
  // of requiring the user to copy/paste its contents.
  const handleFilePick = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      setCsv(String(ev.target.result || ''))
      setFileName(file.name)
    }
    reader.onerror = () => toast.error('Could not read that file.')
    reader.readAsText(file)
    // allow re-selecting the same file name again later
    e.target.value = ''
  }

  const handleImport = async () => {
    if (!csv.trim()) { toast.error('Choose a file or paste data first.'); return }
    setLoading(true)
    try {
      const res = await inventoryDefApi.bulk(csv, backupEnabled)
      if (res.added > 0) {
        toast.success(res.message)
        onSaved()
      } else {
        toast.error(res.message)
      }
      if (res.skipped?.length) {
        setSkippedRows(res.skipped)
      } else {
        onClose()
      }
    } catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl w-full max-w-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">Bulk Import Nodes</h2>
          <button onClick={onClose}><X size={18} className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white" /></button>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
          One node per line, 7 space- or comma-separated fields (matches <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded text-xs">automation/ansible/bootstrap_import.py</code>):
        </p>
        <p className="text-xs font-mono bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded mb-3 overflow-x-auto whitespace-nowrap">
          node ip user group hostname ssh_port password
        </p>
        <p className="text-[11px] text-amber-300/90 mb-3 flex items-start gap-1.5">
          <Lock size={11} className="mt-0.5 shrink-0"/>
          <span>Passwords are sent once over this request, immediately encrypted into the same Ansible Vault every playbook run uses, and never stored in plaintext. Clear this box (or close this dialog) once you're done — don't leave a password-bearing file lying around on your own machine afterward.</span>
        </p>

        {/* Native file picker */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.txt,text/csv,text/plain"
          onChange={handleFilePick}
          className="hidden"
        />
        <div className="flex items-center gap-2 mb-3">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="btn-secondary text-xs"
          >
            <Upload size={13} /> Choose File…
          </button>
          <span className="text-xs text-slate-500 dark:text-slate-400 truncate">
            {fileName || 'No file chosen — or paste text below'}
          </span>
        </div>

        <textarea className="input h-40 font-mono text-xs" value={csv}
          onChange={(e) => { setCsv(e.target.value); setFileName(''); setSkippedRows(null) }}
          placeholder={'cn01 192.168.1.101 root compute cn01.local 22 s3cret\ncn02 192.168.1.102 root compute cn02.local 22 s3cret'} />

        {skippedRows?.length > 0 && (
          <div className="alert-warning mt-3 flex-col items-stretch">
            <p className="font-semibold mb-1.5">
              {skippedRows.length} row(s) were not imported:
            </p>
            <ul className="space-y-1 max-h-32 overflow-y-auto text-xs font-mono">
              {skippedRows.map((r, i) => (
                <li key={i}>
                  Row {r.row} ({r.hostname}): {r.reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex justify-end gap-3 mt-4">
          <button onClick={onClose} className="btn-secondary">
            {skippedRows ? 'Close' : 'Cancel'}
          </button>
          <button onClick={handleImport} disabled={loading} className="btn-primary">
            {loading ? 'Importing…' : 'Import'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── SSH Test indicator ────────────────────────────────────────────────────────
function SshStatus({ status }) {
  if (status === 'testing') return <Loader2 size={13} className="text-yellow-400 animate-spin" />
  if (status === true)      return <CheckCircle2 size={13} className="text-green-400" />
  if (status === false)     return <XCircle size={13} className="text-red-400" />
  return null
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function InventoryDef() {
  const [nodes, setNodes]           = useState([])
  const [loading, setLoading]       = useState(true)
  const [modal, setModal]           = useState(null)   // null | 'add' | 'edit' | 'bulk'
  const [editNode, setEditNode]     = useState(null)
  const [sshStatus, setSshStatus]   = useState({})     // {hostname: true/false/'testing'}
  const [backupEnabled, setBackup]  = useState(true)
  const [showRaw, setShowRaw]       = useState(false)
  const [rawContent, setRawContent] = useState('')
  const [filterGroup, setFilterGroup] = useState('')

  const fetchNodes = async () => {
    setLoading(true)
    try { setNodes(await inventoryDefApi.list()) }
    catch (e) { toast.error(e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchNodes() }, [])

  const handleDelete = async (node) => {
    if (!window.confirm(`Delete '${node.ansible_hostname}'?`)) return
    try {
      await inventoryDefApi.remove(node.ansible_hostname, backupEnabled)
      toast.success(`'${node.ansible_hostname}' deleted.`)
      fetchNodes()
    } catch (e) { toast.error(e.message) }
  }

  const handleSshTest = async (node) => {
    setSshStatus((s) => ({ ...s, [node.ansible_hostname]: 'testing' }))
    try {
      const res = await inventoryDefApi.sshTest({ ansible_hostname: node.ansible_hostname })
      setSshStatus((s) => ({ ...s, [node.ansible_hostname]: res.success }))
      res.success ? toast.success(`Ping OK: ${node.ansible_hostname}`) : toast.error(`Ping failed: ${res.message}`)
    } catch (e) {
      setSshStatus((s) => ({ ...s, [node.ansible_hostname]: false }))
      toast.error(e.message)
    }
  }

  const handleShowRaw = async () => {
    const res = await inventoryDefApi.raw()
    setRawContent(res.content)
    setShowRaw(true)
  }

  const groups = [...new Set(nodes.map((n) => n.group).filter(Boolean))]
  const filtered = filterGroup ? nodes.filter((n) => n.group === filterGroup) : nodes

  return (
    <div className="space-y-4">
      <PageHeader
        title="Inventory Management"
        subtitle={<>Manages <code className="bg-slate-100 dark:bg-slate-800 px-1 rounded">inventory_def.txt</code> — {nodes.length} nodes · passwords stored via Ansible Vault</>}
      />

      {/* Header */}
      <div className="flex flex-wrap items-center justify-end gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Backup toggle */}
          <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400 cursor-pointer select-none">
            <button type="button" onClick={() => setBackup((b) => !b)}
              className={`relative w-9 h-5 rounded-full transition-colors ${backupEnabled ? 'bg-green-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${backupEnabled ? 'translate-x-4' : ''}`} />
            </button>
            <History size={12} className={backupEnabled ? 'text-green-400' : 'text-slate-600'} />
            Backup before save
          </label>
          <button onClick={handleShowRaw} className="btn-secondary">
            <FileText size={13} /> Raw File
          </button>
          <button onClick={() => setModal('bulk')} className="btn-secondary">
            <Upload size={13} /> Bulk Import
          </button>
          <button onClick={fetchNodes} className="btn-secondary">
            <RefreshCw size={13} /> Refresh
          </button>
          <button onClick={() => { setEditNode(null); setModal('add') }} className="btn-primary">
            <Plus size={13} /> Add Node
          </button>
        </div>
      </div>

      {/* Group filter */}
      {groups.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 dark:text-slate-400">Filter by group:</span>
          <button onClick={() => setFilterGroup('')}
            className={`px-2 py-0.5 rounded text-xs ${!filterGroup ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 dark:hover:bg-slate-700'}`}>
            All
          </button>
          {groups.map((g) => (
            <button key={g} onClick={() => setFilterGroup(g)}
              className={`px-2 py-0.5 rounded text-xs ${filterGroup === g ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 dark:hover:bg-slate-700'}`}>
              {g}
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="card overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-7 w-7 border-b-2 border-sky-500" /></div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center py-12 text-slate-600">
            <FileText size={36} className="mb-2 opacity-30" />
            <p className="text-sm">No nodes in inventory_def.txt yet.</p>
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-left text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                {['ansible_hostname','ip','ansible_user','password','group','hostname','ssh_port','SSH','Actions'].map((h) => (
                  <th key={h} className="pb-3 pr-3 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60">
              {filtered.map((node) => (
                <tr key={node.ansible_hostname} className="hover:bg-slate-100 dark:hover:bg-slate-800/30 group">
                  <td className="py-2 pr-3 font-mono text-slate-800 dark:text-slate-200">{node.ansible_hostname}</td>
                  <td className="py-2 pr-3 font-mono text-slate-600 dark:text-slate-400">{node.ip}</td>
                  <td className="py-2 pr-3 text-slate-600 dark:text-slate-400">{node.ansible_user}</td>
                  <td className="py-2 pr-3">
                    {node.password_set ? (
                      <span className="inline-flex items-center gap-1 text-green-400" title="Password stored (ansible-vault encrypted)">
                        <ShieldCheck size={13}/> set
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-slate-600 italic" title="No password stored for this node">
                        <ShieldOff size={13}/> none
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <span className="badge-blue">{node.group}</span>
                  </td>
                  <td className="py-2 pr-3 text-slate-500 dark:text-slate-400 font-mono">{node.hostname || node.ansible_hostname}</td>
                  <td className="py-2 pr-3 text-slate-500 dark:text-slate-400">{node.ssh_port || 22}</td>
                  <td className="py-2 pr-3">
                    <button onClick={() => handleSshTest(node)}
                      className="p-1 text-slate-500 dark:text-slate-400 hover:text-sky-400 transition-colors" title="Test connectivity (ansible -m ping)">
                      {sshStatus[node.ansible_hostname] === 'testing'
                        ? <Loader2 size={13} className="animate-spin text-yellow-400" />
                        : sshStatus[node.ansible_hostname] === true
                        ? <CheckCircle2 size={13} className="text-green-400" />
                        : sshStatus[node.ansible_hostname] === false
                        ? <XCircle size={13} className="text-red-400" />
                        : <Wifi size={13} />}
                    </button>
                  </td>
                  <td className="py-2">
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => { setEditNode(node); setModal('edit') }}
                        className="p-1 text-slate-600 dark:text-slate-400 hover:text-sky-400"><Pencil size={13} /></button>
                      <button onClick={() => handleDelete(node)}
                        className="p-1 text-slate-600 dark:text-slate-400 hover:text-red-400"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Raw file modal */}
      {showRaw && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl w-full max-w-2xl p-6">
            <div className="flex justify-between mb-3">
              <h2 className="text-sm font-semibold">inventory_def.txt — Raw Content</h2>
              <button onClick={() => setShowRaw(false)}><X size={16} className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white" /></button>
            </div>
            <pre className="bg-slate-100 dark:bg-slate-950 rounded-lg p-4 text-xs font-mono text-green-400 overflow-auto max-h-96">{rawContent || '(empty)'}</pre>
          </div>
        </div>
      )}

      {/* Modals */}
      {modal === 'add' && (
        <NodeModal node={null} onClose={() => setModal(null)} onSaved={fetchNodes} backupEnabled={backupEnabled} />
      )}
      {modal === 'edit' && editNode && (
        <NodeModal node={editNode} onClose={() => setModal(null)} onSaved={fetchNodes} backupEnabled={backupEnabled} />
      )}
      {modal === 'bulk' && (
        <BulkModal onClose={() => setModal(null)} onSaved={fetchNodes} backupEnabled={backupEnabled} />
      )}
    </div>
  )
}