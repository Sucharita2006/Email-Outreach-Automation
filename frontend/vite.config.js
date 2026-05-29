import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/targets':  'http://localhost:8000',
      '/research': 'http://localhost:8000',
      '/emails':   'http://localhost:8000',
      '/tracking': 'http://localhost:8000',
      '/campaigns':'http://localhost:8000',
      '/health':   'http://localhost:8000',
      '/auth':     'http://localhost:8000',
    },
  },
})
