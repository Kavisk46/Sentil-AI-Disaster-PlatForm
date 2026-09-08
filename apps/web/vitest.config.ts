import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    // Empirically re-verified in this exact sandboxed shell (2026-08-22):
    // the `threads` pool (worker_threads) never completes a run here —
    // every file times out with "[vitest-pool-runner]: Timeout waiting for
    // worker to respond" before a single test executes, regardless of
    // `fileParallelism`/`maxWorkers`. `forks` (child_process), by
    // contrast, runs reliably (confirmed on both a single file and the
    // full suite). This directly contradicts an earlier version of this
    // file's comment claiming the opposite — environments (or the
    // sandbox's process/thread-spawn characteristics) can shift over
    // time; re-verify empirically rather than trusting a stale comment.
    pool: "forks",
    // Mirrors the same "reliability over wall-clock speed" reasoning the
    // previous `threads`+single-worker configuration used, just via the
    // fork-pool's equivalent knob.
    fileParallelism: false,
    testTimeout: 15_000,
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
