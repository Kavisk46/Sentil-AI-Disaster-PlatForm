import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    // The default `forks` pool spawns child processes via `child_process`,
    // which times out under this project's sandboxed shell. `threads`
    // (worker_threads) avoids process-spawn overhead entirely and is a
    // fully supported Vitest pool — not a correctness compromise, just an
    // execution-environment accommodation.
    pool: "threads",
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
