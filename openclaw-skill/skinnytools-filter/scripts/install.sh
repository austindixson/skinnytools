#!/bin/bash
# Install skinnytools into a virtual environment
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$SKILL_DIR")")"

echo "Installing skinnytools from $PROJECT_ROOT..."

cd "$PROJECT_ROOT"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

.venv/bin/pip install -e ".[dev]" --quiet

echo "skinnytools installed successfully."
echo "CLI available at: $PROJECT_ROOT/.venv/bin/skinnytools"
echo ""
echo "Usage:"
echo "  echo \"\$OUTPUT\" | $PROJECT_ROOT/.venv/bin/skinnytools filter"
echo "  $PROJECT_ROOT/.venv/bin/skinnytools wrap <command>"
echo "  $PROJECT_ROOT/.venv/bin/skinnytools analyze <file>"
