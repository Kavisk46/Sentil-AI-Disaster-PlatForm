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
    // This environment is resource-constrained enough that spawning many
    // worker threads in parallel intermittently times out mid-run (some
    // files never get a worker). Forcing a single, reused worker thread
    // for the whole run trades wall-clock speed for reliability, which
    // matters more here than in a normal CI runner. Vitest 4 removed the
    // old `poolOptions.threads.singleThread` option entirely (and
    // top-level `singleThread` was never a real option, despite an
    // earlier version of this file assuming so) — `fileParallelism: false`
    // is the documented replacement; it explicitly forces `maxWorkers` to 1.
    fileParallelism: false,
    testTimeout: 15_000,
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
