import React, { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Server, Network, Settings2, ScrollText,
  BookOpen, List, History, ChevronDown, ChevronRight,
  LayoutList, Layers, Package, ShieldCheck,
} from 'lucide-react'

// ─── Navigation order (top → bottom) ────────────────────────────────────────
// 1. CHAI Releases   (top priority)
// 2. Dashboard
// 3. Inventory
// 4. Cluster Setup   (collapsible group)
// 5. Remaining modules
// ─────────────────────────────────────────────────────────────────────────────

const NAV_TOP = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard'    },
  { to: '/releases',  icon: Package,         label: 'CHAI Releases' },
  { to: '/inventory', icon: List,            label: 'Inventory'    },
]

const CLUSTER_CHILDREN = [
  { to: '/cluster',        icon: LayoutList, label: 'Setup Wizard'  },
  { to: '/cluster/single', icon: Server,     label: 'Single Server' },
  { to: '/cluster/ha',     icon: Layers,     label: 'HA Server Setup' },
]

const NAV_BOTTOM = [
  { to: '/nodes',     icon: Server,      label: 'Nodes'          },
  { to: '/services',  icon: Settings2,   label: 'Services'       },
  { to: '/playbooks', icon: BookOpen,    label: 'Playbooks'      },
  { to: '/logs',      icon: ScrollText,  label: 'Deploy Logs', newTab: true },
  { to: '/backups',   icon: History,     label: 'Backup History' },
  { to: '/audit',     icon: ShieldCheck, label: 'Audit Log'      },
]

function NavItem({ to, icon: Icon, label, indent = false, newTab = false }) {
  return (
    <NavLink
      to={to}
      target={newTab ? '_blank' : undefined}
      rel={newTab ? 'noopener noreferrer' : undefined}
      title={newTab ? `${label} (opens in a new tab)` : undefined}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
          indent ? 'ml-4 text-[13px]' : ''
        } ${
          // NavLink can't know "active" for a target=_blank link the way it
          // does for in-app routes (this tab is never actually ON /logs),
          // so it intentionally never shows the active/selected state.
          isActive && !newTab
            ? 'bg-sky-600/20 text-sky-400 border border-sky-600/30'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800'
        }`
      }
    >
      <Icon size={indent ? 13 : 15} />
      {label}
    </NavLink>
  )
}

export default function Sidebar() {
  const location   = useLocation()
  const clusterOpen = location.pathname.startsWith('/cluster')
  const [expanded, setExpanded] = useState(clusterOpen)

  return (
    <aside className="w-56 shrink-0 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col">
      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV_TOP.map(({ to, icon, label }) => (
          <NavItem key={to} to={to} icon={icon} label={label} />
        ))}

        {/* Cluster Setup — collapsible group */}
        <div>
          <button
            onClick={() => setExpanded((e) => !e)}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              clusterOpen
                ? 'bg-sky-600/10 text-sky-400'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
          >
            <div className="flex items-center gap-3">
              <Network size={15} />
              Cluster Setup
            </div>
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>

          {expanded && (
            <div className="mt-1 space-y-0.5">
              {CLUSTER_CHILDREN.map(({ to, icon, label }) => (
                <NavItem key={to} to={to} icon={icon} label={label} indent />
              ))}
            </div>
          )}
        </div>

        {NAV_BOTTOM.map(({ to, icon, label, newTab }) => (
          <NavItem key={to} to={to} icon={icon} label={label} newTab={newTab} />
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-slate-200 dark:border-slate-800">
        <p className="text-[10px] text-slate-600">v3.0.0 — MIT License</p>
      </div>
    </aside>
  )
}

