import React, { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar         from './components/Sidebar.jsx'
import Navbar          from './components/Navbar.jsx'
import ProtectedRoute  from './components/ProtectedRoute.jsx'
import Login           from './pages/Login.jsx'

// Lazy-load heavy page bundles
const Dashboard         = lazy(() => import('./pages/Dashboard.jsx'))
const ClusterSetup      = lazy(() => import('./pages/ClusterSetup.jsx'))
const InventoryDef      = lazy(() => import('./pages/InventoryDef.jsx'))
const Nodes             = lazy(() => import('./pages/Nodes.jsx'))
const Services          = lazy(() => import('./pages/Services.jsx'))
const PlaybooksDynamic  = lazy(() => import('./pages/PlaybooksDynamic.jsx'))
const Logs              = lazy(() => import('./pages/Logs.jsx'))
const BackupHistory     = lazy(() => import('./pages/BackupHistory.jsx'))
const AuditLog          = lazy(() => import('./pages/AuditLog.jsx'))
const ChaiReleaseWizard = lazy(() => import('./pages/ChaiReleaseWizard.jsx'))

function ClusterHA()     { return <ClusterSetup preType="ha"     /> }
function ClusterSingle() { return <ClusterSetup preType="single" /> }

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
    </div>
  )
}

// The authenticated shell — Sidebar + Navbar + page content
function AppShell({ children }) {
  return (
    <div className="flex flex-col h-screen overflow-hidden">

      {/* ===================== Full Width Header ===================== */}

      <Navbar />

      {/* ===================== Sidebar + Content ===================== */}

      <div className="flex flex-1 overflow-hidden">

        <Sidebar />

        <main
          className="
             flex-1
             overflow-y-auto
             p-6
             bg-slate-100 dark:bg-slate-950
             text-slate-900 dark:text-slate-100
             transition-colors
             duration-300
          "
        >
          <Suspense fallback={<PageLoader />}>
            {children}
          </Suspense>
        </main>

      </div>

    </div>
  )
}


export default function App() {
  return (
    <Routes>
      {/* Public — login page */}
      <Route path="/login" element={<Login />} />

      {/* All other routes require authentication */}
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <AppShell>
              <Routes>
                <Route path="/"                element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard"       element={<Dashboard />} />
                <Route path="/cluster"         element={<ClusterSetup />} />
                <Route path="/cluster/ha"      element={<ClusterHA />} />
                <Route path="/cluster/single"  element={<ClusterSingle />} />
                <Route path="/inventory"       element={<InventoryDef />} />
                <Route path="/nodes"           element={<Nodes />} />
                <Route path="/services"        element={<Services />} />
                <Route path="/playbooks"       element={<PlaybooksDynamic />} />
                <Route path="/logs"            element={<Logs />} />
                <Route path="/logs/:jobId"     element={<Logs />} />
                <Route path="/backups"         element={<BackupHistory />} />
                <Route path="/audit"           element={<AuditLog />} />
                <Route path="/releases"        element={<ChaiReleaseWizard />} />
                <Route path="*"               element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </AppShell>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}
