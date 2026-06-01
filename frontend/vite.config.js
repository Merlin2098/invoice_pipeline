import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/uploads': { target: 'http://localhost:3001', changeOrigin: true },
      '/invoices': { target: 'http://localhost:3001', changeOrigin: true },
      '/chat':     { target: 'http://localhost:3001', changeOrigin: true },
    },
  },
})
