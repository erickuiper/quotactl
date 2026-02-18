# Local development and build
# Run from repo root: make build | install | test | clean

.PHONY: install build test clean

# Editable install (use quotactl from source)
install:
	pip install -e .

# Single Linux amd64 binary (requires PyInstaller)
build:
	./scripts/build-release.sh

# Run tests
test:
	pip install -e ".[dev]" -q
	pytest

# Remove build artifacts
clean:
	rm -rf dist/ build/ *.spec
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
