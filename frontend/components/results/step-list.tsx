"use client";

import { useEffect, useRef, useState } from "react";
import { apiUrl } from "@/lib/api";
import { formatTime, phaseColor } from "@/lib/format";
import type { Result, ResultStep } from "@/lib/types";
import { Modal } from "@/components/ui";
import { StepCard } from "@/components/results/step-card";

interface Props {
  result: Result;
  activeOrder: number | null;
  onSelect: (step: ResultStep) => void;
}

export function StepList({ result, activeOrder, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef(new Map<number, HTMLLIElement>());
  const [clip, setClip] = useState<ResultStep | null>(null);

  // Keep the active card in view inside the scrollable list (desktop) without moving the page.
  useEffect(() => {
    const container = containerRef.current;
    const card = activeOrder !== null ? cardRefs.current.get(activeOrder) : undefined;
    if (!container || !card) return;
    if (container.scrollHeight <= container.clientHeight + 4) return; // not scrollable (mobile)
    const top = card.offsetTop - container.offsetTop;
    const bottom = top + card.offsetHeight;
    if (top < container.scrollTop || bottom > container.scrollTop + container.clientHeight) {
      container.scrollTo({ top: Math.max(0, top - 12), behavior: "smooth" });
    }
  }, [activeOrder]);

  if (result.steps.length === 0) {
    return (
      <p className="rounded-xl border border-border bg-surface p-4 text-sm text-muted">
        No clear actions were detected in this video. Try a recording where your hands and the
        objects you work with are in view.
      </p>
    );
  }

  const groups = result.phases.length
    ? result.phases.map((p) => ({
        phase: p,
        steps: result.steps.filter((s) => s.order >= p.start_step && s.order <= p.end_step),
      }))
    : [
        {
          phase: { name: "Steps", start_step: 1, end_step: result.steps.length, color_index: 0 },
          steps: result.steps,
        },
      ];

  return (
    <>
      <div
        ref={containerRef}
        className="space-y-5 lg:max-h-[calc(100vh-9rem)] lg:overflow-y-auto lg:pr-1"
        data-testid="step-list"
      >
        {groups.map(({ phase, steps }) => (
          <section key={phase.name + phase.start_step} aria-label={`Phase: ${phase.name}`}>
            <h3 className="sticky top-0 z-10 mb-2 flex items-center gap-2 bg-background/95 py-1 text-sm font-semibold backdrop-blur">
              <span
                aria-hidden
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: phaseColor(phase.color_index) }}
              />
              {phase.name}
              <span className="font-normal text-muted">
                · steps {phase.start_step}–{phase.end_step}
              </span>
            </h3>
            <ol className="space-y-2">
              {steps.map((s) => (
                <StepCard
                  key={s.order}
                  step={s}
                  active={s.order === activeOrder}
                  onSelect={onSelect}
                  onPlayClip={setClip}
                  ref={(el) => {
                    if (el) cardRefs.current.set(s.order, el);
                    else cardRefs.current.delete(s.order);
                  }}
                />
              ))}
            </ol>
          </section>
        ))}
      </div>
      <Modal
        open={clip !== null}
        onClose={() => setClip(null)}
        title={clip ? `Step ${clip.order}: ${clip.title}` : "Clip"}
      >
        {clip?.clip_url ? (
          <div>
            <video
              key={clip.clip_url}
              src={apiUrl(clip.clip_url)}
              controls
              autoPlay
              playsInline
              className="max-h-[70vh] w-full rounded-lg bg-black"
              aria-label={`Clip of step ${clip.order}`}
            />
            <p className="mt-2 text-sm text-muted">
              {formatTime(clip.start)}–{formatTime(clip.end)} · {clip.description}
            </p>
          </div>
        ) : null}
      </Modal>
    </>
  );
}
