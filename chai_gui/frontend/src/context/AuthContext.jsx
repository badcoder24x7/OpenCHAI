/**
 * AuthContext — global auth state for OpenCHAI GUI
 *
 * Token storage: localStorage (persists across page refreshes AND new tabs/
 * windows — fixes Issues 5 & 6 where opening a new tab forced re-login).
 * Security: the token is a signed JWT. localStorage is acceptable here
 * because this is an admin-only intranet tool running on the HPC network,
 * not a public-facing application.
 * To log out from all tabs, call logout() which removes the key from
 * localStorage; other tabs detect the storage event and clear their state.
 */

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
import toast from 'react-hot-toast'
import { authApi, setAuthToken } from '../api/api.js'

const AuthContext = createContext(null)

const SESSION_TOKEN_KEY = 'openchai_token'
const SESSION_USER_KEY  = 'openchai_user'

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)
  const [token,   setToken]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [ready,   setReady]   = useState(false)

  // Restore session from localStorage on mount.
  // CRITICAL: setAuthToken() is called synchronously here, in the SAME tick
  // as the state restore — not in a separate effect elsewhere — so the axios
  // header is guaranteed to be set before any other component can mount and
  // fire a data request. This fixes the "Authentication required" banner
  // that could appear after login/refresh due to a timing race.
  useEffect(() => {
    try {
      const storedToken = localStorage.getItem(SESSION_TOKEN_KEY)
      const storedUser  = localStorage.getItem(SESSION_USER_KEY)
      if (storedToken && storedUser) {
        setToken(storedToken)
        setUser(JSON.parse(storedUser))
        setAuthToken(storedToken)
      }
    } catch {
      localStorage.removeItem(SESSION_TOKEN_KEY)
      localStorage.removeItem(SESSION_USER_KEY)
      setAuthToken(null)
    } finally {
      setReady(true)
    }
  }, [])

  const login = useCallback(async (username, password) => {
    setLoading(true)
    try {
      const res = await authApi.login(username, password)
      const userObj = {
        username:     res.username,
        display_name: res.display_name,
        role:         res.role,
        groups:       res.groups,
        expires_in:   res.expires_in,
      }
      // Set the axios default header FIRST, synchronously, before any state
      // update that could trigger a re-render/navigation. This guarantees
      // every subsequent request (even ones fired the instant the caller's
      // navigate() runs) carries the Authorization header.
      setAuthToken(res.access_token)
      setToken(res.access_token)
      setUser(userObj)
      localStorage.setItem(SESSION_TOKEN_KEY, res.access_token)
      localStorage.setItem(SESSION_USER_KEY,  JSON.stringify(userObj))
      return { ok: true }
    } catch (err) {
      return { ok: false, message: err.message }
    } finally {
      setLoading(false)
    }
  }, [])

  const tokenRef = useRef(null)
  useEffect(() => { tokenRef.current = token }, [token])

  const clearSession = useCallback(() => {
    setAuthToken(null)
    setToken(null)
    setUser(null)
    localStorage.removeItem(SESSION_TOKEN_KEY)
    localStorage.removeItem(SESSION_USER_KEY)
  }, [])

  const logout = useCallback(async () => {
    try { await authApi.logout() } catch { /* ignore network error on logout */ }
    clearSession()
  }, [clearSession])

  // FIX 1: react once, globally, whenever any API call comes back 401.
  // Clearing the session here flips isLoggedIn to false, which every
  // <ProtectedRoute> already watches — so every open page redirects to
  // /login on its own, with no per-page inline "token invalid" banners
  // and no manual navigate() call needed from outside the router.
  useEffect(() => {
    const onUnauthorized = () => {
      // Only act (and only notify) if we actually believed we were logged
      // in — avoids a stray toast/redirect if this fires while already
      // logged out (e.g. a request that was in flight at logout time).
      if (tokenRef.current) {
        toast.error('Your session has expired. Please log in again.')
        clearSession()
      }
    }
    window.addEventListener('openchai:unauthorized', onUnauthorized)
    return () => window.removeEventListener('openchai:unauthorized', onUnauthorized)
  }, [clearSession])

  return (
    <AuthContext.Provider value={{
      user, token, loading, ready,
      login, logout,
      isAdmin:    user?.role === 'admin',
      isLoggedIn: !!token && !!user,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
