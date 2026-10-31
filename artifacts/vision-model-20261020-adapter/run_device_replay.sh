#!/bin/sh
# Explicit transformed IMG00908 offline replay. Never a live camera request.
# Serialize behind the complete golden test: two resident-model clients must
# not thrash each other's snapshots or contaminate latency measurements.
set -eu
native_pid=
trap 'if test -n "$native_pid"; then kill -TERM "$native_pid" 2>/dev/null || :; fi; exit 130' INT TERM
n=0
while test ! -f /run/xq-golden-r04.exit; do
 if test "$n" -ge 720; then
  echo XQ_REPLAY_ABORT golden_deadline
  exit 2
 fi
 n=$((n+1))
 sleep 10
done
test "$(cat /run/xq-golden-r04.exit)" = 0
# The probe's exit code means execution finished, not numerical acceptance.
# PC compares every tensor digest with the immutable dump before releasing us.
n=0
while test ! -f /run/xq-golden-r04-comparison.pass; do
 if test "$n" -ge 360; then
  echo XQ_REPLAY_ABORT comparison_deadline
  exit 2
 fi
 n=$((n+1))
 sleep 10
done
grep -qx GOLDEN_80_PASS /run/xq-golden-r04-comparison.pass
test -s /run/replay-sample2.rgb565
printf '%s\n' 'XQ_MODEL_REQUEST_V1 1 1 88d92842 rv32-driver-quantized-mac' > /run/xq-native-replay.request
( ulimit -t 7200
  exec /run/xq-native/xq-native-worker --models /run/xq-native --driver \
   --request /run/xq-native-replay.request --input /run/replay-sample2.rgb565 \
   --output /run/xq-native-replay.packet
) &
native_pid=$!
if wait "$native_pid"; then result=0; else result=$?; fi
native_pid=
printf '%s\n' "$result" > /run/xq-native-replay.exit
# GUI startup is a separate normal /usr/bin/xiangqi-pikafish operation after
# reviewing this offline result and the selected GUI's regression receipt.
exit "$result"
