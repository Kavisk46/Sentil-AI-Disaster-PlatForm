import type { ApiResult } from "@sentinelai/shared";

/**
 * Base URL of the backend API. Read once from the public env var so it can
 * differ between local dev, Docker Compose, and any future deployment
 * target without a code change.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function toApiResult<T>(response: Response): Promise<ApiResult<T>> {
  if (!response.ok) {
    // The backend's exception handlers always return `{"detail": "..."}`
    // (see `app/api/exception_handlers.py`) — prefer that human-readable
    // message over the bare status line when present, but never surface a
    // raw stack trace or response body beyond that one field.
    const detail = await response
      .json()
      .then((body: unknown) =>
        typeof body === "object" && body !== null && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : null,
      )
      .catch(() => null);
    return { ok: false, error: detail ?? `${response.status} ${response.statusText}` };
  }
  return { ok: true, data: (await response.json()) as T };
}

/**
 * Minimal typed fetch wrapper returning a discriminated result instead of
 * throwing, so callers (e.g. TanStack Query hooks) can render an error state
 * without a try/catch at every call site.
 */
export async function apiGet<T>(path: string): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`);
    return await toApiResult<T>(response);
  } catch (cause) {
    return { ok: false, error: cause instanceof Error ? cause.message : "Unknown error" };
  }
}

/** Same contract as `apiGet`, for JSON request bodies. */
export async function apiPost<T>(path: string, body?: unknown): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return await toApiResult<T>(response);
  } catch (cause) {
    return { ok: false, error: cause instanceof Error ? cause.message : "Unknown error" };
  }
}

/**
 * Same contract as `apiGet`/`apiPost`, for multipart file uploads
 * (`POST /api/v1/analysis`) — the browser sets the multipart boundary
 * itself, so `Content-Type` is deliberately left unset here.
 *
 * Uses `XMLHttpRequest`, not `fetch`, so an optional `onProgress` callback
 * can report real `xhr.upload.onprogress` byte counts — the only way to
 * observe genuine upload progress in a browser (the backend itself has no
 * progress/percentage field; see `POST /api/v1/analysis`). `onProgress` is
 * never invoked with a guessed or animated number, only what the browser
 * actually reports. Same `ApiResult<T>` shape and same
 * backend-`detail`-message-over-status-line preference as `toApiResult`.
 */
export function apiUpload<T>(
  path: string,
  formData: FormData,
  onProgress?: (loaded: number, total: number) => void,
): Promise<ApiResult<T>> {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded, event.total);
      };
    }
    xhr.onerror = () => resolve({ ok: false, error: "Network error" });
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve({ ok: true, data: body as T });
        return;
      }
      const detail =
        typeof body === "object" && body !== null && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : null;
      resolve({ ok: false, error: detail ?? `${xhr.status} ${xhr.statusText}` });
    };
    xhr.send(formData);
  });
}
