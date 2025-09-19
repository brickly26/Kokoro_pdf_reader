import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  root: "renderer",
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "renderer/dist",
    emptyOutDir: true,
  },
});
