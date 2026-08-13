/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // ngrok 터널 도메인의 Host 헤더를 Vite dev server가 차단하지 않도록 허용
    allowedHosts: [".ngrok-free.app", ".ngrok-free.dev"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
