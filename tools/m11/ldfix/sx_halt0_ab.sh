#!/usr/bin/env bash
# sx_halt0_ab.sh — CAB-131: halt0 対応表更新用の shimx survey A/B (--trace --soft --fix = CAB-129 足場)。
#   base (ldfix 無し) / fix (ldfix 有り) の両方を今日の harness 状態 (CAB-177 由来の cbtrans 込み) で実行し,
#   CAB-129 時の baseline (alloca/results/survey/m11_sx_trace_soft_fix.survey.json) とも比較する。
#   成果物: ldfix/work/sxhalt0_{base,fix}/m11_sx_trace_soft_fix.survey.json + 対応表 JSON
# 注意: work/boot_final3.ll を差し替える (他 agent の同時 build と競合しうる; 単発実行のこと)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
REPO="$(cd -- "$M11/../.." && pwd)"
cd "$REPO"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
BASE_IR="$HERE/work/ir_base_noldfix.ll"
FIX_IR="$HERE/work/ir_fix_embedded.ll"

step() { echo "[sx_halt0_ab] $(date +%H:%M:%S) $*"; }
mark() { touch "$HERE/work/sxh_$1.done"; }
done_p() { [ -f "$HERE/work/sxh_$1.done" ]; }

for V in base fix; do
  if done_p "$V"; then step "$V: done マーカーあり skip"; continue; fi
  IR="$BASE_IR"; [ $V = fix ] && IR="$FIX_IR"
  step "[$V] alloca 適用 → m11_post → boot_final3.ll 差替え"
  python3 "$M11/alloca/m11_alloca.py" "$IR" "$HERE/work/sxh_alloca_$V.ll" --report "$HERE/work/sxh_alloca_$V.json" > /dev/null || exit 1
  python3 "$M11/m11_post.py" "$HERE/work/sxh_alloca_$V.ll" "$M11/work/boot_final3.ll" --report "$HERE/work/sxh_post_$V.json" > /dev/null || exit 1
  step "[$V] shimx_link build --trace --soft --fix"
  (cd "$M11/shimx_link" && bash build.sh --trace --soft --fix) > "$HERE/work/sxh_build_$V.log" 2>&1 || { step "FAILED: build/$V"; tail -5 "$HERE/work/sxh_build_$V.log"; exit 1; }
  tail -1 "$HERE/work/sxh_build_$V.log"
  step "[$V] survey_trace"
  node "$M11/shimx_link/survey_trace.mjs" "$M11/work/shimx_link/m11_sx_trace_soft_fix.cjs" --out "$HERE/work/sxhalt0_$V" > "$HERE/work/sxh_survey_$V.out" 2>&1 || true
  grep SXL_SURVEY "$HERE/work/sxh_survey_$V.out" | cut -c1-260 || true
  mark "$V"
done
step "done"
exit 0
