import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet, apiPost, apiUpload } from "@/lib/api-client";

/** A minimal fake standing in for the real `XMLHttpRequest` — `apiUpload`
 * needs `xhr.upload.onprogress` for real byte-progress events, which
 * `fetch` cannot provide, so it's the one function in `api-client.ts`
 * built on XHR instead. jsdom's real `XMLHttpRequest` would attempt an
 * actual network request here, so it's stubbed the same way `fetch` is
 * stubbed above, just with a bit more shape to drive manually. */
class FakeXHR {
  static instances: FakeXHR[] = [];
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  onerror: (() => void) | null = null;
  onload: (() => void) | null = null;
  status = 0;
  statusText = "";
  responseText = "";
  open = vi.fn();
  send = vi.fn();
  constructor() {
    FakeXHR.instances.push(this);
  }
}

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

describe("apiUpload", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    FakeXHR.instances = [];
  });

  it("reports real byte progress via onProgress — never a guessed number", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR as unknown as typeof XMLHttpRequest);
    const onProgress = vi.fn();

    const resultPromise = apiUpload("/api/v1/analysis", new FormData(), onProgress);
    const xhr = FakeXHR.instances[0]!;

    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 200 } as ProgressEvent);
    expect(onProgress).toHaveBeenCalledWith(50, 200);

    xhr.status = 201;
    xhr.responseText = JSON.stringify({ analysis_id: "abc" });
    xhr.onload?.();

    await expect(resultPromise).resolves.toEqual({ ok: true, data: { analysis_id: "abc" } });
  });

  it("works identically with onProgress omitted (same ApiResult<T> contract as before)", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR as unknown as typeof XMLHttpRequest);

    const resultPromise = apiUpload("/api/v1/analysis", new FormData());
    const xhr = FakeXHR.instances[0]!;
    xhr.status = 201;
    xhr.responseText = JSON.stringify({ analysis_id: "abc" });
    xhr.onload?.();

    await expect(resultPromise).resolves.toEqual({ ok: true, data: { analysis_id: "abc" } });
  });

  it("prefers the backend's detail message on a non-2xx response, same as apiGet/apiPost", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR as unknown as typeof XMLHttpRequest);

    const resultPromise = apiUpload("/api/v1/analysis", new FormData());
    const xhr = FakeXHR.instances[0]!;
    xhr.status = 415;
    xhr.statusText = "Unsupported Media Type";
    xhr.responseText = JSON.stringify({ detail: "Unsupported image type." });
    xhr.onload?.();

    await expect(resultPromise).resolves.toEqual({ ok: false, error: "Unsupported image type." });
  });

  it("surfaces a network failure as an error result, never a throw", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR as unknown as typeof XMLHttpRequest);

    const resultPromise = apiUpload("/api/v1/analysis", new FormData());
    FakeXHR.instances[0]!.onerror?.();

    await expect(resultPromise).resolves.toEqual({ ok: false, error: "Network error" });
  });
});
