#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/.yafi-venv}"
REQUIREMENTS_FILE="$REPO_ROOT/requirements.txt"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    else
        PYTHON_BIN="python"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists at $VENV_DIR"
fi

if [ -f "$VENV_DIR/Scripts/python.exe" ]; then
    VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
else
    VENV_PYTHON="$VENV_DIR/bin/python"
fi

echo "Upgrading pip"
"$VENV_PYTHON" -m pip install --upgrade pip

echo "Installing dependencies from $REQUIREMENTS_FILE"
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE"

echo
echo "Setup complete. Activate the environment with:"
if [ -f "$VENV_DIR/Scripts/activate" ]; then
    echo "  source $VENV_DIR/Scripts/activate"
else
    echo "  source $VENV_DIR/bin/activate"
fi
