.PHONY: proto lint typecheck test verify

proto:
	@if [ -d packages/proto ]; then \
		cd packages/proto && buf lint && protolint lint . && buf generate && touch ../shared-schemas/src/inversa/py.typed; \
	else \
		echo "skip proto: packages/proto not present yet"; \
	fi

lint:
	@if [ -f .pre-commit-config.yaml ]; then \
		prek run --all-files; \
	else \
		echo "skip lint: no .pre-commit-config.yaml yet"; \
	fi

typecheck:
	@src=$$(ls -d services packages 2>/dev/null); \
	if [ -n "$$src" ]; then \
		uv run mypy --strict $$src; \
	else \
		echo "skip typecheck: no python sources yet"; \
	fi

test:
	@tests=$$(ls -d services/*/tests packages/*/tests 2>/dev/null); \
	if [ -n "$$tests" ]; then \
		uv run pytest -v; \
	else \
		echo "skip test: no test suites yet"; \
	fi

verify: proto lint typecheck test
