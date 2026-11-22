# 3-minute judge demo

**Before you start:** `make dev` (or `docker compose up`) is running; the demos have been
precomputed (`make demo`); open <http://localhost:3000> in one tab and a demo result in
another. Phone ready with a short recording if you want to show a live upload from mobile.

| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | Landing page | "When you film yourself cooking, assembling or repairing something, you get 10 minutes of footage that's mostly reaching and waiting. Nobody re-watches it. **Replay turns it into the actions you did** — verb, object, tool — so you can search it, check it against the recipe, and share a one-minute recap." |
| 0:20–0:45 | Drop a video in the upload card, click **Use example recipe**, set highlight to 60 s, upload | "It runs on any phone video: portrait, HEVC, variable frame rate. The recipe is optional; with it, Replay checks your procedure." |
| 0:45–1:10 | Processing page: stage checklist, live details | "Live progress over server-sent events. First we remove idle time using the video's own motion curve. Then 4-second windows, each described by a vision-language model as strict JSON: verb, object, tool. Here are the first actions it found." (If it takes long, say "this is the same pipeline we ran on the demos" and switch to the precomputed tab.) |
| 1:10–1:40 | Results header and player | "Task name, summary, and the stats: original length, recap length, compression, idle time removed. The coloured timeline is the chapters, grouped into phases. Click a step and the video jumps there; the list follows the video as it plays." |
| 1:40–2:00 | Search: type "when did I add the butter?" | "Search works by meaning and by exact words, and answers in one sentence with a timestamp. Click it to jump." |
| 2:00–2:20 | Open the **Omelette with a skipped step** demo → Procedure check | "Here I skipped chopping the chives. Replay aligns detected steps to the recipe with the Hungarian algorithm and a longest-increasing-subsequence order check: *6 of 7 steps completed, you skipped 'Chop the chives'.* The shelf demo shows an out-of-order step." |
| 2:20–2:35 | Highlight reel, Export menu | "A captioned highlight reel with title cards, plus exports: PDF report with keyframes, Markdown, JSON, SRT and WebVTT chapters." |
| 2:35–2:50 | **Under the hood** panel | "This is the proof it's action-aware: the raw window-level actions, motion curve with idle spans, stage timings and providers. Providers are swappable: Gemini, OpenAI, Claude, or a local model through Ollama." |
| 2:50–3:00 | **View in XR** | "And the XR path: the same step cards float around you in WebXR. On Galaxy XR or smart glasses the input video is already first-person, and with the local Ollama provider it can run privately on device." |

## Backup plan (network down or a provider fails)

1. Set `VLM_PROVIDER=mock` and `LLM_PROVIDER=mock` (the default) and restart; everything works offline. The UI shows a **Mock mode** badge; say so.
2. Use the precomputed demos at `/demo`; they open instantly and need no network.
3. If the Wi-Fi blocks the phone, upload from the laptop instead.
4. If a live upload is slow, open the matching precomputed demo; it's the same pipeline output.
5. Keep `docs/evaluation_results.md` open as a static fallback for numbers.
