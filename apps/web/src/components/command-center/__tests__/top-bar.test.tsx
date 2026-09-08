import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TopBar } from "@/components/command-center/top-bar";

function jsonResponse(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => body };
}

function renderTopBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TopBar />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TopBar model status indicator (Milestone F4; lifecycle_state added in F5)", () => {
  it("shows the real model name once the worker reports READY", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/model/status")) {
          return jsonResponse({
            enabled: true,
            provider: "open_clip",
            status: {
              model_loaded: true,
              model_name: "deterministic-tile-localizer+ViT-B-32",
              model_version: "openai",
              device: "cpu",
            },
            lifecycle_state: "READY",
            error: null,
          });
        }
        return jsonResponse({ status: "ok", timestamp: "2026-01-01T00:00:00Z" });
      }),
    );

    renderTopBar();

    await waitFor(() => {
      expect(screen.getByText(/Ready/)).toBeInTheDocument();
    });
  });

  it("shows Disabled without implying a fault when the model is off (UNAVAILABLE)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/model/status")) {
          return jsonResponse({
            enabled: false,
            provider: "open_clip",
            status: {
              model_loaded: false,
              model_name: "ViT-B-32",
              model_version: "openai",
              device: "cpu",
            },
            lifecycle_state: "UNAVAILABLE",
            error: null,
          });
        }
        return jsonResponse({ status: "ok", timestamp: "2026-01-01T00:00:00Z" });
      }),
    );

    renderTopBar();

    await waitFor(() => {
      expect(screen.getByText("Disabled")).toBeInTheDocument();
    });
  });

  it("shows Loading... (not a crash) while the worker is still loading the model", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/model/status")) {
          return jsonResponse({
            enabled: true,
            provider: "open_clip",
            status: {
              model_loaded: false,
              model_name: "ViT-B-32",
              model_version: "openai",
              device: "cpu",
            },
            lifecycle_state: "MODEL_LOADING",
            error: null,
          });
        }
        return jsonResponse({ status: "ok", timestamp: "2026-01-01T00:00:00Z" });
      }),
    );

    renderTopBar();

    await waitFor(() => {
      expect(screen.getByText("Loading...")).toBeInTheDocument();
    });
  });

  it("shows a Failed state with the worker's error when model loading failed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/model/status")) {
          return jsonResponse({
            enabled: true,
            provider: "open_clip",
            status: {
              model_loaded: false,
              model_name: "ViT-B-32",
              model_version: "openai",
              device: "cpu",
            },
            lifecycle_state: "FAILED",
            error: "Connection timed out",
          });
        }
        return jsonResponse({ status: "ok", timestamp: "2026-01-01T00:00:00Z" });
      }),
    );

    renderTopBar();

    await waitFor(() => {
      expect(screen.getByText(/Failed: Connection timed out/)).toBeInTheDocument();
    });
  });

  it("shows an honest Unknown state on a backend error, never a fabricated status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/model/status")) {
          return jsonResponse({ detail: "Internal Server Error" }, false);
        }
        return jsonResponse({ status: "ok", timestamp: "2026-01-01T00:00:00Z" });
      }),
    );

    renderTopBar();

    await waitFor(() => {
      expect(screen.getByText("Unknown")).toBeInTheDocument();
    });
  });
});
