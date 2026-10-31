#!/usr/bin/env bash
# Build one host model, then run three performance and one validation firmware.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
group="${COREMARK_RELEASE_ROOT:-$root/work/coremark-release-$(date -u +%Y%m%d-%H%M%S)}"
if [[ -e "$group" ]]; then
  echo "Refusing to overwrite CoreMark release group: $group" >&2
  exit 2
fi
mkdir -p "$group"
echo "COREMARK_RELEASE_ROOT=$group"
COREMARK_BUILD_ONLY=1 COREMARK_HOST_CXX_FLAGS=-Os \
  COREMARK_FIRMWARE_ROOT="$root/coremark_test_soc/sim/coremark_ima" \
  COREMARK_RESULT_ROOT="$group/build-prep" COREMARK_BUILD_ROOT="$group/model" \
  bash scripts/run_coremark_ab.sh ima
python3 scripts/coremark_release_group.py "$group" "$group/model/Vtb_coremark_soc" \
  "$root/coremark_test_soc/sim/coremark_ima" \
  "$root/coremark_test_soc/sim/coremark_validation" --max-cycles 800000000
