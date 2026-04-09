import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'node:path';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    host: '0.0.0.0'
  },
  build: {
    cssCodeSplit: true,
    chunkSizeWarningLimit: 550,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (id.includes('@element-plus/icons-vue')) return 'vendor-element-icons';
          if (id.includes('element-plus/es/components/')) {
            const componentPath = id.split('element-plus/es/components/')[1] ?? '';
            const componentName = componentPath.split('/')[0] ?? 'core';
            return `vendor-element-plus-${componentName}`;
          }
          if (id.includes('element-plus')) return 'vendor-element-plus-core';
          if (id.includes('echarts')) return 'vendor-echarts';
          if (id.includes('axios')) return 'vendor-network';
          if (id.includes('dayjs')) return 'vendor-dayjs';
          if (id.includes('vue')) return 'vendor-vue';
        }
      }
    }
  },
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts']
  }
});
