#!/usr/bin/env bash
# WIN-22 (#3353): CreateFruityInstance の閉包 (boot7) を IR に取り込み、boot 実行と cfi_probe の停止点を記録する。
#   EMSDK_ENV=<[EMSDK] の emsdk_env.sh> RETDEC=<[RETDEC] の bin/retdec-decompiler> bash tools/gui/flengine/cfi_boot7.sh
# 前提: FL_WIN64_DIR (fl-win64)・tools/m11/work (work-m11)・boot6.lift.ll (無ければ m11_wndseed.sh を先に)・apt-mingw。
# 出力: $GF_W/res/boot_b7.json・cfi_b7.json・cfi_closure.json。名前付きの JS スタックは -g2 の診断 build ($GF_W/diag/w) で取る
#   (build.sh の -g1 では関数名が消えるため。診断 build は build.sh を sed で -g2 にした複製。コミットしない)。
# 終了コード: 0 = 手順完了 (停止点の判定は出力 JSON を読む) / 2 = 前提欠如・手順失敗。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; source "$HERE/env.sh"
M="$GF_M11"; R="$GF_W/res"; D="$GF_W/diag"; mkdir -p "$R" "$D"
S() { echo "[cfi_boot7] $*"; }
[ -n "${FL_WIN64_DIR:-}" ] && [ -f "$FL_WIN64_DIR/extracted/block00031_PE.bin" ] || { S "前提欠如: FL_WIN64_DIR/extracted/block00031_PE.bin"; exit 2; }
PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
[ -f "$M/work/boot6.lift.ll" ] || { S "前提欠如: $M/work/boot6.lift.ll (m11_wndseed.sh)"; exit 2; }

# 1. boot7 を含まない IR を作り直す (閉包は boot7 の無い IR に対して求める)
rm -f "$M/work/boot7.lift.ll"
( cd "$M" && bash m11_gen_ir2.sh && bash m11_build.sh ) > "$R/cfi_pre.log" 2>&1 || { S "boot7 無しの IR 生成に失敗 ($R/cfi_pre.log)"; exit 2; }
# 2. CreateFruityInstance (0x1375990) の閉包のうち現 IR に無い関数の ranges
python3 "$HERE/gf_seed_closure.py" --pe "$PE" --ir "$M/work/boot_final3.ll" --seed 0x1375990 \
  --json-out "$R/cfi_closure.json" --ranges-out "$M/work/boot_ranges_cfi.txt" > "$R/cfi_closure.out" 2>&1 || { S "閉包の計算に失敗"; exit 2; }
# 3. RetDec で boot7 を lift (m11_lift.sh は ranges を絶対パスで受ける)
( cd "$M" && bash m11_lift.sh "$M/work/boot_ranges_cfi.txt" boot7 780 ) > "$R/cfi_lift.log" 2>&1 || { S "boot7 の lift に失敗 ($R/cfi_lift.log)"; exit 2; }
# 4. boot7 を含む IR を作り直す (REPORT_APPENDIX_2880 §9-2 と同じ順)
( cd "$M" && bash m11_gen_ir2.sh && bash m11_build.sh ) > "$R/cfi_post.log" 2>&1 || { S "boot7 込みの IR 生成に失敗 ($R/cfi_post.log)"; exit 2; }
# 5. 名前付きスタックを取る診断 build (-g2 の複製。動作は build.sh と同じ)
sed -e "s#^HERE=.*#HERE=$HERE; source \"\$HERE/env.sh\"#" -e 's/-g1/-g2/g' "$HERE/build.sh" > "$D/build_g2.sh"
GF_W="$D/w" bash "$D/build_g2.sh" > "$R/cfi_build_g2.log" 2>&1 || { S "診断 build に失敗 ($R/cfi_build_g2.log)"; exit 2; }
WASM="$D/w/m11_gui.cjs"
# 6. boot 実行 (run.mjs) と cfi_probe (boot の失敗スタックも出力に入る)
node "$HERE/run.mjs" --wasm "$WASM" --out "$R/boot_b7.json" > /dev/null 2>&1
node "$HERE/cfi_probe.mjs" --wasm "$WASM" --out "$R/cfi_b7.json" > /dev/null 2>&1
python3 - "$R" <<'PY'
import json, sys
r = sys.argv[1]
b = json.load(open(r + '/boot_b7.json'))
c = json.load(open(r + '/cfi_b7.json'))
print('closure new functions:', len(json.load(open(r + '/cfi_closure.json'))['new_functions']))
print('boot:', {k: b[k] for k in ('dllmain_done', 'boot_threw', 'boot_failfast', 'units_run', 'init_count')})
print('cfi boot:', c['boot'].get('ok'), c['boot'].get('err'))
print('cfi call:', c['call'].get('returned'), c['call'].get('err'))
for l in (c['boot'].get('stack') or [])[:6] + (c['call'].get('stack') or [])[:6]:
    print('  stack:', l)
PY
S "done (出力: $R)"
