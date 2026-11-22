"""Turn the screencast frames written by record-demo.mjs into raw.mp4 and rel.json.

    python docs/media/tools/frames_to_video.py REC_DIR
"""

import json
import subprocess
import sys
from pathlib import Path

rec = Path(sys.argv[1])
data = json.loads((rec / "marks.json").read_text())
frames, marks = data["frames"], data["marks"]
t0 = frames[0]
with open(rec / "list.txt", "w") as f:
    for i, t in enumerate(frames):
        dur = frames[i + 1] - t if i + 1 < len(frames) else 0.1
        f.write(f"file 'frames/f{i:06d}.jpg'\nduration {max(dur, 0.001):.4f}\n")
    f.write(f"file 'frames/f{len(frames) - 1:06d}.jpg'\n")
(rec / "rel.json").write_text(json.dumps({k: v - t0 for k, v in marks.items()}))
subprocess.run(
    ["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(rec / "list.txt"),
     "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "14", "-preset", "veryfast",
     str(rec / "raw.mp4")],
    check=True,
)
print("wrote", rec / "raw.mp4")
