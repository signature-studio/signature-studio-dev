#!/usr/bin/env bash
# fix_d17_e2e.sh — #968 (LD-21) D17 修復 pass の 1 コマンド再現。PE 無しで work-m11 だけで走る。
#   1/6 audit_lsf_ssa.py (修復前) → 2/6 fix_d17.py で修復 → 3/6 audit_lsf_ssa.py (修復後)
#   → 4/6 spill 宛 CELL_COLLAPSED 37 site の判定対応 (#1169・spill37_1169.py)
#   → 5/6 spill 宛 TRUE_DROP の修復 pass (#2794・fix_spill_2794.py) + 修復後 audit + 突合 (check_spill_2794.py) + ネガコン
#   → 6/6 emcc 構文検証 (修復 IR = 5/6 の出力)
# 使い方: bash tools/m11/ldfix/fix_d17_e2e.sh     環境変数: M11_WORK (既定 tools/m11/work) / PY
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
OUT="${RUNNER_TEMP:-/tmp}/fix_d17_e2e"; mkdir -p "$OUT"
PY="${PY:-python3}"
IR="$W/boot_final3.ll"; IMG="$W/m11_image.bin"; CFG="$W/boot*.drc.config.json"
step() { echo "[fix_d17_e2e] $*"; }

step "1/6 audit (修復前)"
"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa_base.json" | head -1
step "2/6 fix_d17.py"
"$PY" "$HERE/fix_d17.py" "$IR" "$OUT/ssa_base.json" "$OUT/boot_d17.ll" --report "$OUT/d17_report.json" || exit 1
step "3/6 audit (修復後)"
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_d17.ll" "$IMG" "$CFG" --json "$OUT/ssa_fix.json" | head -1
step "4/6 spill 宛 CELL_COLLAPSED の判定対応 (#1169)"
"$PY" "$HERE/spill37_1169.py" "$OUT/spill37_1169.tsv" "$OUT/ssa_base.json" "$OUT/ssa_fix.json" || exit 1
cmp "$OUT/spill37_1169.tsv" "$HERE/results/spill37_1169.tsv" || { echo "[fix_d17_e2e] FAIL: spill37_1169.tsv が results と不一致" >&2; exit 1; }
step "5/6 spill 宛 TRUE_DROP の修復 pass (#2794): 1 対 1 のゲート付き・修復後 audit・突合"
"$PY" "$HERE/fix_spill_2794.py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_spill.ll" \
  --tsv "$HERE/results/spill37_1169.tsv" --report "$OUT/spill_2794.json" || exit 1
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_spill.ll" "$IMG" "$CFG" --json "$OUT/ssa_spill.json" | head -1
"$PY" "$HERE/check_spill_2794.py" "$OUT/ssa_base.json" "$OUT/ssa_spill.json" "$OUT/spill_2794.json" "$HERE/results/spill37_1169.tsv" "$OUT/spill_repair_2794.tsv" || exit 1
cmp "$OUT/spill_repair_2794.tsv" "$HERE/results/spill_repair_2794.tsv" || { echo "[fix_d17_e2e] FAIL: spill_repair_2794.tsv が results と不一致" >&2; exit 1; }
"$PY" "$HERE/check_spill_2794.py" "$OUT/ssa_base.json" "$OUT/ssa_fix.json" "$OUT/spill_2794.json" "$HERE/results/spill37_1169.tsv" /dev/null > /dev/null
if [ $? -eq 0 ]; then echo "[fix_d17_e2e] FAIL: ネガコン (修復を外した audit) が PASS した" >&2; exit 1; fi
echo "[fix_d17_e2e] ネガコン: 修復を外した audit では突合が FAIL (期待どおり)"
nogate="$("$PY" "$HERE/fix_spill_2794.py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_spill_nogate.ll" \
  --tsv "$HERE/results/spill37_1169.tsv" --gate none)" || exit 1
echo "$nogate" | head -1
echo "$nogate" | head -1 | grep -q '^spill fixed=24 skipped=0 ' || { echo "[fix_d17_e2e] FAIL: ネガコン 2 (--gate none) が 24 件を書き換えない" >&2; exit 1; }
step "6/6 emcc 構文検証 (修復 IR)"
if ! source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1 || ! command -v emcc > /dev/null 2>&1; then
  echo "[fix_d17_e2e] FAIL: emsdk が無い (/opt/emsdk/emsdk_env.sh の source か emcc の検出に失敗)" >&2
  exit 2
fi
export TMPDIR="$OUT/tmp"; mkdir -p "$TMPDIR"
emcc -c "$OUT/boot_spill.ll" -o "$OUT/boot_spill.o" -w -Wno-error=int-conversion -O0 -g1 || { echo "[fix_d17_e2e] FAIL: emcc rc!=0" >&2; exit 1; }
echo "[fix_d17_e2e] emcc rc=0"
