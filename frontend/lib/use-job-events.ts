"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiUrl, ApiError } from "@/lib/api";
import type { JobState } from "@/lib/types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const POLL_MS = 1500;

export type Transport = "sse" | "polling";

/**
 * Live job state over Server-Sent Events, falling back to polling if the stream
 * can't be opened or keeps failing (proxies, old browsers).
 */
export function useJobEvents(jobId: string) {
  const [state, setState] = useState<JobState | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [transport, setTransport] = useState<Transport>("sse");
  const [generation, setGeneration] = useState(0);
  const failures = useRef(0);

  const restart = useCallback(() => {
    failures.current = 0;
    setTransport("sse");
    setGeneration((g) => g + 1);
  }, []);

  useEffect(() => {
    let closed = false;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const apply = (next: JobState) => {
      if (closed) return;
      setState(next);
      setError(null);
    };

    const poll = async () => {
      try {
        const next = await api.job(jobId);
        apply(next);
        if (!TERMINAL.has(next.status) && !closed) timer = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (closed) return;
        setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e)));
        if (!(e instanceof ApiError && e.status === 404)) timer = setTimeout(poll, POLL_MS * 2);
      }
    };

    const startPolling = () => {
      source?.close();
      source = null;
      setTransport("polling");
      void poll();
    };

    // Initial snapshot (also surfaces 404s quickly).
    api
      .job(jobId)
      .then((initial) => {
        apply(initial);
        if (TERMINAL.has(initial.status) || closed) return;
        if (typeof EventSource === "undefined") {
          startPolling();
          return;
        }
        source = new EventSource(apiUrl(`/api/jobs/${jobId}/events`));
        source.addEventListener("progress", (ev) => {
          failures.current = 0;
          try {
            apply(JSON.parse((ev as MessageEvent).data) as JobState);
          } catch {
            // Ignore a malformed frame; the next one will update the state.
          }
        });
        source.addEventListener("end", () => {
          source?.close();
          source = null;
        });
        source.onerror = () => {
          failures.current += 1;
          if (failures.current >= 3 || source?.readyState === EventSource.CLOSED) startPolling();
        };
      })
      .catch((e) => {
        if (closed) return;
        setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e)));
        if (!(e instanceof ApiError && e.status === 404)) startPolling();
      });

    return () => {
      closed = true;
      source?.close();
      if (timer) clearTimeout(timer);
    };
  }, [jobId, generation]);

  return { state, error, transport, restart, setState };
}
