#!/usr/bin/env bash
# RT-9 (#127): Firefox 機能マトリクスを仮想 PulseAudio null sink の上で実行する。
#   bash tools/runtime/probe/run_features_firefox_audio.sh  → work/features_result_firefox.json
# 音声バックエンドが無いと Firefox の AudioContext / AudioWorklet が 20 s で止まるため (REPORT.md RT-9)、
# null sink を立てる。Worker 内 WebGL2 を判定するため Xvfb (非 headless) で走らせる。
# 要件: pulseaudio / pactl / xvfb-run (apt: pulseaudio pulseaudio-utils)。
# 自分で起動した pulseaudio だけを pidfile の PID で止める (既存の pulse は触らない)。
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
for c in pulseaudio pactl xvfb-run node; do
  command -v "$c" >/dev/null || { echo "missing command: $c" >&2; exit 2; }
done
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/xdg.XXXXXX")}"
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
pidfile="$XDG_RUNTIME_DIR/pulse/pid"
started=0
cleanup() {
  if [ "$started" = 1 ] && [ -f "$pidfile" ]; then kill "$(cat "$pidfile")" 2>/dev/null || true; fi
}
trap cleanup EXIT
if ! pactl info >/dev/null 2>&1; then
  pulseaudio -D --exit-idle-time=-1 -n --load="module-null-sink sink_name=null_out" --load=module-native-protocol-unix
  started=1
  for _ in $(seq 1 50); do pactl info >/dev/null 2>&1 && break; sleep 0.1; done
  pactl info >/dev/null 2>&1 || { echo "pulseaudio did not start" >&2; exit 1; }
fi
rc=0
FIREFOX_HEADLESS=0 xvfb-run -a node "$here/run_features_firefox.mjs" || rc=$?
exit "$rc"
