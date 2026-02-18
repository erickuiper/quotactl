#!/bin/bash
# Download dependencies for air-gapped installation
#
# This script downloads all dependencies to a wheels/ directory for offline installation.
# Run this on an internet-connected machine, then transfer the wheels/ directory
# to the air-gapped machine.
#
# Usage:
#   ./download-dependencies.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEELS_DIR="${SCRIPT_DIR}/wheels"

echo "Downloading dependencies to ${WHEELS_DIR}..."
mkdir -p "$WHEELS_DIR"

pip download -r requirements.txt -d "$WHEELS_DIR"

echo ""
echo "Dependencies downloaded successfully!"
echo ""
echo "Next steps:"
echo "1. Transfer the wheels/ directory to your air-gapped machine"
echo "2. Run ./install-offline.sh on the air-gapped machine"

