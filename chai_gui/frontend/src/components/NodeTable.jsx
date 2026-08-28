import React from 'react'
import { Pencil, Trash2, Server, Cpu, HardDrive } from 'lucide-react'

const ROLE_BADGE = {
  headnode:   'badge-blue',
  compute:    'badge-green',
  gpu:        'badge-yellow',
  storage:    'badge-gray',
  login:      'badge-gray',
  management: 'badge-gray',
  service:    'badge-gray',
}

/**
 * NodeTable
 * Props:
 *   nodes    — array of Node objects
 *   onEdit   — fn(node)
 *   onDelete — fn(node)
 */
export default function NodeTable({ nodes = [], onEdit, onDelete }) {
  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-600">
        <Server size={40} className="mb-3 opacity-30" />
        <p className="text-sm">No nodes added yet.</p>
        <p className="text-xs mt-1">Click "Add Node" to define cluster members.</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800 text-left text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">
            <th className="pb-3 pr-4 font-medium">Hostname</th>
            <th className="pb-3 pr-4 font-medium">IP Address</th>
            <th className="pb-3 pr-4 font-medium">Role</th>
            <th className="pb-3 pr-4 font-medium">
              <Cpu size={11} className="inline mr-1" />CPUs
            </th>
            <th className="pb-3 pr-4 font-medium">RAM (GB)</th>
            <th className="pb-3 pr-4 font-medium">GPUs</th>
            <th className="pb-3 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60">
          {nodes.map((node) => (
            <tr key={node.id} className="hover:bg-slate-100 dark:hover:bg-slate-800/30 transition-colors group">
              <td className="py-3 pr-4 font-mono text-slate-800 dark:text-slate-200">{node.hostname}</td>
              <td className="py-3 pr-4 font-mono text-slate-600 dark:text-slate-400">{node.ip_address}</td>
              <td className="py-3 pr-4">
                <span className={ROLE_BADGE[node.role] || 'badge-gray'}>
                  {node.role}
                </span>
              </td>
              <td className="py-3 pr-4 text-slate-600 dark:text-slate-400">{node.cpu_count ?? '—'}</td>
              <td className="py-3 pr-4 text-slate-600 dark:text-slate-400">{node.ram_gb ?? '—'}</td>
              <td className="py-3 pr-4 text-slate-600 dark:text-slate-400">
                {node.gpu_count
                  ? `${node.gpu_count}× ${node.gpu_model || 'GPU'}`
                  : '—'}
              </td>
              <td className="py-3">
                <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => onEdit && onEdit(node)}
                    className="p-1 text-slate-600 dark:text-slate-400 hover:text-sky-400 transition-colors"
                    title="Edit node"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    onClick={() => onDelete && onDelete(node)}
                    className="p-1 text-slate-600 dark:text-slate-400 hover:text-red-400 transition-colors"
                    title="Delete node"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
