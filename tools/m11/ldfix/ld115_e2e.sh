#!/usr/bin/env bash
# ld115_e2e.sh — #2447 (LD-115) 1 コマンド再現。666a60 のループの修復 (fix_ld115.py) を検証する。
#   1/5 現行 ldfix (ldfix.py) → fix_ld108.py を work/boot_final.prealloca.ll に掛けて修復前 IR を作る (本番 m11_gen_ir2.sh と同じ順序・同じ pass)。
#       修復前 IR から 2 版を作る: MID = 回数初期値だけ直す / POST = 回数初期値 + ループ内 store を直す
#   2/5 3 版 (修復前 / MID / POST) それぞれで wasm を build (m11_build.sh。ir_conditions は ldfix=applied ld108=applied)
#   3/5 666a60 を 3 版の wasm で直接呼ぶ (dyn_ld115.mjs。期待: 修復前は trap、MID は slot.f16 のみ FAIL、POST は全 PASS)
#   4/5 survey 942 unit を修復前 / POST で測る
#   5/5 unit 単位の突合 (ok 退行 0 であること)
# 前提: tools/m11/work に work-m11 の展開 (boot_final.prealloca.ll・m11_image.bin・boot*.drc.config.json)、
#       FL_WIN64_DIR (fl-win64 の展開先 = extracted/block00031_PE.bin)、[EMSDK] (docs/REFERENCES.md)。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/m11/ldfix/ld115_e2e.sh
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
W="$M11/work"
: "${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 の展開先) を指定してください}"
OUT="${RUNNER_TEMP:-/tmp}/ld115_e2e"; rm -rf "$OUT"; mkdir -p "$OUT/pre" "$OUT/mid" "$OUT/post"
PE_QS="$FL_WIN64_DIR/extracted/block00031_PE.bin"
PY="${PY:-python3}"
step() { echo "[ld115_e2e] $*"; }
# work/boot_final.ll と ir_conditions.json を書き換えるので、終了時に元へ戻す
cp "$W/boot_final.ll" "$OUT/orig_boot_final.ll"
[ -f "$W/ir_conditions.json" ] && cp "$W/ir_conditions.json" "$OUT/orig_ir_conditions.json"
restore() {
  cp "$OUT/orig_boot_final.ll" "$W/boot_final.ll"
  [ -f "$OUT/orig_ir_conditions.json" ] && cp "$OUT/orig_ir_conditions.json" "$W/ir_conditions.json"
}
trap restore EXIT

step "1/5 現行 ldfix → fix_ld108 (修復前) と修復版 IR"
"$PY" "$M11/ldfix/ldfix.py" "$W/boot_final.prealloca.ll" "$OUT/ldfix.ll" --pe "$PE_QS" --report "$OUT/ldfix_report.json" || exit 1
"$PY" "$M11/ldfix/fix_ld108.py" "$OUT/ldfix.ll" "$OUT/pre.ll" || exit 1
"$PY" "$HERE/fix_ld115.py" "$OUT/pre.ll" "$OUT/mid.ll" --only count || exit 1
"$PY" "$HERE/fix_ld115.py" "$OUT/pre.ll" "$OUT/post.ll" || exit 1
for k in mid post; do diff "$OUT/pre.ll" "$OUT/$k.ll" > "$OUT/ir_$k.diff"; echo "[ld115_e2e] $k の IR diff 行数: $(wc -l < "$OUT/ir_$k.diff")"; done

step "2/5 wasm build (修復前 → $OUT/pre, 中間 → $OUT/mid, 修復後 → $OUT/post)"
cd "$M11" || exit 1
for k in pre mid post; do
  cp "$OUT/$k.ll" "$W/boot_final.ll"
  python3 m11_cond.py --reset ldfix=applied ld108=applied pe="$PE_QS" && python3 m11_cond.py --bind "$W/boot_final.ll" || exit 1
  rm -f "$W/obj/boot.o"
  timeout 1500 bash m11_build.sh > "$OUT/build_$k.log" 2>&1 || { echo "build 失敗: $OUT/build_$k.log"; exit 1; }
  cp "$W/m11_boot.cjs" "$OUT/$k/m11_boot.cjs"; cp "$W/m11_boot.cjs.wasm" "$OUT/$k/m11_boot.cjs.wasm"
done

step "3/5 666a60 の動的確認 (dyn_ld115.mjs)"
node "$HERE/dyn_ld115.mjs" "$OUT/pre/m11_boot.cjs" "$OUT/mid/m11_boot.cjs" "$OUT/post/m11_boot.cjs" "$W/m11_image.bin" | tee "$OUT/dyn.txt"

step "4/5 survey 942 unit (修復前 / 修復後)"
cp "$OUT/pre/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/pre/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_pre.json" | tail -1
cp "$OUT/post/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/post/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_post.json" | tail -1

step "5/5 突合"
"$PY" trap_triage/survey_diff.py "$OUT/sv_pre.json" "$OUT/sv_post.json" | tail -8
echo "[ld115_e2e] done: $OUT"
