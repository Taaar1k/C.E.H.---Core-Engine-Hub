#!/usr/bin/env bash
# setup.sh — Create and activate the C.E.H. virtual environment.
#
# Usage:
#   bash scripts/setup.sh
#
# Prerequisites:
#   - Python 3.11+ installed
#   - uv package manager installed (pip install uv)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== C.E.H. Setup ==="

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
    echo "Virtual environment created at .venv/"
else
    echo "Virtual environment already exists at .venv/"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
uv sync

# Verify installation
echo ""
echo "Verifying installation..."
python -c "import llama_cpp; import pydantic; import typer; import rich; import structlog; print('All imports OK')"

echo ""
echo "=== Setup complete! ==="
echo "Run 'source .venv/bin/activate' to activate the environment."
