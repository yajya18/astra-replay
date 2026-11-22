"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Clapperboard, Download, FlaskConical, Glasses } from "lucide-react";
import { api, apiUrl, ApiError } from "@/lib/api";
import { formatDuration, formatTime } from "@/lib/format";
import type { Result, ResultStep } from "@/lib/types";
import { Player, type PlayerHandle } from "@/components/results/player";
import { StepList } from "@/components/results/step-list";
import { SearchPanel } from "@/components/results/search-panel";
import { ProcedurePanel } from "@/components/results/procedure-panel";
import { ExportMenu } from "@/components/results/export-menu";
import { UnderTheHood } from "@/components/results/under-the-hood";
import { Alert, Badge, Card, SectionHeading, Skeleton, buttonClass } from "@/components/ui";

export function stepAt(steps: ResultStep[], t: number): number | null {
  const hit = steps.find((s) => t >= s.start && t < s.end);
  return hit ? hit.order : null;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-3 py-2.5">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

export function ResultsSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading results">
      <Skeleton className="h-9 w-2/3" />
      <Skeleton className="h-4 w-full max-w-2xl" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Skeleton className="aspect-video w-full" />
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function ResultsView({ jobId }: { jobId: string }) {
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["result", jobId],
    queryFn: () => api.result(jobId),
    retry: (count, err) =>
      !(err instanceof ApiError && [404, 409].includes(err.status)) && count < 2,
  });
  if (isPending) return <ResultsSkeleton />;
  if (error) {
    const notReady = error instanceof ApiError && error.status === 409;
    return (
      <Alert
        tone={notReady ? "info" : "danger"}
        title={notReady ? "Still processing" : "Couldn't load this result"}
        action={
          notReady ? (
            <Link href={`/jobs/${jobId}`} className={buttonClass("primary", "sm")}>
              See progress
            </Link>
          ) : (
            <button className={buttonClass("secondary", "sm")} onClick={() => refetch()}>
              Try again
            </button>
          )
        }
      >
        {error.message}
      </Alert>
    );
  }
  return <ResultsContent result={data} />;
}

export function ResultsContent({ result }: { result: Result }) {
  const playerRef = useRef<PlayerHandle>(null);
  const [activeOrder, setActiveOrder] = useState<number | null>(result.steps[0]?.order ?? null);
  const lastOrder = useRef<number | null>(null);

  const onTime = useCallback(
    (t: number) => {
      const order = stepAt(result.steps, t);
      if (order !== null && order !== lastOrder.current) {
        lastOrder.current = order;
        setActiveOrder(order);
      }
    },
    [result.steps],
  );

  const select = useCallback((step: ResultStep) => {
    lastOrder.current = step.order;
    setActiveOrder(step.order);
    playerRef.current?.seek(step.start + 0.01);
  }, []);

  const jump = useCallback((seconds: number, order: number) => {
    lastOrder.current = order;
    setActiveOrder(order);
    playerRef.current?.seek(seconds + 0.01);
    document.getElementById("player")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  const s = result.stats;
  const stats = useMemo(
    () => [
      { label: "Original length", value: formatTime(s.original_duration) },
      {
        label: "Highlight reel",
        value: s.highlight_duration ? formatTime(s.highlight_duration) : "—",
      },
      {
        label: "Compression",
        value: s.compression_ratio ? `${s.compression_ratio.toFixed(1)}×` : "—",
      },
      { label: "Steps", value: String(s.step_count) },
      { label: "Idle removed", value: formatDuration(s.idle_removed_s) },
      { label: "Processing time", value: formatDuration(s.processing_s) },
    ],
    [s],
  );

  return (
    <div className="space-y-8">
      <header className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 max-w-3xl">
            <div className="mb-2 flex flex-wrap gap-2">
              {result.mock_mode ? (
                <Badge
                  tone="warning"
                  title="Generated by the offline mock provider, not a real vision model"
                >
                  <FlaskConical className="h-3 w-3" aria-hidden /> Mock mode
                </Badge>
              ) : null}
              {result.title && result.title !== result.task_name ? (
                <Badge>{result.title}</Badge>
              ) : null}
            </div>
            <h1 className="text-3xl font-semibold tracking-tight">{result.task_name}</h1>
            <p className="mt-2 text-muted">{result.summary}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href={`/xr?job=${result.job_id}`} className={buttonClass("ghost")}>
              <Glasses className="h-4 w-4" aria-hidden /> View in XR
            </Link>
            <ExportMenu exports={result.exports} />
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {stats.map((st) => (
            <Stat key={st.label} {...st} />
          ))}
        </dl>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr] lg:items-start">
        <div className="space-y-6">
          <section id="player" aria-label="Video player">
            <Player ref={playerRef} result={result} activeOrder={activeOrder} onTime={onTime} />
          </section>
          <section aria-labelledby="search-heading">
            <SectionHeading
              id="search-heading"
              title="Search the video"
              description="Ask in plain language; results jump to the moment."
            />
            <SearchPanel result={result} onJump={jump} />
          </section>
        </div>
        <section aria-labelledby="steps-heading" className="lg:sticky lg:top-16">
          <SectionHeading
            id="steps-heading"
            title={`${result.steps.length} action steps`}
            description="Verb + object + tool. Click a step to jump there."
          />
          <StepList result={result} activeOrder={activeOrder} onSelect={select} />
        </section>
      </div>

      {result.alignment ? (
        <section aria-labelledby="procedure-heading">
          <SectionHeading
            id="procedure-heading"
            title="Procedure check"
            description={`${result.alignment.completed} of ${result.alignment.total} reference steps found`}
          />
          <ProcedurePanel alignment={result.alignment} steps={result.steps} onSelect={select} />
        </section>
      ) : null}

      {result.highlight ? (
        <section aria-labelledby="reel-heading">
          <SectionHeading
            id="reel-heading"
            title="Highlight reel"
            description={`${formatDuration(result.highlight.duration)} captioned recap with title cards`}
            action={
              <a
                href={apiUrl(`/api/jobs/${result.job_id}/exports/mp4`)}
                download
                className={buttonClass("secondary", "sm")}
              >
                <Download className="h-4 w-4" aria-hidden /> Download MP4
              </a>
            }
          />
          <Card className="overflow-hidden">
            <video
              src={apiUrl(result.highlight.url)}
              poster={apiUrl(result.highlight.thumbnail_url)}
              controls
              playsInline
              preload="none"
              className="mx-auto aspect-video max-h-[70vh] w-full bg-black object-contain"
              aria-label="Highlight reel with burned-in step captions"
            />
          </Card>
        </section>
      ) : (
        <Card className="flex items-center gap-3 p-4 text-sm text-muted">
          <Clapperboard className="h-4 w-4" aria-hidden /> No highlight reel: no steps were
          detected.
        </Card>
      )}

      <UnderTheHood result={result} />
    </div>
  );
}
