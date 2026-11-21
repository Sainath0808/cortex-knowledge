# Local development helpers. On Windows use `make` via Git Bash, or copy commands manually.
export PYTHONPATH := backend:.

install:
	pip install -e ".[dev]"

infra:
	docker compose up -d postgres redis qdrant

migrate:
	alembic upgrade head

dev:
	uvicorn app.main:app --reload --port 8000

worker:
	arq app.workers.worker.WorkerSettings

mcp:
	python -m mcp_server.server

test:
	pytest -q --cov=backend --cov=ai --cov=agents

lint:
	ruff check backend ai agents mcp_server tests

evals:
	python -m ai.evals.run_evals

seed:
	python scripts/seed.py

up:
	docker compose up --build
