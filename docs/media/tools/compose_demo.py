"""Assemble docs/media/replay-demo.mp4 from a screen recording, title and text cards, and music.

    python docs/media/tools/compose_demo.py REC_DIR MUSIC.wav OUT.mp4

REC_DIR holds raw.mp4 (the recording as constant-frame-rate video) and rel.json (seconds at
which each beat starts), both written by frontend/scripts/record-demo.mjs plus
docs/media/tools/frames_to_video.py. Needs ffmpeg and the Bitstream Vera fonts that ship in
backend/app/assets/fonts. No voiceover; captions are burned in.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FONTS = ROOT / "backend" / "app" / "assets" / "fonts"
BOLD, REG = FONTS / "VeraBd.ttf", FONTS / "Vera.ttf"
W, H, FPS = 1920, 1080, 30
FADE = 0.5
SLOW = 1.35  # play UI footage a little slower so captions can be read

BG = "0x0a0e1a"
CYAN = "0x00b4d8"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def esc(path: Path) -> str:
    return str(path).replace(":", r"\:")


class Composer:
    def __init__(self, rec: Path, tmp: Path) -> None:
        self.rec = rec
        self.tmp = tmp
        self.parts: list[tuple[Path, float]] = []
        self.n = 0

    def textfile(self, text: str) -> Path:
        self.n += 1
        p = self.tmp / f"t{self.n}.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def drawtext(self, text: str, size: int, y: str, bold: bool = False, color: str = "white",
                 alpha: str = "1", x: str = "(w-text_w)/2") -> str:
        f = esc(BOLD if bold else REG)
        return (
            f"drawtext=fontfile='{f}':textfile='{esc(self.textfile(text))}':fontsize={size}:"
            f"fontcolor={color}:x={x}:y={y}:alpha='{alpha}'"
        )

    def footage(self, start: float, end: float, caption: str, speed: float | None = None,
                zoom: tuple[float, float, float] | None = None, hold: float = 0.0) -> None:
        """Cut [start, end] of the recording. speed multiplies playback rate (4 = 4x faster)."""
        pts = (1 / speed) if speed else SLOW
        dur = (end - start) * pts + hold
        i = len(self.parts)
        out = self.tmp / f"seg{i}.mp4"
        chain = [f"setpts={pts}*PTS", f"fps={FPS}"]
        chain.append(f"scale={W}:{H}:flags=lanczos")
        if hold:
            chain.append(f"tpad=stop_mode=clone:stop_duration={hold}")
        if zoom:
            z, fx, fy = zoom  # final zoom factor and focus point (0..1)
            chain.append(
                f"scale=w='trunc({W}*(1+{z - 1}*min(t/{dur},1))/2)*2':h=-2:eval=frame:flags=bicubic,"
                f"crop={W}:{H}:x='(iw-{W})*{fx}':y='(ih-{H})*{fy}'"
            )
        a = f"min(1,min(t/0.5,({dur}-t)/0.5))"
        chain.append(f"drawbox=x=0:y=ih-132:w=iw:h=132:color=black@0.72:t=fill")
        chain.append(self.drawtext(caption, 42, "h-132+44", bold=True, alpha=a))
        chain.append("format=yuv420p")
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(end - start),
             "-i", str(self.rec / "raw.mp4"), "-vf", ",".join(chain), "-r", str(FPS),
             "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", "-an", str(out)])
        self.parts.append((out, dur))

    def card(self, dur: float, lines: list[tuple[str, int, bool, str]], y0: int = 330,
             gap: int = 30) -> None:
        i = len(self.parts)
        out = self.tmp / f"seg{i}.mp4"
        vf = [f"drawbox=x=(iw-360)/2:y={y0 - 50}:w=360:h=6:color={CYAN}:t=fill"]
        y = y0
        for text, size, bold, color in lines:
            for ln in text.split("\n"):
                vf.append(self.drawtext(ln, size, str(y), bold=bold, color=color,
                                        alpha=f"min(1,min(t/0.6,({dur}-t)/0.5))"))
                y += int(size * 1.35)
            y += gap
        vf.append("format=yuv420p")
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             f"color=c={BG}:s={W}x{H}:r={FPS}:d={dur}", "-vf", ",".join(vf),
             "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", str(out)])
        self.parts.append((out, dur))

    def join(self, music: Path, out: Path) -> None:
        inputs: list[str] = []
        for p, _ in self.parts:
            inputs += ["-i", str(p)]
        graph, label, t = [], "[0:v]", self.parts[0][1]
        for i in range(1, len(self.parts)):
            offset = t - FADE
            nxt = f"[v{i}]"
            graph.append(f"{label}[{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.3f}{nxt}")
            label = nxt
            t = offset + self.parts[i][1]
        total = t
        n = len(self.parts)
        graph.append(
            f"[{n}:a]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,"
            f"loudnorm=I=-16:TP=-1.5:LRA=7,afade=t=in:d=2,afade=t=out:st={total - 4:.2f}:d=4[a]"
        )
        run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-i", str(music),
             "-filter_complex", ";".join(graph), "-map", label, "-map", "[a]",
             "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "24",
             "-preset", "slow", "-r", str(FPS), "-maxrate", "1600k", "-bufsize", "3200k",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)])
        print(f"wrote {out}  {total:.1f}s")


def main() -> None:
    rec, music, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    m = json.loads((rec / "rel.json").read_text())
    team = json.loads((ROOT / "docs" / "presentation" / "team.json").read_text())
    with tempfile.TemporaryDirectory() as td:
        c = Composer(rec, Path(td))
        c.card(6, [("Replay", 120, True, "white"),
                   ("Action-aware video summarization", 44, False, "0xa9b4cc"),
                   (f"Team {team['team_name']}  |  {team['college']}\nSamsung PRISM XR Hackathon, track {team['track_no']}",
                    28, False, "0x7d89a6")], y0=330, gap=26)
        c.card(9, [("The problem", 64, True, CYAN),
                   ("A phone, helmet or glasses camera records a whole task.\n"
                    "Most of it is reaching, waiting and repeating.\n"
                    "Scene cuts and transcripts do not tell you what you did.", 38, False, "white")],
               y0=300, gap=40)
        c.footage(m["landing"], m["upload"], "Replay turns a long first-person video into the actions you did")
        c.footage(m["upload"], m["processing"], "Upload the video and, optionally, the recipe you meant to follow")
        c.footage(m["processing"], m["results"], "Live progress while it works (sped up 4x)", speed=4)
        c.card(9, [("How it works", 64, True, CYAN),
                   ("1  Idle time is removed using the video's own motion curve\n"
                    "2  A vision-language model labels each window: verb, object, tool\n"
                    "3  Windows merge into steps, with clips, keyframes and a reel\n"
                    "4  Your recipe is aligned to the steps: done, missed, out of order", 34, False, "white")],
               y0=250, gap=40)
        c.footage(m["results"], m["clip"], "Steps with times, keyframes and a chapter timeline. Click one to jump.",
                  zoom=(1.12, 0.85, 0.35))
        c.footage(m["clip"], m["search"], "Every step has its own clip", zoom=(1.1, 0.5, 0.4))
        c.footage(m["search"], m["procedure"], "Ask in plain language, get an answer with a timestamp",
                  zoom=(1.12, 0.1, 0.5))
        c.footage(m["procedure"], m["reel"], "A skipped step is flagged: 'Chop the chives with a knife'",
                  zoom=(1.12, 0.5, 0.45), hold=3)
        c.footage(m["reel"], m["hood"], "A captioned highlight reel, plus PDF, JSON, SRT and WebVTT exports")
        c.footage(m["hood"], m["xr"], "Under the hood: raw window actions, stage timings, providers")
        c.footage(m["xr"], m["end"], "XR preview: step cards in 3D, WebXR on supported headsets")
        c.card(9, [("Measured on the demos", 56, True, CYAN),
                   ("3 demo videos, 18 labelled steps\n"
                    "Recall 1.00, precision 1.00, skipped and swapped steps found 3 of 3", 36, False, "white"),
                   ("Synthetic footage and a mock provider: this checks the pipeline,\nnot model accuracy on real recordings.",
                    28, False, "0xffb74d")], y0=300, gap=44)
        c.card(8, [("Replay", 100, True, "white"),
                   (team["repo_url"].replace("https://", ""), 40, False, CYAN),
                   (f"Team {team['team_name']}  |  {', '.join(team['members'])}", 28, False, "0xa9b4cc"),
                   ("Demo footage is synthetic, processed in mock mode.", 26, False, "0x7d89a6")],
               y0=340, gap=30)
        c.join(music, out)


if __name__ == "__main__":
    main()
