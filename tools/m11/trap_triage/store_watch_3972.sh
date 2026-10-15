#!/usr/bin/env bash
# #3972 (M11-29): unit 158 (0x26d1a0) で s = 0x10aa1428 (653660 の stack_var_-64) に文字列の中身が入る書込み元の特定。
#   store_watch_2408.sh の派生: 監視の窓を icall 0x1c04a0 .. 0xf960 から「unit WATCH_UNIT の実行だけ」に変えた。
#   既定で M11_FIX_4136A0=1 (unit 158 が ok → oom に回帰する条件)。unit 0..WATCH_UNIT-1 は計装のまま走らせ、監視は WATCH_UNIT だけ ON。
#   監視関数は WATCH_FNS (既定は #3928 補足節の候補関数)。書込みは watch_addr_2408.c の m11_sw で記録する。
#   usage: store_watch_3972.sh <tag> [WATCH_ADDR=0x10aa1428] [WATCH_UNIT=158]
#   出力: work/probe3972/<tag>.err (`[aw] site=... addr=... val=... width=...` 行)・work/probe3972/sites.json で書込み関数と IR 行を引く。
#   終了時に m11_build.sh で clean な wasm に復元する (trap で必ず復元)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source "${EMSDK_HOME:-/opt/emsdk}/emsdk_env.sh" > /dev/null 2>&1   # [EMSDK] (docs/REFERENCES.md)
tag=${1:?tag}
WA=${2:-${WATCH_ADDR:-0x10aa1428}}
WU=${3:-${WATCH_UNIT:-158}}
export M11_FIX_4136A0="${M11_FIX_4136A0:-1}"
WATCH_FNS="${WATCH_FNS:-function_653660,function_43c4c0,function_414c70,function_414bb0,function_414ad0,function_413760,function_4136a0,function_414850,function_44f5d0,function_43c8f0,function_652500,function_43c5e0,function_6535a0,function_413480,function_44f040,function_43c870,function_43ba70,function_409c80,function_412c20,function_6539e0,function_653f40,function_65c540}"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -DM11_FIX_4136A0=$M11_FIX_4136A0 -I."
restore() { rm -f work/obj/sw682.o work/obj/cp3972.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
[ -f work/boot_final3.ll ] || { echo "work/boot_final3.ll が無い (bash m11_gen_ir2.sh を先に実行)"; exit 1; }
mkdir -p work/probe3972
if [ "${WATCH_ALL:-0}" = 1 ]; then   # 全関数の store を計装 (watch_store_682.py は --fns 無しで全 store)
  python3 trap_triage/watch_store_682.py --out work/probe3972 || exit 1
else
  python3 trap_triage/watch_store_682.py --out work/probe3972 --fns "$WATCH_FNS" || exit 1
fi
python3 trap_triage/copy_watch_3972.py work/probe3972/boot_sw.ll work/probe3972/boot_sw_cp.ll || exit 1
emcc -c work/probe3972/boot_sw_cp.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_addr_2408.c -o work/obj/sw682.o ${CF/-O0/-O2} -DM11_WATCH_ADDR_OVR=${WA}u || exit 1
emcc -c trap_triage/watch_copy_3972.c -o work/obj/cp3972.o ${CF/-O0/-O2} -DM11_WATCH_ADDR_OVR=${WA}u -DM11_CP_ALL=${M11_CP_ALL:-0} || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=1 -DM11_NOTIFY_682=0 || exit 1
M11_KEEP_BOOT_O=1 bash m11_build.sh > work/probe3972/build_$tag.log 2>&1 || { tail -5 work/probe3972/build_$tag.log; exit 1; }
cat > work/probe3972/run_$tag.mjs <<EOF
import fs from 'fs';
const M11 = '$HERE';
const m2 = await import(M11 + '/work/m11_boot.cjs');
let mod = null;
const printErr = (s) => {
  s = String(s);
  if (s.startsWith('[aw]')) fs.writeSync(2, s + '\n');
};
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
for (let i = 0; i < $WU; i++) run(i);
fs.writeSync(2, 'unit $WU (watch on)\\n');
mod._m11_watch_on(1);
const r = run($WU);
mod._m11_watch_on(0);
fs.writeSync(2, 'unit $WU ' + r + '\\n');
EOF
timeout ${RUN_TIMEOUT:-600} node work/probe3972/run_$tag.mjs > work/probe3972/$tag.out 2> work/probe3972/$tag.err; echo "[store_watch_3972] run rc=$?"
grep -a -c "^\[aw\]" work/probe3972/$tag.err | sed 's/^/[aw] hits: /'
python3 -c "import json,re,sys; d=json.load(open('work/probe3972/sites.json')); [print(l.rstrip(), '->', d[m.group(1)]['fn'], 'IR line', d[m.group(1)]['line'], '|', d[m.group(1)]['store']) for l in open(sys.argv[1], errors='replace') for m in [re.match(r'\[aw\] site=(\d+)', l)] if m]" work/probe3972/$tag.err
