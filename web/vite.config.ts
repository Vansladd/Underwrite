import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Same-origin as prod: the browser calls /api/*, the dev server proxies it to the api container,
// so no CORS is needed anywhere. See DECISIONS D-025.
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://api:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    // Polling: bind-mounted source under Docker on macOS misses inotify events otherwise.
    watch: { usePolling: true },
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
})
