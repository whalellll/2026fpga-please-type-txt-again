#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export CORE_TEST_SV="$PWD/work/handoff-probes/CoreTop.sv"
test -s "$CORE_TEST_SV"
python3 scripts/verify_generated.py check --simulation "$CORE_TEST_SV"
unset CPU_TEST_SOC_RTL CPU_TEST_GENERATOR WRITE_ERROR_KIND
case "${1:-}" in
  Functional) bash scripts/run_architecture_checks.sh ;;
  Ialign32) bash scripts/run_ialign32_test.sh ;;
  CoreMark) bash scripts/run_coremark_ab.sh ;;
  *) echo 'Expected Functional, Ialign32 or CoreMark' >&2; exit 2 ;;
esac
