"""Generate synthetic test videos with ffmpeg.

Each video is a sequence of segments. An *action* segment is a saturated colour
background with a moving shape (so it has motion); an *idle* segment is a still,
dark frame (so it is detected as idle). Every colour change is a hard cut.

The mock vision provider maps the background colour of a window to an action, so
these videos give deterministic, checkable results without any API key.

Usage:
    uv run python -m scripts.make_test_video --out tests/fixtures/videos
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Eight well-separated hues. The mock provider uses the same table (by hue angle).
PALETTE: list[str] = [
    "e53935",  # 0 red
    "fb8c00",  # 1 orange
    "fdd835",  # 2 yellow
    "43a047",  # 3 green
    "00acc1",  # 4 cyan
    "1e88e5",  # 5 blue
    "8e24aa",  # 6 purple
    "d81b60",  # 7 magenta
]
IDLE_COLOR = "2b2b2b"


@dataclass(frozen=True)
class Segment:
    kind: str  # "action" | "idle"
    duration: float
    hue: int | None = None
    label: str = ""


@dataclass
class VideoSpec:
    segments: list[Segment]
    width: int = 640
    height: int = 360
    fps: int = 30
    audio: bool = True
    codec: str = "h264"  # "h264" | "hevc"
    rotation: int = 0  # display rotation metadata in degrees
    vfr: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.segments)


def _ffmpeg() -> str:
    return os.environ.get("FFMPEG_BINARY", "ffmpeg")


def _run(args: list[str], cwd: Path | None = None) -> None:
    cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{res.stderr}")


def _render_segment(seg: Segment, index: int, spec: VideoSpec, out: Path) -> None:
    w, h, fps, d = spec.width, spec.height, spec.fps, seg.duration
    color = (
        PALETTE[seg.hue % len(PALETTE)]
        if seg.kind == "action" and seg.hue is not None
        else IDLE_COLOR
    )
    inputs = ["-f", "lavfi", "-i", f"color=c=0x{color}:s={w}x{h}:r={fps}:d={d}"]
    if seg.kind == "action":
        box = max(24, min(w, h) // 4)
        r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
        shape = "black" if 0.299 * r + 0.587 * g + 0.114 * b > 140 else "white"
        inputs += ["-f", "lavfi", "-i", f"color=c={shape}:s={box}x{box}:r={fps}:d={d}"]
        # Different motion path per segment so windows are not identical.
        fx = 2.0 + (index % 3)
        fy = 1.5 + (index % 2)
        graph = (
            f"[0][1]overlay=x='(W-w)/2+(W/3)*sin(2*PI*t/{fx})'"
            f":y='(H-h)/2+(H/4)*cos(2*PI*t/{fy})':eval=frame,format=yuv420p[v]"
        )
    else:
        graph = "[0]format=yuv420p[v]"
    audio_args: list[str] = []
    if spec.audio:
        freq = 300 + 60 * (seg.hue if seg.hue is not None else 0)
        vol = "0.25" if seg.kind == "action" else "0.02"
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000:duration={d}"]
        a_idx = 2 if seg.kind == "action" else 1
        graph += f";[{a_idx}]volume={vol}[a]"
        audio_args = ["-map", "[a]", "-c:a", "aac", "-b:a", "96k", "-ac", "2"]
    _run(
        [
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[v]",
            *audio_args,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "20",
            "-g",
            str(fps),
            "-t",
            f"{d}",
            str(out),
        ]
    )


def render(spec: VideoSpec, out: Path) -> Path:
    """Render ``spec`` to ``out``. Returns the output path."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="replay-synth-") as tmp_name:
        tmp = Path(tmp_name)
        parts = []
        for i, seg in enumerate(spec.segments):
            part = tmp / f"seg_{i:03d}.mp4"
            _render_segment(seg, i, spec, part)
            parts.append(part)
        listing = tmp / "list.txt"
        listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        joined = tmp / "joined.mp4"
        _run(["-f", "concat", "-safe", "0", "-i", listing.name, "-c", "copy", joined.name], cwd=tmp)

        stage = joined
        if spec.vfr:
            vfr = tmp / "vfr.mp4"
            # Keep every frame in the first third, then 2 of every 3, then 1 of every 2.
            third = spec.duration / 3
            select = (
                f"if(lt(t,{third:.2f}),1,"
                f"if(lt(t,{2 * third:.2f}),not(eq(mod(n,3),0)),eq(mod(n,2),0)))"
            )
            _run(
                [
                    "-i",
                    stage.name,
                    "-vf",
                    f"select='{select}'",
                    "-fps_mode",
                    "vfr",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "copy",
                    vfr.name,
                ],
                cwd=tmp,
            )
            stage = vfr
        if spec.codec == "hevc":
            hevc = tmp / "hevc.mp4"
            _run(
                [
                    "-i",
                    stage.name,
                    "-c:v",
                    "libx265",
                    "-preset",
                    "ultrafast",
                    "-x265-params",
                    "log-level=error",
                    "-tag:v",
                    "hvc1",
                    "-c:a",
                    "copy",
                    hevc.name,
                ],
                cwd=tmp,
            )
            stage = hevc
        if spec.rotation:
            rotated = tmp / "rotated.mp4"
            _run(
                [
                    "-display_rotation:v:0",
                    str(spec.rotation),
                    "-i",
                    stage.name,
                    "-c",
                    "copy",
                    rotated.name,
                ],
                cwd=tmp,
            )
            stage = rotated
        shutil.copyfile(stage, out)
    return out


def ground_truth(spec: VideoSpec, titles: dict[int, str] | None = None) -> list[dict[str, object]]:
    """Ground-truth steps (title, start, end) for the action segments of ``spec``."""
    steps: list[dict[str, object]] = []
    t = 0.0
    for seg in spec.segments:
        if seg.kind == "action":
            title = seg.label or (titles or {}).get(seg.hue or 0, f"Action {seg.hue}")
            steps.append({"title": title, "start": round(t, 3), "end": round(t + seg.duration, 3)})
        t += seg.duration
    return steps


def standard_segments() -> list[Segment]:
    return [
        Segment("action", 6.0, 0),
        Segment("action", 6.0, 1),
        Segment("idle", 4.0),
        Segment("action", 6.0, 2),
        Segment("action", 6.0, 3),
    ]


def generate_test_set(out_dir: Path) -> dict[str, Path]:
    """Create (or reuse) the synthetic fixtures used by the integration tests."""
    out_dir.mkdir(parents=True, exist_ok=True)
    specs: dict[str, VideoSpec] = {
        "standard.mp4": VideoSpec(standard_segments()),
        "portrait.mp4": VideoSpec(standard_segments()[:2], rotation=90),
        "noaudio.mp4": VideoSpec(standard_segments()[:3], audio=False),
        "hevc.mp4": VideoSpec(standard_segments()[:2], codec="hevc"),
        "vfr.mp4": VideoSpec(standard_segments()[:3], vfr=True),
        "short.mp4": VideoSpec([Segment("action", 3.0, 4)]),
    }
    paths: dict[str, Path] = {}
    manifest = out_dir / "manifest.json"
    known = json.loads(manifest.read_text()) if manifest.exists() else {}
    for name, spec in specs.items():
        path = out_dir / name
        key = repr(spec)
        if not path.exists() or known.get(name) != key:
            render(spec, path)
            known[name] = key
        paths[name] = path
    corrupt = out_dir / "corrupt.mp4"
    if not corrupt.exists():
        # Looks like an MP4 by name and leading bytes, but the payload is garbage.
        corrupt.write_bytes(b"\x00\x00\x00\x18ftypmp42" + os.urandom(64 * 1024))
    paths["corrupt.mp4"] = corrupt
    text = out_dir / "notes.mp4"
    if not text.exists():
        text.write_text("This is a text file pretending to be a video.\n" * 50, encoding="utf-8")
    paths["notes.mp4"] = text
    manifest.write_text(json.dumps(known, indent=2))
    return paths


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/videos"))
    args = parser.parse_args()
    paths = generate_test_set(args.out)
    for name, path in paths.items():
        print(f"{name:14s} {path.stat().st_size / 1024:8.1f} KB  {path}")


if __name__ == "__main__":
    main()
