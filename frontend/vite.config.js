import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The dev server proxies /api and /mcp to the FastAPI backend on :8000,
// so the session cookie is same-origin and no CORS setup is needed.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/mcp': 'http://127.0.0.1:8000',
    },
  },
  // One small app bundle (React 19 + router) is ~510 kB; no need to split it.
  build: { chunkSizeWarningLimit: 600 },
  test: {
    environment: 'jsdom',
  },
})
