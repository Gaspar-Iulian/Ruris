import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        configure(proxy) {
          proxy.on('proxyReq', (request, incoming) => {
            // Keep Flask's origin check aligned with the local proxy target.
            if (['http://127.0.0.1:5173', 'http://localhost:5173'].includes(incoming.headers.origin)) {
              request.setHeader('Origin', 'http://127.0.0.1:5000');
            }
          });
        },
      },
    },
  },
});
