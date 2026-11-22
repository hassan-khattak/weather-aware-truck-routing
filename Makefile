.PHONY: dev-up dev-down test test-backend test-core test-web lint

dev-up:
	docker compose up --build -d --wait
	@echo "Map: http://localhost:5173  ·  API health: http://localhost:5173/api/v1/health"

dev-down:
	docker compose down

test: test-backend test-web

test-backend:
	cd backend && uv run pytest

test-core:
	cd backend && uv run pytest tests/core

test-web:
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && DEBUG=True uv run mypy .
	cd frontend && npm run lint && npm run typecheck && npm run format:check
