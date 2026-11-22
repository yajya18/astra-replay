import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, formatTime, phaseColor } from "@/lib/format";
import { stageProgress } from "@/lib/stages";
import { DEFAULT_LIMITS, validateVideo } from "@/lib/validate";
import { apiUrl } from "@/lib/api";

const MB = 1024 * 1024;

describe("format", () => {
  it("formats times and durations", () => {
    expect(formatTime(75.4)).toBe("1:15");
    expect(formatTime(3725)).toBe("1:02:05");
    expect(formatTime(-3)).toBe("0:00");
    expect(formatDuration(42)).toBe("42 s");
    expect(formatDuration(95)).toBe("1 min 35 s");
    expect(formatDuration(120)).toBe("2 min");
    expect(formatBytes(2.5 * MB)).toBe("2.5 MB");
    expect(phaseColor(7)).toBe("var(--phase-1)");
  });
});

describe("validateVideo", () => {
  const ok = { name: "omelette.mov", type: "video/quicktime", size: 50 * MB };
  it("accepts a normal phone video", () => {
    expect(validateVideo(ok, 120)).toBeNull();
    expect(validateVideo({ ...ok, type: "" }, null)).toBeNull(); // extension is enough
  });
  it("rejects non-videos, too big, too long and too short", () => {
    expect(validateVideo({ name: "notes.txt", type: "text/plain", size: 10 }, null)).toMatch(
      /doesn't look like a video/,
    );
    expect(validateVideo({ ...ok, size: 600 * MB }, 60)).toMatch(/limit is 500 MB/);
    expect(validateVideo(ok, 11 * 60)).toMatch(/up to 10 minutes/);
    expect(validateVideo(ok, 3)).toMatch(/at least 5 seconds/);
    expect(validateVideo(ok, 60, { ...DEFAULT_LIMITS, max_duration_s: 30 })).toMatch(
      /up to 30 seconds/,
    );
  });
});

describe("stageProgress", () => {
  it("is relative to the current stage weight", () => {
    expect(stageProgress("ingest", "motion", ["ingest"], 0.15)).toBe(1);
    expect(stageProgress("motion", "motion", ["ingest"], 0.15)).toBeCloseTo(0.5);
    expect(stageProgress("media", "motion", ["ingest"], 0.15)).toBe(0);
  });
});

describe("apiUrl", () => {
  it("resolves relative API paths against the same host", () => {
    expect(apiUrl("/media/jobs/x/work.mp4")).toBe(
      `http://${window.location.hostname}:8000/media/jobs/x/work.mp4`,
    );
    expect(apiUrl("https://cdn.example/x.mp4")).toBe("https://cdn.example/x.mp4");
  });
});
