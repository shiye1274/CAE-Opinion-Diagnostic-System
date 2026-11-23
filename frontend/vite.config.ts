import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 开发期代理到 FastAPI，前端代码里直接写 /api/v1/...
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
