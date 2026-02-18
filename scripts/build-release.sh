#!/usr/bin/env bash
# Build a single Linux amd64 binary for quotactl using PyInstaller.
# Run from repo root: ./scripts/build-release.sh
# Output: dist/quotactl

set -e
cd "$(dirname "$0")/.."

echo "Installing dependencies and PyInstaller..."
pip install -e . pyinstaller -q

echo "Building single binary (linux amd64)..."
pyinstaller \
  --onefile \
  --name quotactl \
  --clean \
  src/quotactl/__main__.py

chmod +x dist/quotactl
echo "Done: dist/quotactl"
ls -la dist/quotactl
