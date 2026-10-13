#!/usr/bin/env bash
# Blend2D wasm: -msimd128 の画素一致 + 速度試験 (T-SH-02)。
#  base   : wasm32 no-JIT (build.sh の wasm 構成と同一フラグ)
#  simd   : base + -msimd128 (wasm 自動ベクトル化のみ)
#  simd_sse2 : base + -msimd128 -msse2 (emscripten の SSE2 -> wasm SIMD エミュレーション経由で Blend2D の SSE2 経路を有効化)
# 比較基準は native no-JIT (build.sh と同じ構成)。
# usage: bash oss/blend2d/simd_bench.sh   (env: FONT=<ttf> BENCH=<iters> RUNS=<n>)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
SRC="$ROOT/work/src/blend2d"; ASM="$ROOT/work/src/asmjit"; B="$ROOT/work/build/blend2d_simd"
REV=fc827d56fb529cb6977d923733dcb411c172cd03
ASMREV=029075b84bf0161a761beb63e6eda519a29020db
[ -d "$SRC/.git" ] || git clone -q https://github.com/blend2d/blend2d "$SRC"
[ -d "$ASM/.git" ] || git clone -q https://github.com/asmjit/asmjit "$ASM"
git -C "$SRC" checkout -q "$REV"; git -C "$ASM" checkout -q "$ASMREV"
# emsdk の場所は toolchain-emsdk 素材 (/opt/emsdk) を既定とする
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1
FONT="${FONT:-$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Shared/Artwork/Fonts/OpenSans-Regular.ttf}"
[ -f "$FONT" ] || FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
BENCH="${BENCH:-300}"; RUNS="${RUNS:-3}"
mkdir -p "$B"
COMMON="-DBLEND2D_STATIC=ON -DASMJIT_DIR=$ASM -DBLEND2D_NO_INSTALL=ON -DBLEND2D_NO_JIT=ON"
JOBS="$(nproc)"
echo "[simd] font=$FONT nproc=$JOBS emcc=$(emcc --version | head -1 | sed 's/(.*//') node=$(node --version)"

build_native() {
  cmake -S "$SRC" -B "$B/native" -G Ninja -DCMAKE_BUILD_TYPE=Release $COMMON >"$B/native.log" 2>&1 &&
  cmake --build "$B/native" -j"$JOBS" >>"$B/native.log" 2>&1 &&
  g++ -O2 -std=c++17 -I"$SRC/src" "$HERE/test_b2d.cpp" "$B/native/libblend2d.a" -lpthread -lrt -o "$B/test_native"
}
build_wasm() { # name extra-flags
  local n="$1" fl="$2"
  emcmake cmake -S "$SRC" -B "$B/$n" -G Ninja -DCMAKE_BUILD_TYPE=Release $COMMON -DBLEND2D_NO_TLS=ON -DBLEND2D_NO_FUTEX=ON \
    -DCMAKE_C_FLAGS="$fl" -DCMAKE_CXX_FLAGS="$fl" >"$B/$n.log" 2>&1 &&
  cmake --build "$B/$n" -j"$JOBS" >>"$B/$n.log" 2>&1 &&
  em++ -O2 $fl -std=c++17 -I"$SRC/src" "$HERE/test_b2d.cpp" "$B/$n/libblend2d.a" -o "$B/test_$n.cjs" \
    -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 -sSTACK_SIZE=2MB
}
echo "[simd] build native no-JIT"; build_native || { echo "[simd] native build FAIL (see $B/native.log)"; }
for v in "base:" "simd:-msimd128" "simd_sse2:-msimd128 -msse2"; do
  n="${v%%:*}"; fl="${v#*:}"
  echo "[simd] build wasm $n (flags='$fl')"
  build_wasm "$n" "$fl" || echo "[simd] wasm $n build FAIL (see $B/$n.log)"
done

DUMP_PPM="$B/native.ppm" "$B/test_native" "$FONT" > "$B/out_native.txt"
echo "[simd] native: $(tr '\n' ' ' < "$B/out_native.txt")"
echo "[simd] load average before bench: $(cut -d' ' -f1-3 /proc/loadavg)"
for r in $(seq "$RUNS"); do echo "[simd] bench native_nojit run$r: $(BENCH=$BENCH "$B/test_native" "$FONT" | grep bench)"; done
rc=0
for n in base simd simd_sse2; do
  [ -f "$B/test_$n.cjs" ] || { echo "[simd] $n: no binary"; rc=1; continue; }
  DUMP_PPM="$B/$n.ppm" node "$B/test_$n.cjs" "$FONT" > "$B/out_$n.txt" 2>&1
  echo "[simd] $n: $(tr '\n' ' ' < "$B/out_$n.txt")"
  if cmp -s "$B/native.ppm" "$B/$n.ppm"; then echo "[simd] $n: PASS pixel-exact vs native no-JIT"; else
    echo "[simd] $n: FAIL pixel diff vs native no-JIT"
    python3 - "$B/native.ppm" "$B/$n.ppm" <<'PY'
import sys
def load(p):
    d=open(p,'rb').read(); i=0
    for _ in range(3): i=d.index(b'\n',i)+1
    return d[i:]
a=load(sys.argv[1]); b=load(sys.argv[2])
diff=[abs(x-y) for x,y in zip(a,b) if x!=y]
print(f"[simd]   differing bytes={len(diff)}/{len(a)} max_abs={max(diff) if diff else 0}")
PY
    rc=1
  fi
  for r in $(seq "$RUNS"); do echo "[simd] bench $n run$r: $(BENCH=$BENCH node "$B/test_$n.cjs" "$FONT" | grep bench)"; done
  echo "[simd] sizes $n: libblend2d.a=$(stat -c %s "$B/$n/libblend2d.a") test.wasm=$(stat -c %s "$B/test_$n.wasm")"
done
echo "[simd] load average after: $(cut -d' ' -f1-3 /proc/loadavg)"
exit $rc
