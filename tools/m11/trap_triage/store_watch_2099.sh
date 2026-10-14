#!/usr/bin/env bash
# #1046 (#1620 前提): 全 store 計装 (watch_store_682.py) を入れ, unit 単位で監視を ON/OFF して 0x10a9f910 への書込みを取る.
#   usage: store_watch_1046b.sh <from> <to> <tag> [<wfrom> <wto>]
#     unit from..to を順に実行する。監視 (`[aw]`) は unit wfrom..wto の間だけ ON (既定は from..to 全部)。
#     前段 unit が作る状態が要るので、from は 0 のままにして wfrom だけ絞る。
#   出力: work/probe2099/<tag>.err (`unit N` 行と `[aw]` 行), work/probe2099/sites.json
#   終了時に work/obj/boot.o を元の boot_final3.ll から再生成し sw/ov の計装 o を消す (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
FROM=${1:?from}; TO=${2:?to}; tag=${3:?tag}; WFROM=${4:-$FROM}; WTO=${5:-$TO}
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -I."
restore() { rm -f work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe2099
python3 trap_triage/watch_store_682.py --out work/probe2099 || exit 1
emcc -c work/probe2099/boot_sw.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_addr_2099.c -o work/obj/sw682.o $CF || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=1 -DM11_NOTIFY_682=0 || exit 1
bash m11_build.sh > work/probe2099/build_$tag.log 2>&1 || { tail -5 work/probe2099/build_$tag.log; exit 1; }
cat > work/probe2099/run_$tag.mjs <<EOF
import fs from 'fs';
const M11 = '$HERE';
const from = $FROM, to = $TO, wfrom = $WFROM, wto = $WTO;
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
for (let i = from; i <= to; i++) {
  fs.writeSync(2, 'unit ' + i + '\\n');
  mod._m11_watch_on(i >= wfrom && i <= wto ? 1 : 0);
  try { mod._m11_call_unit(i); } catch (e) {
    mod.__emscripten_stack_restore(sp0);
  }
  mod._m11_watch_on(0);
}
EOF
timeout 900 node work/probe2099/run_$tag.mjs > work/probe2099/$tag.out 2> work/probe2099/$tag.err; echo "[store_watch_1046b] run rc=$?"
grep -a -c "^\[aw\]" work/probe2099/$tag.err | sed 's/^/[aw] hits: /'
