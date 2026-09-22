#!/usr/bin/env bash
# Run the gateway locally in SIMULATION mode (no hardware, no ROS2 needed).
set -euo pipefail
cd "$(dirname "$0")/../backend"

if [ ! -d .venv ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv .venv
    else
        python -m venv .venv
    fi
fi

# shellcheck disable=SC1091
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
elif [ -f .venv/Scripts/activate ]; then
    source .venv/Scripts/activate
else
    echo "Backend virtual environment missing; follow README.md setup instructions." >&2
    exit 1
fi
pip install -q -r requirements.txt

export DEPLOYMENT_MODE="${DEPLOYMENT_MODE:-SIMULATION}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
