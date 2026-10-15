#!/usr/bin/env bash
# #3823: 923 (function_410b10) の obj 番地 W への書込みを, 全 unit (0..923) の実行中に採る.
#   store_watch_2408.sh と同じ計装 (watch_store_682.py の全関数 store 計装 + watch_addr_2408.c) を使い,
#   監視番地だけ差し替える. 監視は unit 0 の前から ON (番地が別の unit で別オブジェクトになる点は REPORT_APPENDIX_3823 §2 を見る).
#   usage: [WATCH_ADDR=0x10bd3960u] [EMSDK_HOME=/opt/emsdk] bash trap_triage/watch_obj_3823.sh
#   出力: work/probe3823/aw.err (`[aw] site=<id> addr val width hit=<通算>` と `unit N` 行), work/probe3823/sites.json
#   site は sites.json で fn・IR 行に戻す. 終了時に m11_build.sh で clean な wasm に復元する (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source "${EMSDK_HOME:-/opt/emsdk}/emsdk_env.sh" > /dev/null 2>&1   # [EMSDK] (docs/REFERENCES.md)
W=${WATCH_ADDR:-0x10bd3960u}
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=0 -DM11_OV_CLASSCREATE=0 -I."
restore() { rm -f work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe3823
grep -E '^define' work/boot_final3.ll | sed -E 's/^define [^@]*@([^(]+)\(.*/\1/' > work/probe3823/fns_all.txt
python3 trap_triage/watch_store_682.py --out work/probe3823 --fns-file work/probe3823/fns_all.txt || exit 1
emcc -c work/probe3823/boot_sw.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_addr_2408.c -o work/obj/sw682.o -O2 -DM11_WATCH_ADDR_OVR=$W || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=1 -DM11_NOTIFY_682=0 || exit 1
M11_KEEP_BOOT_O=1 bash m11_build.sh > work/probe3823/build.log 2>&1 || { tail -5 work/probe3823/build.log; exit 1; }
cat > work/probe3823/run.mjs <<EOF
import fs from 'fs';
const M11 = '$HERE';
const m2 = await import(M11 + '/work/m11_boot.cjs');
let mod = null;
const printErr = (s) => { s = String(s); if (s.startsWith('[aw]')) fs.writeSync(2, s + '\n'); };
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
timeout 900 node work/probe3823/run.mjs > work/probe3823/run.out 2> work/probe3823/aw.err; echo "[watch_obj_3823] run rc=$?"
grep -a -c '^\[aw\]' work/probe3823/aw.err | sed 's/^/[aw] hits: /'
