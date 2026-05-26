import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/targets':  'http://localhost:8000',
      '/research': 'http://localhost:8000',
      '/emails':   'http://localhost:8000',
      '/tracking': 'http://localhost:8000',
      '/campaigns':'http://localhost:8000',
      '/health':   'http://localhost:8000',
    },
  },
})
