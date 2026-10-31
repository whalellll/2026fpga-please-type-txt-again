#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export CPU_TEST_GENERATOR=scripts/generate_ialign32_test.py
unset CPU_TEST_SOC_RTL
bash scripts/run_cpu_test.sh
grep 'IALIGN32_CHECKS_PASS traps=6' work/cpu-test/run.log
