import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/node_modules\/(markstream|stream-markdown|markdown-it|shiki|@shikijs)/.test(id)) return 'markdown'
          if (id.includes('node_modules/element-plus')) return 'ui'
          if (id.includes('node_modules')) return 'vendor'
        },
      },
    },
  },
})
