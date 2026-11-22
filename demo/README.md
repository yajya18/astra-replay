# Demo videos

Each folder here becomes a precomputed demo in the app's gallery (`/demo`).

```
demo/<slug>/
  video.mp4           your recording (any of .mp4 .mov .m4v .webm .mkv; any file name)
  reference.txt       the procedure you meant to follow, one step per line (optional)
  ground_truth.json   hand-labelled steps for `make eval` (optional)
  meta.json           title, highlight length, and the synthetic placeholder spec
```

Until you add a real recording, the server renders a **synthetic placeholder**
(`placeholder.mp4`, coloured segments with moving shapes) from the `synthetic` list in
`meta.json`, so the gallery works on a fresh clone. The mock provider maps each colour to the
matching reference step, which makes the placeholders checkable end to end.

## Adding your own recordings

1. Record first-person (phone on your chest or head, or held at eye level), 2–5 minutes, with your hands and the work surface in view. Good light helps.
2. Put the file in the demo folder (e.g. `demo/omelette/video.mp4`). Real recordings take priority over the placeholder.
3. Edit `reference.txt` if your procedure differs. For the *skipped step* demo, deliberately skip one listed step on camera.
4. Label the steps in `ground_truth.json` (title, start, end in seconds) and update `expected_missed` / `expected_out_of_order` in `meta.json`.
5. Set a real provider in `.env` (see the README), then run:

   ```bash
   make demo          # processes new or changed demos
   make eval          # metrics table for your slides
   ```

   `make demo` reprocesses a demo whenever its video or reference changes; use
   `cd backend && uv run python -m scripts.precompute_demo --force` to redo everything.

Video files are gitignored (they're large); keep a copy somewhere safe.

## The three demos

| Folder | Story |
|---|---|
| `omelette` | Every recipe step done in order: *All 7 steps completed in order.* |
| `omelette-skipped-step` | The chives are never chopped: the procedure check flags the missed step. |
| `shelf-assembly` | The shelf board goes on before the pins: flagged as out of order. |
