// Mirrors backend/app/pipeline/run.py STAGES (name, weight).
export const STAGES: { id: string; label: string; detail: string; weight: number }[] = [
  { id: "ingest", label: "Ingest", detail: "Checking and normalising the video", weight: 0.1 },
  {
    id: "motion",
    label: "Motion & scenes",
    detail: "Finding idle time and scene cuts",
    weight: 0.1,
  },
  { id: "transcribe", label: "Speech hints", detail: "Optional speech-to-text", weight: 0.05 },
  {
    id: "understand",
    label: "Understanding actions",
    detail: "Verb + object + tool for each window",
    weight: 0.45,
  },
  { id: "segment", label: "Building steps", detail: "Merging windows into steps", weight: 0.05 },
  { id: "summarize", label: "Summarizing", detail: "Titles, phases and summary", weight: 0.05 },
  {
    id: "align",
    label: "Checking procedure",
    detail: "Comparing with your reference steps",
    weight: 0.05,
  },
  { id: "media", label: "Rendering", detail: "Keyframes, clips and highlight reel", weight: 0.1 },
  { id: "exports", label: "Exports", detail: "Reports, chapters and search index", weight: 0.05 },
];

export type StageStatus = "done" | "active" | "pending" | "failed";

export function stageProgress(
  stageId: string,
  current: string | null,
  completed: string[],
  overall: number,
): number {
  if (completed.includes(stageId)) return 1;
  if (stageId !== current) return 0;
  const doneWeight = STAGES.filter((s) => completed.includes(s.id)).reduce(
    (a, s) => a + s.weight,
    0,
  );
  const stage = STAGES.find((s) => s.id === stageId);
  if (!stage) return 0;
  return Math.max(0, Math.min(1, (overall - doneWeight) / stage.weight));
}
