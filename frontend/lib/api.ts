import type { DemoItem, Health, JobState, Result, SearchResponse } from "@/lib/types";

/**
 * The API base URL. NEXT_PUBLIC_API_URL wins; otherwise the API is assumed to run on
 * the same host at port 8000, which also works when a phone opens the app over the LAN.
 */
export function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window === "undefined") return "http://localhost:8000";
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

/** Absolute URL for an API-relative path such as /media/jobs/... */
export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${apiBase()}${path.startsWith("/") ? "" : "/"}${path}`;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    if (body?.error?.message) return new ApiError(res.status, body.error.code, body.error.message);
  } catch {
    // Not JSON (e.g. a proxy error page); fall through to a generic message.
  }
  return new ApiError(res.status, "http_error", `Request failed (${res.status}).`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(
      0,
      "network_error",
      "Can't reach the Replay server. Is the backend running?",
    );
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  job: (id: string) => request<JobState>(`/api/jobs/${id}`),
  result: (id: string) => request<Result>(`/api/jobs/${id}/result`),
  cancel: (id: string) => request<JobState>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  retry: (id: string) => request<JobState>(`/api/jobs/${id}/retry`, { method: "POST" }),
  remove: (id: string) => request<{ ok: boolean }>(`/api/jobs/${id}`, { method: "DELETE" }),
  demos: () => request<{ items: DemoItem[] }>("/api/demo").then((r) => r.items),
  search: (id: string, q: string, answer = true) =>
    request<SearchResponse>(
      `/api/jobs/${id}/search?q=${encodeURIComponent(q)}&answer=${answer ? "true" : "false"}`,
    ),
};

export interface UploadInput {
  file: File;
  title?: string;
  referenceSteps?: string;
  highlightSeconds?: number;
}

/** Upload with progress (fetch has no upload progress, so this uses XHR). */
export function uploadVideo(
  input: UploadInput,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<{ job_id: string }> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("video", input.file, input.file.name);
    if (input.title) form.append("title", input.title);
    if (input.referenceSteps?.trim()) form.append("reference_steps", input.referenceSteps);
    if (input.highlightSeconds) form.append("highlight_seconds", String(input.highlightSeconds));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl("/api/jobs"));
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      const body = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300 && body?.job_id) {
        onProgress(1);
        resolve(body);
      } else {
        reject(
          new ApiError(
            xhr.status,
            body?.error?.code ?? "upload_failed",
            body?.error?.message ?? `Upload failed (${xhr.status}).`,
          ),
        );
      }
    };
    xhr.onerror = () =>
      reject(
        new ApiError(0, "network_error", "Upload failed. Check your connection and try again."),
      );
    xhr.onabort = () => reject(new ApiError(0, "aborted", "Upload cancelled."));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(form);
  });
}
