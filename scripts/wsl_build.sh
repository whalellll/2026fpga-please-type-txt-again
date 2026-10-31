#!/bin/sh
# Usage: wsl -d pikafish-verify -- sh /mnt/g/fpga/performance_soc_voice_hw/scripts/wsl_build.sh make -C /linux/tree
set -eu
task_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$task_script_dir/wsl_build_profile.sh"
if [ "$#" -eq 0 ]; then
    printf 'jobs=%s\ncache=%s\n' "$FPGA_BUILD_JOBS" "$FPGA_BUILD_CACHE"
    exit 0
fi
# Explicit -j on the command line still takes precedence. Do not call this
# wrapper inside a recursive make: the parent owns its jobserver there.
if [ -n "${MAKEFLAGS:-}" ]; then
    echo 'Run wsl_build.sh outside an existing make/jobserver environment' >&2
    exit 2
fi
export MAKEFLAGS="-j$FPGA_BUILD_JOBS"
export CMAKE_BUILD_PARALLEL_LEVEL=$FPGA_BUILD_JOBS
task_timeout=${FPGA_BUILD_TIMEOUT_SECONDS:-14400}
case "$task_timeout" in ''|*[!0-9]*|0) echo 'Invalid build timeout' >&2; exit 2 ;; esac
exec timeout --kill-after=30 "$task_timeout" "$@"
