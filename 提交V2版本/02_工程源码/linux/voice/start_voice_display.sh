#!/bin/sh
# Explicit foreground entry: preview only, no chess commands are sent.
set -eu
audio=${XQVOICE_AUDIO:-/dev/pango-audio0}
model=${XQVOICE_MODEL:-/opt/xqvoice/tts-candidate.xqt}
program=${XQVOICE_PROGRAM:-/usr/bin/xqvoice}
start=${XQVOICE_VAD_START:-200}
stop=${XQVOICE_VAD_STOP:-160}
score=${XQVOICE_TOKEN_SCORE:-500}
XQVOICE_BACKEND=${XQVOICE_BACKEND:-hardware}
export XQVOICE_BACKEND
if [ "$XQVOICE_BACKEND" = hardware ]; then test -c /dev/pango-voice0; else test -c "$audio"; fi
test -r "$model"
test -x "$program"
exec "$program" "$audio" "$model" "$start" "$stop" "$score"
