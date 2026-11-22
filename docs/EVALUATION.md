# Evaluation

`scripts/evaluate.py` compares processed demo results with hand-labelled ground truth and
prints a Markdown table you can paste into slides.

```bash
make demo   # process demo/ (uses the providers in your .env; mock by default)
make eval   # prints the table and writes docs/evaluation_results.md
```

## Metrics

| Metric | Definition |
|---|---|
| Recall / precision | A detected step matches a ground-truth step when **temporal IoU ≥ 0.3** and the titles are similar (a shared content word, or embedding cosine ≥ 0.5). Matching is one-to-one (Hungarian on 1 − IoU). Recall = matched / ground-truth steps; precision = matched / detected steps. |
| Mean IoU | Average temporal IoU of matched pairs. |
| Kendall's τ | Rank correlation between ground-truth order and detected order of the matched steps (1 = same order). |
| Missed-step check | Whether the procedure check flagged exactly the steps listed in `meta.json` `expected_missed` (and an out-of-order step when `expected_out_of_order` is true), and nothing else. |
| Compression | Original length ÷ highlight-reel length. |
| Processing s / min | Pipeline wall time per minute of input video. |

## Ground-truth format

`demo/<name>/ground_truth.json`:

```json
{
  "source": "hand-labelled from my recording",
  "steps": [
    {"title": "Crack the eggs", "start": 4.0, "end": 15.5},
    {"title": "Whisk the eggs", "start": 15.5, "end": 38.0}
  ]
}
```

Label each step at the moment the hands start and stop the action; leave waiting and reaching
out. Optional keys in `meta.json`: `expected_missed` (list of reference-step texts) and
`expected_out_of_order` (boolean).

## Current results (synthetic placeholders, mock provider)

The repository ships synthetic placeholder videos until real recordings are added. Their
ground truth is exact, so these numbers check the plumbing (windowing, segmentation, boundary
refinement, alignment, missed/out-of-order detection) rather than vision quality:

| Demo | GT steps | Detected | Recall | Precision | Mean IoU | Kendall τ | Missed-step check | Compression | Processing s / min |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| omelette | 7 | 7 | 1.00 | 1.00 | 0.99 | 1.00 | ✓ correct | 1.2× | 64.1 |
| omelette-skipped-step | 6 | 6 | 1.00 | 1.00 | 0.99 | 1.00 | ✓ correct | 1.2× | 67.3 |
| shelf-assembly | 5 | 5 | 1.00 | 1.00 | 0.99 | 1.00 | ✓ correct | 1.2× | 74.8 |
| **mean** |  |  | **1.00** | **1.00** | **0.99** | **1.00** | **3/3** | **1.2**× | **68.7** |

Compression is low here only because the placeholders are about one minute long and the reel
target is 40 to 60 s. On a real 3 to 10 minute recording the reel stays at the target, so
compression is 3 to 10×. Processing time was measured on a Windows laptop (CPU only, 16 GB
RAM) and is dominated by ffmpeg rendering in mock mode. With a
real provider, the understanding stage depends on the provider's latency (4 calls in parallel
by default).

**Re-run `make eval` after recording the real demo videos and labelling their ground truth.**
Those are the numbers to show judges.
