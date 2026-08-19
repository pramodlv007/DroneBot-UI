#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../ui"
npm install
exec npm run dev
