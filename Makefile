AGENT_MODEL ?= openai:glm-5.3-flash:cloud
AGENT_BASE_URL ?= http://localhost:11434/v1
API_PORT ?= 8000
WEB_PORT ?= 3000
RAW ?= 0

ifeq ($(RAW),1)
ASK_SINK := cat
else
ASK_SINK := uv run python scripts/ask_stream.py
endif

export MESSAGE

.DEFAULT_GOAL := help

.PHONY: help proto lint typecheck test backfill verify serve ask

##@ General

help: ## Show available targets and configurable variables
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m [API_PORT=8000] [WEB_PORT=3000] [MESSAGE=...] [AGENT_MODEL=openai:...] [AGENT_BASE_URL=...]\n"} \
		/^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Verification & Data

proto: ## Lint .proto and regenerate Python/TS bindings (buf + protolint)
	@if [ -d packages/proto ]; then \
		cd packages/proto && buf lint && protolint lint . && buf generate && touch ../shared-schemas/src/inversa/py.typed; \
	else \
		echo "skip proto: packages/proto not present yet"; \
	fi

lint: ## Run prek hooks over all files
	@if [ -f .pre-commit-config.yaml ]; then \
		prek run --all-files; \
	else \
		echo "skip lint: no .pre-commit-config.yaml yet"; \
	fi

typecheck: ## Run mypy --strict over every python source tree
	@src=$$(ls -d services packages 2>/dev/null); \
	if [ -n "$$src" ]; then \
		status=0; \
		for d in services/*/ packages/*/; do \
			if [ -n "$$(find "$$d" -name '*.py' 2>/dev/null | head -1)" ]; then \
				echo "mypy: $$d"; \
				uv run mypy --strict "$$d" || status=1; \
			fi; \
		done; \
		exit $$status; \
	else \
		echo "skip typecheck: no python sources yet"; \
	fi

test: ## Run pytest across all service test suites
	@tests=$$(ls -d services/*/tests packages/*/tests 2>/dev/null); \
	if [ -n "$$tests" ]; then \
		uv run pytest -v; \
	else \
		echo "skip test: no test suites yet"; \
	fi

backfill: ## Seed the local datalake (FIRMS fires, wind, stations)
	uv run python -m inversa.ingestion.backfill

verify: proto lint typecheck test ## Full gate — proto + lint + typecheck + test

##@ Local Agent Demo

serve: ## Boot API (API_PORT=8000) + web UI (WEB_PORT=3000); Ctrl-C stops both
	@if [ ! -d "$${DATA_DIR:-$(CURDIR)/.local_datalake}" ]; then \
		echo "warn: datalake $${DATA_DIR:-$(CURDIR)/.local_datalake} not found — run make backfill first"; \
	fi
	@if [ ! -x apps/web/node_modules/.bin/next ]; then \
		echo "warn: apps/web deps missing — run: (cd apps/web && npm ci)"; \
	fi
	@if [ ! -x .venv/bin/uvicorn ]; then \
		echo "err: .venv/bin/uvicorn missing — run: uv sync"; exit 1; \
	fi
	@echo "API on http://127.0.0.1:$(API_PORT) · web on http://localhost:$(WEB_PORT) · agent $(AGENT_MODEL) · Ctrl-C stops both"
	@AGENT_MODEL="$(AGENT_MODEL)" AGENT_BASE_URL="$(AGENT_BASE_URL)" \
		exec .venv/bin/uvicorn inversa.api.app:create_app --factory --port $(API_PORT) & \
	UVICORN_PID=$$!; \
	( cd apps/web && NEXT_PUBLIC_API_URL="$${NEXT_PUBLIC_API_URL:-http://127.0.0.1:$(API_PORT)}" \
		exec ./node_modules/.bin/next dev --port $(WEB_PORT) ) & \
	WEB_PID=$$!; \
	trap 'kill $$WEB_PID $$UVICORN_PID 2>/dev/null || true' EXIT INT TERM; \
	wait $$UVICORN_PID

ask: ## Stream one agent answer — make ask MESSAGE="..." (RAW=1 for raw SSE)
	@if [ -z "$$MESSAGE" ]; then \
		echo 'usage: make ask MESSAGE="your question"  (start the server first: make serve)'; \
		exit 1; \
	fi
	@payload=$$(uv run python -c 'import json, os; print(json.dumps({"message": os.environ["MESSAGE"]}))') && \
	curl -sSN "http://127.0.0.1:$(API_PORT)/api/chat" \
		-H 'Content-Type: application/json' \
		-d "$$payload" | $(ASK_SINK)
