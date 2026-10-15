#!/usr/bin/env bash
# AU-8 (#194) 1 コマンド e2e: ring 版 + worklet 直走行版をビルド → 静的スレッド面 (gate + negctl) → 遅延比較 (gate + negctl)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> PY=<pefile 入りの python3> bash tools/audio/wl/e2e.sh   終了コード 0 = 全 PASS (negctl 含む)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
PY="${PY:-python3}"
: "${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 展開先) が必要}"
mkdir -p "$HERE/results"
bash "$HERE/../build.sh"
bash "$HERE/build.sh"
"$PY" "$HERE/fl_thread_surface.py" --json "$HERE/results/thread_surface.json" | tee "$HERE/results/thread_surface.txt"
"$PY" "$HERE/fl_thread_surface.py" --negctl | tail -6      # exit 0 = gate が期待どおり FAIL (検出能力あり)
"$PY" "$HERE/mixer_reach.py" --json "$HERE/results/mixer_reach.json" | tee "$HERE/results/mixer_reach.txt"
"$PY" "$HERE/mixer_reach.py" --negctl | tail -3              # exit 0 = 入口を関数内部に差替えた gate が期待どおり FAIL
node "$HERE/run.mjs" --reps "${REPS:-3}" --secs "${SECS:-6}" --out "$HERE/results/results.json"
