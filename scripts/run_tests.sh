#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
python -m pytest tests/ -v
