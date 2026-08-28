import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Vite dev server config  (v3)
 *
 * Fix vs original: /ws proxy was unused — actual WS endpoints are
 * /logs/ws/* and /logtail/*.  Both are now correctly proxied.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // HTTP REST API
      '/api': {
        target:       'http://localhost:8000',
        changeOrigin: true,
        rewrite:      (path) => path.replace(/^\/api/, ''),
      },
      // Ansible job log WebSocket
      '/logs/ws': {
        target:       'ws://localhost:8000',
        ws:           true,
        changeOrigin: true,
      },
      // Live log-file tail WebSocket
      '/logtail': {
        target:       'ws://localhost:8000',
        ws:           true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir:                  'dist',
    sourcemap:               false,
    chunkSizeWarningLimit:   800,
  },
})
