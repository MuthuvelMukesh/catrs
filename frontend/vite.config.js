import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 3000,
    proxy: {
      '/routing': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/routing/, ''),
      },
      '/audit': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
    },
  },
});
