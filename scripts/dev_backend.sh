#!/usr/bin/env bash
# Run the gateway locally in SIMULATION mode (no hardware, no ROS2 needed).
set -euo pipefail
cd "$(dirname "$0")/../backend"

if [ ! -d .venv ]; then
    python -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
pip install -q -r requirements.txt

export DEPLOYMENT_MODE="${DEPLOYMENT_MODE:-SIMULATION}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
