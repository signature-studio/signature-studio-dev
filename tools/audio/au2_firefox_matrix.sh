#!/usr/bin/env bash
# AU-2 (#187) 行列: Firefox × PulseAudio null-sink × {48k, 96k} を n 回測る (AU-23 #2540)。
# PulseAudio の既定 sink を ci_null にし、Firefox の出力をその sink へ流す。結果は results/au2/firefox_r<rep>.json、集計は au2_firefox_summary.mjs。
# Chrome 側の行列は au2_matrix.sh (別スクリプト。results/au2 の fake_r*・null_r* を使う)。
# 使い方: bash tools/audio/au2_firefox_matrix.sh [n=3]    終了コード 0 = 全 rep の全条件 PASS
# PASS = underrun 0・sine 一致・ctx.sampleRate 一致・worklet エラー 0 に加え、sink-input が既定 sink (ci_null) に接続したこと
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
N="${1:-3}"
command -v pactl >/dev/null || { echo "pactl not found (apt: pulseaudio-utils)" >&2; exit 1; }
if ! pactl info >/dev/null 2>&1; then
  pulseaudio -D --exit-idle-time=-1
  for _ in 1 2 3 4 5; do pactl info >/dev/null 2>&1 && break; sleep 1; done
fi
pactl list short sinks | awk -F'\t' '$2=="ci_null"{f=1} END{exit !f}' || pactl load-module module-null-sink sink_name=ci_null >/dev/null
pactl set-default-sink ci_null
[ -f "$HERE/build/web/fla_test.js" ] || bash "$HERE/build.sh"
mkdir -p "$HERE/results/au2"
rc=0
for rep in $(seq 1 "$N"); do
  node "$HERE/harness/au2.mjs" --rep "$rep" --out "$HERE/results/au2/firefox_r$rep.json" || rc=1
done
node "$HERE/au2_firefox_summary.mjs" || rc=1
exit $rc
