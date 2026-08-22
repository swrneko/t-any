import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    port: 5173,
    // 127.0.0.1 rather than localhost: the API binds IPv4 only, and on a host
    // that resolves localhost to ::1 first the proxy would fail every request.
    proxy: { "/api": process.env.API_URL ?? "http://127.0.0.1:8927" },
  },
});
