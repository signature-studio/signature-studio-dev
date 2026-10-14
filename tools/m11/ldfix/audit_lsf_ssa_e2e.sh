#!/usr/bin/env bash
# audit_lsf_ssa_e2e.sh — #510 (LD-10) 1 コマンド再現。PE (fl-win64) 無しで work-m11 / work-liftdiff だけで走る。
#   1/7 audit_lsf.py (#484) の集計 (lsf 90 / 解決不能 370 site / 169 関数) と audit_lsf_ssa.py の列挙が一致するか (自己検査)
#   2/7 audit_lsf_ssa.py (alg1 個数収支 + alg2 宛先照合) を boot_final3.ll に実行
#   3/7 window_recount.py (データフロー無しの独立再計算)
#   4/7 dyn_xcheck.py (liftdiff の動的差分 batch_closure.jsonl との突合 = 動的方式の感度/被覆)
#   5/7 tally_510.py (results/manual_verdicts_510.jsonl の目視判定との突合・最終集計)
#   6/7 ネガティブコントロール (negctl_510.sh)
#   7/7 spill_classify_1161.py (LD-35 spill 宛 178 site の分類表と脱落関数の和集合・results/ と一致)
# 使い方: bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh     環境変数: M11_WORK (既定 tools/m11/work) / LD_WORK (既定 tools/liftdiff/work) / PY
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
LW="${LD_WORK:-$REPO/tools/liftdiff/work}"
OUT="${RUNNER_TEMP:-/tmp}/audit_lsf_ssa_e2e"; mkdir -p "$OUT"
if [ -z "${PY:-}" ]; then
  if python3 -c 'import capstone, pefile' 2>/dev/null; then PY=python3
  else uv venv "$OUT/venv" -q && uv pip install -q --python "$OUT/venv/bin/python" capstone pefile && PY="$OUT/venv/bin/python"; fi
fi
CFG="$W/boot*.drc.config.json"; IMG="$W/m11_image.bin"; IR="$W/boot_final3.ll"
step() { echo "[audit_lsf_ssa_e2e] $*"; }

step "1/7 audit_lsf.py (#484) の集計"
"$PY" "$HERE/audit_lsf.py" "$IR" "$IMG" "$CFG" | head -1

step "2/7 audit_lsf_ssa.py"
"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa.json"

step "3/7 window_recount.py (独立再計算)"
"$PY" "$HERE/window_recount.py" "$IR" "$IMG" "$CFG" "$OUT/ssa.json"

step "4/7 dyn_xcheck.py"
if [ -f "$LW/m11/batch_closure.jsonl" ]; then "$PY" "$HERE/dyn_xcheck.py" "$OUT/ssa.json" "$LW/m11/batch_closure.jsonl"; else echo "  (work-liftdiff 未展開: skip)"; fi

step "5/7 tally_510.py"
if [ -f "$LW/m11/batch_closure.jsonl" ]; then B="$LW/m11/batch_closure.jsonl"; else B=""; fi
"$PY" "$HERE/tally_510.py" "$OUT/ssa.json" "$HERE/results/manual_verdicts_510.jsonl" $B "$OUT/drops_510.tsv"
cmp "$OUT/drops_510.tsv" "$HERE/results/drops_510.tsv" && echo "[drops_510.tsv] results/ と一致"

step "6/7 ネガティブコントロール"
M11_WORK="$W" PY="$PY" bash "$HERE/negctl_510.sh"

step "7/7 spill_classify_1161.py (LD-35)"
"$PY" "$HERE/spill_classify_1161.py" "$OUT/ssa.json" "$OUT/spill178_1161.tsv"
cmp "$OUT/spill178_1161.tsv" "$HERE/results/spill178_1161.tsv" && echo "[spill178_1161.tsv] results/ と一致"
