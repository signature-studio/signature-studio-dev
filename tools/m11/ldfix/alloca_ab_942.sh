#!/usr/bin/env bash
# alloca_ab_942.sh — #942: snapshot IR に alloca 縮退修正 (alloca/m11_alloca.py・m11_build.sh の alloca 段と同じ呼出し) を当てて
#   通常 boot (stage4) と survey を A/B する。既存の測定系 (stage4.sh・run_stage4.mjs・survey_stage4.mjs) は変更しない (呼ぶだけ)。
#   variant: raw = boot_final3.ll そのまま / alloca = m11_alloca.py 適用 (全 2377 alloca) /
#            only44bae0 = raw の function_44bae0 の stack_var_-88 だけを [11 x i64] にした対照 (因果の切り分け)
#   使い方: FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/alloca_ab_942.sh
#   前提: tools/m11/work/boot_final3.ll・m11_image.bin・m11_data.c (work-m11 素材)・emsdk。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
cd "$REPO"
source "$REPO/tools/shared/env.sh"
SNAP=tools/m11/work/boot_final3.ll
IMG=$REPO/tools/m11/work/m11_image.bin
W="$HERE/work/ab942"
mkdir -p "$W"
[ -f "$SNAP" ] || { echo "[alloca_ab_942] $SNAP 無し (work-m11 素材を展開)"; exit 2; }

python3 tools/m11/alloca/m11_alloca.py "$SNAP" "$W/alloca.ll" --report "$W/alloca_report.json" > "$W/alloca.log" 2>&1 || { echo "[alloca_ab_942] m11_alloca.py 失敗"; exit 1; }
python3 - "$SNAP" "$W/only44bae0.ll" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
out, inside, done = [], False, False
for ln in open(src).read().split('\n'):
    if ln.startswith('define '):
        inside = '@function_44bae0(' in ln
    if inside and not done and ln.strip() == '%stack_var_-88 = alloca i64, align 8':
        ln, done = '  %stack_var_-88 = alloca [11 x i64], align 8', True
    out.append(ln)
assert done, 'function_44bae0 の stack_var_-88 が見つからない'
open(dst, 'w').write('\n'.join(out))
PYEOF

declare -A IRS=([raw]="$REPO/$SNAP" [alloca]="$W/alloca.ll" [only44bae0]="$W/only44bae0.ll")
for V in raw alloca only44bae0; do
  bash "$HERE/stage4.sh" "${IRS[$V]}" "ab942_$V" > "$W/stage4_$V.log" 2>&1 || { echo "[alloca_ab_942] stage4 build 失敗: $V"; tail -3 "$W/stage4_$V.log"; exit 1; }
done
for V in raw alloca only44bae0; do
  S4_NAME=ab942_$V S4_IMAGE=$IMG timeout 300 node "$HERE/run_stage4.mjs" 2>/dev/null | grep M11_RESULT | python3 -c "
import json, sys
d = json.loads(sys.stdin.read().split('M11_RESULT ', 1)[1])
print('STAGE4 $V', {k: d.get(k) for k in ['units_run', 'init_count', 'icall_ok', 'dllmain_done', 'threw']})"
  S4_NAME=ab942_$V S4_IMAGE=$IMG timeout 900 node "$HERE/survey_stage4.mjs" 2>/dev/null | grep -o 'M11_SURVEY {.*}' | python3 -c "
import json, sys
d = json.loads(sys.stdin.read().split('M11_SURVEY ', 1)[1])
print('SURVEY $V', {k: d.get(k) for k in ['ok', 'miss', 'trap', 'trap_kinds', 'boot_threw']})"
done
