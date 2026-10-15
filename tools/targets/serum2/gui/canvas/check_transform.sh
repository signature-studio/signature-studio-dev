#!/usr/bin/env bash
# SR-69 #4428: setTransformMatrix の実測。原点 (0,0) と原点以外 (40,20) のコンテナに置いた子 view が、
# それぞれの位置に描かれることを確かめる (transform_check_main.cpp)。
# 段階 (compile / link / run) ごとに rc・所要 ms を summary に出す。判定は run の pass 行。
# 前提: work/vstgui4 (vstgui4_14_3)、work/emsdk/upstream/emscripten (toolchain-emsdk の展開)、node。
# 前提: check_render_poc.sh を先に 1 回走らせて work/render_poc/upstream_cpp.txt を作っておく。
# 出力: work/transform_check/ (gitignore)。
# usage: bash check_transform.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
gui="$(dirname "$here")"
work="$gui/work"
out="$work/transform_check"
export EM_IGNORE_SANITY=1
export PATH="$work/emsdk/upstream/emscripten:$PATH"
export HERE="$here" OUT="$out"

cd "$work/vstgui4" || exit 2
if [ ! -f "$work/render_poc/upstream_cpp.txt" ]; then
  echo "upstream_cpp.txt が無い。先に check_render_poc.sh を実行する" >&2
  exit 2
fi
rm -rf "$out" && mkdir -p "$out/obj"

compile_one () {
	local src="$1"
	local obj="$OUT/obj/$(echo "$src" | tr '/' '_').o"
	timeout 300 em++ -std=c++17 -O0 -g -c -I. -I"$HERE" "$src" -o "$obj" > "$obj.log" 2>&1
	echo "$? $src"
}
export -f compile_one

{ cat "$work/render_poc/upstream_cpp.txt"; ls "$here"/canvas_*.cpp; echo "$here/transform_check_main.cpp"; } > "$out/all_cpp.txt"
t0=$(date +%s%N)
xargs -P 4 -n 1 bash -c 'compile_one "$0"' < "$out/all_cpp.txt" > "$out/compile_rc.txt"
t1=$(date +%s%N)
n_fail=$(awk '$1!=0' "$out/compile_rc.txt" | wc -l)
echo "compile: total=$(wc -l < "$out/all_cpp.txt") fail=$n_fail secs=$(( (t1 - t0) / 1000000 ))ms" | tee "$out/summary.txt"

objs=$(awk '$1==0 {print $2}' "$out/compile_rc.txt" | while read -r s; do echo "$out/obj/$(echo "$s" | tr '/' '_').o"; done)
t2=$(date +%s%N)
timeout 600 em++ -std=c++17 -O0 -g $objs -o "$out/transform_check.js" \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1 > "$out/link.log" 2>&1
link_rc=$?
t3=$(date +%s%N)
echo "link: rc=$link_rc secs=$(( (t3 - t2) / 1000000 ))ms" | tee -a "$out/summary.txt"

rc=0
if [ -f "$out/transform_check.js" ]; then
  # package.json が "type": "module" のため、emscripten の .js は CommonJS の複製 (.cjs) で実行する。
  cp "$out/transform_check.js" "$out/transform_check_run.cjs"
  t4=$(date +%s%N)
  timeout 60 node "$out/transform_check_run.cjs" > "$out/run.log" 2>&1
  run_rc=$?
  t5=$(date +%s%N)
  echo "run: rc=$run_rc secs=$(( (t5 - t4) / 1000000 ))ms $(grep -h 'transform_' "$out/run.log" | tr '\n' ' ')" | tee -a "$out/summary.txt"
  [ "$(grep -c 'result=pass' "$out/run.log")" -eq 2 ] || rc=1
  [ "$run_rc" -eq 0 ] || rc=1
else
  echo "run: skipped (no transform_check.js)" | tee -a "$out/summary.txt"
  rc=1
fi
[ "$link_rc" -eq 0 ] || rc=1
[ "$n_fail" -eq 0 ] || rc=1
exit $rc
