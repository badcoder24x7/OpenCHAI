import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { clusterApi, nodesApi, deployApi } from '../api/api.js'
import PageHeader from '../components/PageHeader.jsx'
import {
  Server, Network, Cpu, Activity, CheckCircle2,
  XCircle, Clock, ChevronRight, AlertCircle,
} from 'lucide-react'

function StatCard({ icon: Icon, label, value, sub, color = 'sky' }) {
  const colors = {
    sky:    'bg-sky-900/30 text-sky-400 border-sky-800/50',
    green:  'bg-green-900/30 text-green-400 border-green-800/50',
    yellow: 'bg-yellow-900/30 text-yellow-400 border-yellow-800/50',
    red:    'bg-red-900/30 text-red-400 border-red-800/50',
  }
  return (
    <div className={`card flex items-start gap-4 border ${colors[color]}`}>
      <div className={`p-2 rounded-lg ${colors[color]}`}>
        <Icon size={20} />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-900 dark:text-white">{value ?? '—'}</p>
        <p className="text-sm font-medium text-slate-600 dark:text-slate-300 mt-0.5">{label}</p>
        {sub && <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{sub}</p>}
      </div>
    </div>
  )
}

function JobStatusBadge({ status }) {
  if (status === 'success') return <span className="badge-green">Success</span>
  if (status === 'failed')  return <span className="badge-red">Failed</span>
  if (status === 'running') return <span className="badge-yellow">Running</span>
  return <span className="badge-gray">{status}</span>
}

export default function Dashboard() {
  const [clusterState, setClusterState] = useState(null)
  const [jobs, setJobs]                 = useState([])
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState(null)

  useEffect(() => {
    async function fetchAll() {
      try {
        const [state, jobList] = await Promise.all([
          clusterApi.state(),
          deployApi.jobs(),
        ])
        setClusterState(state)
        setJobs(jobList.slice(0, 5))
        setError(null)   // clear any stale error now that the fetch succeeded
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    fetchAll()
    const id = setInterval(fetchAll, 10_000)
    return () => clearInterval(id)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
      </div>
    )
  }

  const cfg   = clusterState?.config
  const nodes = clusterState?.nodes || []
  const status = clusterState?.deployment_status || 'pending'

  const computeNodes = nodes.filter((n) => n.role === 'compute').length
  const gpuNodes     = nodes.filter((n) => n.role === 'gpu').length
  const totalGPUs    = nodes.reduce((s, n) => s + (n.gpu_count || 0), 0)

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" subtitle="Cluster overview and recent activity" />

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
          <AlertCircle size={16} />
          {error.toLowerCase().includes('authentication') || error.toLowerCase().includes('401')
            ? 'Your session has expired or is invalid — please sign in again.'
            : `${error} — check that the backend is reachable.`}
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          icon={Server}
          label="Total Nodes"
          value={nodes.length}
          sub={`${computeNodes} compute · ${gpuNodes} GPU`}
          color="sky"
        />
        <StatCard
          icon={Cpu}
          label="Total GPUs"
          value={totalGPUs}
          sub={totalGPUs > 0 ? 'Across GPU nodes' : 'No GPU nodes'}
          color="yellow"
        />
        <StatCard
          icon={Network}
          label="Cluster"
          value={cfg?.cluster_name || 'Not configured'}
          sub={cfg ? `Scheduler: ${cfg.scheduler}` : 'No config yet'}
          color="sky"
        />
        <StatCard
          icon={Activity}
          label="Deploy Status"
          value={status.charAt(0).toUpperCase() + status.slice(1)}
          sub={clusterState?.last_deploy_at ? `Last: ${new Date(clusterState.last_deploy_at).toLocaleString()}` : 'Never deployed'}
          color={status === 'success' ? 'green' : status === 'failed' ? 'red' : 'sky'}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Cluster summary */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Cluster Overview</h2>
            <Link to="/cluster" className="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1">
              Configure <ChevronRight size={12} />
            </Link>
          </div>
          {cfg ? (
            <dl className="space-y-3 text-sm">
              {[
                ['Cluster Name',   cfg.cluster_name],
                ['Head Node IP',   cfg.headnode_ip],
                ['Scheduler',      cfg.scheduler],
                ['Network',        cfg.network?.management_network],
                ['Fabric',         cfg.network?.fabric],
                ['SLURM',          cfg.services?.slurm_enabled ? '✓ Enabled' : '✗ Disabled'],
                ['LDAP',           cfg.services?.ldap_enabled  ? '✓ Enabled' : '✗ Disabled'],
                ['NFS',            cfg.services?.nfs_enabled   ? '✓ Enabled' : '✗ Disabled'],
                ['Monitoring',     cfg.services?.monitoring_enabled ? '✓ Enabled' : '✗ Disabled'],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <dt className="text-slate-500 dark:text-slate-400">{k}</dt>
                  <dd className="text-slate-600 dark:text-slate-300 font-mono text-xs">{v ?? '—'}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <div className="flex flex-col items-center py-8 text-slate-600">
              <AlertCircle size={32} className="mb-2 opacity-40" />
              <p className="text-sm">No cluster configured yet.</p>
              <Link to="/cluster" className="mt-3 btn-primary text-xs">
                Start Cluster Setup
              </Link>
            </div>
          )}
        </div>

        {/* Recent jobs */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Recent Deployments</h2>
            <Link to="/logs" className="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1">
              All jobs <ChevronRight size={12} />
            </Link>
          </div>
          {jobs.length === 0 ? (
            <div className="flex flex-col items-center py-8 text-slate-600">
              <Clock size={32} className="mb-2 opacity-40" />
              <p className="text-sm">No deployments yet.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {jobs.map((job) => (
                <a
                  key={job.job_id}
                  href={`/logs/${job.job_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between p-3 rounded-lg bg-slate-100 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                >
                  <div>
                    <p className="text-xs font-mono text-slate-600 dark:text-slate-300 truncate max-w-[220px]">
                      {job.playbook?.split('/').pop()}
                    </p>
                    <p className="text-[10px] text-slate-600 mt-0.5">
                      {job.started_at ? new Date(job.started_at).toLocaleString() : 'Unknown'}
                    </p>
                  </div>
                  <JobStatusBadge status={job.status} />
                </a>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Node role breakdown */}
      {nodes.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-4">Node Inventory</h2>
          <div className="flex flex-wrap gap-3">
            {['headnode','compute','gpu','storage','login','management','service'].map((role) => {
              const count = nodes.filter((n) => n.role === role).length
              if (count === 0) return null
              return (
                <div key={role} className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-lg">
                  <Server size={13} className="text-sky-400" />
                  <span className="text-xs text-slate-600 dark:text-slate-300 capitalize">{role}</span>
                  <span className="text-xs font-bold text-slate-900 dark:text-white">{count}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
