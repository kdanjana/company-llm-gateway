import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Docker dev (docker-compose.dev.yml) sets these: Django is at http://backend:8000, and file
// changes on a Windows drive are not noticed inside the container unless Vite polls for them.
const apiTarget = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
const usePolling = process.env.WATCH_POLLING === "true";

// The dev server forwards /api/* to Django, so the browser sees one origin (no CORS setup needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch: { usePolling },
    proxy: { "/api": apiTarget },
  },
});
