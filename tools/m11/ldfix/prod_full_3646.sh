#!/usr/bin/env bash
# prod_full_3646.sh — #3646: 本番 tools/m11/m11_build.sh 全体 (既定の経路) で通常起動・survey・寛容起動を測る。
#   既存の測定系・pass は変更しない (呼ぶだけ)。結果は REPORT_942_PRODORDER.md §9。
#   使い方: FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/prod_full_3646.sh [fix|base]
#   fix : 既定の IR (ldfix・ld108・ld115・src412770・r8b 適用)。m11_e2e.sh が IR を作る
#   base: M11_LDFIX=0 で IR を作り直す (ldfix 系を全て外す)。build は M11_ALLOW_LDFIX_DISABLED=1 で opt-in
#   lift 段: M11_SKIP_LIFT_FP=1 (work-m11 に lift_pe.sha256 が無い。PE 一致は未検証・REPORT §9.4)
#   出力: tools/m11/ldfix/work/prod3646/<mode>/ (gitignore)
set -uo pipefail
MODE="${1:-fix}"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
M11="$REPO/tools/m11"
OUT="$HERE/work/prod3646/$MODE"
mkdir -p "$OUT"
cd "$M11" || exit 2
source "$REPO/tools/shared/env.sh"
case "$MODE" in
  fix) ;;
  base)
    export M11_LDFIX=0 M11_ALLOW_LDFIX_DISABLED=1
    M11_LDFIX=0 bash m11_gen_ir2.sh > "$OUT/gen_ir2.log" 2>&1 || { echo "[prod3646] gen_ir2 失敗 ($OUT/gen_ir2.log)"; exit 1; } ;;
  *) echo "[prod3646] MODE は fix か base"; exit 2 ;;
esac
M11_SKIP_LIFT_FP=1 bash m11_e2e.sh > "$OUT/e2e.log" 2>&1; rc=$?
cp work/e2e_full.out work/e2e_survey.out work/e2e_tolerant.out work/ir_conditions.json work/link.log "$OUT/"
python3 m11_judge.py --require-stage 4 --min-survey-ok 800 > "$OUT/judge.txt" 2>&1; echo "[prod3646] judge rc=$?"
sha256sum work/boot_final.ll work/m11_boot.cjs.wasm > "$OUT/sha256.txt"
echo "[prod3646] $MODE e2e rc=$rc"
grep -o '"units_run":[0-9]*\|"threw":"[^"]*"\|"dllmain_done":[a-z]*' "$OUT/e2e_full.out" | head -3
grep "  ok=\|M11_TOLERANT gate" "$OUT/e2e.log" | cut -c1-200
