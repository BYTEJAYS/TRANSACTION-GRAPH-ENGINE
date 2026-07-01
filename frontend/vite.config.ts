import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  optimizeDeps: {
    include: ['react-force-graph-3d', 'three', 'framer-motion'],
  },

  build: {
    target: 'es2020',
    chunkSizeWarningLimit: 3000,
  },

  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/transaction': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Narrowed to the only backend graph route so the client-side /graph
      // page route (react-router) is served by the SPA instead of being proxied.
      '/graph/clear': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ub': {
        // UB runs as its own service on :8001 (see TGIE/control). The voice orb's
        // /ub/* calls are proxied here so UB is independently start/stoppable.
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
