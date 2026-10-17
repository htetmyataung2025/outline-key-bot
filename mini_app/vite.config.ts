import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: './',
  plugins: [vue(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
    // Arena's per-sandbox preview uses a dynamic *.e2b.app hostname.
    // Restrict to your own domain when deploying a development server elsewhere.
    allowedHosts: true,
  },
  preview: { host: '0.0.0.0', port: 4173, allowedHosts: true },
  build: { target: 'es2022', cssCodeSplit: false, assetsInlineLimit: 1_000_000 },
})
