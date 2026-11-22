"use client";

import { forwardRef } from "react";
import { ArrowUpDown, Check, Hand, Play, Plus, Wrench } from "lucide-react";
import { apiUrl } from "@/lib/api";
import { cn, formatDuration, formatTime, phaseColor } from "@/lib/format";
import type { ResultStep } from "@/lib/types";
import { Badge } from "@/components/ui";

const ALIGN: Record<
  string,
  { label: string; tone: "success" | "warning" | "neutral"; icon: typeof Check }
> = {
  done: { label: "Done", tone: "success", icon: Check },
  out_of_order: { label: "Out of order", tone: "warning", icon: ArrowUpDown },
  extra: { label: "Extra", tone: "neutral", icon: Plus },
};

interface Props {
  step: ResultStep;
  active: boolean;
  onSelect: (step: ResultStep) => void;
  onPlayClip: (step: ResultStep) => void;
}

export const StepCard = forwardRef<HTMLLIElement, Props>(function StepCard(
  { step, active, onSelect, onPlayClip },
  ref,
) {
  const align = step.alignment ? ALIGN[step.alignment] : null;
  return (
    <li
      ref={ref}
      data-step={step.order}
      aria-current={active ? "step" : undefined}
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-surface transition",
        active
          ? "border-accent shadow-md ring-2 ring-accent/30"
          : "border-border hover:border-muted/50",
      )}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 w-1"
        style={{ background: phaseColor(step.phase_index) }}
      />
      <button
        type="button"
        onClick={() => onSelect(step)}
        className="flex w-full gap-3 p-3 pl-4 text-left"
        aria-label={`Step ${step.order}: ${step.title}, ${formatTime(step.start)} to ${formatTime(step.end)}. Seek the video here.`}
      >
        <div className="relative aspect-video w-28 shrink-0 overflow-hidden rounded-lg bg-surface-2 sm:w-32">
          {step.keyframe_url ? (
            <picture>
              <source srcSet={apiUrl(step.keyframe_url)} type="image/webp" />
              <img
                src={apiUrl(step.keyframe_jpg_url ?? step.keyframe_url)}
                alt={`Keyframe: ${step.description || step.title}`}
                className="h-full w-full object-cover"
                loading="lazy"
              />
            </picture>
          ) : null}
          <span className="absolute left-1 top-1 rounded-md bg-black/70 px-1.5 py-0.5 text-xs font-semibold text-white">
            {step.order}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-x-2 gap-y-1">
            <p className="font-semibold leading-snug">{step.title}</p>
            {align ? (
              <Badge tone={align.tone}>
                <align.icon className="h-3 w-3" aria-hidden /> {align.label}
              </Badge>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs tabular-nums text-muted">
            {formatTime(step.start)}–{formatTime(step.end)} · {formatDuration(step.duration)} ·{" "}
            {Math.round(step.confidence * 100)}% confident
          </p>
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Action">
            <li>
              <Badge tone="accent">
                <Hand className="h-3 w-3" aria-hidden /> {step.verb}
              </Badge>
            </li>
            {step.object ? (
              <li>
                <Badge>{step.object}</Badge>
              </li>
            ) : null}
            {step.tool ? (
              <li>
                <Badge>
                  <Wrench className="h-3 w-3" aria-hidden /> {step.tool}
                </Badge>
              </li>
            ) : null}
          </ul>
        </div>
      </button>
      {step.clip_url ? (
        <button
          type="button"
          onClick={() => onPlayClip(step)}
          className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs font-medium hover:bg-surface-2"
          aria-label={`Play clip of step ${step.order}: ${step.title}`}
        >
          <Play className="h-3 w-3" aria-hidden /> Clip
        </button>
      ) : null}
    </li>
  );
});
