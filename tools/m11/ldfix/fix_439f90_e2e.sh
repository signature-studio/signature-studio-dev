#!/usr/bin/env bash
# fix_439f90_e2e.sh — #5700 (CI-236): M11_FIX_439F90=1 の IR で wasm を作り、既定 IR と unit 結果を突合する。
#   1/4 IR 生成: 既定 (M11_FIX_439F90=0 相当の既定) と M11_FIX_439F90=1 の m11_gen_ir2.sh
#   2/4 wasm build: 既定 IR と fix IR を m11_build.sh で作る (fix IR は ir_conditions 439f90=applied)
#   3/4 survey: 942 unit を既定 wasm と fix wasm で測る (trap_triage/survey_units.mjs)
#   4/4 突合: survey_diff.py で ok 退行・kind 以外の差・icall 差を見る
# 前提: tools/m11/work に work-m11 の展開、FL_WIN64_DIR (fl-win64 の展開先)、[EMSDK] (/opt/emsdk)、Python の capstone・pefile。
# 使い方: FL_WIN64_DIR=<展開先> bash tools/m11/ldfix/fix_439f90_e2e.sh
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd -- "$HERE/.." && pwd)"
W="$M11/work"
: "${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 の展開先) を指定してください}"
export FL_WIN64_DIR
OUT="${RUNNER_TEMP:-/tmp}/fix439f90_e2e"; rm -rf "$OUT"; mkdir -p "$OUT/def" "$OUT/fix"
FAIL=0
step() { echo "[fix439f90_e2e] $*"; }
chk() { # chk <名前> <rc 0 なら PASS>
  if [ "$2" = 0 ]; then echo "[fix439f90_e2e] PASS $1"; else echo "[fix439f90_e2e] FAIL $1"; FAIL=$((FAIL + 1)); fi
}
step "環境: node $(node --version) / nproc $(nproc) / load $(cut -d' ' -f1-3 /proc/loadavg)"
cp "$W/boot_final.ll" "$OUT/orig_boot_final.ll"
[ -f "$W/ir_conditions.json" ] && cp "$W/ir_conditions.json" "$OUT/orig_ir_conditions.json"
cp "$W/m11_boot.cjs" "$OUT/orig_m11_boot.cjs" 2>/dev/null; cp "$W/m11_boot.cjs.wasm" "$OUT/orig_m11_boot.cjs.wasm" 2>/dev/null
restore() {
  cp "$OUT/orig_boot_final.ll" "$W/boot_final.ll"
  if [ -f "$OUT/orig_ir_conditions.json" ]; then cp "$OUT/orig_ir_conditions.json" "$W/ir_conditions.json"; else rm -f "$W/ir_conditions.json"; fi
  [ -f "$OUT/orig_m11_boot.cjs" ] && cp "$OUT/orig_m11_boot.cjs" "$W/m11_boot.cjs"
  [ -f "$OUT/orig_m11_boot.cjs.wasm" ] && cp "$OUT/orig_m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
}
trap restore EXIT
cd "$M11" || exit 1

step "1/4 IR 生成 (既定 / M11_FIX_439F90=1)"
bash m11_gen_ir2.sh > "$OUT/gen_def.log" 2>&1 || { echo "gen_ir2 (既定) 失敗: $OUT/gen_def.log"; exit 1; }
cp "$W/boot_final.ll" "$OUT/def.ll"; cp "$W/ir_conditions.json" "$OUT/def.cond.json"
M11_FIX_439F90=1 bash m11_gen_ir2.sh > "$OUT/gen_fix.log" 2>&1 || { echo "gen_ir2 (439f90) 失敗: $OUT/gen_fix.log"; exit 1; }
cp "$W/boot_final.ll" "$OUT/fix.ll"; cp "$W/ir_conditions.json" "$OUT/fix.cond.json"
python3 m11_cond.py --check "$OUT/fix.ll"; chk "m11_cond --check (fix IR・生成直後)" $?
python3 -c "import json,sys; c=json.load(open(sys.argv[1])); sys.exit(0 if c.get('439f90')=='applied' else 1)" "$OUT/fix.cond.json"; chk "ir_conditions 439f90=applied" $?
diff "$OUT/def.ll" "$OUT/fix.ll" > "$OUT/ir.diff"; echo "[diff def.ll fix.ll] 変更行 $(grep -c '^[<>]' "$OUT/ir.diff") 行"

step "2/4 wasm build (既定 → $OUT/def、fix → $OUT/fix)"
build() { # build <def|fix>
  local k="$1"
  cp "$OUT/$k.ll" "$W/boot_final.ll"; cp "$OUT/$k.cond.json" "$W/ir_conditions.json"
  rm -f "$W/obj/boot.o" "$W/boot_final3.ll"
  timeout 1500 bash m11_build.sh > "$OUT/build_$k.log" 2>&1 || { echo "build 失敗: $OUT/build_$k.log"; exit 1; }
  cp "$W/m11_boot.cjs" "$W/m11_boot.cjs.wasm" "$OUT/$k/"
}
build def
build fix
cmp -s "$OUT/def/m11_boot.cjs.wasm" "$OUT/fix/m11_boot.cjs.wasm"; [ $? != 0 ]; chk "既定 wasm と fix wasm が別バイナリ (fix 適用が wasm に入っている)" $?

step "3/4 survey 942 unit (既定 wasm / fix wasm)"
cp "$OUT/def/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/def/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_def.json" | tail -1
cp "$OUT/fix/m11_boot.cjs" "$W/m11_boot.cjs"; cp "$OUT/fix/m11_boot.cjs.wasm" "$W/m11_boot.cjs.wasm"
timeout 900 node trap_triage/survey_units.mjs "$OUT/sv_fix.json" | tail -1

step "4/4 突合 (survey_diff.py)"
python3 trap_triage/survey_diff.py "$OUT/sv_def.json" "$OUT/sv_fix.json" | tee "$OUT/survey_diff.txt" | tail -8
grep -q '^ok 退行 unit: 0 ' "$OUT/survey_diff.txt"; chk "ok 退行 0" $?
grep -q '^kind 以外も含めた差分 unit (frames は深さのみ比較): 0 ' "$OUT/survey_diff.txt"; chk "kind 以外の差分 0" $?

echo "FIX439F90_E2E_SUMMARY fail=$FAIL"
echo "[fix439f90_e2e] done: $OUT"
exit $((FAIL > 0))
