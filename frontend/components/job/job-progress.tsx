"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Activity, Ban, RotateCcw, Sparkles } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatDuration, formatPercent } from "@/lib/format";
import { useJobEvents } from "@/lib/use-job-events";
import { StageChecklist } from "@/components/job/stage-checklist";
import { Alert, Badge, Button, Card, ProgressBar, Skeleton, buttonClass } from "@/components/ui";

export function JobProgress({ jobId }: { jobId: string }) {
  const router = useRouter();
  const { state, error, transport, restart, setState } = useJobEvents(jobId);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (state?.status === "completed") {
      const t = setTimeout(() => router.replace(`/results/${jobId}`), 900);
      return () => clearTimeout(t);
    }
  }, [state?.status, jobId, router]);

  async function act(kind: "cancel" | "retry") {
    setBusy(true);
    setActionError(null);
    try {
      const next = kind === "cancel" ? await api.cancel(jobId) : await api.retry(jobId);
      setState(next);
      if (kind === "retry") restart();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error?.status === 404) {
    return (
      <Alert
        title="We couldn't find this job"
        action={
          <Link href="/" className={buttonClass("secondary", "sm")}>
            Upload a video
          </Link>
        }
      >
        It may have been deleted after the 24-hour retention period.
      </Alert>
    );
  }
  if (!state) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading job">
        {error ? (
          <Alert tone="warning" title="Reconnecting…">
            {error.message}
          </Alert>
        ) : null}
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-3 w-full" />
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  const info = state.info ?? {};
  const active = state.status === "queued" || state.status === "running";
  const failed = state.status === "failed" || state.status === "cancelled";

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div className="space-y-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{state.title || "Your video"}</h1>
            <Badge tone={failed ? "danger" : state.status === "completed" ? "success" : "accent"}>
              {state.status}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted" aria-live="polite">
            {state.status === "queued"
              ? "Waiting for a free worker…"
              : state.status === "completed"
                ? "Done! Opening your results…"
                : state.message || "Working…"}
          </p>
        </div>
        <div>
          <div className="mb-1.5 flex justify-between text-sm">
            <span className="font-medium">Overall progress</span>
            <span className="tabular-nums text-muted">{formatPercent(state.progress)}</span>
          </div>
          <ProgressBar value={state.progress} label="Overall processing progress" />
        </div>

        {failed && state.error ? (
          <Alert
            tone={state.status === "cancelled" ? "warning" : "danger"}
            title={state.status === "cancelled" ? "Processing cancelled" : "Processing failed"}
            action={
              <Button onClick={() => act("retry")} disabled={busy}>
                <RotateCcw className="h-4 w-4" aria-hidden /> Retry
              </Button>
            }
          >
            {state.error.message}
            {state.completed_stages.length > 0
              ? " Retry resumes from the stage that stopped; finished stages are reused."
              : ""}
          </Alert>
        ) : null}
        {actionError ? <Alert title="That didn't work">{actionError}</Alert> : null}

        <StageChecklist job={state} />

        <div className="flex flex-wrap items-center gap-3">
          {active ? (
            <Button variant="danger" onClick={() => act("cancel")} disabled={busy}>
              <Ban className="h-4 w-4" aria-hidden /> Cancel
            </Button>
          ) : null}
          {state.status === "completed" ? (
            <Link href={`/results/${jobId}`} className={buttonClass("primary")}>
              <Sparkles className="h-4 w-4" aria-hidden /> View results
            </Link>
          ) : null}
          <span className="text-xs text-muted">
            Live updates via {transport === "sse" ? "server-sent events" : "polling"}
          </span>
        </div>
      </div>

      <aside className="space-y-4" aria-label="Live details">
        <Card className="p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Activity className="h-4 w-4 text-accent" aria-hidden /> Live details
          </h2>
          <dl className="mt-3 space-y-2 text-sm">
            {info.source ? (
              <Row
                k="Source"
                v={`${info.source.width}×${info.source.height} ${info.source.codec.toUpperCase()}${
                  info.source.rotation ? ` · rotated ${info.source.rotation}°` : ""
                }${info.source.vfr ? " · VFR" : ""}`}
              />
            ) : null}
            {info.source ? <Row k="Length" v={formatDuration(info.source.duration)} /> : null}
            {info.idle_seconds !== undefined ? (
              <Row k="Idle time found" v={formatDuration(info.idle_seconds)} />
            ) : null}
            {info.scene_cuts !== undefined ? (
              <Row k="Scene cuts" v={String(info.scene_cuts)} />
            ) : null}
            {info.windows_total !== undefined ? (
              <Row
                k="Windows analyzed"
                v={`${info.windows_analyzed ?? 0} / ${info.windows_total}`}
              />
            ) : null}
            {info.cached_windows ? <Row k="From cache" v={String(info.cached_windows)} /> : null}
            {info.steps_detected !== undefined ? (
              <Row k="Steps detected" v={String(info.steps_detected)} />
            ) : null}
          </dl>
          {!info.source ? (
            <p className="mt-2 text-xs text-muted">Details appear as stages finish.</p>
          ) : null}
        </Card>
        {info.first_actions && info.first_actions.length > 0 ? (
          <Card className="p-4">
            <h2 className="text-sm font-semibold">First actions spotted</h2>
            <ul className="mt-2 flex flex-wrap gap-2">
              {info.first_actions.map((a) => (
                <li key={a}>
                  <Badge tone="accent">{a}</Badge>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
        {info.task_name ? (
          <Card className="p-4 text-sm">
            <p className="text-muted">Task</p>
            <p className="font-medium">{info.task_name}</p>
            {info.verdict ? <p className="mt-2 text-muted">{info.verdict}</p> : null}
          </Card>
        ) : null}
      </aside>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{k}</dt>
      <dd className="text-right font-medium tabular-nums">{v}</dd>
    </div>
  );
}
