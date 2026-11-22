"""Thin, cancellable wrappers around the ffmpeg / ffprobe binaries."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.errors import JobCancelledError

log = logging.getLogger("replay.ffmpeg")

CancelCheck = Callable[[], bool]

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FFmpegError(RuntimeError):
    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


@lru_cache
def binary_available(name: str) -> bool:
    return shutil.which(name) is not None


def ffmpeg_available() -> bool:
    s = get_settings()
    return binary_available(s.ffmpeg_binary) and binary_available(s.ffprobe_binary)


def run_process(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    cancel: CancelCheck | None = None,
    timeout: float | None = None,
    capture_stdout: bool = True,
) -> tuple[bytes, str]:
    """Run a subprocess, polling ``cancel`` so long encodes can be interrupted."""
    proc = subprocess.Popen(
        list(args),
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW,
    )
    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []

    def _drain(stream: Any, sink: list[bytes]) -> None:
        for chunk in iter(lambda: stream.read(65536), b""):
            sink.append(chunk)

    threads = []
    if capture_stdout and proc.stdout is not None:
        threads.append(threading.Thread(target=_drain, args=(proc.stdout, out_chunks), daemon=True))
    if proc.stderr is not None:
        threads.append(threading.Thread(target=_drain, args=(proc.stderr, err_chunks), daemon=True))
    for t in threads:
        t.start()
    started = time.monotonic()
    try:
        while True:
            try:
                proc.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel():
                    proc.kill()
                    proc.wait()
                    raise JobCancelledError() from None
                if timeout is not None and time.monotonic() - started > timeout:
                    proc.kill()
                    proc.wait()
                    raise FFmpegError(f"{Path(args[0]).name} timed out") from None
    finally:
        for t in threads:
            t.join(timeout=5)
    stderr = b"".join(err_chunks).decode("utf-8", errors="replace")
    if proc.returncode != 0:
        tail = "\n".join(stderr.strip().splitlines()[-8:])
        raise FFmpegError(f"{Path(args[0]).name} exited with code {proc.returncode}", tail)
    return b"".join(out_chunks), stderr


def ffmpeg(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    cancel: CancelCheck | None = None,
    timeout: float | None = None,
) -> str:
    s = get_settings()
    cmd = [s.ffmpeg_binary, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
    log.debug("ffmpeg %s", " ".join(args))
    _, err = run_process(cmd, cwd=cwd, cancel=cancel, timeout=timeout, capture_stdout=False)
    return err


def ffprobe_json(path: Path) -> dict[str, Any]:
    s = get_settings()
    cmd = [
        s.ffprobe_binary,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    out, _ = run_process(cmd, timeout=60)
    data: dict[str, Any] = json.loads(out.decode("utf-8", errors="replace") or "{}")
    return data


def iter_raw_frames(
    path: Path,
    *,
    fps: float,
    width: int,
    height: int,
    pix_fmt: str,
    start: float | None = None,
    duration: float | None = None,
    cancel: CancelCheck | None = None,
) -> Any:
    """Yield raw frames (bytes) decoded by ffmpeg at a fixed rate and size."""
    s = get_settings()
    channels = {"gray": 1, "bgr24": 3, "rgb24": 3}[pix_fmt]
    frame_size = width * height * channels
    cmd = [s.ffmpeg_binary, "-hide_banner", "-nostdin", "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += [
        "-an",
        "-vf",
        f"fps={fps},scale={width}:{height}:flags=area,format={pix_fmt}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        pix_fmt,
        "pipe:1",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW,
        bufsize=frame_size * 4,
    )
    assert proc.stdout is not None
    try:
        while True:
            if cancel is not None and cancel():
                raise JobCancelledError()
            buf = proc.stdout.read(frame_size)
            if len(buf) < frame_size:
                break
            yield buf
    finally:
        proc.kill()
        proc.wait()
