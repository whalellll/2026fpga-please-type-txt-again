#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/verify_generated.py "${1:-check}" --snapshot work/emit-inputs.json
