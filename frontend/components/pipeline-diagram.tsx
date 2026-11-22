import { ArrowRight } from "lucide-react";

const NODES = [
  { title: "Ingest", text: "Probe, upright, 720p 30 fps" },
  { title: "Motion", text: "Idle spans + scene cuts" },
  { title: "Windows", text: "4 s windows, sharp frames" },
  { title: "Understand", text: "VLM → verb · object · tool" },
  { title: "Steps", text: "Merge similar windows" },
  { title: "Summarize", text: "Titles, phases, summary" },
  { title: "Check", text: "Align to your procedure" },
  { title: "Render", text: "Keyframes, clips, reel" },
];

export function PipelineDiagram({ compact = false }: { compact?: boolean }) {
  return (
    <ol
      aria-label="Replay pipeline"
      className={`grid gap-2 ${compact ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-2 sm:grid-cols-4 lg:grid-cols-8"}`}
    >
      {NODES.map((n, i) => (
        <li key={n.title} className="relative rounded-xl border border-border bg-surface p-3">
          <p className="text-xs font-medium text-accent">{String(i + 1).padStart(2, "0")}</p>
          <p className="text-sm font-semibold">{n.title}</p>
          <p className="mt-0.5 text-xs text-muted">{n.text}</p>
          {i < NODES.length - 1 ? (
            <ArrowRight
              aria-hidden
              className="absolute -right-2.5 top-1/2 z-10 hidden h-4 w-4 -translate-y-1/2 rounded-full bg-background text-muted lg:block"
            />
          ) : null}
        </li>
      ))}
    </ol>
  );
}
