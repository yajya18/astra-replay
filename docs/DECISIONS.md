# Decisions

Choices made during the build that the spec left open or that deviate from it, and why.

## Platform and tooling

| Decision | Why |
|---|---|
| Python 3.12 managed by **uv**; `backend/` is a non-packaged uv project | Fast, reproducible installs (`uv.lock`); 3.12 has wheels for every dependency (torch, ctranslate2, opencv). |
| Linux/Docker installs **CPU-only torch** from the PyTorch CPU index (`[tool.uv.sources]`) | The default PyPI torch on Linux pulls ~2 GB of CUDA libraries; the embedding model only needs CPU. |
| **ReportLab** for PDF (not WeasyPrint) | Pure Python; WeasyPrint needs GTK/Pango system libraries, which are painful on Windows. |
| **Bitstream Vera** fonts bundled in `backend/app/assets/fonts` (and `frontend/public/fonts`) | Permissive licence (included); used for burned-in captions (ffmpeg `drawtext`), the PDF, and 3D text, so nothing depends on system fonts or a CDN. |
| SSE implemented with a plain `StreamingResponse` that polls in-memory job state every 0.4 s | No extra dependency; works across worker threads without cross-thread asyncio plumbing. The frontend falls back to polling after repeated stream errors. |
| Streaming multipart parser built on `python-multipart`'s low-level `MultipartParser` | Starlette's form parser spools the whole upload to a temp file first; ours writes the video part straight to `data/jobs/<id>/input.<ext>` and enforces the size limit while bytes arrive. |
| Uploads are **probed and validated synchronously** at upload time | Corrupt, non-video, too-long and too-short files are rejected immediately with a clear 4xx message instead of failing later in the job. |
| Media served by a FastAPI route using Starlette `FileResponse` | `FileResponse` supports HTTP Range (206) for seeking; the route also restricts paths to `data/jobs/<uuid>/` and hides internal files (`audio.wav`, `probe.json`, ...). |
| Frontend talks to the API directly (CORS), not through Next.js rewrites | Large uploads and SSE through a dev proxy are unreliable; the API URL defaults to *same host, port 8000*, so phones on the LAN work without configuration. Private-network origins are allowed by a CORS regex. |
| Next.js 16 with **Cache Components** (the scaffold default) | Dynamic routes read `params` inside `<Suspense>` as the docs require; pages are partially prerendered. |
| No shadcn CLI; hand-built equivalents in `components/ui.tsx` | Avoids an interactive generator; the primitives are small and fully accessible (native `<dialog>`, real buttons, focus styles). |
| `docker compose` could not be run on the build machine (Docker isn't installed there) | The Dockerfiles and compose file follow standard patterns; see "Known limitations" in the README. |

## Pipeline

| Decision | Why |
|---|---|
| **Transcription runs before understanding** (stage order: ingest, motion, transcribe, understand, ...) | The spec uses the transcript as a hint for understanding, so it has to exist first. Progress weights are unchanged. |
| Speech model loading is **non-blocking**: if the Whisper model isn't cached yet, it downloads in the background and that job skips speech hints | On a slow connection the 480 MB `small` model blocked the first job for many minutes. Speech is only a hint, so a job never waits for it. The server also warms both local models at startup, and `make setup` pre-downloads them (`scripts/download_models.py`). |
| Embeddings: `all-MiniLM-L6-v2` by default, with a deterministic **hashing fallback** if the model can't be loaded | Keeps the app working offline. `/api/health` reports which one is active. Tests use the hash embedder for speed. |
| Idle threshold = `min(P25, 0.5 × median)` of the smoothed motion curve, with a small absolute floor | A pure percentile would always mark a quarter of a busy video as idle; capping at half the median keeps slow but real actions (careful slicing). |
| Frame sampling decodes the video **once** at 10 fps and keeps the sharpest frame (Laplacian variance) within ±0.2 s of each target time | One ffmpeg pass instead of hundreds of seeks. |
| The window cache key also includes the vocabulary hints and transcript snippet (not only frames + prompt version + model) | These change the prompt, so they must change the key or the cache could return answers to a different prompt. |
| Provider SDK retries are disabled (`max_retries=0`); the pipeline does exponential backoff with jitter | One retry policy, cancellable, configured in one place. |
| `FatalProviderError` (missing key, bad model, auth failure) stops the job with a clear message; other errors fall back per window | Retrying 200 windows against a wrong API key wastes time and hides the real problem. |
| Strict structured output on every provider (`json_schema` / `response_json_schema` / `output_config.format` / Ollama `format`), plus our own Pydantic validation and one repair attempt | Belt and braces: the schema constrains the model, Pydantic guarantees the types, the repair prompt handles the rare miss, and a failed window becomes `unknown` with confidence 0. |
| The mock provider maps the **dominant colour** of a window to an action (synthetic videos) and otherwise uses window position and motion | Deterministic, offline results that are *checkable*: the synthetic demos have known ground truth, so tests and the evaluation script measure the real segmentation/alignment code. With a reference procedure, mock actions come from its steps, so the procedure check is meaningful in mock mode. |
| Boundary refinement moves only **shared** boundaries between contiguous steps; a boundary within 1 s of a hard cut snaps to the cut | Edges next to idle gaps have nothing to refine against; cuts are the most reliable boundaries. |
| Alignment rejects matches with similarity < 0.2 outright and sends 0.2–0.45 to the LLM verifier | The Hungarian algorithm always assigns something; the floor avoids paying an LLM call to reject obviously unrelated pairs. |
| Summary validation: exact step count, no empty/overlong titles, and a token-overlap check that catches reordered titles. Invalid phases fall back independently of titles | The spec asks to detect dropped, invented and reordered steps. Keeping valid LLM titles when only the phases are wrong preserves quality. |
| Highlight budgets: √duration-proportional, clamped to [2, 6] s; if the clamped total is below target, the cap is relaxed towards each step's full length; if minimums don't fit, the shortest steps are left out | Meets the ±10 % length target whenever there is enough material. A video shorter than the target produces a shorter reel (it can't invent footage). |
| Highlight output is 1280×720, or 720×1280 for portrait sources | "720p" for both orientations, without letterboxing a phone video into landscape. |
| Crossfades with `xfade`/`acrossfade`, falling back to concat-demuxer hard cuts if the filter graph fails | As the spec allows. |
| Text files are always written with LF line endings | Deterministic SRT/VTT/Markdown on Windows too. |

## Product

| Decision | Why |
|---|---|
| Demo jobs are seeded automatically on server start (and by `make demo`) from `demo/*/`; if a folder has no recording yet, a synthetic placeholder is rendered from its `meta.json` | The gallery works on a fresh clone and in Docker with no manual step. Dropping a real video in the folder replaces the placeholder on the next start. |
| Demo jobs are excluded from the 24 h retention cleanup | As specified. |
| Default models live in `config.py`/`.env.example`; I used aliases where they exist (`gemini-flash-latest`) | Model names go stale fast. The README explains where to change them. |
| Anthropic provider defaults to `claude-opus-5-5` at **effort `low`**, with the server-side refusal fallback enabled | Per-window description is a short perception task; effort, not a smaller model, is the cost lever. Switch with `ANTHROPIC_VLM_MODEL` / `ANTHROPIC_EFFORT`. |
| The XR preview was built (not cut): `/xr` and an embedded preview on `/about` | It was stable and quick with React Three Fiber + `@react-three/xr`. It shows the real step timeline of a result (or a clearly labelled sample when none exists). |
