"""Download the local models once (embeddings + Whisper) so the first job is fast.

Usage: uv run python -m scripts.download_models
"""

from __future__ import annotations

import importlib.util

from app.config import get_settings


def main() -> None:
    s = get_settings()
    print(f"Embedding model: {s.embedding_model}")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(s.embedding_model, device="cpu")
    if s.whisper_enabled and importlib.util.find_spec("faster_whisper") is not None:
        print(f"Whisper model: {s.whisper_model} ({s.whisper_compute_type})")
        from faster_whisper import WhisperModel

        WhisperModel(s.whisper_model, device=s.whisper_device, compute_type=s.whisper_compute_type)
    print("Models ready.")


if __name__ == "__main__":
    main()
