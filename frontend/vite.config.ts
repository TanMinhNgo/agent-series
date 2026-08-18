import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.dirname(fileURLToPath(import.meta.url)) } },
  server: { proxy: { '/api': 'http://localhost:8000' } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('react-markdown') || id.includes('remark-') || id.includes('rehype-')) return 'markdown-vendor';
          if (id.includes('katex')) return 'katex-vendor';
          if (id.includes('@tanstack/react-query')) return 'query-vendor';
          if (id.includes('react-dom') || id.includes('/react/') || id.includes('scheduler')) return 'react-vendor';
          if (id.includes('lucide-react') || id.includes('@base-ui') || id.includes('class-variance-authority') || id.includes('tailwind-merge')) return 'ui-vendor';
          return undefined;
        },
      },
    },
  },
});
