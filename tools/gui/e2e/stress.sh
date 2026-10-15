#!/usr/bin/env bash
# stress.sh — GUI-8 長時間ストレス + ネガコン。前提: gui_e2e.sh の 3〜5 段 (lift / wasm / wasm_grow / tsc) が済んでいること。
#   STRESS_FRAMES (既定 50000) / STRESS_SAMPLE (既定 2500) / STRESS_NEG_FRAMES (ネガコンの frames; 既定 2000)
#   本番 2 本 (固定メモリ / memory.grow 注入) は exit 0、ネガコン 2 本 (burst / leak) は exit 1 でなければ全体 FAIL。
#   ネガコンは exit 1 (= 判定が不合格を返した) のみ受理する。タイムアウト (3) / 例外 (2) / 0 は FAIL。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; BUILD="$HERE/../build"
FR="${STRESS_FRAMES:-50000}"; SM="${STRESS_SAMPLE:-2500}"; NFR="${STRESS_NEG_FRAMES:-2000}"
for d in wasm wasm_grow; do [ -f "$BUILD/$d/app.wasm" ] || { echo "[stress.sh] $BUILD/$d/app.wasm 無し (先に gui_wasm.sh)" >&2; exit 2; }; done
echo "[stress.sh] 1/4 固定メモリ ${FR} frames"
STRESS_FRAMES=$FR STRESS_SAMPLE=$SM node "$HERE/stress.mjs" | grep -E "summary|golden|PASS|FAIL|eval|slow-eval"
echo "[stress.sh] 2/4 ALLOW_MEMORY_GROWTH + memory.grow 注入 (worker の memory.buffer 再取得) ${FR} frames"
GUI_WASM_DIR="$BUILD/wasm_grow" STRESS_GROW=6 STRESS_FRAMES=$FR STRESS_SAMPLE=$SM node "$HERE/stress.mjs" | grep -E "summary|golden|PASS|FAIL|eval|slow-eval"
negctl() {   # negctl <label> <env...>: stress.mjs が exit 1 で落ちること
  local label="$1"; shift; local rc=0 out
  out="$(env "$@" node "$HERE/stress.mjs" 2>&1)" || rc=$?
  if [ "$rc" -ne 1 ]; then echo "[stress.sh] negctl $label: exit=$rc (want 1) — 判定が不合格を検出していない" >&2; echo "$out" | tail -8 >&2; exit 1; fi
  echo "[stress.sh] negctl $label OK: exit 1 ($(echo "$out" | grep -m1 'FAIL:' | cut -c1-120))"
}
echo "[stress.sh] 3/4 ネガコン burst (200000 move 同期 push → 入力リング drop を検出)"
negctl burst STRESS_FAULT=burst
echo "[stress.sh] 4/4 ネガコン leak (後半も memory.grow → 後半増加を検出)"
negctl leak STRESS_FAULT=leak STRESS_FRAMES=$NFR STRESS_SAMPLE=$((NFR / 4)) GUI_WASM_DIR="$BUILD/wasm_grow"
echo "[stress.sh] ALL PASS"
