#!/usr/bin/env bash
# AU-2 (#187) CI 代理指標の行列: {Chrome fake シンク, Chrome PulseAudio null-sink} × {48k, 96k} を N 回測る。
# fake = PulseAudio を止めた状態 (Chrome は fake 出力へフォールバック)、null = PulseAudio + module-null-sink (ci_null) を既定 sink にした状態。
# 結果は tools/audio/results/au2/<cond>_r<rep>.json (results.json と同形式)、集計は au2_summary.mjs。
# 使い方: bash tools/audio/au2_matrix.sh [N]   (既定 3。build 済みの build/web が前提: bash tools/audio/build.sh)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
N="${1:-3}"
OUT="$HERE/results/au2"
SCEN="asio_sine_b256_d2,asio_sine_b256_96k,asio_sine_b512_96k"
mkdir -p "$OUT"
pulse_off() { pulseaudio -k >/dev/null 2>&1 || true; sleep 1; }
pulse_on() {
  pulseaudio --start --exit-idle-time=-1 >/dev/null 2>&1
  sleep 2
  pactl load-module module-null-sink sink_name=ci_null >/dev/null
  pactl set-default-sink ci_null
}
for rep in $(seq 1 "$N"); do
  pulse_off
  node "$HERE/harness/run.mjs" --only "$SCEN" --out "$OUT/fake_r$rep.json" || echo "[au2] fake_r$rep exit=$? (FAIL は JSON の ok で判定)"
  pulse_on
  node "$HERE/harness/run.mjs" --only "$SCEN" --out "$OUT/null_r$rep.json" || echo "[au2] null_r$rep exit=$? (FAIL は JSON の ok で判定)"
  pulse_off
done
