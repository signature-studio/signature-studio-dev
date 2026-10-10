#!/usr/bin/env bash
# entry_e2e.sh — CAB-137 (OTT-T4): VST 入口拡張 lift の 1 コマンド検収。
#   bash tools/ott/entry/entry_e2e.sh [--quick]
#   env: ENTRY_SKIP_COV=1  native 単歩 coverage の再取得を省略 (work/entrylift/cov_entry.json を再利用)
#        ENTRY_SKIP_LIFT=1 lift/emcc を省略 (既存 ottl_entry.cjs を再利用)
# 判定 (exit 0 = PASS): scenario matrix 全部で native 実機械語と (rax/xmm0/buf/obj/heap/alloc 配置) 一致、
#   かつ tools/ott/ott_e2e.sh (DSP 本筋) も引き続き PASS。
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
ENTRY="$OTT/entry"
OUT="$OTT/work/entrylift"
DLL=/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll
NODE_BIN="$(command -v node || true)"; [ -n "$NODE_BIN" ] || NODE_BIN="$(ls /opt/emsdk/node/*/bin/node 2>/dev/null | head -1)"
export NODE="$NODE_BIN"
[ -f "$DLL" ] || { echo "[entry_e2e] $DLL 無し" >&2; exit 2; }
QUICK=""; [ "${1:-}" = "--quick" ] && { QUICK=--quick; export ENTRY_SKIP_COV=1 ENTRY_SKIP_LIFT=1; }
mkdir -p "$OUT"

echo "[1/7] scenario 定義生成"
python3 "$ENTRY/entry_scen.py" "$OUT/scen.json"

echo "[2/7] native 参照ハーネス build (ott_native.c を include, audioMaster 実装)"
gcc -O1 -g -fPIC -shared -o "$OUT/libottnatentry.so" "$ENTRY/entry_native.c" "$OTT/native/ms_call.S" -I"$OTT/rt" -I"$ENTRY"

if [ "${ENTRY_SKIP_COV:-0}" != "1" ] || [ ! -f "$OUT/cov_entry.json" ]; then
  echo "[3/7] native 単歩 coverage (VST 入口 + DSP、約 6〜8 分)"
  python3 -u "$ENTRY/entry_nat.py" --out "$OUT/nat_covraw.json" --cov "$OUT/cov_entry.json" 2>&1 | tail -2
else
  echo "[3/7] coverage 再利用 ($OUT/cov_entry.json)"
fi

if [ "${ENTRY_SKIP_LIFT:-0}" != "1" ]; then
  echo "[4/7] lift (x64c + 入口 roots + overrides) → emcc"
  bash "$ENTRY/lift_entry.sh" "$OUT/cov_entry.json" 2>&1 | grep -E "^\[|functions" | tail -4
else
  echo "[4/7] lift 再利用 ($OUT/ottl_entry.cjs)"
fi

echo "[5/7] scenario matrix: wasm (ott_run) → alog 収集 → native (alloc replay) "
python3 -u "$ENTRY/run_matrix.py" "$OUT/ottl_entry.cjs" "$OUT/matrix" $QUICK 2>&1 | tail -3

echo "[6/7] 突合判定 + 差分表"
python3 -u "$ENTRY/cmp_entries.py" "$OUT/matrix/nat_result.json" "$OUT/matrix/wasm_result.json" \
  --cov "$OUT/cov_entry.json" --covdsp "$OTT/ref/cov_all.json" \
  --out "$OUT/summary.json" --table "$OUT/fn_table.md" | tail -4

echo "[7/7] 既存 DSP e2e の継続性確認 (tools/ott/ott_e2e.sh)"
OTT_SKIP_INFO=1 bash "$OTT/ott_e2e.sh" 2>&1 | tail -2
echo "[entry_e2e] PASS"
