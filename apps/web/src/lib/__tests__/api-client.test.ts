import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet, apiPost } from "@/lib/api-client";

describe("apiGet/apiPost error handling", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("surfaces the backend's `detail` message on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: async () => ({ detail: "No analysis with that id." }),
      }),
    );

    const result = await apiGet("/api/v1/analysis/unknown");

    expect(result).toEqual({ ok: false, error: "No analysis with that id." });
  });

  it("falls back to the HTTP status line when there is no `detail` field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => {
          throw new Error("not json");
        },
      }),
    );

    const result = await apiGet("/api/v1/analysis/x");

    expect(result).toEqual({ ok: false, error: "500 Internal Server Error" });
  });

  it("surfaces a network failure (backend unreachable) as an error result, never a throw", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    const result = await apiGet("/api/v1/analysis/x");

    expect(result).toEqual({ ok: false, error: "Failed to fetch" });
  });

  it("returns typed data on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok" }),
      }),
    );

    const result = await apiGet<{ status: string }>("/health");

    expect(result).toEqual({ ok: true, data: { status: "ok" } });
  });

  it("apiPost sends a JSON body and content-type header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    await apiPost("/api/v1/routing", { mode: "risk_aware" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ mode: "risk_aware" }));
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
});
