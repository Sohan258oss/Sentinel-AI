.DEFAULT_GOAL := help
SHELL := /bin/bash
PY := backend/.venv/bin/python

.PHONY: help setup backend frontend dev ingest train dataset test lint demo clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create the venv, install backend + frontend dependencies, build the RAG index
	python3 -m venv backend/.venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install -r backend/requirements.txt
	cd frontend && npm install
	$(MAKE) ingest
	@echo ""
	@echo "Setup complete. Run 'make dev' in one terminal, 'make frontend' in another."

backend: ## Run the API on :8000
	cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

frontend: ## Run the command centre on :5173
	cd frontend && npm run dev

dev: backend ## Alias for backend

ingest: ## Build the doctrine vector index and verify retrieval
	cd backend && .venv/bin/python -m app.rag.ingest --reset --probe

dataset: ## Download and normalise the AIDER training corpus (275 MB)
	cd backend && .venv/bin/python -m ml.prepare_dataset

train: ## Fine-tune the damage classifier
	cd backend && .venv/bin/python -m ml.train_damage_classifier --epochs 9

test: ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest -q

lint: ## Typecheck the frontend
	cd frontend && npx tsc --noEmit

demo: ## Run the flagship scenario in the terminal with a live trace
	cd backend && .venv/bin/python -m app.cli run kerala_flood --trace

scenarios: ## List available demo scenarios
	cd backend && .venv/bin/python -m app.cli scenarios

clean: ## Remove caches and build artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.pytest_cache frontend/dist frontend/.vite
