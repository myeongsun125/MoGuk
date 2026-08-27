import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev proxy: 실경로는 /api/v1 프리픽스 (skeleton-v3 §3). edge-api 는 dev 에서 host:8000 노출.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/v1": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
