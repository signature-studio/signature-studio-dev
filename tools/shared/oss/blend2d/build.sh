#!/usr/bin/env bash
# Blend2D (FL の libblend2d は camelCase C ABI (blArrayInit) + asmjit ABI _abi_1_13 => 2024-01..2025-03 頃の pre-v0.20 系。
#  v0.20.0 (2025-09) で snake_case 化 (bl_array_init) されているため master は不一致) を
#  (a) native + JIT (元バイナリと同じ x86 JIT パイプライン) / (b) native no-JIT / (c) emscripten wasm32 no-JIT
# で upstream から再ビルドし、test_b2d.cpp の画素ハッシュを突合する。
#  wasm では JIT 不可 (実行時コード生成不可) -> BLEND2D_NO_JIT=ON (固定パイプライン) が唯一の選択。
# usage: bash oss/blend2d/build.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
SRC="$ROOT/work/src/blend2d"; B="$ROOT/work/build/blend2d"
REV=fc827d56fb529cb6977d923733dcb411c172cd03   # blend2d 2024-12-13 (v0.20.0 の snake_case 改名の直前)
if [ ! -d "$SRC/.git" ]; then git clone -q https://github.com/blend2d/blend2d "$SRC"; fi
git -C "$SRC" checkout -q "$REV"
ASM="$ROOT/work/src/asmjit"
[ -d "$ASM/.git" ] || git clone -q https://github.com/asmjit/asmjit "$ASM"
git -C "$ASM" fetch -q --unshallow 2>/dev/null || true
git -C "$ASM" checkout -q 029075b84bf0161a761beb63e6eda519a29020db   # asmjit 最後の _abi_1_13 (342b57f が 1_14 化する直前; FL バイナリの asmjit 名前空間と一致)
COMMON="-DBLEND2D_STATIC=ON -DASMJIT_DIR=$ASM -DBLEND2D_NO_INSTALL=ON"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
[ "${CLEAN:-0}" = 1 ] && rm -rf "$B"; mkdir -p "$B"
FONT="${FONT:-/home/ubuntu/work/analysis/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Shared/Artwork/Fonts/OpenSans-Regular.ttf}"
echo "[b2d] native JIT"
cmake -S "$SRC" -B "$B/native_jit" -G Ninja -DCMAKE_BUILD_TYPE=Release $COMMON >"$B/native_jit.log" 2>&1
cmake --build "$B/native_jit" -j12 >>"$B/native_jit.log" 2>&1
echo "[b2d] native no-JIT"
cmake -S "$SRC" -B "$B/native_nojit" -G Ninja -DCMAKE_BUILD_TYPE=Release $COMMON -DBLEND2D_NO_JIT=ON >"$B/native_nojit.log" 2>&1
cmake --build "$B/native_nojit" -j12 >>"$B/native_nojit.log" 2>&1
echo "[b2d] wasm32 no-JIT (emcmake)"
emcmake cmake -S "$SRC" -B "$B/wasm" -G Ninja -DCMAKE_BUILD_TYPE=Release $COMMON -DBLEND2D_NO_JIT=ON -DBLEND2D_NO_TLS=ON -DBLEND2D_NO_FUTEX=ON >"$B/wasm.log" 2>&1
cmake --build "$B/wasm" -j12 >>"$B/wasm.log" 2>&1
for v in native_jit native_nojit; do
  g++ -O2 -std=c++17 -I"$SRC/src" "$HERE/test_b2d.cpp" "$B/$v/libblend2d.a" -lpthread -lrt -o "$B/test_$v"
done
em++ -O2 -std=c++17 -I"$SRC/src" "$HERE/test_b2d.cpp" "$B/wasm/libblend2d.a" -o "$B/test_wasm.cjs" \
  -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 -sSTACK_SIZE=2MB
echo "[b2d] sizes: libblend2d.a jit=$(stat -c %s "$B/native_jit/libblend2d.a") nojit=$(stat -c %s "$B/native_nojit/libblend2d.a") wasm=$(stat -c %s "$B/wasm/libblend2d.a"); test.wasm=$(stat -c %s "$B/test_wasm.wasm")"
DUMP_PPM="$B/jit.ppm"    "$B/test_native_jit"   "$FONT" > "$B/out_native_jit.txt"
DUMP_PPM="$B/nojit.ppm"  "$B/test_native_nojit" "$FONT" > "$B/out_native_nojit.txt"
DUMP_PPM="$B/wasm.ppm"   node "$B/test_wasm.cjs" "$FONT" > "$B/out_wasm.txt"
for f in native_jit native_nojit wasm; do echo "[b2d] $f: $(cat "$B/out_$f.txt" | tr '\n' ' ')"; done
for v in native_jit native_nojit; do echo "[b2d] bench $v: $(BENCH=300 "$B/test_$v" "$FONT" | grep bench)"; done
echo "[b2d] bench wasm32 (node $(node --version)): $(BENCH=300 node "$B/test_wasm.cjs" "$FONT" | grep bench)"
rc=0
if cmp -s "$B/nojit.ppm" "$B/wasm.ppm"; then echo "[b2d] PASS: native(no-JIT) == wasm(no-JIT) pixel-exact"; else echo "[b2d] FAIL: native(no-JIT) != wasm"; rc=1; fi
python3 - "$B/jit.ppm" "$B/nojit.ppm" <<'PY'
import sys
def load(p):
    d=open(p,'rb').read(); i=0; hdr=[]
    for _ in range(4):
        j=d.index(b'\n',i); hdr.append(d[i:j]); i=j+1
    return d[i:]
a=load(sys.argv[1]); b=load(sys.argv[2])
diff=[abs(x-y) for x,y in zip(a,b) if x!=y]
print(f"[b2d] JIT vs no-JIT (native): differing bytes={len(diff)}/{len(a)} max_abs={max(diff) if diff else 0}")
PY
exit $rc
