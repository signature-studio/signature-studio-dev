#!/usr/bin/env bash
# AU-2 (#187) CI 代理指標の行列: {Chrome fake シンク, Chrome PulseAudio null-sink} × {48k, 96k} を N 回測る。
# fake = PulseAudio を止めた状態 (Chrome は fake 出力へフォールバック)、null = PulseAudio + module-null-sink (ci_null) を既定 sink にした状態。
# 結果は <出力先>/<cond>_r<rep>.json (results.json と同形式)、集計は au2_summary.mjs。
# null の各 run では再生中の sink 一覧と Chrome の sink-input を 1 秒ごとに <出力先>/null_r<rep>_sinkinputs.txt へ採る (接続の根拠)。
# 行列の最後に NC (--inject-hiccup の soak 15 秒。FAIL になることが検出能力の確認) を <出力先>/nc_soak15_negctl.json へ採る。
# 使い方: bash tools/audio/au2_matrix.sh [N]   (既定 3。build 済みの build/web が前提: bash tools/audio/build.sh)
#         AU2_OUT=<dir> で出力先を変える (既定 tools/audio/results/au2)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
N="${1:-3}"
OUT="${AU2_OUT:-$HERE/results/au2}"
SCEN="asio_sine_b256_d2,asio_sine_b256_96k,asio_sine_b512_96k"
mkdir -p "$OUT"
pulse_off() { pulseaudio -k >/dev/null 2>&1 || true; sleep 1; }
pulse_on() {
  pulseaudio --start --exit-idle-time=-1 >/dev/null 2>&1
  sleep 2
  pactl load-module module-null-sink sink_name=ci_null >/dev/null
  pactl set-default-sink ci_null
}
# 監視対象 PID ($2) が生きている間、sink の index→名前 と Chrome の sink-input を 1 秒ごとに $1 へ追記する
capture_sinks() {
  while kill -0 "$2" 2>/dev/null; do
    {
      echo "# $(date +%T)"
      pactl list short sinks | grep -F ci_null || true
      pactl list sink-inputs | grep -E '^\s*Sink:|application\.name' || true
    } >> "$1" 2>&1
    sleep 1
  done
}
for rep in $(seq 1 "$N"); do
  pulse_off
  node "$HERE/harness/run.mjs" --only "$SCEN" --out "$OUT/fake_r$rep.json" || echo "[au2] fake_r$rep exit=$? (FAIL は JSON の ok で判定)"
  pulse_on
  node "$HERE/harness/run.mjs" --only "$SCEN" --out "$OUT/null_r$rep.json" &
  pid=$!
  capture_sinks "$OUT/null_r${rep}_sinkinputs.txt" "$pid"
  wait "$pid" || echo "[au2] null_r$rep exit=$? (FAIL は JSON の ok で判定)"
  pulse_off
done
pulse_on
node "$HERE/harness/run.mjs" --soak 15 --inject-hiccup --out "$OUT/nc_soak15_negctl.json" || echo "[au2] nc exit=$? (NC は FAIL になることが期待値)"
pulse_off
