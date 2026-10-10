#!/usr/bin/env bash
# libkio_x64.dylib (x86_64 slice, 純粋ユーティリティ 15 関数) の lift PoC:
#   RetDec --select-ranges -> ir_normalize (m2 コピー) -> emcc (standalone wasm) -> 差分テスト
# usage: bash lift/libkio/lift.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
W="$ROOT/work/lift/libkio"; mkdir -p "$W"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
python3 - <<PY
import sys; sys.path.insert(0, "$ROOT/scripts")
from common import *
import shutil
shutil.copy(fat_slice(f"{MAC_SHARED}/libkio_x64.dylib"), "$W/kio.dylib")
rows=[l.split() for l in open("$HERE/funcs.txt") if not l.startswith('#') and l.strip() and 'ConvertUTF' not in l]
open("$W/ranges.txt","w").write(','.join('%s-0x%x'%(a,int(a,16)+int(s)) for n,a,s in rows))
open("$W/exports.txt","w").write('\n'.join(n for n,a,s in rows))
PY
cd "$W"
/opt/retdec/bin/retdec-decompiler kio.dylib -o kio.drc.c --select-ranges "$(cat ranges.txt)" --select-decode-only --timeout 600 > kio.retdec.log 2>&1
echo "[kio] retdec: $(grep -c '^define' kio.drc.ll) functions lifted"
python3 "$HERE/ir_normalize.py" kio.drc.ll kio_norm_raw.ll >/dev/null
cp kio_norm_raw.ll kio_norm.ll
[ "${FIX:-1}" = 1 ] && python3 "$HERE/kio_fix.py" kio_norm_raw.ll kio_norm.ll
EXP=$(sed 's/^/-Wl,--export=/' exports.txt | tr '\n' ' ')
emcc kio_norm.ll "$HERE/kio_simd.c" -o kio.wasm -O1 -w -Wno-error=int-conversion \
  -sSTANDALONE_WASM=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 -sALLOW_MEMORY_GROWTH=0 -sINITIAL_MEMORY=16MB -sSTACK_SIZE=256KB \
  -sGLOBAL_BASE=1024 --no-entry -Wl,--no-gc-sections $EXP
echo "[kio] wasm: $(stat -c %s kio.wasm) bytes, exports: $(wasm-objdump -x kio.wasm 2>/dev/null | grep -c 'func.*Z' || true)"
python3 "$HERE/diff_test.py" "$W"
