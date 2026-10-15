#!/usr/bin/env bash
# #3972 (M11-29): callchk で書込みを検出した call (function_414c70 → function_4133f0) の入口で、
#   引数と監視番地の値を記録する (読み取りだけの計装)。callchk_3972.sh と同じ前提・出力形式。
#   usage: entry_3972.sh <tag> [WATCH_ADDR=0x10aa1428] [WATCH_UNIT=158]
#   前提: work/boot_final.ll (bash m11_gen_ir2.sh 済み)。FL_WIN64_DIR は呼び出し側で設定する。
#   出力: work/probe3972/en_<tag>.err (`[wp] id=... a1=... a2=... watch=...`)。
#   id: 1 = function_4133f0 (a1=dst, a2=値), 2 = function_414c70 (a1,a2,a3 は引数)。
#   終了時に m11_build.sh で clean な wasm に復元する (trap で必ず復元)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source "${EMSDK_HOME:-/opt/emsdk}/emsdk_env.sh" > /dev/null 2>&1   # [EMSDK] (docs/REFERENCES.md)
tag=${1:?tag}
WA=${2:-${WATCH_ADDR:-0x10aa1428}}
WU=${3:-${WATCH_UNIT:-158}}
export M11_FIX_4136A0="${M11_FIX_4136A0:-1}"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -DM11_FIX_4136A0=$M11_FIX_4136A0 -I."
restore() { rm -f work/obj/en3972.o work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
[ -f work/boot_final.ll ] || { echo "work/boot_final.ll が無い (bash m11_gen_ir2.sh を先に実行)"; exit 1; }
mkdir -p work/probe3972
bash m11_build.sh > /dev/null 2>&1   # boot_final3.ll (post 済み) を作る。clean build の後に計装する
[ -f work/boot_final3.ll ] || { echo "work/boot_final3.ll が無い"; exit 1; }
python3 trap_triage/entry_3972.py work/boot_final3.ll work/probe3972/boot_en.ll || exit 1
emcc -c work/probe3972/boot_en.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/entry_3972.c -o work/obj/en3972.o ${CF/-O0/-O2} -DM11_WATCH_ADDR_OVR=${WA}u || exit 1
emcc -c trap_triage/watch_addr_2408.c -o work/obj/sw682.o ${CF/-O0/-O2} -DM11_WATCH_ADDR_OVR=${WA}u || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=1 -DM11_NOTIFY_682=0 || exit 1
M11_KEEP_BOOT_O=1 bash m11_build.sh > work/probe3972/build_en_$tag.log 2>&1 || { tail -5 work/probe3972/build_en_$tag.log; exit 1; }
cat > work/probe3972/run_en_$tag.mjs <<EOF
import fs from 'fs';
const M11 = '$HERE';
const m2 = await import(M11 + '/work/m11_boot.cjs');
const printErr = (s) => { s = String(s); if (s.startsWith('[wp]')) fs.writeSync(2, s + '\n'); };
const mod = await m2.default({ printErr });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
for (let i = 0; i < $WU; i++) run(i);
fs.writeSync(2, 'unit $WU (entry on)\\n');
mod._m11_watch_on(1);
const r = run($WU);
mod._m11_watch_on(0);
fs.writeSync(2, 'unit $WU ' + r + '\\n');
EOF
timeout ${RUN_TIMEOUT:-600} node work/probe3972/run_en_$tag.mjs > work/probe3972/en_$tag.out 2> work/probe3972/en_$tag.err; echo "[entry_3972] run rc=$?"
grep -a -c "^\[wp\]" work/probe3972/en_$tag.err | sed 's/^/[wp] hits: /'
