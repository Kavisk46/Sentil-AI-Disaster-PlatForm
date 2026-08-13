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

/** Same contract as `apiGet`/`apiPost`, for multipart file uploads
 * (`POST /api/v1/analysis`) — the browser sets the multipart boundary
 * itself, so `Content-Type` is deliberately left unset here. */
export async function apiUpload<T>(path: string, formData: FormData): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST", body: formData });
    return await toApiResult<T>(response);
  } catch (cause) {
    return { ok: false, error: cause instanceof Error ? cause.message : "Unknown error" };
  }
}
