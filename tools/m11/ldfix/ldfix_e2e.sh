#!/usr/bin/env bash
# ldfix_e2e.sh — CAB-231 load 修復 pass の 1 コマンド検証 (tools/m11/ldfix 内で完結)。
#   既存 tools/m11 のファイルは変更しない (ラッパのみ)。
#
#   bash tools/m11/ldfix/ldfix_e2e.sh            # pass 適用 + emcc 検証 + stage4 回帰 (base/fix) + 判定
#   bash tools/m11/ldfix/ldfix_e2e.sh --batch    # + liftdiff closure 全数 batch (base/fix 各約 10 分)
#
# 前提: tools/m11/work/{boot_final3.ll,m11_image.bin,m11_data.c,boot_final3_probes.json} (m11_e2e.sh 生成物),
#       tools/liftdiff/work/m11/boot_state.json (liftdiff --state auto 用), /opt/emsdk, node, capstone/pefile
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
cd "$REPO"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
source "$REPO/tools/shared/env.sh"
PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
BATCH=0
for a in "$@"; do case "$a" in --batch) BATCH=1 ;; esac; done

step() { echo "[ldfix_e2e] $*"; }
fail() { echo "[ldfix_e2e] FAILED: $*"; exit 1; }

[ -f tools/m11/work/boot_final3.ll ] || fail "tools/m11/work/boot_final3.ll 無し (bash tools/m11/m11_e2e.sh を先に)"
[ -f "$PE" ] || fail "PE 無し"

mkdir -p "$HERE/work/stage4"
step "1/5 修復 pass 適用: boot_final3.ll -> work/ldfix_fixed.ll"
python3 "$HERE/ldfix.py" tools/m11/work/boot_final3.ll "$HERE/work/ldfix_fixed.ll" \
  --pe "$PE" --report "$HERE/work/ldfix_report.json" || fail "ldfix.py"
step "1b/5 function_450560 の 2 段 deref 復元 (#2502・機械語検証付き): work/ldfix_fixed.ll を上書き"
python3 "$HERE/fix_450560.py" "$HERE/work/ldfix_fixed.ll" "$HERE/work/ldfix_fixed_450560.ll" --pe "$PE" || fail "fix_450560.py"
mv "$HERE/work/ldfix_fixed_450560.ll" "$HERE/work/ldfix_fixed.ll"
step "1c/5 同類型の site 単位修復 (#3326・機械語照合付き): work/ldfix_fixed.ll を上書き"
python3 "$HERE/fix_site_3326.py" "$HERE/work/ldfix_fixed.ll" "$HERE/work/ldfix_fixed_site.ll" --pe "$PE" || fail "fix_site_3326.py"
mv "$HERE/work/ldfix_fixed_site.ll" "$HERE/work/ldfix_fixed.ll"
step "1d/5 function_44f040 / 47cf10 / 6074b0 の *arg1 読出し脱落 (#3372・機械語照合付き): work/ldfix_fixed.ll を上書き"
python3 "$HERE/fix_site_3372.py" "$HERE/work/ldfix_fixed.ll" "$HERE/work/ldfix_fixed_3372.ll" --pe "$PE" || fail "fix_site_3372.py"
mv "$HERE/work/ldfix_fixed_3372.ll" "$HERE/work/ldfix_fixed.ll"
python3 - <<'PYEOF'
import json
r = json.load(open('tools/m11/ldfix/work/ldfix_report.json'))
print('[ldfix_e2e] 修復関数数: F1(load_dropped)=%d F2(spill_slot)=%d F3a(old-value)=%d F3b(count-load)=%d F3c(store-arg)=%d / %d 関数中'
      % (r['f1_fns'], r['f2_fns'], r['f3a_fns'], r['f3b_fns'], r['f3c_fns'], r['functions_processed']))
PYEOF

step "2/5 emcc 構文検証 (修復 IR がコンパイル通ること)"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
export TMPDIR="$HERE/work/tmp"; mkdir -p "$TMPDIR"
emcc -c "$HERE/work/ldfix_fixed.ll" -o "$HERE/work/ldfix_fixed.o" -w -Wno-error=int-conversion -O0 -g1 || fail "emcc (fixed IR)"

step "3/5 stage4 回帰 (m11_e2e.sh 相当: base = 修復前 / fix = 修復後)"
bash "$HERE/stage4.sh" tools/m11/work/boot_final3.ll base | tee "$HERE/work/stage4_base.log" | grep STAGE4_RESULT
S4_EXTRA_CF=-DM11_OV_NO_450560 bash "$HERE/stage4.sh" "$HERE/work/ldfix_fixed.ll" fix | tee "$HERE/work/stage4_fix.log" | grep STAGE4_RESULT

step "4/5 unit survey (942 unit 隔離: base/fix)"
for N in base fix; do
  (export S4_NAME=$N; export S4_IMAGE=tools/m11/work/m11_image.bin; \
   timeout 900 node "$HERE/survey_stage4.mjs" > "$HERE/work/stage4/$N/e2e_survey.out" 2> "$HERE/work/stage4/$N/e2e_survey.err" || true) &
done
wait
for N in base fix; do
  grep -o 'M11_SURVEY {.*}' "$HERE/work/stage4/$N/e2e_survey.out" | head -c 200; echo " <- $N"
done

step "5/5 判定"
python3 "$HERE/judge_e2e.py"

if [ "$BATCH" = 1 ]; then
  step "liftdiff closure 全数 batch (base / fix 各約 10 分)"
  python3 tools/liftdiff/liftdiff.py batch tools/liftdiff/targets/m11.json --set closure --shards 12 --state auto \
    --out "$HERE/work/batch_base.jsonl" > "$HERE/work/batch_base.log" 2>&1
  python3 tools/liftdiff/liftdiff.py batch "$(python3 "$HERE/render_target.py" "$HERE/targets/m11_ldfix.json")" --set closure --shards 12 --state auto \
    --out "$HERE/work/batch_ldfix.jsonl" > "$HERE/work/batch_ldfix.log" 2>&1
  python3 tools/liftdiff/liftdiff.py summary "$HERE/work/batch_base.jsonl" | head -8
  python3 tools/liftdiff/liftdiff.py summary "$HERE/work/batch_ldfix.jsonl" | head -8
fi
exit 0
