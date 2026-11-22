import { formatTime } from "@/lib/format";
import type { Result } from "@/lib/types";

// Fixed hex versions of the dark-theme phase colours (WebGL can't read CSS variables).
export const XR_PHASE_COLORS = ["#818cf8", "#2dd4bf", "#fb923c", "#f472b6", "#38bdf8", "#a3e635"];

export interface XRStep {
  order: number;
  title: string;
  time: string;
  phase: string;
  color: string;
  description: string;
  status: "done" | "out_of_order" | "extra" | null;
}

export function stepsFromResult(result: Result): XRStep[] {
  return result.steps.map((s) => ({
    order: s.order,
    title: s.title,
    time: `${formatTime(s.start)}–${formatTime(s.end)}`,
    phase: s.phase || "Steps",
    color: XR_PHASE_COLORS[s.phase_index % XR_PHASE_COLORS.length],
    description: s.description,
    status: s.alignment,
  }));
}

/** Shown only when no processed result is available yet; labelled as a sample in the UI. */
export const SAMPLE_STEPS: XRStep[] = [
  ["Crack the eggs", "0:04–0:15", "Prep", 0],
  ["Whisk the eggs", "0:15–0:38", "Prep", 0],
  ["Chop the chives", "0:41–1:20", "Prep", 0],
  ["Heat the butter", "1:24–1:50", "Cook", 1],
  ["Pour the eggs", "1:52–2:05", "Cook", 1],
  ["Fold the omelette", "2:30–2:48", "Cook", 1],
  ["Plate the omelette", "2:55–3:10", "Finish", 2],
].map(([title, time, phase, idx], i) => ({
  order: i + 1,
  title: title as string,
  time: time as string,
  phase: phase as string,
  color: XR_PHASE_COLORS[idx as number],
  description: "",
  status: null,
}));
