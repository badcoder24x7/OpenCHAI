import React, { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { logsApi, deployApi } from '../api/api.js'
import LogViewer from '../components/LogViewer.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { ScrollText, ChevronLeft, Clock, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

function StatusIcon({ status }) {
  if (status === 'success') return <CheckCircle2 size={14} className="text-green-400" />
  if (status === 'failed')  return <XCircle size={14} className="text-red-400" />
  if (status === 'running') return <Loader2 size={14} className="text-yellow-400 animate-spin" />
  return <Clock size={14} className="text-slate-500 dark:text-slate-400" />
}

export default function Logs() {
  const { jobId } = useParams()
  const navigate  = useNavigate()
  const [jobs, setJobs]     = useState([])
  const [loading, setLoading] = useState(true)

  const fetchJobs = async () => {
    try {
      const list = await logsApi.jobs()
      setJobs(list.sort((a, b) => new Date(b.started_at) - new Date(a.started_at)))
    } catch (e) {
      toast.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchJobs()
    const id = setInterval(fetchJobs, 5000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="space-y-4">
      <PageHeader title="Deployment Logs" subtitle="Live and historical job output" />
      <div className="flex gap-4 h-[calc(100vh-12rem)]">
      {/* Job list sidebar */}
      <div className="w-64 shrink-0 flex flex-col gap-2">
        <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400 text-xs font-medium uppercase tracking-wide px-1">
          <ScrollText size={12} /> Deployment Jobs
        </div>
        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-sky-500" />
            </div>
          ) : jobs.length === 0 ? (
            <p className="text-xs text-slate-600 text-center mt-8">No jobs yet.</p>
          ) : (
            jobs.map((job) => (
              <Link
                key={job.job_id}
                to={`/logs/${job.job_id}`}
                className={`flex flex-col gap-0.5 p-3 rounded-lg border transition-colors text-left w-full ${
                  jobId === job.job_id
                    ? 'bg-sky-900/20 border-sky-700/50'
                    : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-2">
                  <StatusIcon status={job.status} />
                  <span className="text-xs font-mono text-slate-600 dark:text-slate-300 truncate flex-1">
                    {job.playbook?.split('/').pop() || 'unknown'}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-[10px] text-slate-600">
                    {job.started_at ? new Date(job.started_at).toLocaleTimeString() : '—'}
                  </span>
                  <span className="text-[10px] text-slate-600">{job.line_count} lines</span>
                </div>
              </Link>
            ))
          )}
        </div>
      </div>

      {/* Log viewer */}
      <div className="flex-1 flex flex-col">
        {jobId ? (
          <>
            <div className="flex items-center gap-3 mb-3">
              <button onClick={() => navigate('/logs')} className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
                <ChevronLeft size={16} />
              </button>
              <span className="text-xs font-mono text-slate-600 dark:text-slate-400">Job: {jobId}</span>
            </div>
            <div className="flex-1">
              <LogViewer jobId={jobId} />
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center flex-1 text-slate-600">
            <ScrollText size={48} className="mb-3 opacity-20" />
            <p className="text-sm">Select a job to view logs.</p>
          </div>
        )}
      </div>
      </div>
    </div>
  )
}
