import { ArrowUpDown, Check, X } from "lucide-react";
import { cn } from "@/lib/format";
import type { ResultAlignment, ResultStep } from "@/lib/types";
import { Badge, Card } from "@/components/ui";

const STATUS = {
  done: { icon: Check, label: "Done", tone: "success" as const, ring: "bg-success text-white" },
  missed: { icon: X, label: "Missed", tone: "danger" as const, ring: "bg-danger text-white" },
  out_of_order: {
    icon: ArrowUpDown,
    label: "Out of order",
    tone: "warning" as const,
    ring: "bg-warning text-white",
  },
};

export function ProcedurePanel({
  alignment,
  steps,
  onSelect,
}: {
  alignment: ResultAlignment;
  steps: ResultStep[];
  onSelect: (step: ResultStep) => void;
}) {
  const byOrder = new Map(steps.map((s) => [s.order, s]));
  const allGood =
    alignment.completed === alignment.total &&
    alignment.reference.every((r) => r.status === "done");
  return (
    <Card className="p-4 sm:p-5">
      <p
        className={cn(
          "rounded-xl p-3 text-sm font-medium",
          allGood ? "bg-success-soft text-success" : "bg-warning-soft text-warning",
        )}
        data-testid="verdict"
      >
        {alignment.verdict}
      </p>
      <ol className="mt-4 space-y-2" aria-label="Reference procedure">
        {alignment.reference.map((ref) => {
          const meta = STATUS[ref.status];
          return (
            <li
              key={ref.index}
              className="flex flex-wrap items-center gap-3 rounded-xl border border-border p-3"
            >
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                  meta.ring,
                )}
                aria-hidden
              >
                <meta.icon className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {ref.index}. {ref.text}
                </p>
                {ref.reason ? <p className="text-xs text-muted">Verified: {ref.reason}</p> : null}
              </div>
              <Badge tone={meta.tone}>{meta.label}</Badge>
              {ref.matched_steps.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {ref.matched_steps.map((order) => {
                    const step = byOrder.get(order);
                    return step ? (
                      <button
                        key={order}
                        type="button"
                        onClick={() => onSelect(step)}
                        className="rounded-md border border-border px-2 py-1 text-xs hover:bg-surface-2"
                        aria-label={`Go to detected step ${order}: ${step.title}`}
                      >
                        Step {order}
                      </button>
                    ) : null;
                  })}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
      {alignment.extra_steps.length > 0 ? (
        <p className="mt-3 text-xs text-muted">
          Extra steps not in your procedure:{" "}
          {alignment.extra_steps.map((o) => `#${o} ${byOrder.get(o)?.title ?? ""}`).join(", ")}
        </p>
      ) : null}
    </Card>
  );
}
