import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/monaco-editor/') || id.includes('node_modules/@monaco-editor/')) return 'editor'
          if (id.includes('node_modules/recharts/') || id.includes('node_modules/d3-')) return 'charts'
          if (id.includes('node_modules/react-dom/') || id.includes('node_modules/react/') || id.includes('node_modules/scheduler/')) return 'react'
        },
      },
    },
  },
})