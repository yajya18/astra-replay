import { Check, Circle, Loader2, XCircle } from "lucide-react";
import { STAGES, stageProgress, type StageStatus } from "@/lib/stages";
import { cn, formatPercent } from "@/lib/format";
import type { JobState } from "@/lib/types";

export function stageStatus(id: string, job: JobState): StageStatus {
  if (job.completed_stages.includes(id)) return "done";
  if (job.stage === id) {
    if (job.status === "failed" || job.status === "cancelled") return "failed";
    if (job.status === "running") return "active";
  }
  return "pending";
}

export function StageChecklist({ job }: { job: JobState }) {
  const allDone = job.status === "completed";
  return (
    <ol className="space-y-2" aria-label="Processing stages">
      {STAGES.map((stage) => {
        const status = allDone ? "done" : stageStatus(stage.id, job);
        const pct = allDone
          ? 1
          : stageProgress(stage.id, job.stage, job.completed_stages, job.progress);
        return (
          <li
            key={stage.id}
            aria-current={status === "active" ? "step" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-xl border px-3 py-2.5 transition",
              status === "active" ? "border-accent bg-accent-soft/60" : "border-border bg-surface",
            )}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center" aria-hidden>
              {status === "done" ? (
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-success text-white">
                  <Check className="h-4 w-4" />
                </span>
              ) : status === "active" ? (
                <Loader2 className="h-5 w-5 animate-spin text-accent" />
              ) : status === "failed" ? (
                <XCircle className="h-6 w-6 text-danger" />
              ) : (
                <Circle className="h-5 w-5 text-border" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className={cn("text-sm font-medium", status === "pending" && "text-muted")}>
                {stage.label}
              </p>
              <p className="truncate text-xs text-muted">{stage.detail}</p>
            </div>
            <span className="w-12 text-right text-xs tabular-nums text-muted">
              <span className="sr-only">{status}, </span>
              {status === "pending" ? "" : formatPercent(pct)}
            </span>
          </li>
        );
      })}
      <li
        className={cn(
          "flex items-center gap-3 rounded-xl border px-3 py-2.5",
          allDone ? "border-success bg-success-soft" : "border-border bg-surface",
        )}
      >
        <span className="flex h-7 w-7 items-center justify-center" aria-hidden>
          {allDone ? (
            <Check className="h-5 w-5 text-success" />
          ) : (
            <Circle className="h-5 w-5 text-border" />
          )}
        </span>
        <p className={cn("text-sm font-medium", !allDone && "text-muted")}>Done</p>
      </li>
    </ol>
  );
}
