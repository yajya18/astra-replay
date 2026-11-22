"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Clock, ListChecks, PlayCircle } from "lucide-react";
import { api, apiUrl } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { Alert, Badge, Card, Skeleton } from "@/components/ui";

export function DemoGallery({ limit }: { limit?: number }) {
  const { data, isPending, error, refetch } = useQuery({ queryKey: ["demos"], queryFn: api.demos });

  if (isPending) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
        {[0, 1, 2].slice(0, limit ?? 3).map((i) => (
          <Card key={i} className="overflow-hidden">
            <Skeleton className="aspect-video rounded-none" />
            <div className="space-y-2 p-4">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-full" />
            </div>
          </Card>
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <Alert
        title="Couldn't load the demos"
        action={
          <button className="text-sm font-medium underline" onClick={() => refetch()}>
            Try again
          </button>
        }
      >
        {error.message}
      </Alert>
    );
  }
  const items = (data ?? []).slice(0, limit);
  if (items.length === 0) {
    return (
      <Card className="p-6 text-sm text-muted">
        No demo results yet. Run <code className="rounded bg-surface-2 px-1">make demo</code> to
        process the videos in <code className="rounded bg-surface-2 px-1">demo/</code>; the server
        also prepares them automatically on first start.
      </Card>
    );
  }
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((d) => {
        const ready = d.status === "completed";
        const href = ready ? `/results/${d.job_id}` : `/jobs/${d.job_id}`;
        return (
          <li key={d.job_id}>
            <Link
              href={href}
              className="group block h-full overflow-hidden rounded-2xl border border-border bg-surface shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="relative aspect-video bg-surface-2">
                {d.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- media is served by the API
                  <img
                    src={apiUrl(d.thumbnail_url)}
                    alt={`Preview of ${d.task_name}`}
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-muted">
                    {ready ? "No preview" : "Processing…"}
                  </div>
                )}
                <PlayCircle
                  className="absolute bottom-3 right-3 h-9 w-9 text-white drop-shadow transition group-hover:scale-110"
                  aria-hidden
                />
              </div>
              <div className="space-y-2 p-4">
                <p className="font-semibold leading-snug">{d.task_name}</p>
                {d.summary ? <p className="line-clamp-2 text-sm text-muted">{d.summary}</p> : null}
                <div className="flex flex-wrap gap-2">
                  <Badge>
                    <Clock className="h-3 w-3" aria-hidden /> {formatDuration(d.duration)}
                  </Badge>
                  <Badge tone="accent">{d.step_count} steps</Badge>
                  {d.has_reference ? (
                    <Badge tone="success">
                      <ListChecks className="h-3 w-3" aria-hidden /> procedure check
                    </Badge>
                  ) : null}
                  {!ready ? <Badge tone="warning">{d.status}</Badge> : null}
                </div>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
