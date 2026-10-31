#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p work/logs/architecture
export CORE_TEST_SV="${CORE_TEST_SV:-$PWD/generated/sim/CoreTop.sv}"
sha256sum "$CORE_TEST_SV" >work/logs/architecture/rtl-input.sha256
for name in cpu atomic machine memory_order bus_error ialign32; do
  export CPU_TEST_GENERATOR="scripts/generate_${name}_test.py"
  unset CPU_TEST_SOC_RTL
  if [[ "$name" == bus_error ]]; then export CPU_TEST_SOC_RTL=work/cpu-test/bus_error_soc.v; fi
  bash scripts/run_cpu_test.sh
  cp work/cpu-test/run.log "work/logs/architecture/$name.log"
  cp work/cpu-test/oracle.json "work/logs/architecture/$name-oracle.json"
done
for kind in bresp fill; do
  export WRITE_ERROR_KIND="$kind"
  export CPU_TEST_GENERATOR=scripts/generate_write_error_test.py
  export CPU_TEST_SOC_RTL=work/cpu-test/write_error_soc.v
  bash scripts/run_cpu_test.sh
  cp work/cpu-test/run.log "work/logs/architecture/write-$kind.log"
done
printf 'Architectural self-checks passed.\n'
