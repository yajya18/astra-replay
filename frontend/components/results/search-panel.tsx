"use client";

import { useId, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, MessageSquareText, Search } from "lucide-react";
import { api, apiUrl } from "@/lib/api";
import { formatTime } from "@/lib/format";
import type { Result, SearchHit } from "@/lib/types";
import { Alert, Button, Card } from "@/components/ui";

export function suggestedQueries(result: Result, max = 3): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const s of result.steps) {
    if (!s.object || s.verb === "unknown") continue;
    const q = `When did I ${s.verb} the ${s.object}?`;
    if (!seen.has(q)) {
      seen.add(q);
      out.push(q);
    }
  }
  // Spread the suggestions across the video rather than the first few steps.
  if (out.length <= max) return out;
  const step = (out.length - 1) / (max - 1);
  return Array.from({ length: max }, (_, i) => out[Math.round(i * step)]);
}

export function SearchPanel({
  result,
  onJump,
}: {
  result: Result;
  onJump: (seconds: number, order: number) => void;
}) {
  const inputId = useId();
  const [query, setQuery] = useState("");
  const suggestions = useMemo(() => suggestedQueries(result), [result]);
  const search = useMutation({
    mutationFn: (q: string) => api.search(result.job_id, q, true),
  });

  function run(q: string) {
    const text = q.trim();
    if (!text) return;
    setQuery(text);
    search.mutate(text);
  }

  const data = search.data;
  return (
    <Card className="p-4">
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          run(query);
        }}
        className="flex gap-2"
      >
        <label htmlFor={inputId} className="sr-only">
          Search the video
        </label>
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <input
            id={inputId}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about the video, e.g. when did I add the salt?"
            maxLength={300}
            className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm"
          />
        </div>
        <Button type="submit" disabled={search.isPending || !query.trim()}>
          {search.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Search
        </Button>
      </form>
      {suggestions.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2" aria-label="Suggested questions">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => run(s)}
              className="rounded-full border border-border px-3 py-1 text-xs text-muted transition hover:border-accent hover:text-foreground"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}

      <div aria-live="polite" className="mt-3 space-y-3">
        {search.isError ? <Alert title="Search failed">{search.error.message}</Alert> : null}
        {data?.answer ? (
          <div className="flex gap-3 rounded-xl bg-accent-soft p-3 text-sm">
            <MessageSquareText className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
            <div className="min-w-0">
              <p>{data.answer}</p>
              {data.answer_time !== null ? (
                <button
                  type="button"
                  onClick={() => {
                    const hit = data.hits.find(
                      (h) => data.answer_time! >= h.start - 1 && data.answer_time! <= h.end + 1,
                    );
                    onJump(data.answer_time!, hit?.step_order ?? data.hits[0]?.step_order ?? 1);
                  }}
                  className="mt-1 text-xs font-medium text-accent hover:underline"
                >
                  Jump to {formatTime(data.answer_time)}
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
        {data && data.hits.length === 0 ? (
          <p className="text-sm text-muted">No matching moments. Try different words.</p>
        ) : null}
        {data && data.hits.length > 0 ? (
          <ol className="space-y-1.5" aria-label="Search results">
            {data.hits.map((h: SearchHit) => (
              <li key={h.step_order}>
                <button
                  type="button"
                  onClick={() => onJump(h.start, h.step_order)}
                  className="flex w-full items-center gap-3 rounded-lg border border-border p-2 text-left transition hover:bg-surface-2"
                >
                  {h.keyframe_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- media is served by the API
                    <img
                      src={apiUrl(h.keyframe_url)}
                      alt=""
                      className="h-10 w-16 rounded object-cover"
                    />
                  ) : null}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">
                      {h.step_order}. {h.title}
                    </span>
                    <span className="block text-xs tabular-nums text-muted">
                      {formatTime(h.start)}–{formatTime(h.end)} · match {Math.round(h.score * 100)}%
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </Card>
  );
}
