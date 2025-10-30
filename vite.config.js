import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const BACKEND_IP = '192.168.30.95'

// 환경 변수에서 포트 가져오기 (없으면 기본값 사용)
const PORT = process.env.PORT || process.env.VITE_PORT || 5173

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: PORT, // 환경 변수에서 포트 가져오기
    strictPort: false, // 포트가 사용 중이면 다른 포트 자동 선택
    proxy: {
      // 백엔드 API
      '/api': {
        target: `http://${BACKEND_IP}:8080`,
        changeOrigin: true,
      }
    }
  }
})