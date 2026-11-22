"""Synthesize the demo video's music bed. Everything is generated here, nothing is sampled.

    cd backend && uv run python ../docs/media/tools/make_music.py OUT.wav [SECONDS]

Soft detuned pads on a slow A minor progression, a quiet pentatonic pluck on the beat with
an echo, and a short synthetic room reverb. Loudness is set later by ffmpeg (-16 LUFS).
"""

from __future__ import annotations

import sys
import wave

import numpy as np
from scipy.signal import fftconvolve

SR = 44100
BPM = 72
BEAT = 60 / BPM
rng = np.random.default_rng(7)


def midi(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


# Am - F - C - G, one chord per four bars of 4/4 at BPM
CHORDS = [(57, 60, 64, 67), (53, 57, 60, 64), (48, 55, 60, 64), (55, 59, 62, 66)]
PENTA = [69, 72, 74, 76, 79, 81]  # A minor pentatonic around A4


def pad(freq: float, dur: float) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    for detune in (-0.35, 0.0, 0.4):
        for k, amp in ((1, 1.0), (2, 0.35), (3, 0.15), (4, 0.06)):
            out += amp * np.sin(2 * np.pi * (freq * k + detune * k) * t + rng.uniform(0, 6.28))
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.11 * t + rng.uniform(0, 6.28))
    return out * lfo / 6


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    env[:a] = np.linspace(0, 1, a) ** 2
    env[-r:] = np.minimum(env[-r:], np.linspace(1, 0, r) ** 2)
    return env


def pluck(freq: float, dur: float = 1.6) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-6 * t)
    return tone * np.exp(-3.2 * t) * np.minimum(1, t * 400)


def render(seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    mix = np.zeros((2, n))
    chord_len = 4 * 4 * BEAT
    i = 0
    start = 0.0
    while start < seconds:
        chord = CHORDS[i % len(CHORDS)]
        dur = chord_len + 3.0  # overlap for smooth changes
        for j, note in enumerate(chord):
            sig = pad(midi(note), dur) * envelope(int(dur * SR), 2.5, 3.0)
            pos = int(start * SR)
            seg = sig[: max(0, n - pos)]
            pan = 0.35 + 0.1 * j
            mix[0, pos : pos + len(seg)] += seg * (1 - pan)
            mix[1, pos : pos + len(seg)] += seg * pan
        # bass root, an octave down
        bass = pad(midi(chord[0] - 12), dur) * envelope(int(dur * SR), 2.5, 3.0) * 1.2
        pos = int(start * SR)
        seg = bass[: max(0, n - pos)]
        mix[:, pos : pos + len(seg)] += seg * 0.7
        start += chord_len
        i += 1
    # light pulse: a pentatonic pluck every other beat, with a dotted-eighth echo
    rnd = np.random.default_rng(11)
    beat_t = 8.0
    while beat_t < seconds - 4:
        note = PENTA[int(rnd.integers(0, len(PENTA)))]
        sig = pluck(midi(note)) * 0.18
        for k, gain in enumerate((1.0, 0.45, 0.2)):
            pos = int((beat_t + k * BEAT * 0.75) * SR)
            seg = sig[: max(0, n - pos)]
            side = 0.3 if k % 2 == 0 else 0.7
            mix[0, pos : pos + len(seg)] += seg * gain * (1 - side)
            mix[1, pos : pos + len(seg)] += seg * gain * side
        beat_t += 2 * BEAT * (2 if rnd.random() < 0.35 else 1)
    # room: exponentially decaying noise, low-passed by averaging
    ir_len = int(1.8 * SR)
    ir = rng.normal(size=ir_len) * np.exp(-np.arange(ir_len) / (0.45 * SR))
    ir = np.convolve(ir, np.ones(24) / 24, mode="same")
    wet = np.stack([fftconvolve(mix[c], ir)[:n] for c in range(2)])
    wet /= np.max(np.abs(wet)) + 1e-9
    out = mix / (np.max(np.abs(mix)) + 1e-9) * 0.8 + wet * 0.22
    fade_in, fade_out = int(2.0 * SR), int(5.0 * SR)
    out[:, :fade_in] *= np.linspace(0, 1, fade_in)
    out[:, -fade_out:] *= np.linspace(1, 0, fade_out)
    return out / np.max(np.abs(out)) * 0.9


def main() -> None:
    path = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 170.0
    audio = render(seconds)
    pcm = (audio.T * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", path, f"{seconds:.0f}s")


if __name__ == "__main__":
    main()
