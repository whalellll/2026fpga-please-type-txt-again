#!/usr/bin/env bash
set -euo pipefail
base=/g/fpga/build/pds25-cpu120-20261101-03
host_bin=$(cygpath -u "$CPU_HOST_LLVM_BIN")
export PATH=/g/fpga/workspace/tools/riscv32-gcc16/bin:$host_bin:/mingw64/bin:/usr/bin:/bin:$PATH
export TMPDIR="$base/tmp" CPU_TEST_JOBS=2 RISCV_PREFIX=riscv32-unknown-elf-
export VERILATOR="$base/tools/verilator-llvm"
#!/usr/bin/env bash
set -euo pipefail
cd /g/fpga/build/pds25-cpu120-20261101-03/cpu-source/cpu
mkdir -p work/logs/architecture
export CORE_TEST_SV="${CORE_TEST_SV:-$PWD/generated/sim/CoreTop.sv}"
sha256sum "$CORE_TEST_SV" >work/logs/architecture/rtl-input.sha256
for name in cpu atomic privileged memory_order bus_error ialign32; do
  export CPU_TEST_ORIGINAL_GENERATOR="scripts/generate_${name}_test.py"
  export CPU_TEST_GENERATOR=/g/fpga/build/pds25-cpu120-20261101-03/generate_qualified_architecture.py
  unset CPU_TEST_SOC_RTL
  if [[ "$name" == bus_error ]]; then export CPU_TEST_SOC_RTL=work/cpu-test/bus_error_soc.v; fi
  CPU_TEST_CASE_ID="$name" bash /g/fpga/build/pds25-cpu120-20261101-03/run_cpu_test_isolated.sh
  cp work/cpu-test/run.log "work/logs/architecture/$name.log"
  cp work/cpu-test/oracle.json "work/logs/architecture/$name-oracle.json"
  cp work/cpu-test/fixture-adaptation.json "work/logs/architecture/$name-fixture.json"
done
for kind in bresp fill; do
  export WRITE_ERROR_KIND="$kind"
  export CPU_TEST_ORIGINAL_GENERATOR=scripts/generate_write_error_test.py
  export CPU_TEST_GENERATOR=/g/fpga/build/pds25-cpu120-20261101-03/generate_qualified_architecture.py
  export CPU_TEST_SOC_RTL=work/cpu-test/write_error_soc.v
  CPU_TEST_CASE_ID="write-$kind" bash /g/fpga/build/pds25-cpu120-20261101-03/run_cpu_test_isolated.sh
  cp work/cpu-test/run.log "work/logs/architecture/write-$kind.log"
done
printf 'Architectural self-checks passed.\n'
