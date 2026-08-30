import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api so the frontend uses the same relative paths it will use
// behind nginx in Docker. Without this the two setups would need different base URLs
// and one of them would rot.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Split the two heavy visual libraries out of the app bundle. They change far
        // less often than the app does, so a browser keeps them across deploys.
        manualChunks: {
          flow: ["@xyflow/react"],
          charts: ["recharts"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8071", changeOrigin: true } },
  },
});
