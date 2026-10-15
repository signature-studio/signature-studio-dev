#!/usr/bin/env bash
# 版の組の probe (#151): symbol 解析と整合する 2021 年当時の組で連結ビルドし、スモーク比較する。
#   svgdom 0.3.61 (cssom 化済み・enum 名 default_) + svgren 0.6.3 + cssom 0.1.19 + utki 1.1.124 + r4 1.0.53 + mikroxml 0.1.36 + papki 6ec4c66 (1.0.93) + agg 2.8.9
#   probe 限定の置換: svgren/util.cpp の scope_exit::release() → reset() (utki 1.1.124 の名前。動作は同じ)
#   usage: bash tools/shared/oss/ilsvg/probe_pair_0361.sh
# 生成物は tools/shared/work/ilsvg_pair_0361/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
W="$ROOT/work/ilsvg_pair_0361"; mkdir -p "$W"; cd "$W"
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1
emcc --version | head -1

co() { [ -d "$1" ] || git clone -q --depth 1 --branch "$2" "https://github.com/cppfw/$3.git" "$1"; }
co svgdom-0.3.61 0.3.61 svgdom
co svgren-0.6.3 0.6.3 svgren
co cssom-0.1.19 0.1.19 cssdom
co r4-1.0.53 1.0.53 r4
co mikroxml-0.1.36 0.1.36 mikroxml
[ -d utki-1.1.124 ] || { [ -d utki ] || git clone -q --filter=blob:none --no-checkout https://github.com/cppfw/utki.git utki; mkdir utki-1.1.124 && git -C utki archive 1.1.124 | tar -x -C utki-1.1.124; }
[ -d papki-6ec4c66 ] || { [ -d papki ] || git clone -q --filter=blob:none --no-checkout https://github.com/cppfw/papki.git papki; mkdir papki-6ec4c66 && git -C papki archive 6ec4c66 | tar -x -C papki-6ec4c66; }
[ -d agg ] || git clone -q --filter=blob:none https://github.com/cppfw/agg.git agg
git -C agg checkout -q 2.8.9
mkdir -p aggroot && ln -sfn "$W/agg/src/agg/include" aggroot/agg

sed -i 's/scope_exit\.release()/scope_exit.reset()/' svgren-0.6.3/src/svgren/util.cpp

INC="-include cstdint -include limits -I utki-1.1.124/src -I r4-1.0.53/src -I papki-6ec4c66/src -I cssom-0.1.19/src -I mikroxml-0.1.36/src -I svgdom-0.3.61/src -I agg/src/agg/include -I aggroot -I svgren-0.6.3/src"
# papki の fs_file.cpp は OS 依存 (emscripten 非対応) のため外す
SRCS="$(find svgdom-0.3.61/src/svgdom -name '*.cpp' | sort) $(find svgren-0.6.3/src/svgren -name '*.cpp' | sort) $(ls agg/src/agg/src/*.cpp | sort) $(find mikroxml-0.1.36/src -name '*.cpp' | sort) $(find utki-1.1.124/src -name '*.cpp' | sort) $(find papki-6ec4c66/src -name '*.cpp' | grep -v fs_file | sort) $(find cssom-0.1.19/src -name '*.cpp' | sort)"

em++ -O2 -w -std=c++17 -fno-sized-deallocation $INC $SRCS "$HERE/wrap/ilsvg_wrap.cpp" \
  -sWASM=1 -sMODULARIZE=1 -sEXPORT_NAME=createILSvg -sALLOW_MEMORY_GROWTH=1 -sUSE_ZLIB=1 \
  -sEXPORTED_FUNCTIONS=_svgCreate,_svgRender,_svgDestroy,_malloc,_free \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32 -o ilsvg.js
echo "[probe] wasm: $(stat -c %s ilsvg.wasm) B"

g++ -O2 -w -std=c++17 $INC $SRCS "$HERE/wrap/native_main.cpp" -lz -o nat
echo "[probe] native: built"

SMOKE="$HERE/wrap/smoke.svg"
cp ilsvg.js ilsvg.cjs
./nat "$SMOKE" nat.bin > nat.txt
node "$HERE/wrap/wasm_smoke.cjs" ./ilsvg.cjs "$SMOKE" wasm.bin 64 64 > wasm.txt
echo "[probe] native: $(cat nat.txt)"
echo "[probe] wasm:   $(cat wasm.txt)"
echo "[probe] native bytes: $(stat -c %s nat.bin)  wasm bytes: $(stat -c %s wasm.bin)"
if cmp nat.bin wasm.bin; then
  echo "[probe] cmp: IDENTICAL"
else
  echo "[probe] cmp: DIFFER"
  exit 1
fi
