#!/bin/bash
# Offline installation script for air-gapped environments
#
# This script installs the Rancher Quota Automation Tool from a local wheel cache.
# 
# Prerequisites:
# 1. Transfer the wheels/ directory to the air-gapped machine
# 2. Ensure Python 3.9+ is installed
#
# Usage:
#   ./install-offline.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEELS_DIR="${SCRIPT_DIR}/wheels"

if [ ! -d "$WHEELS_DIR" ]; then
    echo "Error: wheels/ directory not found"
    echo "Please ensure wheels/ directory exists with downloaded dependencies"
    exit 1
fi

echo "Installing dependencies from local wheel cache..."
pip install --no-index --find-links "$WHEELS_DIR" -r requirements.txt

echo "Installing quotactl package..."
pip install -e .

echo "Installation complete!"
echo ""
echo "Verify installation:"
echo "  quotactl --help"

