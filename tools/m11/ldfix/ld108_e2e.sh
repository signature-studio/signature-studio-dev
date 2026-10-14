#!/usr/bin/env bash
# ld108_e2e.sh — #2316 (LD-108) / #2402 (LD-112) 1 コマンド再現。41a670 の head 解除 store の修復 (fix_ld108.py) が
# 本番の IR 生成経路 (m11_gen_ir2.sh → m11_build.sh) に組み込まれていることを検証する。
#   1/6 IR 生成: M11_FIX_LD108=0 (修復前) と既定 (修復後 = 本番) の m11_gen_ir2.sh。ir_conditions と m11_cond --check、IR の diff
#   2/6 検出器 audit_lsf_disp.py を修復前 / 修復後 IR に実行 (41a670 が SUSPECT から消えること)
#   3/6 wasm build (m11_build.sh)。修復前は M11_ALLOW_LD108_DISABLED=1、修復後は通常の build
#   4/6 41a670 を修復前 / 修復後 wasm で直接呼ぶ (dyn_ld108.mjs。期待 head=0x2222)
#   5/6 survey 942 unit を修復前 / 修復後で測り、unit ごとに突合 (ok 退行 0 であること)
#   6/6 ネガティブコントロール (fix_ld108 の assert・m11_cond の指紋・m11_build の ld108 記録拒否)
# 前提: tools/m11/work に work-m11 の展開 (boot0..4.lift.ll / m11_image.bin / boot*.drc.config.json ほか)、
#       FL_WIN64_DIR (fl-win64 の展開先 = extracted/block00031_PE.bin が入る)、[EMSDK] (docs/REFERENCES.md)、
#       Python の capstone・pefile。boot_final.ll は本スクリプトが m11_gen_ir2.sh で作り直す (snapshot の boot_final.ll は使わない)。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/m11/ldfix/ld108_e2e.sh
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
W="$M11/work"
: "${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 の展開先) を指定してください}"
export FL_WIN64_DIR
OUT="${RUNNER_TEMP:-/tmp}/ld108_e2e"; rm -rf "$OUT"; mkdir -p "$OUT/pre" "$OUT/post"
PY="${PY:-python3}"
FAIL=0
step() { echo "[ld108_e2e] $*"; }
chk() { # chk <名前> <rc 0 なら PASS>
  if [ "$2" = 0 ]; then echo "[ld108_e2e] PASS $1"; else echo "[ld108_e2e] FAIL $1"; FAIL=$((FAIL + 1)); fi
}
# 元の IR (work/) を退避し、終了時に必ず戻す (本スクリプトは work/boot_final*.ll と ir_conditions.json を書き換える)
cp "$W/boot_final.ll" "$OUT/orig_boot_final.ll"; cp "$W/boot_final3.ll" "$OUT/orig_boot_final3.ll"
[ -f "$W/ir_conditions.json" ] && cp "$W/ir_conditions.json" "$OUT/orig_ir_conditions.json"
restore() {
  cp "$OUT/orig_boot_final.ll" "$W/boot_final.ll"; cp "$OUT/orig_boot_final3.ll" "$W/boot_final3.ll"
  if [ -f "$OUT/orig_ir_conditions.json" ]; then cp "$OUT/orig_ir_conditions.json" "$W/ir_conditions.json"; else rm -f "$W/ir_conditions.json"; fi
}
trap restore EXIT
cd "$M11" || exit 1

step "1/6 IR 生成 (本番経路 m11_gen_ir2.sh。修復前 = M11_FIX_LD108=0、修復後 = 既定)"
M11_FIX_LD108=0 bash m11_gen_ir2.sh > "$OUT/gen_pre.log" 2>&1 || { echo "gen_ir2 (修復前) 失敗: $OUT/gen_pre.log"; exit 1; }
cp "$W/boot_final.ll" "$OUT/pre.ll"; cp "$W/ir_conditions.json" "$OUT/pre.cond.json"
python3 m11_cond.py --check "$OUT/pre.ll"; chk "m11_cond --check (修復前 IR・生成直後)" $?
bash m11_gen_ir2.sh > "$OUT/gen_post.log" 2>&1 || { echo "gen_ir2 (修復後) 失敗: $OUT/gen_post.log"; exit 1; }
cp "$W/boot_final.ll" "$OUT/post.ll"; cp "$W/ir_conditions.json" "$OUT/post.cond.json"
python3 m11_cond.py --check "$OUT/post.ll"; chk "m11_cond --check (修復後 IR・生成直後)" $?
echo "[ir_conditions pre ] $(tr -d '\n ' < "$OUT/pre.cond.json")"
echo "[ir_conditions post] $(tr -d '\n ' < "$OUT/post.cond.json")"
"$PY" - "$OUT/pre.cond.json" "$OUT/post.cond.json" <<'PYEOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
same = all(a.get(k) == b.get(k) for k in ('ldfix', 'qstore', 'pe'))
print('[ir_conditions] ldfix・qstore・pe は修復前後で %s。ld108: %s -> %s。ir_sha256: %s' % (
    '一致' if same else '不一致', a.get('ld108'), b.get('ld108'), '差あり' if a.get('ir_sha256') != b.get('ir_sha256') else '同一'))
sys.exit(0 if same and a.get('ld108') == 'disabled' and b.get('ld108') == 'applied' and a.get('ir_sha256') != b.get('ir_sha256') else 1)
PYEOF
chk "ir_conditions (ldfix・qstore・pe 一致、ld108 disabled -> applied、指紋は別)" $?
diff "$OUT/pre.ll" "$OUT/post.ll" > "$OUT/ir.diff"
echo "[diff pre.ll post.ll] 変更行 $(grep -c '^[<>]' "$OUT/ir.diff") 行"; cat "$OUT/ir.diff"
"$PY" "$HERE/ld108_irdiff.py" "$OUT/pre.ll" "$OUT/post.ll"; chk "IR の差は function_41a670 の 1 関数だけ" $?

step "2/6 検出器 (修復前 / 修復後 IR)"
for k in pre post; do
  "$PY" "$HERE/audit_lsf_disp.py" "$OUT/$k.ll" "$W/m11_image.bin" "$W/boot*.drc.config.json" --json "$OUT/disp_$k.json" | sed "s/^/[$k] /"
done

step "3/6 wasm build (修復前 → $OUT/pre, 修復後 → $OUT/post)"
build() { # build <pre|post> <環境変数...>
  local k="$1"; shift
  cp "$OUT/$k.ll" "$W/boot_final.ll"; cp "$OUT/$k.cond.json" "$W/ir_conditions.json"
  rm -f "$W/obj/boot.o" "$W/boot_final3.ll"
  env "$@" timeout 1500 bash m11_build.sh > "$OUT/build_$k.log" 2>&1 || { echo "build 失敗: $OUT/build_$k.log"; exit 1; }
  python3 m11_cond.py --check "$W/boot_final.ll"; chk "m11_cond --check ($k・build 後。qstore 等の書換え後に指紋が更新されている)" $?
  cp "$W/ir_conditions.json" "$OUT/$k.cond_built.json"; cp "$W/boot_final.ll" "$OUT/${k}_built.ll"
  cp "$W/m11_boot.cjs" "$OUT/$k/m11_boot.cjs"; cp "$W/m11_boot.cjs.wasm" "$OUT/$k/m11_boot.cjs.wasm"
}
build pre M11_ALLOW_LD108_DISABLED=1
build post M11_ALLOW_LD108_DISABLED=0
echo "[ir_conditions post・build 後] $(tr -d '\n ' < "$OUT/post.cond_built.json")"

step "4/6 41a670 の動的確認 (dyn_ld108.mjs。通常 build の wasm)"
node "$HERE/dyn_ld108.mjs" "$OUT/pre/m11_boot.cjs" "$OUT/post/m11_boot.cjs" "$W/m11_image.bin" | tee "$OUT/dyn.txt"
grep -q 'DYN_SUMMARY after_fail=0/1' "$OUT/dyn.txt"; chk "修復後 wasm の head が期待値と一致" $?

step "5/6 survey 942 unit (修復前 / 修復後)"
cp "$OUT/pre/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/pre/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_pre.json" | tail -1
cp "$OUT/post/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/post/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_post.json" | tail -1
python3 trap_triage/survey_diff.py "$OUT/sv_pre.json" "$OUT/sv_post.json" | tee "$OUT/survey_diff.txt" | tail -8
grep -q '^ok 退行 unit: 0 ' "$OUT/survey_diff.txt"; chk "ok 退行 0" $?

step "6/6 ネガティブコントロール"
sed 's/^define i64 @function_41a670(i64 %arg1)/define i64 @function_41a670(i32 %arg1)/' "$OUT/pre.ll" > "$OUT/neg_i32.ll"
cmp -s "$OUT/pre.ll" "$OUT/neg_i32.ll" && { echo "negctl: sed が効いていない"; FAIL=$((FAIL + 1)); }
"$PY" "$HERE/fix_ld108.py" "$OUT/neg_i32.ll" "$OUT/neg_i32.out.ll" 2> "$OUT/neg_i32.err"; [ $? != 0 ] && grep -q '第 1 仮引数が i64 %arg1 でない' "$OUT/neg_i32.err"; rc=$?
chk "NC1 第 1 仮引数が i32 の IR を fix_ld108 が拒否 ($(tail -1 "$OUT/neg_i32.err"))" $rc
"$PY" "$HERE/fix_ld108.py" "$OUT/post.ll" "$OUT/neg_twice.ll" 2> "$OUT/neg_twice.err"; [ $? != 0 ]; rc=$?
chk "NC2 適用済み IR への二重適用を fix_ld108 が拒否 ($(tail -1 "$OUT/neg_twice.err"))" $rc
cp "$OUT/post.cond_built.json" "$W/ir_conditions.json"
python3 m11_cond.py --check "$OUT/post_built.ll"; chk "NC3 対照: 記録どおりの IR は m11_cond --check が一致" $?
cp "$OUT/post_built.ll" "$OUT/neg_tamper.ll"; echo '; tamper' >> "$OUT/neg_tamper.ll"
python3 m11_cond.py --check "$OUT/neg_tamper.ll" 2> /dev/null; [ $? != 0 ]; rc=$?
chk "NC3 同じ IR に 1 行書き足すと m11_cond --check が不一致" $rc
cp "$OUT/pre.ll" "$W/boot_final.ll"; cp "$OUT/pre.cond.json" "$W/ir_conditions.json"
M11_ALLOW_LD108_DISABLED=0 bash m11_build.sh > "$OUT/neg_build.log" 2>&1; [ $? = 2 ] && grep -q 'ld108=applied の記録無し' "$OUT/neg_build.log"; chk "NC4 ld108=disabled の IR は opt-in 無しの m11_build.sh が拒否 (rc 2)" $?

echo "LD108_E2E_SUMMARY fail=$FAIL"
echo "[ld108_e2e] done: $OUT"
exit $((FAIL > 0))
