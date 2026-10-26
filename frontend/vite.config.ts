import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => ({
  // Deployed under https://gadzhilaev.ru/aspekt/
  base: mode === 'production' ? '/aspekt/' : '/',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || loadEnv(mode, process.cwd(), 'VITE_').VITE_PROXY_TARGET || 'http://127.0.0.1:8003',
        changeOrigin: true,
      },
    },
  },
}))
