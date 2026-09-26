/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Sestavené GUI podává `agencast serve` na `/` (docs/spec/api.md „GUI a CORS“).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  build: { outDir: "../framework/src/agencast/ui", emptyOutDir: true },
  test: { environment: "jsdom" },
});
