import { defineConfig } from "vite";

export default defineConfig({
  root: "src",
  server: {
    port: 5173,
    proxy: {
      "/ws/voice": {
        target: "https://localhost:8340",
        ws: true,
        secure: false,
      },
      "/api": {
        target: "https://localhost:8340",
        secure: false,
      },
    },
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
