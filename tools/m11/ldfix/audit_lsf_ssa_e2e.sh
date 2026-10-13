#!/usr/bin/env bash
# audit_lsf_ssa_e2e.sh — #510 (LD-10) 1 コマンド再現。PE (fl-win64) 無しで work-m11 / work-liftdiff だけで走る。
#   1/5 audit_lsf.py (#484) の集計 (lsf 90 / 解決不能 370 site / 169 関数) と audit_lsf_ssa.py の列挙が一致するか (自己検査)
#   2/5 audit_lsf_ssa.py (alg1 個数収支 + alg2 宛先照合) を boot_final3.ll に実行
#   3/5 window_recount.py (データフロー無しの独立再計算)
#   4/5 dyn_xcheck.py (liftdiff の動的差分 batch_closure.jsonl との突合 = 動的方式の感度/被覆)
#   5/5 ネガティブコントロール (negctl_510.sh)
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

step "1/5 audit_lsf.py (#484) の集計"
"$PY" "$HERE/audit_lsf.py" "$IR" "$IMG" "$CFG" | head -1

step "2/5 audit_lsf_ssa.py"
"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa.json"

step "3/5 window_recount.py (独立再計算)"
"$PY" "$HERE/window_recount.py" "$IR" "$IMG" "$CFG" "$OUT/ssa.json"

step "4/5 dyn_xcheck.py"
if [ -f "$LW/m11/batch_closure.jsonl" ]; then "$PY" "$HERE/dyn_xcheck.py" "$OUT/ssa.json" "$LW/m11/batch_closure.jsonl"; else echo "  (work-liftdiff 未展開: skip)"; fi

step "5/5 ネガティブコントロール"
M11_WORK="$W" PY="$PY" bash "$HERE/negctl_510.sh"
