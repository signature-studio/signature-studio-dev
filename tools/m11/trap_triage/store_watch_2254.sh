#!/usr/bin/env bash
# #2254: 窓内候補関数だけに store 計装を入れ, list B (0x10bd4c20) への書込みを取る (store_watch_2099.sh の関数限定版).
#   usage: store_watch_2254.sh <fns,comma-separated> <tag> <unit>
#   unit は probe の対象 unit (既定 114)。終了時に boot.o を元に戻す (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
FNS=${1:?fns}; tag=${2:?tag}; U=${3:-114}
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -I."
restore() { rm -f work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe2254
python3 trap_triage/watch_fn_2254.py "$FNS" --out work/probe2254 || exit 1
emcc -c work/probe2254/boot_sw.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_addr_2099.c -o work/obj/sw682.o $CF || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=1 -DM11_NOTIFY_682=0 || exit 1
bash m11_build.sh > work/probe2254/build_$tag.log 2>&1 || { tail -5 work/probe2254/build_$tag.log; exit 1; }
cat > work/probe2254/run_$tag.mjs <<EOF
import fs from 'fs';
const M11 = '$HERE';
const target = $U;
const m2 = await import(M11 + '/work/m11_boot.cjs');
const errs = [];
const mod = await m2.default({ printErr: (s) => { s = String(s); errs.push(s); if (s.startsWith('[aw]')) fs.writeSync(2, s + '\n'); } });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
for (let i = 0; i < target; i++) {
  fs.writeSync(2, 'unit ' + i + '\\n');
  mod._m11_watch_on(0);
  try { mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); }
}
fs.writeSync(2, 'unit ' + target + '\\n');
mod._m11_watch_on(1);
try { mod._m11_call_unit(target); console.log('unit', target, 'ret'); } catch (e) {
  console.log('unit', target, e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap');
}
mod._m11_watch_on(0);
EOF
timeout 900 node work/probe2254/run_$tag.mjs > work/probe2254/$tag.out 2> work/probe2254/$tag.err; echo "[store_watch_2254] run rc=$?"
grep -a -c "^\[aw\]" work/probe2254/$tag.err | sed 's/^/[aw] hits: /'
