#!/usr/bin/env bash
# ILSvg の版の組 (svgdom 0.4.7 + svgren 0.6.4) を wasm と native で連結ビルドし、スモーク比較する (#927)。
#   usage: bash tools/shared/oss/ilsvg/build_pair.sh
# 生成物は tools/shared/work/ilsvg_pair/ (gitignore)。結論は tools/shared/oss/ilsvg/REPORT.md。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
W="$ROOT/work/ilsvg_pair"; mkdir -p "$W"; cd "$W"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc --version | head -1

co() { [ -d "$1" ] || git clone -q --depth 1 --branch "$2" "https://github.com/cppfw/$3.git" "$1"; }
co svgdom-0.4.7 0.4.7 svgdom
co svgren-0.6.4 0.6.4 svgren
co r4-1.0.74 1.0.74 r4
co cssom-0.2.4 0.2.4 cssom
co mikroxml-0.1.56 0.1.56 mikroxml
[ -d utki-1.1.200 ] || { git clone -q --filter=blob:none --no-checkout https://github.com/cppfw/utki.git utki; mkdir utki-1.1.200 && git -C utki archive 1.1.200 | tar -x -C utki-1.1.200; }
[ -d papki-1.0.101 ] || { [ -d papki ] || git clone -q --filter=blob:none --no-checkout https://github.com/cppfw/papki.git papki; mkdir papki-1.0.101 && git -C papki archive 3ed8151 | tar -x -C papki-1.0.101; }
[ -d agg ] || git clone -q --filter=blob:none https://github.com/cppfw/agg.git agg
git -C agg checkout -q 2.8.9
mkdir -p aggroot && ln -sfn "$W/agg/src/agg/include" aggroot/agg

# probe 限定の置換 (utki 1.1.200 に無い API)。FL 版の papki / cssom との一致は未確認。
sed -i 's/utki::make_unique/std::make_unique/g' papki-1.0.101/src/papki/vector_file.hpp
sed -i 's/utki::kilobyte/1024/g' cssom-0.2.4/src/cssom/om.cpp

INC="-I utki-1.1.200/src -I r4-1.0.74/src -I papki-1.0.101/src -I cssom-0.2.4/src -I mikroxml-0.1.56/src -I svgdom-0.4.7/src -I agg/src/agg/include -I aggroot -I svgren-0.6.4/src"
# papki の fs_file.cpp は OS 依存 (emscripten 非対応) のため外す
SRCS="$(find svgdom-0.4.7/src/svgdom -name '*.cpp' | sort) $(find svgren-0.6.4/src/svgren -name '*.cpp' | sort) $(ls agg/src/agg/src/*.cpp | sort) $(find mikroxml-0.1.56/src -name '*.cpp' | sort) $(find utki-1.1.200/src -name '*.cpp' | sort) $(find papki-1.0.101/src -name '*.cpp' | grep -v fs_file | sort) $(find cssom-0.2.4/src -name '*.cpp' | sort)"

# wasm: svgdom/svgren/agg/mikroxml/utki/papki/cssom を連結
em++ -O2 -w -std=c++17 -fno-sized-deallocation $INC $SRCS "$HERE/wrap/ilsvg_wrap.cpp" \
  -sWASM=1 -sMODULARIZE=1 -sEXPORT_NAME=createILSvg -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS=_svgCreate,_svgRender,_svgDestroy,_malloc,_free \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32 -o ilsvg.js
echo "[ilsvg] wasm: $(stat -c %s ilsvg.wasm) B"

# native: 同じソースで一致比較用の基準を作る
g++ -O2 -w -std=c++17 $INC $SRCS "$HERE/wrap/native_main.cpp" -lz -o nat
echo "[ilsvg] native: built"
