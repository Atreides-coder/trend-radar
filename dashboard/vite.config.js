import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发时（npm run dev）把 /api 转发给 FastAPI；正式使用时由 FastAPI 直接托管 dist/
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765", "/video-files": "http://127.0.0.1:8765" } },
});
