import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development, open http://apurvam.localhost:5173. The /api proxy keeps the
// Host header, so the backend picks the tenant from the subdomain.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: [".localhost"],
    proxy: {
      "/api": { target: process.env.VITE_API_TARGET ?? "http://localhost:8000", changeOrigin: false },
    },
  },
});
