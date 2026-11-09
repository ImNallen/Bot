import { defineConfig } from "vite";

export default defineConfig({
  clearScreen: false,
  server: { port: 1420, strictPort: true, fs: { allow: [".."] } },
  build: {
    target: "safari16",
    rollupOptions: { input: { overlay: "index.html", dev: "dev.html" } },
  },
});
