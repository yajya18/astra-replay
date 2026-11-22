"use client";

import { useEffect, useId, useRef, useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { FileVideo, ListChecks, Loader2, UploadCloud, X } from "lucide-react";
import { api, ApiError, uploadVideo } from "@/lib/api";
import { formatBytes, formatDuration } from "@/lib/format";
import { ACCEPT, DEFAULT_LIMITS, EXAMPLE_RECIPE, validateVideo } from "@/lib/validate";
import { Alert, Button, Card, ProgressBar } from "@/components/ui";

interface Picked {
  file: File;
  url: string;
  duration: number | null;
  previewable: boolean;
}

export function UploadCard() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const ids = { file: useId(), title: useId(), ref: useId(), slider: useId(), help: useId() };
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    staleTime: 60_000,
  });
  const limits = health?.limits ?? DEFAULT_LIMITS;

  const [picked, setPicked] = useState<Picked | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [title, setTitle] = useState("");
  const [reference, setReference] = useState("");
  const [highlight, setHighlight] = useState<number | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const highlightValue = highlight ?? limits.highlight_default_s;

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => {
    const url = picked?.url;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [picked?.url]);

  function choose(file: File | undefined) {
    setUploadError(null);
    if (!file) return;
    const quick = validateVideo(file, null, limits);
    if (quick) {
      setPicked(null);
      setProblem(quick);
      return;
    }
    const url = URL.createObjectURL(file);
    setPicked({ file, url, duration: null, previewable: true });
    setProblem(null);
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
  }

  function onMetadata(duration: number) {
    if (!picked) return;
    setPicked({ ...picked, duration });
    setProblem(validateVideo(picked.file, duration, limits));
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    choose(e.dataTransfer.files?.[0]);
  }

  async function submit() {
    if (!picked || problem) return;
    setUploadError(null);
    setProgress(0);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const { job_id } = await uploadVideo(
        {
          file: picked.file,
          title: title.trim() || undefined,
          referenceSteps: reference,
          highlightSeconds: highlightValue,
        },
        setProgress,
        controller.signal,
      );
      router.push(`/jobs/${job_id}`);
    } catch (e) {
      setProgress(null);
      if (e instanceof ApiError && e.code === "aborted") return;
      setUploadError(e instanceof Error ? e.message : "Upload failed.");
    }
  }

  const uploading = progress !== null;

  return (
    <Card className="p-4 sm:p-6">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        aria-describedby={ids.help}
        className="space-y-5"
      >
        <div>
          <label htmlFor={ids.file} className="mb-2 block text-sm font-medium">
            Your first-person video
          </label>
          {!picked ? (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={`flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-10 text-center transition ${
                dragging ? "border-accent bg-accent-soft" : "border-border bg-surface-2/50"
              }`}
            >
              <UploadCloud className="h-10 w-10 text-accent" aria-hidden />
              <div>
                <p className="font-medium">Drop a video here, or choose one</p>
                <p id={ids.help} className="mt-1 text-sm text-muted">
                  MP4, MOV, M4V, WebM or MKV · {limits.min_duration_s} s to{" "}
                  {formatDuration(limits.max_duration_s)} · up to {limits.max_upload_mb} MB
                </p>
              </div>
              <Button onClick={() => inputRef.current?.click()} disabled={uploading}>
                <FileVideo className="h-4 w-4" aria-hidden /> Choose video
              </Button>
            </div>
          ) : (
            <div className="grid gap-4 rounded-xl border border-border bg-surface-2/50 p-3 sm:grid-cols-[minmax(0,14rem)_1fr]">
              {picked.previewable ? (
                <video
                  src={picked.url}
                  className="aspect-video w-full rounded-lg bg-black object-contain"
                  controls
                  muted
                  playsInline
                  preload="metadata"
                  aria-label="Preview of the selected video"
                  onLoadedMetadata={(e) => onMetadata(e.currentTarget.duration)}
                  onError={() => setPicked({ ...picked, previewable: false })}
                />
              ) : (
                <div className="flex aspect-video w-full items-center justify-center rounded-lg bg-surface text-center text-xs text-muted">
                  Preview not supported in this browser. The server will check the video.
                </div>
              )}
              <div className="min-w-0 space-y-1 text-sm">
                <p className="truncate font-medium" title={picked.file.name}>
                  {picked.file.name}
                </p>
                <p className="text-muted">
                  {formatBytes(picked.file.size)}
                  {picked.duration !== null ? ` · ${formatDuration(picked.duration)}` : ""}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="-ml-2"
                  onClick={() => {
                    setPicked(null);
                    setProblem(null);
                  }}
                  disabled={uploading}
                >
                  <X className="h-4 w-4" aria-hidden /> Choose a different video
                </Button>
              </div>
            </div>
          )}
          <input
            ref={inputRef}
            id={ids.file}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            tabIndex={-1}
            onChange={(e) => {
              choose(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          {problem ? (
            <p role="alert" className="mt-2 text-sm text-danger">
              {problem}
            </p>
          ) : null}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor={ids.title} className="mb-1.5 block text-sm font-medium">
              Title <span className="font-normal text-muted">(optional)</span>
            </label>
            <input
              id={ids.title}
              value={title}
              maxLength={120}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Sunday omelette"
              className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
            />
          </div>
          <div>
            <label htmlFor={ids.slider} className="mb-1.5 flex justify-between text-sm font-medium">
              <span>Highlight reel length</span>
              <span className="tabular-nums text-muted">{highlightValue} s</span>
            </label>
            <input
              id={ids.slider}
              type="range"
              min={limits.highlight_min_s}
              max={limits.highlight_max_s}
              step={5}
              value={highlightValue}
              onChange={(e) => setHighlight(Number(e.target.value))}
              className="h-10 w-full accent-[var(--accent)]"
            />
          </div>
        </div>

        <div>
          <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
            <label htmlFor={ids.ref} className="text-sm font-medium">
              Reference procedure <span className="font-normal text-muted">(optional)</span>
            </label>
            <Button variant="ghost" size="sm" onClick={() => setReference(EXAMPLE_RECIPE)}>
              <ListChecks className="h-4 w-4" aria-hidden /> Use example recipe
            </Button>
          </div>
          <textarea
            id={ids.ref}
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            rows={5}
            maxLength={20000}
            placeholder={
              "One step per line, e.g.\n1. Crack two eggs into a bowl\n2. Whisk the eggs"
            }
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
          />
          <p className="mt-1 text-xs text-muted">
            Paste the steps you meant to follow. Replay will flag missed and out-of-order steps.
          </p>
        </div>

        {uploadError ? <Alert title="Upload failed">{uploadError}</Alert> : null}

        {uploading ? (
          <div className="space-y-2" aria-live="polite">
            <div className="flex justify-between text-sm">
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                {progress < 1 ? "Uploading…" : "Starting processing…"}
              </span>
              <span className="tabular-nums text-muted">{Math.round(progress * 100)}%</span>
            </div>
            <ProgressBar value={progress} label="Upload progress" />
            <Button variant="ghost" size="sm" onClick={() => abortRef.current?.abort()}>
              Cancel upload
            </Button>
          </div>
        ) : (
          <Button type="submit" size="lg" className="w-full" disabled={!picked || !!problem}>
            <UploadCloud className="h-5 w-5" aria-hidden /> Upload and create my replay
          </Button>
        )}
      </form>
    </Card>
  );
}
