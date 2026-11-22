"""FastAPI application: CORS, consistent errors, routers, Range-enabled media."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, jobs, media
from app.config import get_settings
from app.db import init_db
from app.errors import install_error_handlers
from app.worker import get_worker

log = logging.getLogger("replay")


def _configure_logging() -> None:
    level = get_settings().log_level.upper()
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", force=False
    )
    logging.getLogger("replay").setLevel(level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    s = get_settings()
    s.jobs_dir.mkdir(parents=True, exist_ok=True)
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    log.info(
        "Replay %s | VLM provider: %s (%s) | LLM provider: %s (%s)",
        __version__,
        s.vlm_provider,
        s.model_for("vlm"),
        s.llm_provider,
        s.model_for("llm"),
    )
    worker = get_worker()
    worker.start()
    if s.seed_demos_on_startup:
        worker.seed_demos()
    try:
        yield
    finally:
        worker.shutdown()


def create_app() -> FastAPI:
    s = get_settings()
    s.jobs_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(
        title="Replay API",
        version=__version__,
        description="Action-aware summarization of first-person task videos.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_origin_regex=s.cors_origin_regex or None,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Accept-Ranges", "Content-Length", "Content-Disposition"],
    )
    install_error_handlers(app)
    for module in (health, jobs, media):
        app.include_router(module.router)
    return app


app = create_app()
