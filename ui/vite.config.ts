/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The built GUI is served by `agencast serve` at `/` (docs/spec/api.md "GUI and CORS").
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  build: { outDir: "../framework/src/agencast/ui", emptyOutDir: true },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});
