.PHONY: proto lint typecheck test verify

proto:
	@if [ -d packages/proto ]; then \
		cd packages/proto && buf lint && protolint lint . && buf generate; \
	else \
		echo "skip proto: packages/proto not present yet"; \
	fi

lint:
	prek run --all-files

typecheck:
	@src=$$(ls -d services packages 2>/dev/null); \
	if [ -n "$$src" ]; then \
		uv run mypy $$src; \
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
