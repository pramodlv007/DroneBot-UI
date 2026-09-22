import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const gatewayTarget = process.env.GATEWAY_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": gatewayTarget,
      "/ws": {
        target: gatewayTarget,
        ws: true,
      },
    },
  },
});
