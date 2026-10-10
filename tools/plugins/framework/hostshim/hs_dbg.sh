#!/usr/bin/env bash
# hs_dbg.sh — CAB-195 デバッグ用 link trace ビルド + 実行 (hs_e2e.sh の派生)。
#   bash hs_dbg.sh
# IR 全 define に入力 trace を挿入した hs_dbgflat.ll から hs_dbg.cjs を組み,
# Phase B のみ (CreatePlugInstance → ctor 連鎖) を実行して trap 直前の到達点を出す。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T=/home/ubuntu/work/webstudio
FW="$T/tools/plugins/framework"
W="$T/tools/plugins/work/hs/dbg"
WHS="$T/tools/plugins/work/hs"
WFW="$T/tools/plugins/work/fw"
mkdir -p "$W"
cd "$W"

[ -f hs_dbgflat.ll ] || python3 "$HERE/hs_dbg_trace.py" "$WHS/hs_flat3.ll" hs_dbgflat.ll
[ -f hs_dbtable.c ] || python3 "$FW/fw_table.py" --ir hs_dbgflat.ll --imports "$WFW/fw_imports.json" --out hs_dbtable.c --blk 0x8A1000

source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"
emcc hs_dbgflat.ll "$WFW/fw_simd.c" hs_dbtable.c "$HERE/hs_dbg_tr.c" "$HERE/hs_plug.c" "$HERE/hostshim.c" "$HERE/hs_utl.c" "$WFW/fw_rt.c" "$WFW/fw_boot.c" \
  -I"$HERE" -I"$WFW" -I"$FW" -I"$T/tools/liftlib/liftlib/simd" \
  -w -O0 -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB \
  -sGLOBAL_BASE=$((0x10000000)) -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sEXIT_RUNTIME=0 -sERROR_ON_UNDEFINED_SYMBOLS=0 \
  -sEXPORTED_FUNCTIONS=_function_6c13a0,_fw_call_cur,_hs_e2e_run,_hs_plug_get,_fw_hs_count,_fw_hs_records,_fw_hs_host_va,_fw_hs_install,_fw_hs_trace,_g_fw_utl_dbg \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x14000000)) -Wl,--max-memory=$((0x80000000)) \
  -o hs_dbg.cjs 2> emcc.log || { grep -v 'warning\|>>>\|^$' emcc.log | head -20; exit 1; }

node - "$WFW/fw_image.bin" "$W/hs_dbg.cjs" <<'JS'
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const [, , IMG, CJS] = process.argv;
const img = readFileSync(IMG);
const req = createRequire(import.meta.url);
const mod = await req(CJS)();
mod.HEAPU8.set(img, 0x400000);
for (let o = 0; o < 0x100; o++) mod.HEAPU8[0x8a1000 + o] = 0;
if (process.env.HS_UTL_DBG) mod.HEAPU8[Number(mod._g_fw_utl_dbg) + 0] = 1;
try { console.error('[dbg] status=0x' + Number(mod._hs_e2e_run()).toString(16)); }
catch (e) { console.error('[dbg] EXC: ' + (e.message || '').split('\n')[0]); }
JS