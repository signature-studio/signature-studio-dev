#!/usr/bin/env bash
# ld108_e2e.sh — #2316 (LD-108) 1 コマンド再現。41a670 の head 解除 store の修復 (fix_ld108.py) を検証する。
#   1/5 検出器 audit_lsf_disp.py を修復前 / 修復後 IR に実行 (41a670 が SUSPECT から消えること)
#   2/5 修復前 wasm / 修復後 wasm を build (m11_build.sh。修復前は ldfix=disabled、修復後は ldfix=applied)
#   3/5 41a670 を修復前 / 修復後 wasm で直接呼ぶ (dyn_ld108.mjs。期待 head=0x2222)
#   4/5 survey 942 unit を修復前 / 修復後で測り、unit ごとに突合 (退行 0 であること)
#   5/5 ok 退行・unit 差分の要約
# 前提: tools/m11/work に work-m11 の展開 (boot_final.ll / boot_final3.ll / m11_image.bin / boot*.drc.config.json)、
#       FL_WIN64_DIR (fl-win64 の展開先 = extracted/block00031_PE.bin が入る)、/opt/emsdk。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/m11/ldfix/ld108_e2e.sh
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
W="$M11/work"
: "${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 の展開先) を指定してください}"
OUT="${RUNNER_TEMP:-/tmp}/ld108_e2e"; rm -rf "$OUT"; mkdir -p "$OUT/pre" "$OUT/post"
PE_QS="$FL_WIN64_DIR/extracted/block00031_PE.bin"
PY="${PY:-python3}"
step() { echo "[ld108_e2e] $*"; }
# 元の IR (work/) を退避し、終了時に必ず戻す (本スクリプトは work/boot_final*.ll と ir_conditions.json を書き換える)
cp "$W/boot_final.ll" "$OUT/orig_boot_final.ll"; cp "$W/boot_final3.ll" "$OUT/orig_boot_final3.ll"
[ -f "$W/ir_conditions.json" ] && cp "$W/ir_conditions.json" "$OUT/orig_ir_conditions.json"
restore() {
  cp "$OUT/orig_boot_final.ll" "$W/boot_final.ll"; cp "$OUT/orig_boot_final3.ll" "$W/boot_final3.ll"
  [ -f "$OUT/orig_ir_conditions.json" ] && cp "$OUT/orig_ir_conditions.json" "$W/ir_conditions.json"
}
trap restore EXIT
if grep -q ldfx108 "$W/boot_final.ll"; then echo "work/boot_final.ll は修復済み (ldfx108 を含む)。元 IR に戻してから実行すること"; exit 1; fi

step "1/5 検出器 (修復前 / 修復後 IR)"
cp "$W/boot_final.ll" "$OUT/pre.ll"
"$PY" "$HERE/fix_ld108.py" "$OUT/pre.ll" "$OUT/post.ll" || exit 1
for k in pre post; do
  "$PY" "$HERE/audit_lsf_disp.py" "$OUT/$k.ll" "$W/m11_image.bin" "$W/boot*.drc.config.json" --json "$OUT/disp_$k.json" | sed "s/^/[$k] /"
done

step "2/5 wasm build (修復前 → $OUT/pre, 修復後 → $OUT/post)"
cd "$M11" || exit 1
python3 m11_cond.py --reset ldfix=disabled pe="$PE_QS" && python3 m11_cond.py --bind "$W/boot_final.ll"
rm -f "$W/obj/boot.o"
M11_ALLOW_LDFIX_DISABLED=1 timeout 1500 bash m11_build.sh > "$OUT/build_pre.log" 2>&1 || { echo "build 失敗: $OUT/build_pre.log"; exit 1; }
cp "$W/m11_boot.cjs" "$OUT/pre/m11_boot.cjs"; cp "$W/m11_boot.cjs.wasm" "$OUT/pre/m11_boot.cjs.wasm"
cp "$OUT/post.ll" "$W/boot_final.ll"; "$PY" "$HERE/fix_ld108.py" "$OUT/orig_boot_final3.ll" "$W/boot_final3.ll"
python3 m11_cond.py ldfix=applied && python3 m11_cond.py --bind "$W/boot_final.ll"
rm -f "$W/obj/boot.o"
timeout 1500 bash m11_build.sh > "$OUT/build_post.log" 2>&1 || { echo "build 失敗: $OUT/build_post.log"; exit 1; }
cp "$W/m11_boot.cjs" "$OUT/post/m11_boot.cjs"; cp "$W/m11_boot.cjs.wasm" "$OUT/post/m11_boot.cjs.wasm"

step "3/5 41a670 の動的確認 (dyn_ld108.mjs)"
node "$HERE/dyn_ld108.mjs" "$OUT/pre/m11_boot.cjs" "$OUT/post/m11_boot.cjs" "$W/m11_image.bin" | tee "$OUT/dyn.txt"

step "4/5 survey 942 unit (修復前 / 修復後)"
cp "$OUT/pre/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/pre/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_pre.json" | tail -1
cp "$OUT/post/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/post/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_post.json" | tail -1

step "5/5 突合"
python3 trap_triage/survey_diff.py "$OUT/sv_pre.json" "$OUT/sv_post.json" | tail -6
echo "[ld108_e2e] done: $OUT"
