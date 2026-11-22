import { Cpu } from "lucide-react";
import { formatTime } from "@/lib/format";
import { STAGES } from "@/lib/stages";
import type { Result } from "@/lib/types";
import { PipelineDiagram } from "@/components/pipeline-diagram";
import { Badge, Card } from "@/components/ui";

function MotionChart({ result }: { result: Result }) {
  const curve = result.under_the_hood.motion_curve;
  const duration = result.video.duration || 1;
  if (curve.length < 2) return null;
  const max = Math.max(...curve.map(([, v]) => v), result.under_the_hood.motion_threshold, 1e-6);
  const W = 600;
  const H = 80;
  const points = curve
    .map(([t, v]) => `${(t / duration) * W},${H - (v / max) * (H - 4)}`)
    .join(" ");
  const thrY = H - (result.under_the_hood.motion_threshold / max) * (H - 4);
  return (
    <figure>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-20 w-full"
        role="img"
        aria-label="Motion over time with idle spans shaded"
      >
        {result.under_the_hood.idle_spans.map((s) => (
          <rect
            key={s.start}
            x={(s.start / duration) * W}
            width={((s.end - s.start) / duration) * W}
            y={0}
            height={H}
            fill="var(--warning-soft)"
          />
        ))}
        {result.under_the_hood.scene_cuts.map((c) => (
          <line
            key={c}
            x1={(c / duration) * W}
            x2={(c / duration) * W}
            y1={0}
            y2={H}
            stroke="var(--border)"
            strokeDasharray="3 3"
          />
        ))}
        <line
          x1={0}
          x2={W}
          y1={thrY}
          y2={thrY}
          stroke="var(--warning)"
          strokeDasharray="4 4"
          strokeWidth={1}
        />
        <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
      </svg>
      <figcaption className="mt-1 text-xs text-muted">
        Motion curve. Shaded = idle spans removed ({formatTime(result.stats.idle_removed_s)} total),
        dashed vertical = scene cuts, dashed horizontal = adaptive idle threshold.
      </figcaption>
    </figure>
  );
}

export function UnderTheHood({ result }: { result: Result }) {
  const u = result.under_the_hood;
  const timings = STAGES.map((s) => ({ ...s, seconds: u.stage_timings[s.id] ?? 0 }));
  const maxT = Math.max(...timings.map((t) => t.seconds), 0.001);
  return (
    <details
      className="group rounded-2xl border border-border bg-surface"
      data-testid="under-the-hood"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4 font-semibold">
        <span className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-accent" aria-hidden /> Under the hood
        </span>
        <span className="text-sm font-normal text-muted group-open:hidden">
          {u.windows.length} windows analyzed · show details
        </span>
      </summary>
      <div className="space-y-6 border-t border-border p-4">
        <PipelineDiagram />
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="p-4">
            <h3 className="text-sm font-semibold">Providers</h3>
            <dl className="mt-2 space-y-1 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Vision (actions)</dt>
                <dd className="text-right font-medium">
                  {u.vlm.name} · {u.vlm.model}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Text (titles, check)</dt>
                <dd className="text-right font-medium">
                  {u.llm.name} · {u.llm.model}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Embeddings</dt>
                <dd className="text-right font-medium">{u.embedding}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Prompt version</dt>
                <dd className="text-right font-medium">{u.prompt_version}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Titles from</dt>
                <dd className="text-right font-medium">
                  {u.summary_source === "llm" ? "LLM (validated)" : "deterministic fallback"}
                </dd>
              </div>
            </dl>
          </Card>
          <Card className="p-4">
            <h3 className="text-sm font-semibold">Stage timings</h3>
            <ul className="mt-2 space-y-1.5">
              {timings.map((t) => (
                <li
                  key={t.id}
                  className="grid grid-cols-[8.5rem_1fr_3.5rem] items-center gap-2 text-xs"
                >
                  <span className="truncate text-muted">{t.label}</span>
                  <span className="h-2 overflow-hidden rounded-full bg-surface-2">
                    <span
                      className="block h-full rounded-full bg-accent"
                      style={{ width: `${(t.seconds / maxT) * 100}%` }}
                    />
                  </span>
                  <span className="text-right tabular-nums">{t.seconds.toFixed(1)} s</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <MotionChart result={result} />
        <div>
          <h3 className="mb-2 text-sm font-semibold">Raw window-level actions</h3>
          <div className="max-h-80 overflow-auto rounded-xl border border-border">
            <table className="w-full min-w-[40rem] text-left text-xs">
              <caption className="sr-only">Action recognised in each analysis window</caption>
              <thead className="sticky top-0 bg-surface-2">
                <tr>
                  <th scope="col" className="px-3 py-2">
                    #
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Time
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Verb
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Object
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Tool
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Conf.
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Frames
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Description
                  </th>
                </tr>
              </thead>
              <tbody>
                {u.windows.map((w) => (
                  <tr key={w.id} className="border-t border-border">
                    <td className="px-3 py-1.5 tabular-nums">{w.id}</td>
                    <td className="px-3 py-1.5 tabular-nums">
                      {formatTime(w.start)}–{formatTime(w.end)}
                    </td>
                    <td className="px-3 py-1.5 font-medium">{w.is_idle ? "idle" : w.verb}</td>
                    <td className="px-3 py-1.5">{w.object}</td>
                    <td className="px-3 py-1.5">{w.tool}</td>
                    <td className="px-3 py-1.5 tabular-nums">{Math.round(w.confidence * 100)}%</td>
                    <td className="px-3 py-1.5 tabular-nums">
                      {w.frames} {w.cached ? <Badge className="ml-1">cached</Badge> : null}
                    </td>
                    <td className="px-3 py-1.5 text-muted">{w.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </details>
  );
}
