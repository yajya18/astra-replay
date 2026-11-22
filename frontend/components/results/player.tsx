"use client";

import { forwardRef, useImperativeHandle, useRef, useState, type KeyboardEvent } from "react";
import { apiUrl } from "@/lib/api";
import { formatTime, phaseColor } from "@/lib/format";
import type { Result } from "@/lib/types";

export interface PlayerHandle {
  seek: (seconds: number, play?: boolean) => void;
}

interface Props {
  result: Result;
  activeOrder: number | null;
  onTime: (seconds: number) => void;
}

/** Main video with VTT chapters/captions and a custom, phase-coloured chapter timeline. */
export const Player = forwardRef<PlayerHandle, Props>(function Player(
  { result, activeOrder, onTime },
  ref,
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState(0);
  const duration = result.video.duration || 1;

  useImperativeHandle(ref, () => ({
    seek(seconds, play = true) {
      const v = videoRef.current;
      if (!v) return;
      v.currentTime = Math.max(0, Math.min(seconds, duration - 0.05));
      setTime(v.currentTime);
      onTime(v.currentTime);
      if (play) void v.play().catch(() => undefined);
    },
  }));

  function seekTo(seconds: number) {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(seconds, duration - 0.05));
    setTime(v.currentTime);
    onTime(v.currentTime);
  }

  function onBarKey(e: KeyboardEvent<HTMLDivElement>) {
    const steps = result.steps;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      seekTo(time + (e.key === "ArrowRight" ? 5 : -5));
    } else if (e.key === "PageDown" || e.key === "PageUp") {
      e.preventDefault();
      const idx = steps.findIndex((s) => s.order === activeOrder);
      const next = e.key === "PageDown" ? steps[idx + 1] : steps[Math.max(0, idx - 1)];
      if (next) seekTo(next.start);
    } else if (e.key === "Home") {
      e.preventDefault();
      seekTo(0);
    } else if (e.key === "End") {
      e.preventDefault();
      seekTo(duration);
    }
  }

  const portrait = result.video.height > result.video.width;
  const current = result.steps.find((s) => s.order === activeOrder);

  return (
    <div>
      <div className={`overflow-hidden rounded-2xl bg-black ${portrait ? "mx-auto max-w-sm" : ""}`}>
        <video
          ref={videoRef}
          src={apiUrl(result.media.video_url)}
          poster={result.media.poster_url ? apiUrl(result.media.poster_url) : undefined}
          crossOrigin="anonymous"
          controls
          playsInline
          preload="metadata"
          className="aspect-video w-full bg-black object-contain"
          style={
            portrait ? { aspectRatio: `${result.video.width} / ${result.video.height}` } : undefined
          }
          aria-label={`Video: ${result.task_name}`}
          onTimeUpdate={(e) => {
            const t = e.currentTarget.currentTime;
            setTime(t);
            onTime(t);
          }}
        >
          <track
            kind="chapters"
            src={apiUrl(result.media.chapters_vtt_url)}
            srcLang="en"
            label="Steps"
            default
          />
          <track
            kind="captions"
            src={apiUrl(result.media.captions_vtt_url)}
            srcLang="en"
            label={result.under_the_hood.transcript_available ? "Speech" : "Actions"}
          />
        </video>
      </div>

      <div className="mt-3">
        <div
          role="slider"
          tabIndex={0}
          aria-label="Step timeline. Arrow keys move 5 seconds, Page Up and Page Down jump between steps."
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={Math.round(time)}
          aria-valuetext={`${formatTime(time)}${current ? `, step ${current.order}: ${current.title}` : ""}`}
          onKeyDown={onBarKey}
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            seekTo(((e.clientX - rect.left) / rect.width) * duration);
          }}
          className="relative h-9 cursor-pointer rounded-lg bg-surface-2"
          data-testid="chapter-timeline"
        >
          {result.steps.map((s) => (
            <button
              key={s.order}
              type="button"
              tabIndex={-1}
              title={`${s.order}. ${s.title} (${formatTime(s.start)}–${formatTime(s.end)})`}
              aria-label={`Jump to step ${s.order}: ${s.title}`}
              onClick={(e) => {
                e.stopPropagation();
                seekTo(s.start);
              }}
              className="absolute top-1 bottom-1 rounded-md transition hover:brightness-110"
              style={{
                left: `${(s.start / duration) * 100}%`,
                width: `max(${((s.end - s.start) / duration) * 100}%, 4px)`,
                background: phaseColor(s.phase_index),
                opacity: activeOrder === null || activeOrder === s.order ? 1 : 0.55,
                outline: activeOrder === s.order ? "2px solid var(--foreground)" : "none",
                outlineOffset: 1,
              }}
            />
          ))}
          <div
            aria-hidden
            className="pointer-events-none absolute top-0 bottom-0 w-0.5 bg-foreground"
            style={{ left: `${(time / duration) * 100}%` }}
          />
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
          <span className="tabular-nums">
            {formatTime(time)} / {formatTime(duration)}
          </span>
          <ul className="flex flex-wrap gap-3" aria-label="Phases">
            {result.phases.map((p) => (
              <li key={p.name + p.start_step} className="flex items-center gap-1.5">
                <span
                  aria-hidden
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: phaseColor(p.color_index) }}
                />
                {p.name}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
});
