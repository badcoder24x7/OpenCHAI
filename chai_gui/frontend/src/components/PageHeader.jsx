import React from 'react'

/**
 * PageHeader — per-page section title, rendered in the page BODY.
 *
 * The top header bar (Navbar.jsx) is constant across every page (logo +
 * user menu only) so it never changes on navigation, matching the
 * reference "emulazim" layout. Each page is responsible for rendering its
 * own title via this component instead of relying on a route→title map
 * in the header.
 *
 * Usage:
 *   <PageHeader title="Inventory Management" subtitle="Manage cluster nodes" />
 */
export default function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{title}</h1>
        {subtitle && <p className="text-xs text-slate-600 dark:text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}
