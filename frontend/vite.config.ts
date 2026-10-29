import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// dev.py injects the discovered ports so the proxy and API base stay in sync
// even when the default ports are already in use.
const port = Number(process.env.PORT) || 5177
const backendTarget =
  process.env.VITE_BACKEND_TARGET || process.env.VITE_API_URL || 'http://127.0.0.1:8800'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true
      },
      '/admin': {
        target: backendTarget,
        changeOrigin: true
      },
      '/static': {
        target: backendTarget,
        changeOrigin: true
      }
    }
  }
})
