"use client";

import { useSyncExternalStore } from "react";
import { apiUrl } from "@/lib/api";

const subscribe = () => () => undefined;

/** Link to the backend's OpenAPI docs, resolved against the API host in the browser. */
export function ApiDocsLink({ className }: { className?: string }) {
  const href = useSyncExternalStore(
    subscribe,
    () => apiUrl("/docs"),
    () => "http://localhost:8000/docs",
  );
  return (
    <a href={href} className={className}>
      API reference (OpenAPI)
    </a>
  );
}
