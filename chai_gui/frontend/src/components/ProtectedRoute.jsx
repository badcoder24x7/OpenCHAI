/**
 * ProtectedRoute — redirects to /login if not authenticated.
 * Preserves the attempted URL so after login the user lands back
 * where they wanted to go.
 */

import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function ProtectedRoute({ children }) {
  const { isLoggedIn, ready } = useAuth()
  const location = useLocation()

  // Wait for auth context to initialise (avoids flash of login page)
  if (!ready) return (
    <div className="flex items-center justify-center h-screen">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500" />
    </div>
  )

  if (!isLoggedIn) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}
