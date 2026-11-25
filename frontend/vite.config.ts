import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development, open http://apurvam.localhost:5173. The /api proxy keeps the
// Host header, so the backend picks the tenant from the subdomain.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // React in a file of its own: it does not change between deploys, so the
        // browser keeps it while the app's own files are fetched afresh.
        manualChunks: (id) => (/node_modules\/(react|react-dom|scheduler)\//.test(id) ? "react" : undefined),
      },
    },
  },
  server: {
    host: true,
    allowedHosts: [".localhost"],
    proxy: {
      "/api": { target: process.env.VITE_API_TARGET ?? "http://localhost:8000", changeOrigin: false },
    },
  },
});
