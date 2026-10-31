#!/bin/sh
set -eu
samples=${NNUE_SAMPLES:-200}
logs=${NNUE_LOG_DIR:-/tmp/nnue10ms-$(date +%s)}
mkdir -p "$logs"
restart_gui=0
if [ -s /run/xiangqi-pikafish.pid ] && kill -0 "$(cat /run/xiangqi-pikafish.pid)" 2>/dev/null; then
    restart_gui=1
    gui_pid=$(cat /run/xiangqi-pikafish.pid)
    /etc/init.d/S95pikafish stop
    attempts=0
    while kill -0 "$gui_pid" 2>/dev/null; do
        attempts=$((attempts+1))
        if [ "$attempts" -gt 10 ]; then echo 'NNUE_BOARD_FAIL reason=gui-still-running'; exit 1; fi
        sleep 1
    done
fi
restore_gui() {
    if [ "$restart_gui" = 1 ]; then /etc/init.d/S95pikafish start; fi
}
trap restore_gui EXIT
run_case() {
    name=$1
    shift
    if "$@" > "$logs/$name.log" 2>&1; then
        cat "$logs/$name.log"
    else
        result=$?
        cat "$logs/$name.log" >&2
        echo "NNUE_BOARD_FAIL case=$name exit=$result logs=$logs" >&2
        exit "$result"
    fi
}
uname -a
cat /proc/cpuinfo
run_case hashes sha256sum -c /opt/pikafish/nnue10ms-payloads.sha256
run_case resident pango-mac-resident-test
run_case yolo-compat pango-mac-conv-compute-test
run_case pool pango-mac-pool-test
run_case scheduler pango-mac-scheduler-test
run_case cpu env NNUE_SAMPLES="$samples" NNUE_REQUIRE_HW=0 PIKAFISH_STAGEA_ACCEL=0 PIKAFISH_STAGEB_ACCEL=0 pikafish-nnue-latency
run_case verify env NNUE_SAMPLES="$samples" NNUE_REQUIRE_HW=1 PIKAFISH_STAGEA_ACCEL=1 PIKAFISH_STAGEB_ACCEL=verify pikafish-nnue-latency
run_case accelerated env NNUE_SAMPLES="$samples" NNUE_REQUIRE_HW=1 PIKAFISH_STAGEA_ACCEL=1 PIKAFISH_STAGEB_ACCEL=1 pikafish-nnue-latency
echo "NNUE10MS_BOARD_PASS logs=$logs"
