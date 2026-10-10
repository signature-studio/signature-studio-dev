#!/usr/bin/env bash
# shimx_link 純リンク (--soft, --fix 無し) の A/B: 修正前 IR (boot_final.prealloca.ll) での survey を取得する。
#   bash tools/m11/alloca/ab_baseline.sh
# 注意: work/boot_final3.ll を一時的に修正前版に差し替えて build.sh --soft し、元に戻して再度 build する。
#       (mainline の work/m11_boot.cjs には触らない)
set -u
cd "$(dirname "$0")"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
M11=..
step() { echo "[ab_base] $*"; }

[ -f "$M11/work/boot_final.prealloca.ll" ] || { step "退避 IR 無し: 先に e2e.sh を実行"; exit 1; }

# widened boot_final3.ll を退避
cp "$M11/work/boot_final3.ll" work/boot_final3.alloca.keep.ll
# baseline boot_final3.ll を生成
python3 "$M11/m11_post.py" "$M11/work/boot_final.prealloca.ll" "$M11/work/boot_final3.ll" | tail -1
# baseline pure ビルド (既存の widened pure 成果物を退避)
for ext in cjs cjs.wasm; do
  [ -f "$M11/work/shimx_link/m11_sx_plain_soft.$ext" ] && cp "$M11/work/shimx_link/m11_sx_plain_soft.$ext" "work/m11_sx_plain_soft_alloca.$ext"
done
(cd "$M11/shimx_link" && bash build.sh --soft) > work/sxbuild_soft_base.log 2>&1 || { step "baseline build FAILED"; tail -5 work/sxbuild_soft_base.log; exit 1; }
tail -1 work/sxbuild_soft_base.log
# baseline 実行 (起動 + survey)
node "$M11/shimx_link/run_trace.mjs" "$M11/work/shimx_link/m11_sx_plain_soft.cjs" > results/run/sx_plain_soft_BASE.out 2>&1 || true
grep SXL_RESULT results/run/sx_plain_soft_BASE.out | cut -c1-360 || true
node "$M11/shimx_link/survey_trace.mjs" "$M11/work/shimx_link/m11_sx_plain_soft.cjs" --out results/baseline > results/run/sx_plain_soft_BASE_survey.out 2>&1 || true
grep SXL_SURVEY results/run/sx_plain_soft_BASE_survey.out | cut -c1-300 || true

# 復元 (widened) + 再ビルド (成果物を widened 版に戻す)
cp work/boot_final3.alloca.keep.ll "$M11/work/boot_final3.ll"
(cd "$M11/shimx_link" && bash build.sh --soft) > work/sxbuild_soft_restore.log 2>&1 || { step "restore build FAILED"; tail -5 work/sxbuild_soft_restore.log; exit 1; }
tail -1 work/sxbuild_soft_restore.log
step "done (baseline survey: results/baseline/m11_sx_plain_soft.survey.json)"
