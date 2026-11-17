.PHONY: proto lint typecheck test verify

proto:
	cd packages/proto && buf lint && protolint lint . && buf generate

lint:
	prek run --all-files

typecheck:
	uv run mypy services packages

test:
	uv run pytest -v

verify: proto lint typecheck test