import { existsSync } from "node:fs";
import { defineConfig } from "vite";

const useTls =
  existsSync(new URL("../cert.pem", import.meta.url)) &&
  existsSync(new URL("../key.pem", import.meta.url));
const backendTarget = `${useTls ? "https" : "http"}://localhost:8340`;

export default defineConfig({
  root: "src",
  server: {
    port: 5173,
    proxy: {
      "/ws/voice": {
        target: backendTarget,
        ws: true,
        secure: false,
      },
      "/api": {
        target: backendTarget,
        secure: false,
      },
    },
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
