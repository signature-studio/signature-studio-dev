#!/usr/bin/env bash
# SR-68 #4427: 線の太さ・アンチエイリアスを line_width_main.cpp で bitmap へ描き、判定する。
# 判定: (1) 全ケース rc=1 かつ非ゼロ>0 (2) 太い線 (w4) は細い線 (w1) より非ゼロ画素が多い
#       (3) aliasing は部分被覆 0 (4) aliasing の w4 は完全被覆のみ (5) AA は部分被覆 > 0 (6) AA の非ゼロ数が aliasing より多い。
# fail なら rc=1。出力: work/line_width/ (gitignore)。
# usage: bash check_line_width.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
gui="$(dirname "$here")"
work="$gui/work"
out="$work/line_width"
export EM_IGNORE_SANITY=1
export PATH="$work/emsdk/upstream/emscripten:$PATH"
export OUT="$out" HERE="$here"

cd "$work/vstgui4" || exit 2
for p in vstguibase_emscripten platformfwd_emscripten platformfactory_emscripten; do
  if git apply --reverse --check "$gui/patches/$p.patch" 2>/dev/null; then
    echo "$p: 適用済み (patch 適用済み扱い)"
  else
    git apply "$gui/patches/$p.patch" || exit 2
  fi
done

rm -rf "$out" && mkdir -p "$out/obj"
{ ls vstgui/lib/*.cpp; ls vstgui/lib/controls/*.cpp; ls vstgui/lib/animation/*.cpp; echo vstgui/lib/platform/platformfactory.cpp; } > "$out/upstream_cpp.txt"
{ ls "$here"/canvas_*.cpp | grep -v render_poc; echo "$here/line_width_main.cpp"; } > "$out/canvas_cpp.txt"
cat "$out/upstream_cpp.txt" "$out/canvas_cpp.txt" > "$out/all_cpp.txt"

compile_one () {
	local src="$1"
	local obj="$OUT/obj/$(echo "$src" | tr '/' '_').o"
	timeout 300 em++ -std=c++17 -O0 -g -c -I. -I"$HERE" "$src" -o "$obj" > "$obj.log" 2>&1
	echo "$? $src"
}
export -f compile_one

xargs -P 4 -n 1 bash -c 'compile_one "$0"' < "$out/all_cpp.txt" > "$out/compile_rc.txt"
objs=$(awk '$1==0 {print $2}' "$out/compile_rc.txt" | while read -r s; do echo "$out/obj/$(echo "$s" | tr '/' '_').o"; done)
timeout 600 em++ -std=c++17 -O0 -g $objs -o "$out/line_width.js" \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1 > "$out/link.log" 2>&1
link_rc=$?
echo "link: rc=$link_rc" | tee "$out/summary.txt"

rc=0
[ "$link_rc" -eq 0 ] || rc=1
if [ -f "$out/line_width.js" ]; then
  cp "$out/line_width.js" "$out/line_width_run.cjs"
  timeout 60 node "$out/line_width_run.cjs" > "$out/run.log" 2>&1
  run_rc=$?
  echo "run: rc=$run_rc" | tee -a "$out/summary.txt"
  [ "$run_rc" -eq 0 ] || rc=1
  declare -A nz part full
  while read -r _ namef ok nzf partf fullf; do
    name=${namef#name=}
    nz[$name]=${nzf#nonzero=}; part[$name]=${partf#partial=}; full[$name]=${fullf#full=}
    echo "case $name: $ok nonzero=${nz[$name]} partial=${part[$name]} full=${full[$name]}" | tee -a "$out/summary.txt"
    if [ "$ok" != "rc=1" ] || [ "${nz[$name]:-0}" -le 0 ]; then rc=1; fi
  done < <(grep '^line_width ' "$out/run.log")
  chk () { if eval "$2"; then echo "check $1: pass" | tee -a "$out/summary.txt"; else echo "check $1: fail" | tee -a "$out/summary.txt"; rc=1; fi; }
  chk "thick_more_pixels" '[ "${nz[w4_alias]:-0}" -gt "${nz[w1_alias]:-0}" ]'
  chk "alias_no_partial" '[ "${part[w1_alias]:-1}" -eq 0 ] && [ "${part[w4_alias]:-1}" -eq 0 ]'
  chk "aa_has_partial" '[ "${part[w1_aa]:-0}" -gt 0 ] && [ "${part[w4_aa]:-0}" -gt 0 ]'
  chk "aa_more_pixels" '[ "${nz[w4_aa]:-0}" -gt "${nz[w4_alias]:-0}" ]'
  corner_over=$(grep '^corner_join ' "$out/run.log" | sed -n 's/.* over=\([0-9]*\).*/\1/p')
  chk "corner_no_double_blend" '[ -n "$corner_over" ] && [ "$corner_over" -eq 0 ]'
else
  echo "run: skipped (no line_width.js)" | tee -a "$out/summary.txt"
  rc=1
fi
echo "rc=$rc" | tee -a "$out/summary.txt"
exit $rc
