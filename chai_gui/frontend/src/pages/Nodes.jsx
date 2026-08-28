import React, { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { nodesApi } from '../api/api.js'
import NodeTable from '../components/NodeTable.jsx'
import { Plus, X, Upload, RefreshCw } from 'lucide-react'

const ROLES = ['headnode','compute','gpu','storage','login','management','service']

const EMPTY_NODE = {
  hostname: '', ip_address: '', role: 'compute',
  bmc_ip: '', mac_address: '', cpu_count: '', ram_gb: '',
  gpu_count: 0, gpu_model: '', tags: {},
}

function NodeModal({ node, onClose, onSaved }) {
  const [form, setForm] = useState(node ? { ...EMPTY_NODE, ...node } : { ...EMPTY_NODE })
  const [saving, setSaving] = useState(false)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const handleSave = async () => {
    if (!form.hostname || !form.ip_address) {
      toast.error('Hostname and IP address are required.')
      return
    }
    setSaving(true)
    try {
      const payload = {
        ...form,
        cpu_count: form.cpu_count ? parseInt(form.cpu_count) : null,
        ram_gb:    form.ram_gb    ? parseInt(form.ram_gb)    : null,
        gpu_count: parseInt(form.gpu_count) || 0,
      }
      if (node?.id) {
        await nodesApi.update(node.id, payload)
        toast.success(`Node '${form.hostname}' updated.`)
      } else {
        await nodesApi.add(payload)
        toast.success(`Node '${form.hostname}' added.`)
      }
      onSaved()
      onClose()
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            {node?.id ? 'Edit Node' : 'Add Node'}
          </h2>
          <button onClick={onClose} className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Hostname *</label>
              <input className="input" value={form.hostname}
                onChange={(e) => set('hostname', e.target.value)} placeholder="cn01" />
            </div>
            <div>
              <label className="label">IP Address *</label>
              <input className="input" value={form.ip_address}
                onChange={(e) => set('ip_address', e.target.value)} placeholder="192.168.1.101" />
            </div>
          </div>

          <div>
            <label className="label">Role</label>
            <select className="input" value={form.role} onChange={(e) => set('role', e.target.value)}>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="label">CPUs</label>
              <input className="input" type="number" value={form.cpu_count}
                onChange={(e) => set('cpu_count', e.target.value)} placeholder="64" />
            </div>
            <div>
              <label className="label">RAM (GB)</label>
              <input className="input" type="number" value={form.ram_gb}
                onChange={(e) => set('ram_gb', e.target.value)} placeholder="256" />
            </div>
            <div>
              <label className="label">GPU Count</label>
              <input className="input" type="number" value={form.gpu_count}
                onChange={(e) => set('gpu_count', e.target.value)} placeholder="0" />
            </div>
          </div>

          {parseInt(form.gpu_count) > 0 && (
            <div>
              <label className="label">GPU Model</label>
              <input className="input" value={form.gpu_model}
                onChange={(e) => set('gpu_model', e.target.value)} placeholder="A100, H100, V100…" />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">BMC IP</label>
              <input className="input" value={form.bmc_ip}
                onChange={(e) => set('bmc_ip', e.target.value)} placeholder="192.168.2.101" />
            </div>
            <div>
              <label className="label">MAC Address</label>
              <input className="input" value={form.mac_address}
                onChange={(e) => set('mac_address', e.target.value)} placeholder="AA:BB:CC:DD:EE:FF" />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-200 dark:border-slate-800">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? 'Saving…' : node?.id ? 'Update Node' : 'Add Node'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Nodes() {
  const [nodes, setNodes]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [modalNode, setModalNode] = useState(null)   // null = closed, {} = new, node = edit
  const [showModal, setShowModal] = useState(false)

  const fetchNodes = async () => {
    setLoading(true)
    try {
      setNodes(await nodesApi.list())
    } catch (e) {
      toast.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchNodes() }, [])

  const handleDelete = async (node) => {
    if (!window.confirm(`Delete node '${node.hostname}'?`)) return
    try {
      await nodesApi.remove(node.id)
      toast.success(`'${node.hostname}' deleted.`)
      fetchNodes()
    } catch (e) {
      toast.error(e.message)
    }
  }

  const openAdd  = () => { setModalNode(null); setShowModal(true) }
  const openEdit = (node) => { setModalNode(node); setShowModal(true) }
  const closeModal = () => setShowModal(false)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">Node Management</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{nodes.length} node{nodes.length !== 1 ? 's' : ''} defined</p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchNodes} className="btn-secondary">
            <RefreshCw size={14} /> Refresh
          </button>
          <button onClick={openAdd} className="btn-primary">
            <Plus size={14} /> Add Node
          </button>
        </div>
      </div>

      <div className="card">
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-sky-500" />
          </div>
        ) : (
          <NodeTable
            nodes={nodes}
            onEdit={openEdit}
            onDelete={handleDelete}
          />
        )}
      </div>

      {showModal && (
        <NodeModal
          node={modalNode}
          onClose={closeModal}
          onSaved={fetchNodes}
        />
      )}
    </div>
  )
}
