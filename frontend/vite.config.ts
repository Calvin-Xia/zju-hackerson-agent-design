import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    plugins: [react()],
    server: {
        port: 5174,
        strictPort: true,
        proxy: {
            '/api': {
                target: 'http://localhost:8001',
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: 'dist',
        // 生产构建不产出 sourcemap：单个 .map 比 JS 本身体积还大，
        // 放进 Docker 镜像只会白白增加体积。
        sourcemap: false,
        rollupOptions: {
            output: {
                // 只把体积最大的两个依赖单独成包，便于浏览器并行加载与缓存。
                // 注意：不要按 id.includes('react') 这类模糊规则切分 —— 那会让
                // 相互引用的模块落到不同 chunk，生产构建下出现初始化顺序错误
                // （页面白屏），而 dev 模式因为不打包完全看不出来。
                manualChunks: {
                    antd: ['antd', '@ant-design/icons'],
                    echarts: ['echarts', 'echarts-for-react', 'zrender'],
                },
            },
        },
    },
});
