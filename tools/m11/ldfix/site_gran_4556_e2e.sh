#!/usr/bin/env bash
# site_gran_4556_e2e.sh — #4556 (LD-224) 受入 1: site 単位の CELL_COLLAPSED 判定 (非既定) の 1 コマンド再現。
#   1/4 audit (修復前) → 2/4 fix_d17.py + fix_spill_2794.py で修復 (fix_d17_e2e.sh と同じ経路) → 3/4 audit (修復後)
#   → 4/4 site_gran_4556.py (修復前後の判定) → ネガコン: 修復を外した (修復前 IR を後の IR に使う) 判定で減少が 0
# 既定の audit の数値 (関数 × K) は変えない。本スクリプトは別の TSV / JSON を出すだけ。
# 使い方: bash tools/m11/ldfix/site_gran_4556_e2e.sh     環境変数: M11_WORK (既定 tools/m11/work) / PY / RUNNER_TEMP
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
W="${M11_WORK:-$HERE/../work}"
OUT="${RUNNER_TEMP:-/tmp}/site_gran_4556"; mkdir -p "$OUT"
PY="${PY:-python3}"
IR="$W/boot_final3.ll"; IMG="$W/m11_image.bin"; CFG="$W/boot*.drc.config.json"
step() { echo "[site_gran_4556_e2e] $*"; }

step "1/4 audit (修復前)"
"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa_base.json" | head -1 || exit 1
step "2/4 修復 (fix_d17 → fix_spill_2794: 1 対 1 のゲート付き)"
"$PY" "$HERE/fix_d17.py" "$IR" "$OUT/ssa_base.json" "$OUT/boot_d17.ll" --report "$OUT/d17_report.json" > /dev/null || exit 1
"$PY" "$HERE/fix_spill_2794.py" "$OUT/boot_d17.ll" "$OUT/ssa_base.json" "$IMG" "$CFG" "$OUT/boot_spill.ll" \
  --tsv "$HERE/results/spill37_1169.tsv" --report "$OUT/spill_2794.json" | head -1 || exit 1
step "3/4 audit (修復後)"
"$PY" "$HERE/audit_lsf_ssa.py" "$OUT/boot_spill.ll" "$IMG" "$CFG" --json "$OUT/ssa_spill.json" | head -1 || exit 1
step "4/4 site 単位の判定 (修復前後)"
"$PY" "$HERE/site_gran_4556.py" "$IR" "$OUT/boot_spill.ll" "$IMG" "$CFG" "$OUT/ssa_base.json" "$OUT/ssa_spill.json" \
  --tsv "$OUT/site_gran.tsv" --json "$OUT/site_gran.json" || exit 1
step "ネガコン: 修復を外した判定 (修復前 IR を両方に渡す)"
"$PY" "$HERE/site_gran_4556.py" "$IR" "$IR" "$IMG" "$CFG" "$OUT/ssa_base.json" "$OUT/ssa_base.json" \
  --tsv "$OUT/site_gran_neg.tsv" > "$OUT/neg.log" || exit 1
head -1 "$OUT/neg.log"
grep -q '^site 単位 (#4556・非既定): spill 宛 CELL_COLLAPSED 関数×K 判定の後 37 site / 22 関数 -> site 単位の後 37 site / 22 関数$' "$OUT/neg.log" \
  || { echo "[site_gran_4556_e2e] FAIL: ネガコンで減少が 0 にならない" >&2; exit 1; }
echo "[site_gran_4556_e2e] PASS (ネガコン: 修復を外すと site 単位の減少は 0)"
