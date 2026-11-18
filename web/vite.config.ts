import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" + 해시 라우팅 → GitHub Pages 하위 경로, 커스텀 도메인 어디서든 동작
export default defineConfig({
  base: "./",
  plugins: [react()],
});
