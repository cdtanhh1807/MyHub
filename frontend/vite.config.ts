import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Dev: trình duyệt chỉ gọi cùng origin; Vite proxy /api đến FastAPI cục bộ.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true, proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: false } } },
  build: { chunkSizeWarningLimit: 1200 },
});
