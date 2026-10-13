#!/usr/bin/env bash
# CAB-129 alloca 縮退修正 — 1 コマンド検収 (tools/m11/alloca/)
#
#   bash tools/m11/alloca/e2e.sh [--full]
#
# やること:
#   1. m11 mainline: closure IR (work/boot_final.ll) に m11_alloca.py を適用 (in-place, idempotent)
#      → m11_build.sh (増分) → 通常起動 (m11_run.mjs) + 942 unit survey (m11_survey.mjs) → m11_judge.py
#   2. shimx_link 純リンク (--soft, --fix 無し): run_trace (起動 unit 数) + survey_trace (942 unit 隔離)
#      ※ tools/m11/shimx_link は読取専用で運用 (build.sh は work/boot_final3.ll = pass 適用後 IR を自動で拾う)
#   3. 集計 (baseline との比較表) を results/ に保存
#
# 前提: bash tools/m11/m11_e2e.sh が一度通っていること (lift 成果物の生成)。
#       --full は lift からの全再生成 (pass は再適用される)。
# 注意: work/boot_final.ll は in-place 改変される (元は work/boot_final.prealloca.ll に退避)。
#       m11_e2e.sh を --full で再実行すると素の IR に戻るため、本スクリプトを再実行して再適用する。
set -u
cd "$(dirname "$0")"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
M11=..
FULL=0
for a in "$@"; do case "$a" in --full) FULL=1 ;; esac; done
step() { echo "[alloca_e2e] $*"; }

# 0. lift 成果物の確保 ------------------------------------------------------------
if [ ! -f "$M11/work/boot_final.ll" ] || [ $FULL = 1 ]; then
  step "m11_e2e.sh ($([ $FULL = 1 ] && echo --full || echo 成果物生成)) を実行"
  (cd "$M11" && bash m11_e2e.sh $([ $FULL = 1 ] && echo --full)) > work/m11_e2e_prepare.log 2>&1 || { step "m11_e2e FAILED"; tail -5 work/m11_e2e_prepare.log; exit 1; }
fi

# 1. pass 適用 (in-place, idempotent) ---------------------------------------------
if [ ! -f "$M11/work/boot_final.prealloca.ll" ]; then
  cp "$M11/work/boot_final.ll" "$M11/work/boot_final.prealloca.ll"
  step "素 IR を退避: work/boot_final.prealloca.ll"
fi
step "m11_alloca.py 適用 (in-place)"
python3 m11_alloca.py "$M11/work/boot_final.ll" "$M11/work/boot_final.ll" --report work/alloca_report.json || exit 1
python3 "$M11/m11_cond.py" --bind "$M11/work/boot_final.ll" || exit 1   # #680: 正規の pass なので指紋を更新 (m11_build.sh の検査用)

# 2. mainline build + 実行 --------------------------------------------------------
step "m11_build.sh (増分)"
(cd "$M11" && bash m11_build.sh) > work/build.log 2>&1 || { step "build FAILED"; tail -20 work/build.log; exit 1; }
tail -1 work/build.log
[ -f "$M11/work/m11_boot.cjs.wasm" ] || { step "wasm 未生成"; exit 1; }

step "実行 A: 通常起動 (DllMain attach → InitUnits ループ)"
(cd "$M11" && timeout 300 node m11_run.mjs > work/e2e_full.out 2>&1) || true
step "実行 B: 942 unit survey (m11_survey.mjs)"
(cd "$M11" && timeout 600 node m11_survey.mjs > work/e2e_survey.out 2>&1) || true
(cd "$M11" && python3 m11_judge.py) | tee work/judge.out | grep -E "reached_stage|stop_reason|units:|survey ok=|trap kinds|top trap" || true
cp "$M11/work/e2e_full.out" "$M11/work/e2e_survey.out" results/run/ 2>/dev/null

# 3. shimx_link 純リンク (--fix 無し) ---------------------------------------------
step "shimx_link build --soft (純リンク, --fix 無し)"
(cd "$M11/shimx_link" && bash build.sh --soft) > work/sxbuild_soft.log 2>&1 || { step "sx build FAILED"; tail -5 work/sxbuild_soft.log; exit 1; }
tail -1 work/sxbuild_soft.log
step "shimx_link 起動 (run_trace)"
node "$M11/shimx_link/run_trace.mjs" "$M11/work/shimx_link/m11_sx_plain_soft.cjs" > results/run/sx_plain_soft.out 2>&1 || true
grep SXL_RESULT results/run/sx_plain_soft.out | cut -c1-360 || true
step "shimx_link 942 unit survey (survey_trace)"
node "$M11/shimx_link/survey_trace.mjs" "$M11/work/shimx_link/m11_sx_plain_soft.cjs" --out results/survey > results/run/sx_plain_soft_survey.out 2>&1 || true
grep SXL_SURVEY results/run/sx_plain_soft_survey.out | cut -c1-300 || true
# 比較用: --fix 付き (fix_alloca.py は拡幅済みの上でほぼ no-op) も survey だけ実行
if [ -f "$M11/work/shimx_link/m11_sx_trace_soft_fix.cjs" ]; then
  (cd "$M11/shimx_link" && bash build.sh --trace --soft --fix) > work/sxbuild_fix.log 2>&1 || true
  node "$M11/shimx_link/survey_trace.mjs" "$M11/work/shimx_link/m11_sx_trace_soft_fix.cjs" --out results/survey > results/run/sx_trace_soft_fix_survey.out 2>&1 || true
  grep SXL_SURVEY results/run/sx_trace_soft_fix_survey.out | cut -c1-300 || true
fi
# mainline ビルドも同じ survey_trace 手順で (shimx REPORT の分類と揃える)
node "$M11/shimx_link/survey_trace.mjs" "$M11/work/m11_boot.cjs" --out results/survey > results/run/m11_boot_surveytrace.out 2>&1 || true
grep SXL_SURVEY results/run/m11_boot_surveytrace.out | cut -c1-300 || true

# 4. 集計 -------------------------------------------------------------------------
python3 summarize.py || true
exit 0
