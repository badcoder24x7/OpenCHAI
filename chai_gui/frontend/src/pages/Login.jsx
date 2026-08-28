/**
 * Login.jsx — OpenCHAI GUI Login Page
 * Authenticates using Linux system (PAM) credentials.
 */

import React, { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import {
  Eye,
  EyeOff,
  Loader2,
  AlertCircle
} from 'lucide-react'

import cdacLogo from '../assets/logo/cdac.png'
import nsmLogo from '../assets/logo/nsm.png'
import openchaiLogo from '../assets/logo/openchai.png'
import wallImage from '../assets/logo/param_wallpaper.png'

export default function Login() {
  const { login, isLoggedIn, loading } = useAuth()

  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from?.pathname || '/dashboard'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const usernameRef = useRef(null)

  // The login page always renders in Light Mode, even if the user's last
  // session was in Dark Mode — it's a fixed brand screen, not part of the
  // themed app shell. This restores whichever theme was saved as soon as
  // the user leaves the login page (e.g. after a successful sign-in).
  useEffect(() => {
    const root = document.documentElement
    const wasDark = root.classList.contains('dark')
    root.classList.remove('dark')
    root.classList.add('light')
    return () => {
      if (wasDark) {
        root.classList.remove('light')
        root.classList.add('dark')
      }
    }
  }, [])

  useEffect(() => {
    if (isLoggedIn) {
      navigate(from, { replace: true })
    }
  }, [isLoggedIn, navigate, from])

  useEffect(() => {
    usernameRef.current?.focus()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!username.trim() || !password) {
      setError('Username and password are required.')
      return
    }

    setError('')
    setSubmitting(true)

    const result = await login(username.trim(), password)

    setSubmitting(false)

    if (result.ok) {
      navigate(from, { replace: true })
    } else {
      setError(result.message || 'Login failed.')
      setPassword('')
    }
  }

  return (
    <div className="min-h-screen w-full bg-white overflow-x-hidden">

      {/* ===========================================================
                            Top Header
      ============================================================ */}

      <header className="h-16 bg-brand border-b border-sky-800 shadow-md">
        <div className="flex items-center h-full px-4 sm:px-6">

          <img
            src={nsmLogo}
            alt="NSM"
            className="h-6 sm:h-8 w-auto"
          />

          <div className="mx-3 sm:mx-5 h-6 sm:h-8 border-l border-slate-300"></div>

          <img
            src={cdacLogo}
            alt="CDAC"
            className="h-8 sm:h-11 w-auto"
          />

        </div>
      </header>

      {/* ===========================================================
                          Login Area
      ============================================================ */}

      <div className="flex min-h-[calc(100vh-56px)] sm:min-h-[calc(100vh-64px)] w-full">

        {/* ================= Wallpaper (hidden on small/medium) ================= */}

        <div className="hidden lg:block lg:w-3/5 xl:w-2/3 relative overflow-hidden">

          <img
            src={wallImage}
            alt="OpenCHAI Wallpaper"
            className="absolute inset-0 h-full w-full object-cover object-center"
          />

          {/* Light overlay for brand tint */}
          <div className="absolute inset-0 bg-gradient-to-br from-brand/20 to-white/10"></div>

        </div>

        {/* ================= Login Panel ================= */}

        <div className="w-full lg:w-2/5 xl:w-1/3 flex items-center justify-center bg-gray-200 px-4 sm:px-8 md:px-10 py-8 sm:py-10">

          <div className="w-full max-w-md">

            {/* Logo */}

            <div className="text-center mb-6 sm:mb-8">

              <img
                src={openchaiLogo}
                alt="OpenCHAI"
                className="mx-auto h-14 sm:h-16 md:h-20 object-contain"
              />

              <p className="mt-3 font-bold text-brand" style={{ fontSize: 'clamp(1.5rem, 4vw, 1.875rem)' }}>
                C-HAI
              </p>

              <p className="mt-2 tracking-widest uppercase text-slate-700" style={{ fontSize: 'clamp(0.7rem, 1.6vw, 0.875rem)' }}>
                C-DAC HPC-AI Cluster Management Platform
              </p>

            </div>

            {/* Login Card */}

            <div className="bg-white rounded-xl border border-slate-200 shadow-lg shadow-slate-200/60 p-5 sm:p-7 md:p-8">

              <div className="mb-5 sm:mb-6">

                <h2 className="text-lg sm:text-xl font-semibold text-slate-900">
                  Sign In
                </h2>

                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                  Login using your Linux system credentials
                </p>

              </div>

              {error && (
                <div className="flex items-start gap-3 mb-5 rounded-lg border border-red-200 bg-red-50 p-3">

                  <AlertCircle
                    size={18}
                    className="mt-0.5 shrink-0 text-red-500"
                  />

                  <p className="text-sm text-red-700">
                    {error}
                  </p>

                </div>
              )}

              <form
                onSubmit={handleSubmit}
                autoComplete="off"
                className="space-y-4 sm:space-y-5"
              >

                <div>

                  <label className="block text-m font-medium text-slate-900 mb-1.5">
                    Username
                  </label>

                  <input
                    ref={usernameRef}
                    type="text"
                    className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 placeholder-slate-400 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20 disabled:bg-slate-100 disabled:text-slate-600 dark:text-slate-400"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Linux username"
                    autoComplete="username"
                    disabled={submitting}
                  />

                </div>

                <div>

                  <label className="block text-m font-medium text-slate-900 mb-1.5">
                    Password
                  </label>

                  <div className="relative">

                    <input
                      type={showPwd ? 'text' : 'password'}
                      className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 pr-10 text-slate-900 placeholder-slate-400 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20 disabled:bg-slate-100 disabled:text-slate-600 dark:text-slate-400"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="System password"
                      autoComplete="current-password"
                      disabled={submitting}
                    />

                    <button
                      type="button"
                      tabIndex={-1}
                      onClick={() => setShowPwd(!showPwd)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 dark:text-slate-400 hover:text-slate-700 transition"
                    >
                      {showPwd ? (
                        <EyeOff size={18} />
                      ) : (
                        <Eye size={18} />
                      )}
                    </button>

                  </div>

                </div>

                <button
                  type="submit"
                  disabled={loading || submitting}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand py-3 font-medium text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {(loading || submitting) ? (
                    <>
                      <Loader2
                        size={18}
                        className="animate-spin"
                      />
                      Authenticating...
                    </>
                  ) : (
                    'Sign In'
                  )}
                </button>

              </form>

            </div>

            <div className="mt-4 text-center text-s text-slate-600">
              C-HAI GUI v1.0 • Powered by C-DAC Pune
            </div>

          </div>

        </div>

      </div>

    </div>
  )
}
