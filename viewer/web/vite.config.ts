import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api so the frontend uses the same relative paths it will use
// behind nginx in Docker. Without this the two setups would need different base URLs
// and one of them would rot.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: { workspace: "index.html", developer: "developer.html" },
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
    port: Number(process.env.MEMSTARA_WEB_PORT || 5173),
    strictPort: true,
    proxy: {
      "/api": { target: `http://127.0.0.1:${process.env.MEMSTARA_API_PORT || 8071}`, changeOrigin: true },
      // The control service runs on the host directly, not in a container, so in
      // development it is simply another port on localhost. `changeOrigin` is off: it
      // would rewrite Host to `localhost:8072`, which this service does accept, but the
      // header it must not lose is Origin — that is what tells it the request came from
      // this dev server and not from a page on the open web.
      "/control": { target: `http://127.0.0.1:${process.env.MEMSTARA_CONTROL_PORT || 8072}` },
    },
  },
});
