#!/usr/bin/env bash
# #4183: unit 830・880 (書込み候補) と 923 (trap) の入口で obj (第 1 引数) の値を採る.
#   watch_obj_3823.sh と同じ build 手順で、関数入口の計装 (entry_obj_4183.py) を入れた IR を作る.
#   出力: work/probe4183/ob.err (`[ob] site=<id> val=<値> hit=<通算>` と `unit N` 行), work/probe4183/ob_sites.json
#   usage: EMSDK_HOME=<emsdk の場所> bash trap_triage/entry_obj_4183.sh
#   終了時に m11_build.sh で clean な wasm に復元する (trap で必ず復元)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source "${EMSDK_HOME:?EMSDK_HOME を設定する ([EMSDK]、docs/REFERENCES.md)}/emsdk_env.sh" > /dev/null 2>&1
FNS=${ENTRY_FNS:-function_10c7cd0,function_125da90,function_410b10,function_1263540,function_1264050,function_10d50d0,function_410730,function_4fb910}
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=0 -DM11_OV_CLASSCREATE=0 -I."
restore() { rm -f work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe4183
grep -E '^define' work/boot_final3.ll | sed -E 's/^define [^@]*@([^(]+)\(.*/\1/' > work/probe4183/fns_all.txt
python3 trap_triage/entry_obj_4183.py --src work/boot_final3.ll --out work/probe4183 --fns "$FNS" || exit 1
emcc -c work/probe4183/boot_ob.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_entry_4183.c -o work/obj/sw682.o -O2 || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=1 -DM11_NOTIFY_682=0 || exit 1
M11_KEEP_BOOT_O=1 bash m11_build.sh > work/probe4183/build.log 2>&1 || { tail -5 work/probe4183/build.log; exit 1; }
cat > work/probe4183/run.mjs <<EOF
import fs from 'fs';
const M11 = '$HERE';
const m2 = await import(M11 + '/work/m11_boot.cjs');
let mod = null;
const printErr = (s) => { s = String(s); if (s.startsWith('[ob]')) fs.writeSync(2, s + '\n'); };
mod = await m2.default({ printErr });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
mod._m11_watch_on(1);
for (let i = 0; i <= 923; i++) { fs.writeSync(2, 'unit ' + i + '\\n'); const r = run(i); if (i >= 920) fs.writeSync(2, 'unit ' + i + ' ' + r + '\\n'); }
mod._m11_watch_on(0);
EOF
timeout 900 node work/probe4183/run.mjs > work/probe4183/run.out 2> work/probe4183/ob.err; echo "[entry_obj_4183] run rc=$?"
grep -a -c '^\[ob\]' work/probe4183/ob.err | sed 's/^/[ob] hits: /'
