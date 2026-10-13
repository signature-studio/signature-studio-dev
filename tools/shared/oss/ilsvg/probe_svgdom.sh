#!/usr/bin/env bash
# ILSvg の svgdom/svgren 連結ビルドの版の組を probe する (#877)。
#   usage: bash tools/shared/oss/ilsvg/probe_svgdom.sh
# 生成物は tools/shared/work/ilsvg_probe/ (gitignore)。結果の解釈は NOTES.md。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
W="$ROOT/work/ilsvg_probe"; mkdir -p "$W/ob"; cd "$W"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc --version | head -1

co() { [ -d "$1" ] || git clone -q --depth 1 --branch "$2" "https://github.com/cppfw/$3.git" "$1"; }
co svgdom-0.4.7 0.4.7 svgdom
co svgren-0.6.3 0.6.3 svgren
co svgren-0.5.9 0.5.9 svgren
co r4-1.0.74 1.0.74 r4
co cssom-0.2.4 0.2.4 cssom
co mikroxml-0.1.56 0.1.56 mikroxml
[ -d utki ] || git clone -q --filter=blob:none --no-checkout https://github.com/cppfw/utki.git utki
[ -d utki-1.1.200 ] || { mkdir utki-1.1.200 && git -C utki archive 1.1.200 | tar -x -C utki-1.1.200; }
[ -d papki-1.0.101 ] || { [ -d papki ] || git clone -q --filter=blob:none --no-checkout https://github.com/cppfw/papki.git papki; mkdir papki-1.0.101 && git -C papki archive 3ed8151 | tar -x -C papki-1.0.101; }
# papki 1.0.101 は utki::make_unique を使うが utki 1.1.200 に無い。std::make_unique へ置換 (probe のみ)
sed -i 's/utki::make_unique/std::make_unique/g' papki-1.0.101/src/papki/vector_file.hpp
[ -d agg ] || git clone -q --filter=blob:none https://github.com/cppfw/agg.git agg
git -C agg checkout -q 2.8.9
mkdir -p aggroot && ln -sfn "$W/agg/src/agg/include" aggroot/agg

B="-I utki-1.1.200/src -I r4-1.0.74/src -I papki-1.0.101/src -I cssom-0.2.4/src -I mikroxml-0.1.56/src"

count() { # $1=label $2=src dir $3=extra include
  local ok=0 fail=0 f
  for f in $(find "$2" -name '*.cpp' | sort); do
    if emcc -c -O0 -w -std=c++17 $B $3 "$f" -o ob/x.o 2>ob/err.txt; then ok=$((ok+1))
    else fail=$((fail+1)); echo "  FAIL $(basename "$f"): $(grep -m1 error ob/err.txt | cut -c1-200)"; fi
  done
  echo "[$1] ok=$ok fail=$fail"
}

echo "== A: svgdom 0.4.7 (utki 1.1.200 / r4 1.0.74 / papki 1.0.101 / cssom 0.2.4 / mikroxml 0.1.56)"
count "svgdom-0.4.7" svgdom-0.4.7/src/svgdom "-I svgdom-0.4.7/src"
echo "== B: svgren 0.6.3 (+ svgdom 0.4.7, agg 2.8.9 headers)"
count "svgren-0.6.3" svgren-0.6.3/src "-I svgdom-0.4.7/src -I aggroot -I svgren-0.6.3/src"
echo "== C: svgren 0.5.9 (+ svgdom 0.4.7, -include <list>)"
count "svgren-0.5.9" svgren-0.5.9/src "-include list -I svgdom-0.4.7/src -I aggroot -I svgren-0.5.9/src"
