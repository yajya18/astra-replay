# Replay task runner. Works with GNU make on macOS/Linux, and on Windows from Git Bash.
SHELL := /bin/sh
BACKEND := backend
FRONTEND := frontend
UV ?= uv
NPM ?= npm

.PHONY: help setup dev dev-backend dev-frontend test test-backend test-frontend e2e lint \
        lint-backend lint-frontend format demo eval test-videos clean docker

help:
	@echo "make setup     install backend (uv) and frontend (npm) dependencies"
	@echo "make dev       run API on :8000 and web app on :3000"
	@echo "make test      backend pytest + frontend vitest"
	@echo "make e2e       Playwright end-to-end test (mock provider)"
	@echo "make lint      ruff + mypy + eslint + prettier + tsc"
	@echo "make demo      process every video in demo/ into cached results"
	@echo "make eval      evaluate demo results against ground truth"
	@echo "make docker    docker compose up --build"

setup:
	cd $(BACKEND) && $(UV) sync --all-extras
	cd $(BACKEND) && $(UV) run python -m scripts.download_models
	cd $(FRONTEND) && $(NPM) install
	cd $(FRONTEND) && npx playwright install chromium

dev:
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd $(BACKEND) && $(UV) run uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000

dev-frontend:
	cd $(FRONTEND) && $(NPM) run dev -- --hostname 0.0.0.0 --port 3000

test: test-backend test-frontend

test-backend:
	cd $(BACKEND) && $(UV) run pytest -q -n 4 --dist loadfile

test-frontend:
	cd $(FRONTEND) && $(NPM) test

e2e: test-videos
	cd $(FRONTEND) && $(NPM) run test:e2e

lint: lint-backend lint-frontend

lint-backend:
	cd $(BACKEND) && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy app scripts

lint-frontend:
	cd $(FRONTEND) && $(NPM) run lint && $(NPM) run format:check && $(NPM) run typecheck

format:
	cd $(BACKEND) && $(UV) run ruff check --fix . && $(UV) run ruff format .
	cd $(FRONTEND) && $(NPM) run format

test-videos:
	cd $(BACKEND) && $(UV) run python -m scripts.make_test_video --out tests/fixtures/videos

demo:
	cd $(BACKEND) && $(UV) run python -m scripts.precompute_demo

eval:
	cd $(BACKEND) && $(UV) run python -m scripts.evaluate --out ../docs/evaluation_results.md

docker:
	docker compose up --build

clean:
	rm -rf data $(BACKEND)/tests/fixtures/videos $(FRONTEND)/.next
