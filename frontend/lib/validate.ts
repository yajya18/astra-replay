export interface Limits {
  max_upload_mb: number;
  max_duration_s: number;
  min_duration_s: number;
  highlight_min_s: number;
  highlight_max_s: number;
  highlight_default_s: number;
  retention_hours: number;
}

export const DEFAULT_LIMITS: Limits = {
  max_upload_mb: 500,
  max_duration_s: 600,
  min_duration_s: 5,
  highlight_min_s: 20,
  highlight_max_s: 180,
  highlight_default_s: 60,
  retention_hours: 24,
};

export const VIDEO_EXTENSIONS = [".mp4", ".mov", ".m4v", ".webm", ".mkv"];
export const ACCEPT = "video/*,.mp4,.mov,.m4v,.webm,.mkv";

function extension(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function minutes(seconds: number): string {
  return seconds >= 60 ? `${+(seconds / 60).toFixed(1)} minutes` : `${seconds} seconds`;
}

/** Browser-side checks before uploading. ``duration`` is null if the browser can't decode it. */
export function validateVideo(
  file: { name: string; type: string; size: number },
  duration: number | null,
  limits: Limits = DEFAULT_LIMITS,
): string | null {
  const ext = extension(file.name);
  const looksLikeVideo = file.type.startsWith("video/") || VIDEO_EXTENSIONS.includes(ext);
  if (!looksLikeVideo) {
    return "That doesn't look like a video. Please choose an MP4, MOV, M4V, WebM or MKV file.";
  }
  if (file.size > limits.max_upload_mb * 1024 * 1024) {
    return `This video is ${Math.round(file.size / 1024 / 1024)} MB. The limit is ${limits.max_upload_mb} MB.`;
  }
  if (file.size === 0) return "This file is empty.";
  if (duration !== null && Number.isFinite(duration)) {
    if (duration > limits.max_duration_s + 0.5) {
      return `This video is ${(duration / 60).toFixed(1)} minutes long. Please upload up to ${minutes(limits.max_duration_s)}.`;
    }
    if (duration < limits.min_duration_s) {
      return `This video is only ${duration.toFixed(1)} seconds long. Please upload at least ${minutes(limits.min_duration_s)}.`;
    }
  }
  return null;
}

export const EXAMPLE_RECIPE = `1. Crack two eggs into a bowl
2. Whisk the eggs with a fork
3. Chop the chives with a knife
4. Heat butter in the pan
5. Pour the eggs into the pan
6. Fold the omelette with a spatula
7. Plate the omelette`;
