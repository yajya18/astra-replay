"""Captioned highlight reel with title and closing cards.

Each step gets a time budget proportional to sqrt(duration), clamped to
[step_min, step_max] and centred on its motion peak. Segments are rendered with a
lower-third caption (bundled font, so it works in Docker), then joined with short
crossfades; if the crossfade graph fails, hard cuts are used instead.
"""

from __future__ import annotations

import logging
import math
import shutil
import textwrap
from collections.abc import Sequence
from pathlib import Path

from app.media_tools import FFmpegError, ffmpeg, ffprobe_json
from app.pipeline.context import JobContext
from app.pipeline.types import HighlightInfo, StepData, SummaryData, WorkVideo

log = logging.getLogger("replay.highlights")

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
BG = "0x10121c"


def allocate_budgets(
    durations: Sequence[float], target: float, min_s: float, max_s: float
) -> list[float]:
    """Seconds per step (0 = step left out). Sums to ``target`` whenever material allows.

    Budgets are proportional to sqrt(duration), clamped to [min_s, max_s] and never
    longer than the step. If even the minimums don't fit, the shortest steps are
    left out. If the clamped budgets fall short of the target, the cap is relaxed
    towards each step's full length so the reel still reaches its target length.
    """
    n = len(durations)
    if n == 0 or target <= 0:
        return [0.0] * n
    used = list(range(n))
    floors = {i: min(min_s, durations[i]) for i in used}
    while len(used) > 1 and sum(floors[i] for i in used) > target:
        used.remove(min(used, key=lambda i: (durations[i], -i)))
    weights = {i: math.sqrt(max(durations[i], 1e-6)) for i in used}

    def fill(caps: dict[int, float]) -> dict[int, float]:
        if sum(caps.values()) <= target:
            return dict(caps)
        lo, hi = 0.0, target / min(weights.values()) + max(caps.values())
        for _ in range(60):
            k = (lo + hi) / 2
            total = sum(min(max(k * weights[i], floors[i]), caps[i]) for i in used)
            lo, hi = (k, hi) if total < target else (lo, k)
        return {i: min(max(hi * weights[i], floors[i]), caps[i]) for i in used}

    caps = {i: max(floors[i], min(max_s, durations[i])) for i in used}
    budget = fill(caps)
    if sum(budget.values()) < target - 1e-6:
        budget = fill({i: durations[i] for i in used})
    out = [0.0] * n
    for i, b in budget.items():
        out[i] = round(b, 3)
    return out


def segment_window(step: StepData, budget: float) -> tuple[float, float]:
    start = step.peak_time - budget / 2
    start = min(max(start, step.start), max(step.start, step.end - budget))
    return round(start, 3), round(min(budget, step.end - start), 3)


def _wrap(text: str, width: int, lines: int = 2) -> str:
    wrapped = textwrap.wrap(text, width=width) or [""]
    if len(wrapped) > lines:
        wrapped = wrapped[:lines]
        wrapped[-1] = wrapped[-1][: max(0, width - 1)].rstrip() + "…"
    return "\n".join(wrapped)


def fmt_duration(seconds: float) -> str:
    s = max(0, round(seconds))
    return f"{s // 60}:{s % 60:02d}"


class _Renderer:
    def __init__(self, ctx: JobContext, work: WorkVideo, tmp: Path) -> None:
        self.ctx = ctx
        self.work = work
        self.tmp = tmp
        portrait = work.height > work.width
        self.w, self.h = (720, 1280) if portrait else (1280, 720)
        self.chars = 30 if portrait else 46
        self.size = 30 if portrait else 34
        shutil.copyfile(FONTS / "VeraBd.ttf", tmp / "bold.ttf")
        shutil.copyfile(FONTS / "Vera.ttf", tmp / "regular.ttf")
        self.encode = [
            "-c:v",
            "libx264",
            "-preset",
            ctx.settings.work_preset,
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-ac",
            "2",
        ]

    def _text(self, name: str, text: str) -> str:
        (self.tmp / name).write_text(text, encoding="utf-8", newline="\n")
        return name

    def card(self, name: str, duration: float, lines: list[tuple[str, int, str, float]]) -> Path:
        """lines: (text, fontsize, font file, y as a fraction of height)."""
        draws = []
        for i, (text, size, font, y) in enumerate(lines):
            tf = self._text(f"{name}_{i}.txt", text)
            draws.append(
                f"drawtext=fontfile={font}:textfile={tf}:expansion=none:fontcolor=white:fontsize={size}"
                f":x=(w-text_w)/2:y=h*{y:.3f}:line_spacing=8"
            )
        out = self.tmp / f"{name}.mp4"
        ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                f"color=c={BG}:s={self.w}x{self.h}:r=30:d={duration}",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-filter_complex",
                f"[0:v]{','.join(draws)},format=yuv420p[v]",
                "-map",
                "[v]",
                "-map",
                "1:a",
                "-t",
                f"{duration}",
                *self.encode,
                out.name,
            ],
            cwd=self.tmp,
            cancel=self.ctx.is_cancelled,
        )
        return out

    def segment(self, index: int, start: float, duration: float, caption: str, badge: str) -> Path:
        cap = self._text(f"cap_{index:02d}.txt", _wrap(caption, self.chars))
        tag = self._text(f"tag_{index:02d}.txt", badge)
        box_h = 150
        vf = (
            f"[0:v]scale={self.w}:{self.h}:force_original_aspect_ratio=decrease,"
            f"pad={self.w}:{self.h}:(ow-iw)/2:(oh-ih)/2:color={BG},setsar=1,fps=30,"
            f"drawbox=x=0:y=ih-{box_h}:w=iw:h={box_h}:color=black@0.55:t=fill,"
            f"drawtext=fontfile=regular.ttf:textfile={tag}:expansion=none:fontcolor=white@0.85:fontsize=22"
            f":x=36:y=h-{box_h}+18,"
            f"drawtext=fontfile=bold.ttf:textfile={cap}:expansion=none:fontcolor=white:fontsize={self.size}"
            f":x=36:y=h-{box_h}+52:line_spacing=6,format=yuv420p[v]"
        )
        if self.work.has_audio:
            audio = ["-map", "0:a:0"]
            inputs = [
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(self.ctx.path(self.work.filename)),
            ]
        else:
            audio = ["-map", "1:a"]
            inputs = [
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(self.ctx.path(self.work.filename)),
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
            ]
        out = self.tmp / f"seg_{index:02d}.mp4"
        ffmpeg(
            [
                *inputs,
                "-filter_complex",
                vf,
                "-map",
                "[v]",
                *audio,
                "-t",
                f"{duration:.3f}",
                *self.encode,
                out.name,
            ],
            cwd=self.tmp,
            cancel=self.ctx.is_cancelled,
        )
        return out


def _duration(path: Path) -> float:
    data = ffprobe_json(path)
    return float((data.get("format") or {}).get("duration") or 0.0)


def join_crossfade(
    parts: list[Path], durations: list[float], fade: float, out: Path, ctx: JobContext
) -> None:
    inputs: list[str] = []
    for p in parts:
        inputs += ["-i", p.name]
    vlabel, alabel = "0:v", "0:a"
    graph = []
    offset = 0.0
    for k in range(1, len(parts)):
        offset += durations[k - 1] - fade
        v_out, a_out = f"v{k}", f"a{k}"
        graph.append(
            f"[{vlabel}][{k}:v]xfade=transition=fade:duration={fade}:offset={offset:.3f}[{v_out}]"
        )
        graph.append(f"[{alabel}][{k}:a]acrossfade=d={fade}[{a_out}]")
        vlabel, alabel = v_out, a_out
    ffmpeg(
        [
            *inputs,
            "-filter_complex",
            ";".join(graph),
            "-map",
            f"[{vlabel}]",
            "-map",
            f"[{alabel}]",
            "-c:v",
            "libx264",
            "-preset",
            ctx.settings.work_preset,
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            out.name,
        ],
        cwd=out.parent,
        cancel=ctx.is_cancelled,
    )


def join_hard_cuts(parts: list[Path], out: Path, ctx: JobContext) -> None:
    listing = out.parent / "parts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8", newline="\n")
    ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listing.name,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            out.name,
        ],
        cwd=out.parent,
        cancel=ctx.is_cancelled,
    )


def run(
    ctx: JobContext, work: WorkVideo, steps: list[StepData], summary: SummaryData
) -> HighlightInfo | None:
    if ctx.exists("highlight.json") and ctx.exists("highlights.mp4"):
        return ctx.read_model("highlight.json", HighlightInfo)
    if not steps:
        return None
    s = ctx.settings
    target = min(max(ctx.highlight_seconds, s.highlight_min_s), s.highlight_max_s)
    fade = s.highlight_crossfade_s
    title_s, closing_s = s.highlight_title_s, s.highlight_closing_s
    used_count_guess = len(steps)
    body = target - title_s - closing_s + fade * (used_count_guess + 1)
    budgets = allocate_budgets(
        [st.duration for st in steps], body, s.highlight_step_min_s, s.highlight_step_max_s
    )
    chosen = [(st, b) for st, b in zip(steps, budgets, strict=True) if b > 0]
    if len(chosen) != used_count_guess:  # fewer segments → fewer crossfades to compensate
        body = target - title_s - closing_s + fade * (len(chosen) + 1)
        budgets = allocate_budgets(
            [st.duration for st, _ in chosen], body, s.highlight_step_min_s, s.highlight_step_max_s
        )
        chosen = [(st, b) for (st, _), b in zip(chosen, budgets, strict=True) if b > 0]

    tmp = ctx.path("highlights_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    r = _Renderer(ctx, work, tmp)
    title_lines = [
        (_wrap(summary.task_name, r.chars - 8), r.size + 14, "bold.ttf", 0.36),
        (f"Original {fmt_duration(work.duration)}  ·  {len(steps)} steps", 26, "regular.ttf", 0.56),
        ("REPLAY  ·  action-aware recap", 18, "regular.ttf", 0.86),
    ]
    parts = [r.card("title", title_s, title_lines)]
    durations = [title_s]
    titles = {st.order: t for st, t in zip(steps, summary.titles, strict=False)}
    segments_meta: list[dict[str, float | int | str]] = []
    for i, (st, budget) in enumerate(chosen):
        start, dur = segment_window(st, budget)
        caption = titles.get(st.order, st.verb)
        parts.append(r.segment(i, start, dur, caption, f"STEP {st.order} OF {len(steps)}"))
        durations.append(dur)
        segments_meta.append({"order": st.order, "start": start, "duration": dur, "title": caption})
        ctx.progress(
            0.1 + 0.75 * (i + 1) / len(chosen), f"Rendering highlight {i + 1}/{len(chosen)}"
        )
    closing_lines = [
        ("That's the recap.", r.size + 8, "bold.ttf", 0.40),
        (f"{len(steps)} steps in {fmt_duration(work.duration)}", 26, "regular.ttf", 0.54),
        ("Made with Replay", 18, "regular.ttf", 0.86),
    ]
    parts.append(r.card("closing", closing_s, closing_lines))
    durations.append(closing_s)

    out = tmp / "highlights.mp4"
    ctx.progress(0.9, "Joining highlight reel")
    try:
        join_crossfade(parts, durations, fade, out, ctx)
    except FFmpegError as exc:
        log.warning("Crossfade join failed (%s); using hard cuts", exc)
        join_hard_cuts(parts, out, ctx)
    final = ctx.path("highlights.mp4")
    out.replace(final)
    total = _duration(final)
    thumb_at = min(total - 0.1, title_s + 1.0) if total > title_s + 1.5 else total / 2
    ffmpeg(
        [
            "-ss",
            f"{max(0.0, thumb_at):.3f}",
            "-i",
            str(final),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:-2",
            str(ctx.path("highlights.jpg")),
        ],
        cancel=ctx.is_cancelled,
    )
    shutil.rmtree(tmp, ignore_errors=True)
    info = HighlightInfo(
        filename="highlights.mp4",
        thumbnail="highlights.jpg",
        duration=round(total, 2),
        target=target,
        segments=segments_meta,
    )
    ctx.write_json("highlight.json", info)
    return info
