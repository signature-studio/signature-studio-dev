#!/usr/bin/env bash
# #2408 (#2369 の子; store_watch_2270.sh の派生): store_watch_2217.sh と同じ窓 (icall 0x5c04a0 入口 -- icall 0xf960 入口) の監視だが,
#   全 store ではなく WATCH_FNS (カンマ区切りの関数名。例 function_8651a0,function_40f9e0) の store だけを計装する.
#   全 store 計装 (54,342 箇所) は unit 106 で止まるため (REPORT_1676 §13). 陽性対照は WATCH_FNS に既知の書込み関数を入れて確かめる.
#   WATCH_ADDR (既定 0x10bd4c20 = list B) で監視番地を変えられる (陽性対照用)。
#   usage: WATCH_FNS=<fn,...> または WATCH_FNS_FILE=<1 行 1 関数のファイル> または WATCH_ALL=1 [WATCH_EXCLUDE=fn,...] [WATCH_ADDR=0x...] [SW_OPT=-O2|-O0] [SW_LEGACY=1] [RUN_TIMEOUT=600] store_watch_2408.sh <tag> [w114|diag|full]
#     full: 監視を unit 114 の開始から ON にし, icall 行ごとに [WATCH_ADDR, +32) の 4 qword と `[aw]` を時系列で出す (窓に依らない).
#   出力: work/probe2408/<tag>.err (`[aw]` 行). 終了時に m11_build.sh で clean な wasm に復元する (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
tag=${1:?tag}
mode=${2:-w114}
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -I."
restore() { rm -f work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe2408
if [ "${WATCH_ALL:-0}" = 1 ]; then   # IR に定義のある全関数 (除外は WATCH_EXCLUDE=fn,fn の完全一致)
  WATCH_FNS_FILE=work/probe2408/fns_all.txt
  grep -E '^define' work/boot_final3.ll | sed -E 's/^define [^@]*@([^(]+)\(.*/\1/' | grep -vxF -f <(echo "${WATCH_EXCLUDE:-__none__}" | tr ',' '\n') > "$WATCH_FNS_FILE"
fi
FNS_ARG=(--fns "${WATCH_FNS:-}"); [ -n "${WATCH_FNS_FILE:-}" ] && FNS_ARG=(--fns-file "$WATCH_FNS_FILE")
[ -n "${WATCH_FNS:-}${WATCH_FNS_FILE:-}" ] || { echo "WATCH_FNS / WATCH_FNS_FILE / WATCH_ALL=1 のいずれかが必要"; exit 1; }
python3 trap_triage/watch_store_682.py --out work/probe2408 "${FNS_ARG[@]}" || exit 1
emcc -c work/probe2408/boot_sw.ll -o work/obj/boot.o $CF || exit 1
SWC=trap_triage/watch_addr_2408.c; SWO="${SW_OPT:--O2}"; [ "${SW_LEGACY:-0}" = 1 ] && { SWC=trap_triage/watch_addr_2099.c; SWO=-O0; }
emcc -c $SWC -o work/obj/sw682.o ${CF/-O0/$SWO} -DM11_WATCH_ADDR_OVR=${WATCH_ADDR:-0x10bd4c20u} || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=1 -DM11_NOTIFY_682=0 || exit 1
M11_KEEP_BOOT_O=1 bash m11_build.sh > work/probe2408/build_$tag.log 2>&1 || { tail -5 work/probe2408/build_$tag.log; exit 1; }
cat > work/probe2408/run_$tag.mjs <<EOF
import fs from 'fs';
const M11 = '$HERE';
const diag = '$mode' === 'diag';
const full = '$mode' === 'full';
const WA = Number('${WATCH_ADDR:-0x10bd4c20}'.replace(/u\$/, ''));
const dumpw = () => { const dv = new DataView(mod.HEAPU8.buffer); let o = []; for (let k = 0; k < 4; k++) o.push(dv.getBigUint64(WA + 8 * k, true).toString(16)); return o.join(' '); };
const m2 = await import(M11 + '/work/m11_boot.cjs');
let mod = null, n_on = 0, n_off = 0;
const printErr = (s) => {
  s = String(s);
  if (!mod) { if (s.startsWith('[aw]')) fs.writeSync(2, s + '\n'); return; }
  if (full) { if (s.startsWith('[aw]')) fs.writeSync(2, s + '\\n'); else if (s.includes('[m11][icall]')) fs.writeSync(2, s + ' | mem@WA ' + dumpw() + '\\n'); return; }
  if (s.includes('[m11][icall] 0x1c04a0')) { n_on++; mod._m11_watch_on(1); fs.writeSync(2, '[win] ON ' + n_on + '\n'); }
  else if (s.includes('[m11][icall] 0xf960') && n_on > n_off) { n_off++; mod._m11_watch_on(0); fs.writeSync(2, '[win] OFF ' + n_off + '\n'); }
  else if (s.startsWith('[aw]')) fs.writeSync(2, s + '\n');
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
for (let i = 0; i < 114; i++) { const t0 = Date.now(); fs.writeSync(2, 'unit ' + i + '\\n'); const r0 = run(i); if (diag) fs.writeSync(2, 'unit ' + i + ' ' + r0 + ' ms=' + (Date.now() - t0) + '\\n'); }
fs.writeSync(2, 'unit 114 (trace on)\\n');
mod._m11_set_trace(1);
if (full) mod._m11_watch_on(1);
const r = run(114);
mod._m11_set_trace(0);
mod._m11_watch_on(0);
fs.writeSync(2, 'unit 114 ' + r + '\\n');
EOF
timeout ${RUN_TIMEOUT:-600} node work/probe2408/run_$tag.mjs > work/probe2408/$tag.out 2> work/probe2408/$tag.err; echo "[store_watch_2408] run rc=$?"
grep -a -c "^\[aw\]" work/probe2408/$tag.err | sed 's/^/[aw] hits: /'
python3 -c "import json,re,sys; d=json.load(open('work/probe2408/sites.json')); [print(l.rstrip(), '->', d[m.group(1)]['fn'], 'IR line', d[m.group(1)]['line'], '|', d[m.group(1)]['store']) for l in open(sys.argv[1], errors='replace') for m in [re.match(r'\[aw\] site=(\d+)', l)] if m]" work/probe2408/$tag.err
