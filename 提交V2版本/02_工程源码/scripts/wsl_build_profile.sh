# Source from a build shell. No changes to login shells or WSL VM settings.
# FPGA_BUILD_REQUESTED_JOBS=0 selects automatic parallelism (maximum 8).
fpga_build_profile() {
    task_clean_path=
    task_saved_ifs=$IFS
    IFS=:
    for task_path in $PATH; do
        case "$task_path" in
            /*) case "$task_path" in /mnt/*) continue ;; esac ;;
            *) continue ;;
        esac
        task_clean_path=${task_clean_path:+$task_clean_path:}$task_path
    done
    IFS=$task_saved_ifs
    PATH=${task_clean_path:-/usr/local/bin:/usr/bin:/bin}
    export PATH

    task_cpus=$(nproc)
    task_mem_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    # Reserve 2 GiB in the guest, then allow 1.5 GiB per compiler process.
    task_mem_jobs=$(( (task_mem_kb - 2097152) / 1572864 ))
    task_cpu_jobs=$((task_cpus - 4))
    [ "$task_mem_jobs" -gt 0 ] || task_mem_jobs=1
    [ "$task_cpu_jobs" -gt 0 ] || task_cpu_jobs=1
    FPGA_BUILD_JOBS=8
    [ "$task_mem_jobs" -ge "$FPGA_BUILD_JOBS" ] || FPGA_BUILD_JOBS=$task_mem_jobs
    [ "$task_cpu_jobs" -ge "$FPGA_BUILD_JOBS" ] || FPGA_BUILD_JOBS=$task_cpu_jobs
    task_requested=${FPGA_BUILD_REQUESTED_JOBS:-0}
    case "$task_requested" in ''|*[!0-9]*) echo 'Invalid FPGA_BUILD_REQUESTED_JOBS' >&2; return 2 ;; esac
    if [ "$task_requested" -gt 0 ] && [ "$task_requested" -lt "$FPGA_BUILD_JOBS" ]; then
        FPGA_BUILD_JOBS=$task_requested
    fi
    export FPGA_BUILD_JOBS

    FPGA_BUILD_CACHE=disabled
    if [ "${FPGA_BUILD_NO_CACHE:-0}" != 1 ] && command -v ccache >/dev/null 2>&1; then
        task_cache_root=${XDG_CACHE_HOME:-$HOME/.cache}/fpga-build
        # Never put compiler cache metadata on a Windows mounted filesystem.
        case "$task_cache_root" in /mnt/*) echo 'FPGA build cache must be on Linux storage' >&2; return 2 ;; esac
        mkdir -p "$task_cache_root/bin" "$task_cache_root/ccache"
        export CCACHE_DIR="$task_cache_root/ccache"
        export CCACHE_MAXSIZE=1G CCACHE_COMPILERCHECK=content
        # Keep strict ccache defaults: no sloppiness, ignored headers or flags.
        task_ccache=$(command -v ccache)
        for task_cc in cc c++ gcc g++ riscv64-linux-gnu-gcc riscv64-linux-gnu-g++ riscv32-linux-musl-gcc riscv32-linux-musl-g++; do
            if command -v "$task_cc" >/dev/null 2>&1; then
                ln -sfn "$task_ccache" "$task_cache_root/bin/$task_cc"
            fi
        done
        PATH="$task_cache_root/bin:$PATH"
        export PATH
        FPGA_BUILD_CACHE=$CCACHE_DIR
    fi
    export FPGA_BUILD_CACHE
    printf 'WSL_BUILD_PROFILE jobs=%s available_kib=%s cache=%s\n' "$FPGA_BUILD_JOBS" "$task_mem_kb" "$FPGA_BUILD_CACHE" >&2
}
fpga_build_profile
