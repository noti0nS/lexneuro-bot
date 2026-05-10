#!/usr/bin/env bash
set -euo pipefail

echo "=== ruff check ==="
uv run ruff check .

echo "=== ruff format (--check) ==="
uv run ruff format --check .

echo "=== basedpyright ==="
uv run basedpyright src tests

echo "=== pytest ==="
uv run pytest
