import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import './index.css'
import { ThemeProvider, useTheme } from './context/ThemeContext.jsx'

// Toast palette follows the active theme instead of being hardcoded dark —
// previously toasts stayed dark-on-dark styled even in Light Mode.
function ThemedToaster() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 4000,
        style: isDark
          ? { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' }
          : { background: '#ffffff', color: '#0f172a', border: '1px solid #e2e8f0' },
        success: {
          iconTheme: { primary: '#22c55e', secondary: isDark ? '#1e293b' : '#ffffff' },
        },
        error: {
          iconTheme: { primary: '#ef4444', secondary: isDark ? '#1e293b' : '#ffffff' },
        },
      }}
    />
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
        <ThemeProvider>

            <AuthProvider>

                <App />

                <ThemedToaster />

            </AuthProvider>

        </ThemeProvider>
    </BrowserRouter>

  </React.StrictMode>
)
