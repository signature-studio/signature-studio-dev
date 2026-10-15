#!/usr/bin/env bash
# ld116_e2e.sh — #2513 (LD-116) 1 コマンド再現。666a60 の entry の回数 0 早期脱出 (fix_ld116.py) を検証する。
#   1/5 現行 ldfix → fix_ld108 → fix_ld115 (修復前 = post115。#2447 の修復後 IR) と、その上に fix_ld116 を掛けた修復後 IR (post116) を作る
#       (本番と同じ順序。中間版 pre/mid は dyn の 3 版の既存判定 (BASE TRAP / MID FAIL / NEW PASS) を同じ実行で再測定するために作る)
#   2/5 4 版 (pre / mid / post115 / post116) それぞれで wasm を build (m11_build.sh。ir_conditions は ldfix=applied ld108=applied)
#   3/5 666a60 を wasm で直接呼ぶ (dyn_ld115.mjs。既存の 3 版判定に加え、arg2=0 (trap せず ret=0) と arg2=3 (post115 と同一) を見る)
#   4/5 survey 942 unit を post115 / post116 で測る
#   5/5 unit 単位の突合 (ok 退行 0 であること)
# 前提: tools/m11/work に work-m11 の展開 (boot_final.prealloca.ll・m11_image.bin・boot*.drc.config.json)、
#       FL_WIN64_DIR (fl-win64 の展開先 = extracted/block00031_PE.bin)、[EMSDK] (docs/REFERENCES.md)。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/m11/ldfix/ld116_e2e.sh
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
W="$M11/work"
: "${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 の展開先) を指定してください}"
OUT="${RUNNER_TEMP:-/tmp}/ld116_e2e"; rm -rf "$OUT"; mkdir -p "$OUT/pre" "$OUT/mid" "$OUT/post115" "$OUT/post116"
PE_QS="$FL_WIN64_DIR/extracted/block00031_PE.bin"
PY="${PY:-python3}"
step() { echo "[ld116_e2e] $*"; }
# work/boot_final.ll と ir_conditions.json を書き換えるので、終了時に元へ戻す
cp "$W/boot_final.ll" "$OUT/orig_boot_final.ll"
[ -f "$W/ir_conditions.json" ] && cp "$W/ir_conditions.json" "$OUT/orig_ir_conditions.json"
restore() {
  cp "$OUT/orig_boot_final.ll" "$W/boot_final.ll"
  [ -f "$OUT/orig_ir_conditions.json" ] && cp "$OUT/orig_ir_conditions.json" "$W/ir_conditions.json"
}
trap restore EXIT

step "1/5 現行 ldfix → fix_ld108 → fix_ld115 (修復前 post115) と fix_ld116 (修復後 post116) の IR"
"$PY" "$M11/ldfix/ldfix.py" "$W/boot_final.prealloca.ll" "$OUT/ldfix.ll" --pe "$PE_QS" --report "$OUT/ldfix_report.json" || exit 1
"$PY" "$M11/ldfix/fix_ld108.py" "$OUT/ldfix.ll" "$OUT/pre.ll" || exit 1
"$PY" "$HERE/fix_ld115.py" "$OUT/pre.ll" "$OUT/mid.ll" --only count || exit 1
"$PY" "$HERE/fix_ld115.py" "$OUT/pre.ll" "$OUT/post115.ll" || exit 1
"$PY" "$HERE/fix_ld116.py" "$OUT/post115.ll" "$OUT/post116.ll" || exit 1
diff "$OUT/post115.ll" "$OUT/post116.ll" > "$OUT/ir_116.diff"; echo "[ld116_e2e] post115 → post116 の IR diff 行数: $(wc -l < "$OUT/ir_116.diff")"

step "2/5 wasm build (pre → $OUT/pre, mid → $OUT/mid, post115 → $OUT/post115, post116 → $OUT/post116)"
cd "$M11" || exit 1
for k in pre mid post115 post116; do
  cp "$OUT/$k.ll" "$W/boot_final.ll"
  python3 m11_cond.py --reset ldfix=applied ld108=applied pe="$PE_QS" && python3 m11_cond.py --bind "$W/boot_final.ll" || exit 1
  rm -f "$W/obj/boot.o"
  timeout 1500 bash m11_build.sh > "$OUT/build_$k.log" 2>&1 || { echo "build 失敗: $OUT/build_$k.log"; exit 1; }
  cp "$W/m11_boot.cjs" "$OUT/$k/m11_boot.cjs"; cp "$W/m11_boot.cjs.wasm" "$OUT/$k/m11_boot.cjs.wasm"
done

step "3/5 666a60 の動的確認 (dyn_ld115.mjs)"
node "$HERE/dyn_ld115.mjs" "$OUT/pre/m11_boot.cjs" "$OUT/mid/m11_boot.cjs" "$OUT/post115/m11_boot.cjs" "$W/m11_image.bin" "$OUT/post116/m11_boot.cjs" | tee "$OUT/dyn.txt"

step "4/5 survey 942 unit (修復前 post115 / 修復後 post116)"
cp "$OUT/post115/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/post115/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_pre.json" | tail -1
cp "$OUT/post116/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/post116/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_post.json" | tail -1

step "5/5 突合"
"$PY" trap_triage/survey_diff.py "$OUT/sv_pre.json" "$OUT/sv_post.json" | tail -8
echo "[ld116_e2e] done: $OUT"
