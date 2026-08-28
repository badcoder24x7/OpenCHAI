import React, { useEffect, useState } from 'react'
import { RefreshCw, Wifi, WifiOff, LogOut, User, Shield, ChevronDown } from 'lucide-react'
import client from '../api/api.js'
import { useAuth } from '../context/AuthContext.jsx'
import openchaiLogo from '../assets/logo/chai.png'
import cdacLogo from '../assets/logo/cdac.png'
import nsmLogo from '../assets/logo/nsm.png'
import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'
// ─────────────────────────────────────────────────────────────────────────────
// Navbar — constant top header bar (does NOT change between pages).
//
// Layout mirrors the reference "emulazim" header:
//   ┌──────────────────────────────────────────────────────────────────┐
//   │ [Logo] OpenCHAI            (constant)            [status][user▾] │
//   └──────────────────────────────────────────────────────────────────┘
//
// The per-page section title (e.g. "Inventory Management") used to live
// here and changed on every navigation — that's been moved into each page's
// own body via <PageHeader/> so this bar never changes after login.
// ─────────────────────────────────────────────────────────────────────────────

export default function Navbar() {
  const { user, logout, isAdmin } = useAuth()
  const [online, setOnline]       = useState(null)
  const [menuOpen, setMenuOpen]   = useState(false)
  const { theme, setTheme } = useTheme()
  const checkHealth = async () => {
    try { await client.get('/health'); setOnline(true)  }
    catch { setOnline(false) }
  }

  useEffect(() => {
    checkHealth()
    const id = setInterval(checkHealth, 15_000)
    return () => clearInterval(id)
  }, [])

  // Close user menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return
    const handler = () => setMenuOpen(false)
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [menuOpen])

  return (
    <header className="h-16 shrink-0 bg-brand border-b border-sky-900 shadow-md flex items-center justify-between px-6">

        {/* ===========================================================
            Left : OpenCHAI
        =========================================================== */}

        <div className="flex items-center gap-3">
            {/* NSM Logo */}

            <img
                src={nsmLogo}
                alt="NSM"
                className="h-6 w-auto"
            />

       	  <div className="mx-3 sm:mx-5 h-6 sm:h-8 border-l border-slate-300"></div>

            {/* CDAC Logo */}

            <img
                src={cdacLogo}
                alt="CDAC"
                className="h-10 w-auto"
            />


	  <div className="mx-3 sm:mx-5 h-6 sm:h-8 border-l border-slate-300"></div>

            <img
                src={openchaiLogo}
                alt="OpenCHAI"
                className="h-10 w-auto"
            />

            <div className="leading-tight">
                <p className="text-white text-xl font-black tracking-wide">
                    C-HAI
                </p>

                <p className="text-sky-100 text-xs">
                    Cluster Manager Tool
                </p>
            </div>

        </div>


        {/* ===========================================================
            Right Side
        =========================================================== */}

        <div className="flex items-center gap-5">

            <button
                onClick={() =>
                    setTheme(theme === 'dark' ? 'light' : 'dark')
                }
                title={
                    theme === 'dark'
                        ? 'Switch to Light Mode'
                        : 'Switch to Dark Mode'
                }
                className="flex items-center justify-center w-10 h-10 rounded-lg bg-brand-panel hover:bg-brand-panelHover transition-colors"
            >

                {theme === 'dark'
                    ? (
                        <Sun
                            size={18}
                            className="text-yellow-300"
                        />
                    )
                    : (
                        <Moon
                            size={18}
                            className="text-white"
                        />
                    )}

            </button>	  

            {/* Backend Status */}

            <button
                onClick={checkHealth}
                title="Check backend connectivity"
                className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-brand-panel hover:bg-brand-panelHover transition-colors"
            >

                {online === null
                    ? <RefreshCw size={13} className="animate-spin text-white" />
                    : online
                    ? <Wifi size={13} className="text-green-400" />
                    : <WifiOff size={13} className="text-red-400" />}

                <span className="text-xs text-white">
                    {online === null
                        ? 'Checking...'
                        : online
                        ? 'Online'
                        : 'Offline'}
                </span>

            </button>


            {/* User */}

            {user && (
                <div className="relative">

                    <button
                        onClick={(e) => {
                            e.stopPropagation()
                            setMenuOpen((o) => !o)
                        }}
                        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-brand-panel hover:bg-brand-panelHover transition-colors"
                    >

                        <div
                            className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-semibold ${
                                isAdmin ? 'bg-sky-600' : 'bg-slate-600'
                            }`}
                        >
                            {user.display_name?.charAt(0).toUpperCase()}
                        </div>

                        <div className="text-left">

                            <p className="text-white text-sm">
                                {user.display_name || user.username}
                            </p>

                            <p className="text-sky-100 text-[10px]">
                                {user.role}
                            </p>

                        </div>

                        <ChevronDown
                            size={13}
                            className="text-sky-100"
                        />

                    </button>

                    {menuOpen && (
                        <div className="absolute right-0 top-full mt-1 w-56 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl shadow-xl z-50 overflow-hidden">

                            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">

                                <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                                    {user.display_name || user.username}
                                </p>

                                <p className="text-[10px] text-slate-600 dark:text-slate-400 mt-1">
                                    {user.username}
                                </p>

                            </div>

                            <button
                                onClick={logout}
                                className="w-full flex items-center gap-2 px-4 py-3 text-xs text-red-400 hover:bg-red-900/20"
                            >
                                <LogOut size={13} />
                                Sign Out
                            </button>

                        </div>
                    )}

                </div>
            )}

        </div>

    </header>

  )
}
