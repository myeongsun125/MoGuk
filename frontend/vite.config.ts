import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev proxy: 실경로는 /api/v1 프리픽스 (skeleton-v3 §3). edge-api 는 dev 에서 host:8000 노출.
// VITE_PROXY_TARGET 으로 재정의 가능 — cutover 검증 시 배포 백엔드를 직접 겨냥할 때 사용.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/v1": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
