import React, { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { clusterApi } from '../api/api.js'
import PageHeader from '../components/PageHeader.jsx'
import { Settings2, Save, AlertCircle } from 'lucide-react'

const TABS = ['SLURM', 'NFS', 'LDAP', 'Kubernetes', 'Monitoring']

function Toggle({ checked, onChange, label, sub }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <button type="button" role="switch" onClick={() => onChange(!checked)}
        className={`mt-0.5 relative w-10 h-5 rounded-full transition-colors shrink-0 ${checked ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : ''}`} />
      </button>
      <div>
        <span className="text-sm text-slate-800 dark:text-slate-200">{label}</span>
        {sub && <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </label>
  )
}

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="text-xs text-slate-600 mt-1">{hint}</p>}
    </div>
  )
}

export default function Services() {
  const [tab, setTab]     = useState('SLURM')
  const [cfg, setCfg]     = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    clusterApi.get()
      .then((c) => setCfg(c))
      .catch((e) => setError(e.message))
  }, [])

  const setSvc = (k, v) =>
    setCfg((c) => ({ ...c, services: { ...c.services, [k]: v } }))

  const handleSave = async () => {
    setSaving(true)
    try {
      await clusterApi.create(cfg)
      toast.success('Service configuration saved!')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (error) {
    return (
      <div className="card flex items-center gap-3 text-red-300 text-sm">
        <AlertCircle size={18} /> {error} — Configure your cluster first.
      </div>
    )
  }
  if (!cfg) {
    return (
      <div className="flex justify-center py-16">
        <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-sky-500" />
      </div>
    )
  }

  const svc = cfg.services || {}

  return (
    <div className="max-w-2xl space-y-4">
      <PageHeader title="Services Configuration" subtitle="Enable and configure cluster services" />

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg w-fit">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t ? 'bg-sky-600 text-white' : 'text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:text-slate-200'
            }`}>
            {t}
          </button>
        ))}
      </div>

      <div className="card space-y-5">
        {/* ── SLURM ─────────────────────────────────────────────────── */}
        {tab === 'SLURM' && (
          <>
            <Toggle checked={!!svc.slurm_enabled} onChange={(v) => setSvc('slurm_enabled', v)}
              label="Enable SLURM Workload Manager"
              sub="Installs and configures slurmctld on head node and slurmd on compute nodes." />
            {svc.slurm_enabled && (
              <>
                <Field label="Default Partition Name">
                  <input className="input" value={svc.slurm_partition_name || ''}
                    onChange={(e) => setSvc('slurm_partition_name', e.target.value)} />
                </Field>
              </>
            )}
          </>
        )}

        {/* ── NFS ───────────────────────────────────────────────────── */}
        {tab === 'NFS' && (
          <>
            <Toggle checked={!!svc.nfs_enabled} onChange={(v) => setSvc('nfs_enabled', v)}
              label="Enable NFS Shared Storage"
              sub="Mounts a shared filesystem across all cluster nodes." />
            {svc.nfs_enabled && (
              <>
                <Field label="NFS Server IP" hint="Leave blank to use head node IP">
                  <input className="input" value={svc.nfs_server || ''}
                    onChange={(e) => setSvc('nfs_server', e.target.value)} placeholder="192.168.1.10" />
                </Field>
                <Field label="Export / Mount Path">
                  <input className="input" value={svc.nfs_export_path || '/home'}
                    onChange={(e) => setSvc('nfs_export_path', e.target.value)} />
                </Field>
              </>
            )}
          </>
        )}

        {/* ── LDAP ──────────────────────────────────────────────────── */}
        {tab === 'LDAP' && (
          <>
            <Toggle checked={!!svc.ldap_enabled} onChange={(v) => setSvc('ldap_enabled', v)}
              label="Enable LDAP Authentication"
              sub="Centralized user management via OpenLDAP or Active Directory." />
            {svc.ldap_enabled && (
              <>
                <Field label="LDAP Server Hostname / IP">
                  <input className="input" value={svc.ldap_server || ''}
                    onChange={(e) => setSvc('ldap_server', e.target.value)} placeholder="ldap.example.com" />
                </Field>
                <Field label="Base DN">
                  <input className="input" value={svc.ldap_base_dn || ''}
                    onChange={(e) => setSvc('ldap_base_dn', e.target.value)} placeholder="dc=cluster,dc=local" />
                </Field>
              </>
            )}
          </>
        )}

        {/* ── Kubernetes ────────────────────────────────────────────── */}
        {tab === 'Kubernetes' && (
          <Toggle checked={!!svc.kubernetes_enabled} onChange={(v) => setSvc('kubernetes_enabled', v)}
            label="Enable Kubernetes (K8s)"
            sub="Deploys a K8s cluster for containerized AI/ML workloads alongside HPC." />
        )}

        {/* ── Monitoring ────────────────────────────────────────────── */}
        {tab === 'Monitoring' && (
          <>
            <Toggle checked={!!svc.monitoring_enabled} onChange={(v) => setSvc('monitoring_enabled', v)}
              label="Enable Monitoring Stack"
              sub="Deploys Prometheus + Grafana + node-exporter for cluster observability." />
            <Toggle checked={!!svc.infiniband_enabled} onChange={(v) => setSvc('infiniband_enabled', v)}
              label="Enable InfiniBand / RDMA Support"
              sub="Installs Mellanox OFED drivers and configures RDMA networking." />
          </>
        )}

        <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            <Save size={14} /> {saving ? 'Saving…' : 'Save Services Config'}
          </button>
        </div>
      </div>
    </div>
  )
}
