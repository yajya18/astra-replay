# Replay — Build Plan

Action-aware video summarization for first-person "how I did it" videos.
This file is the running plan. Items are ticked as each one is finished and verified.

## Milestones and task list

### M1 — Scaffold
- [x] Repo layout, `.gitignore`, `.env.example`, LICENSE
- [x] Backend: `pyproject.toml` (uv), ruff, mypy (strict on `app/pipeline`, `app/providers`), pytest
- [x] Backend: `config.py` (pydantic-settings), `main.py` (CORS, error shape, routers), `/api/health`
- [x] Frontend: Next.js App Router + TS + Tailwind, theme (dark/light), layout shell, ESLint + Prettier, Vitest
- [x] Dockerfiles, `docker-compose.yml`, `Makefile`
- [x] `make lint test` green, commit

### M2 — Ingest, motion, worker, synthetic videos
- [x] `scripts/make_test_video.py` (colored segments, moving shapes, idle stills, hard cut, portrait-rotated, no-audio, HEVC, VFR)
- [x] DB models (Job, Video, Step, ReferenceStep, Export), SQLite via SQLModel
- [x] Streaming multipart upload → disk with size limit, UUID paths, per-IP rate limit
- [x] Worker: thread pool, persisted job state, progress events, cancellation, restart recovery, retry from failed stage
- [x] SSE progress endpoint
- [x] Ingest: ffprobe validation, limits, rotation/HEVC/VFR → H.264 720p CFR 30 fps + mono 16 kHz WAV
- [x] Motion curve, adaptive idle spans, PySceneDetect cuts
- [x] Integration tests on synthetic videos, commit

### M3 — Understanding with providers
- [x] `providers/base.py` interfaces, provider registry from `VLM_PROVIDER` / `LLM_PROVIDER`
- [x] `mock` provider (deterministic, offline)
- [x] `gemini`, `openai`, `anthropic`, `ollama` providers (current SDK APIs, models in config)
- [x] Adaptive windowing, sharp-frame sampling, 4/8 frames per window
- [x] Concurrency limit, per-call timeout, exponential backoff, strict JSON + repair retry + fallback
- [x] Window cache keyed by hash(frames + prompt version + model)
- [x] Verb normalization + synonym map, tests, commit

### M4 — Segmentation, summarization, alignment
- [x] `segment.py` pure functions + unit tests (merge rules, cuts, idle, short-step absorption, boundary refinement)
- [x] `summarize.py` with validation and deterministic fallback + tests
- [x] `align.py` Hungarian + one-to-many + LLM verification + LIS ordering + verdict, tests (all done / one missed / swapped / extra / empty)
- [x] Optional faster-whisper transcription, commit

### M5 — Media, search, exports
- [x] Keyframes (sharpness × motion-peak closeness, WebP + JPEG, 480 px)
- [x] Per-step clips (accurate cuts, H.264, faststart)
- [x] Highlight reel (√duration budgets, captions, title/closing cards, crossfades with hard-cut fallback, thumbnail)
- [x] Hybrid search (embeddings + BM25) + LLM/mock answer
- [x] Exports: result.json, report.md, report.pdf, chapters.srt, chapters.vtt
- [x] Range-enabled media serving; ffprobe checks of every output in tests, commit

### M6 — Frontend
- [x] API client + types mirrored from backend schemas, TanStack Query
- [x] `/` landing + upload (client validation, preview, progress)
- [x] `/jobs/[id]` live progress (SSE with polling fallback), cancel, retry
- [x] `/results/[id]` player + chapter timeline, step cards, scroll sync, clip modal, search, procedure panel, highlight reel, exports, under-the-hood
- [x] `/demo`, `/about`
- [x] Component tests (Vitest + RTL), Playwright e2e (upload → results in mock mode), commit

### M7 — Demo, evaluation, docs
- [x] `demo/` folders with reference + ground truth, synthetic placeholders, `precompute_demo.py`, `make demo`
- [x] `scripts/evaluate.py` + `docs/EVALUATION.md`
- [x] README, ARCHITECTURE, DEMO_SCRIPT, DECISIONS, commit

### M8 — XR preview
- [x] React Three Fiber step-card scene on `/xr` and `/about`, WebXR enter via `@react-three/xr`, commit

### M9 — Hardening
- [ ] Acceptance checklist pass (Section 10 of the spec), final commit
  - [ ] 1 full test and lint run
  - [ ] 2 Playwright e2e
  - [ ] 3 demo precompute and evaluation table
  - [ ] 4 browser review at desktop and 375 px, Lighthouse
  - [ ] 5 README screenshots, team section
  - [ ] 6 acceptance checks
  - [ ] 7 copy polish
  - [ ] Submission deck (docs/presentation)
  - [ ] Demo video (docs/media)

#### Acceptance checklist status (local run, re-verified in the final pass)

| Item | Status |
|---|---|
| `docker compose up` on a clean machine | **Not verified**: Docker isn't installed on the build machine. Compose and Dockerfiles are written and statically checked. `make dev` works locally. |
| Full flow with no API keys (mock mode) | ✅ Playwright e2e: upload → live progress → results with steps, seek, search |
| Real key, 2–3 min phone video | **Needs the user**: no API key or real recording was available. Providers are request-shape tested offline. |
| Portrait, HEVC, VFR, no-audio work; too-long, too-big, corrupt, non-video rejected clearly | ✅ integration tests on synthetic videos |
| Range seeking; chapter markers; active-step sync | ✅ 206 tests; checked in the browser |
| Search by exact word and meaning; answer cites a timestamp | ✅ tests + browser |
| Missed / out-of-order detection on fixtures and the skipped-step demo | ✅ unit tests; demos: "6 of 7 … skipped 'Chop the chives'", out-of-order shelf |
| Highlight reel plays, captions + title cards, within ±10 % of target | ✅ ffprobe test (25 s target) |
| Exports download and open (PDF keyframes, valid SRT/VTT) | ✅ tests |
| Cancel and retry; restart leaves no stuck jobs | ✅ tests; checked in the browser (interrupted → Retry resumes at the failed stage) |
| ruff, mypy, eslint, tsc, pytest, vitest, Playwright | ✅ all pass |
| Lighthouse a11y ≥ 90 on landing and results; 375 px layout | ✅ 100 / 100 (desktop and mobile); no horizontal scroll at 375 px |
| No TODOs, placeholders, dead links, secrets; `.env.example` complete | ✅ scanned; a test enforces `.env.example` completeness |
| README quickstart from a fresh clone | ✅ local path (see final report); Docker path not verified |

## File tree

```
replay/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app, CORS, error handlers, routers, /media
│   │   ├── config.py          Settings (all tunables)
│   │   ├── db.py, models.py   SQLModel engine + tables
│   │   ├── schemas.py         Pydantic API + result schemas (versioned)
│   │   ├── errors.py          ApiError + consistent error shape
│   │   ├── api/               health, jobs (upload/status/events/cancel/retry/delete),
│   │   │                      results, search, exports, demo, media
│   │   ├── worker.py          thread-pool job queue, progress, cancellation, recovery, cleanup
│   │   ├── media_tools.py     ffmpeg/ffprobe wrappers (cancellable subprocesses)
│   │   ├── embeddings.py      sentence-transformers embedder with hashing fallback
│   │   ├── pipeline/          ingest, motion, windows, understand, transcribe, segment,
│   │   │                      summarize, align, keyframes, clips, highlights,
│   │   │                      search_index, exports, run, context, textnorm
│   │   ├── providers/         base, mock, gemini, openai, anthropic, ollama, registry
│   │   ├── prompts/           window_action.v1.md, summarize.v1.md, verify_match.v1.md, ...
│   │   └── assets/fonts/      bundled caption font (Bitstream Vera, permissive licence)
│   ├── tests/
│   ├── scripts/               make_test_video.py, evaluate.py, precompute_demo.py
│   ├── pyproject.toml, Dockerfile
├── frontend/
│   ├── app/                   /, /jobs/[id], /results/[id], /demo, /about, /xr
│   ├── components/            ui primitives + feature components
│   ├── lib/                   api client, types, formatting, hooks
│   ├── tests/  e2e/
│   └── Dockerfile
├── demo/                      <slug>/{video.*, reference.txt, ground_truth.json, meta.json}
├── docs/                      PLAN, DECISIONS, ARCHITECTURE, DEMO_SCRIPT, EVALUATION
└── docker-compose.yml, Makefile, .env.example, README.md, LICENSE
```

## Key interfaces

```python
# providers/base.py
class WindowAction(BaseModel):
    is_idle: bool; verb: str; object: str; tool: str; hands: str
    description: str; confidence: float  # 0..1

class WindowContext(BaseModel):
    window_index: int; start: float; end: float; motion_level: float
    frame_times: list[float]; transcript: str | None
    vocabulary: list[str]          # reference steps as hints

class VisionLanguageProvider(Protocol):
    name: str; model: str
    def describe_window(self, frames: list[bytes], context: WindowContext) -> WindowAction: ...

class TextLLMProvider(Protocol):
    name: str; model: str
    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict[str, Any]: ...
```

```python
# pipeline/run.py
STAGES = [ingest, motion, understand, transcribe, segment, summarize, align, media, exports]
WEIGHTS = {ingest: .10, motion: .10, understand: .45, transcribe: .05, segment: .05,
           summarize: .05, align: .05, media: .10, exports: .05}
def run_job(ctx: JobContext, start_from: str | None = None) -> None
```

```
REST
GET  /api/health
POST /api/jobs                     multipart: video, reference_steps?, highlight_seconds?, title?
GET  /api/jobs/{id}                status, stage, progress, error, info
GET  /api/jobs/{id}/events         SSE
POST /api/jobs/{id}/cancel | /retry
GET  /api/jobs/{id}/result
GET  /api/jobs/{id}/search?q=&answer=
GET  /api/jobs/{id}/exports/{kind} json|md|pdf|srt|vtt|mp4
GET  /media/jobs/{id}/...          Range-enabled static media
GET  /api/demo
DELETE /api/jobs/{id}
```
