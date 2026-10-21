import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const realApi = process.env.RURIS_REAL_API === '1';
const port = realApi ? 5174 : 5173;
const apiTarget = realApi ? 'http://127.0.0.1:5201' : 'http://127.0.0.1:5000';

export default defineConfig({
  plugins: [react()],
  server: {
    port,
    strictPort: true,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        configure(proxy) {
          proxy.on('proxyReq', (request, incoming) => {
            // Keep Flask's origin check aligned with the local proxy target.
            if ([`http://127.0.0.1:${port}`, `http://localhost:${port}`].includes(incoming.headers.origin)) {
              request.setHeader('Origin', apiTarget);
            }
          });
        },
      },
    },
  },
});
