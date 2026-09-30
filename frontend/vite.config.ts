import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backend = process.env.INET_BACKEND_URL || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: { '/api': backend, '/health': backend },
  },
  build: { outDir: 'build', emptyOutDir: true },
});
