import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/docs": { target: "http://localhost:8000", changeOrigin: true },
      "/redoc": { target: "http://localhost:8000", changeOrigin: true }
    }
  },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          maps: ["leaflet", "react-leaflet"],
          icons: ["lucide-react"]
        }
      }
    }
  }
});