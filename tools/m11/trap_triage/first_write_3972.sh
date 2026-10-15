#!/usr/bin/env bash
# #3972 (M11-29): 計装なしの clean build で、WATCH_ADDR の 8 バイトが unit ごとに変化する最初の unit を測る。
#   store 計装 (watch_store_682.py) と C 側の書込みに依らず、unit の前後でメモリを読むだけ。
#   usage: first_write_3972.sh <tag> [WATCH_ADDR=0x10aa1428] [UNITS=158]
#   出力: work/probe3972/fw_<tag>.txt (unit ごとの値の変化)。終了時に clean build は作り直さない (呼出し側で m11_build.sh)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source "${EMSDK_HOME:-/opt/emsdk}/emsdk_env.sh" > /dev/null 2>&1   # [EMSDK] (docs/REFERENCES.md)
tag=${1:?tag}
WA=${2:-${WATCH_ADDR:-0x10aa1428}}
UN=${3:-${UNITS:-158}}
export M11_FIX_4136A0="${M11_FIX_4136A0:-1}"
[ -f work/boot_final.ll ] || { echo "work/boot_final.ll が無い (bash m11_gen_ir2.sh を先に実行)"; exit 1; }
mkdir -p work/probe3972
bash m11_build.sh > work/probe3972/build_fw_$tag.log 2>&1 || { tail -5 work/probe3972/build_fw_$tag.log; exit 1; }
cat > work/probe3972/fw_$tag.mjs <<EOF
import fs from 'fs';
const M11 = '$HERE';
const m2 = await import(M11 + '/work/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
const WA = $WA;
const hex = (a) => Array.from(mod.HEAPU8.subarray(a, a + 8)).map(b => b.toString(16).padStart(2, '0')).join('');
let prev = hex(WA);
fs.writeSync(1, 'init ' + prev + '\\n');
for (let i = 0; i <= $UN; i++) {
  const r = run(i);
  const cur = hex(WA);
  if (cur !== prev) fs.writeSync(1, 'unit ' + i + ' ' + r + ' changed ' + prev + ' -> ' + cur + '\\n');
  prev = cur;
}
fs.writeSync(1, 'final ' + prev + '\\n');
EOF
timeout ${RUN_TIMEOUT:-600} node work/probe3972/fw_$tag.mjs > work/probe3972/fw_$tag.txt 2> work/probe3972/fw_$tag.err; echo "[first_write_3972] rc=$?"
cat work/probe3972/fw_$tag.txt
