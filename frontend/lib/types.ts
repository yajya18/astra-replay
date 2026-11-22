// Mirrors backend/app/pipeline/types.py (Result, schema 1.0) and backend/app/schemas.py.

export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type StepAlignment = "done" | "out_of_order" | "extra";
export type ReferenceStatus = "done" | "missed" | "out_of_order";

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export interface ProviderInfo {
  name: string;
  model: string;
  mock: boolean;
}

import type { Limits } from "@/lib/validate";

export interface Health {
  status: string;
  version: string;
  vlm: ProviderInfo;
  llm: ProviderInfo;
  embedding: string;
  ffmpeg: boolean;
  whisper: boolean;
  mock_mode: boolean;
  limits: Limits;
}

export interface JobInfo {
  source?: {
    codec: string;
    width: number;
    height: number;
    rotation: number;
    vfr: boolean;
    duration: number;
    has_audio: boolean;
  };
  idle_seconds?: number;
  scene_cuts?: number;
  transcript_segments?: number;
  windows_total?: number;
  windows_analyzed?: number;
  first_actions?: string[];
  window_errors?: number;
  cached_windows?: number;
  steps_detected?: number;
  step_preview?: string[];
  task_name?: string;
  verdict?: string;
}

export interface JobState {
  id: string;
  status: JobStatus;
  stage: string | null;
  progress: number;
  message: string;
  error: { code: string; message: string } | null;
  info: JobInfo;
  completed_stages: string[];
  title: string | null;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResultStep {
  id: number;
  order: number;
  start: number;
  end: number;
  duration: number;
  title: string;
  verb: string;
  object: string;
  tool: string;
  hands: string;
  description: string;
  confidence: number;
  phase: string;
  phase_index: number;
  transcript: string;
  window_ids: number[];
  keyframe_url: string | null;
  keyframe_jpg_url: string | null;
  clip_url: string | null;
  alignment: StepAlignment | null;
  reference_index: number | null;
}

export interface ResultPhase {
  name: string;
  start_step: number;
  end_step: number;
  color_index: number;
}

export interface ResultReference {
  index: number;
  text: string;
  status: ReferenceStatus;
  matched_steps: number[];
  similarity: number;
  verified_by_llm: boolean;
  reason: string;
}

export interface ResultAlignment {
  verdict: string;
  completed: number;
  total: number;
  reference: ResultReference[];
  extra_steps: number[];
}

export interface ResultWindow {
  id: number;
  start: number;
  end: number;
  frames: number;
  motion: number;
  is_idle: boolean;
  verb: string;
  object: string;
  tool: string;
  description: string;
  confidence: number;
  cached: boolean;
}

export interface ResultExport {
  kind: string;
  label: string;
  url: string;
  filename: string;
  size_bytes: number;
}

export interface Result {
  schema_version: string;
  job_id: string;
  title: string;
  task_name: string;
  summary: string;
  mock_mode: boolean;
  created_at: string;
  video: {
    url: string;
    duration: number;
    width: number;
    height: number;
    fps: number;
    has_audio: boolean;
    source_codec: string;
    rotation: number;
    variable_frame_rate: boolean;
  };
  stats: {
    original_duration: number;
    highlight_duration: number;
    compression_ratio: number;
    step_count: number;
    idle_removed_s: number;
    processing_s: number;
    windows_analyzed: number;
  };
  phases: ResultPhase[];
  steps: ResultStep[];
  alignment: ResultAlignment | null;
  highlight: { url: string; thumbnail_url: string; duration: number; target: number } | null;
  media: {
    video_url: string;
    chapters_vtt_url: string;
    captions_vtt_url: string;
    poster_url: string | null;
  };
  exports: ResultExport[];
  transcript: { start: number; end: number; text: string }[];
  under_the_hood: {
    vlm: { name: string; model: string };
    llm: { name: string; model: string };
    embedding: string;
    prompt_version: string;
    stage_timings: Record<string, number>;
    windows: ResultWindow[];
    idle_spans: { start: number; end: number }[];
    scene_cuts: number[];
    motion_curve: [number, number][];
    motion_threshold: number;
    summary_source: "llm" | "fallback";
    transcript_available: boolean;
  };
}

export interface SearchHit {
  step_order: number;
  step_id: number;
  title: string;
  start: number;
  end: number;
  score: number;
  semantic_score: number;
  keyword_score: number;
  snippet: string;
  keyframe_url: string | null;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  answer: string | null;
  answer_time: number | null;
}

export interface DemoItem {
  job_id: string;
  slug: string;
  title: string;
  task_name: string;
  summary: string;
  duration: number;
  step_count: number;
  thumbnail_url: string | null;
  has_reference: boolean;
  status: JobStatus;
}
