#!/usr/bin/env bash
# fix_d17_e2e.sh — #968 (LD-21) D17 修復 pass の 1 コマンド再現。PE 無しで work-m11 だけで走る。
#   1/4 audit_lsf_ssa.py (修復前) → 2/4 fix_d17.py で修復 → 3/4 audit_lsf_ssa.py (修復後) → 4/4 emcc 構文検証
# 使い方: bash tools/m11/ldfix/fix_d17_e2e.sh     環境変数: M11_WORK (既定 tools/m11/work) / PY
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
OUT="${RUNNER_TEMP:-/tmp}/fix_d17_e2e"; mkdir -p "$OUT"
PY="${PY:-python3}"
IR="$W/boot_final3.ll"; IMG="$W/m11_image.bin"; CFG="$W/boot*.drc.config.json"
step() { echo "[fix_d17_e2e] $*"; }

step "1/4 audit (修復前)"
"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa_base.json" | head -1
step "2/4 fix_d17.py"
"$PY" "$HERE/fix_d17.py" "$IR" "$OUT/ssa_base.json" "$OUT/boot_d17.ll" --report "$OUT/d17_report.json" || exit 1
step "3/4 audit (修復後)"
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_d17.ll" "$IMG" "$CFG" --json "$OUT/ssa_fix.json" | head -1
step "4/4 emcc 構文検証 (修復 IR)"
if ! source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1 || ! command -v emcc > /dev/null 2>&1; then
  echo "[fix_d17_e2e] FAIL: emsdk が無い (/opt/emsdk/emsdk_env.sh の source か emcc の検出に失敗)" >&2
  exit 2
fi
export TMPDIR="$OUT/tmp"; mkdir -p "$TMPDIR"
emcc -c "$OUT/boot_d17.ll" -o "$OUT/boot_d17.o" -w -Wno-error=int-conversion -O0 -g1 || { echo "[fix_d17_e2e] FAIL: emcc rc!=0" >&2; exit 1; }
echo "[fix_d17_e2e] emcc rc=0"
