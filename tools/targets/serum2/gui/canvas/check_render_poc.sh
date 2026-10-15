#!/usr/bin/env bash
# SR-36 #2065: CTextLabel のみの canvas 描画 harness (render_poc_main.cpp) を wasm にコンパイル・リンク・実行する。
# 段階 (compile / link / run / render) ごとに rc・所要秒・件数を summary に出す。途中で失敗しても後段は試行する。
# SR-50 #3260: render 行 (nonzero_after>0 かつ text_width>=0) を判定にし、fail なら rc=1。
# 前提: work/vstgui4 (vstgui4_14_3)、work/emsdk/upstream/emscripten (toolchain-emsdk の展開)、node。
# 出力: work/render_poc/ (gitignore)。
# usage: bash check_render_poc.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
gui="$(dirname "$here")"
work="$gui/work"
out="$work/render_poc"
export EM_IGNORE_SANITY=1
export PATH="$work/emsdk/upstream/emscripten:$PATH"
export HERE="$here" OUT="$out"

cd "$work/vstgui4" || exit 2
if ! git diff --quiet -- vstgui/lib/vstguibase.h vstgui/lib/platform/platformfwd.h; then
  echo "vstguibase.h / platformfwd.h は既に変更済み (patch 適用済み扱い)"
else
  git apply "$gui/patches/vstguibase_emscripten.patch" || exit 2
  git apply "$gui/patches/platformfwd_emscripten.patch" || exit 2
fi

rm -rf "$out" && mkdir -p "$out/obj"

# upstream は lib/*.cpp・lib/controls/*.cpp・lib/animation/*.cpp を対象にする (platform/ 以下は canvas で置換するため除外)。
# lib/animation は CView::~CView → Animator::removeAnimations の未解決を止めるために加えた (初回リンクで 1 件)。
# platform/platformfactory.cpp は WASM 分岐が無いため除外し、harness が getPlatformFactory を定義する。
{ ls vstgui/lib/*.cpp; ls vstgui/lib/controls/*.cpp; ls vstgui/lib/animation/*.cpp; } > "$out/upstream_cpp.txt"
{ ls "$here"/canvas_*.cpp; echo "$here/render_poc_main.cpp"; } > "$out/canvas_cpp.txt"
cat "$out/upstream_cpp.txt" "$out/canvas_cpp.txt" > "$out/all_cpp.txt"

compile_one () {
	local src="$1"
	local obj="$OUT/obj/$(echo "$src" | tr '/' '_').o"
	timeout 300 em++ -std=c++17 -O0 -g -c -I. -I"$HERE" "$src" -o "$obj" > "$obj.log" 2>&1
	echo "$? $src"
}
export -f compile_one

t0=$(date +%s%N)
xargs -P 4 -n 1 bash -c 'compile_one "$0"' < "$out/all_cpp.txt" > "$out/compile_rc.txt"
t1=$(date +%s%N)
n_total=$(wc -l < "$out/all_cpp.txt")
n_ok=$(awk '$1==0' "$out/compile_rc.txt" | wc -l)
n_upstream_ok=$(awk '$1==0 && $2 ~ /^vstgui\//' "$out/compile_rc.txt" | wc -l)
n_upstream_total=$(wc -l < "$out/upstream_cpp.txt")
n_canvas_fail=$(awk '$1!=0 && $2 !~ /^vstgui\//' "$out/compile_rc.txt" | wc -l)
err_lines=$(cat "$out"/obj/*.log 2>/dev/null | grep -c 'error:')
echo "compile: total=$n_total ok=$n_ok upstream_ok=$n_upstream_ok/$n_upstream_total canvas_or_harness_fail=$n_canvas_fail error_lines=$err_lines secs=$(( (t1 - t0) / 1000000 ))ms" | tee "$out/summary.txt"

objs=$(awk '$1==0 {print $2}' "$out/compile_rc.txt" | while read -r s; do echo "$out/obj/$(echo "$s" | tr '/' '_').o"; done)
t2=$(date +%s%N)
timeout 600 em++ -std=c++17 -O0 -g $objs -o "$out/render_poc.js" \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1 > "$out/link.log" 2>&1
link_rc=$?
t3=$(date +%s%N)
n_undef=$(grep -o 'undefined symbol: [^ ]*' "$out/link.log" | sort -u | wc -l)
echo "link: rc=$link_rc undefined_symbols=$n_undef secs=$(( (t3 - t2) / 1000000 ))ms wasm_bytes=$(stat -c %s "$out/render_poc.wasm" 2>/dev/null) js_bytes=$(stat -c %s "$out/render_poc.js" 2>/dev/null)" | tee -a "$out/summary.txt"

if [ -f "$out/render_poc.js" ]; then
  # リポジトリ直下の package.json が "type": "module" のため、.js (emscripten の出力) は ESM 扱いで読まれて require できない。
  # 同じ wasm を参照する CommonJS の複製 (.cjs) で実行する。
  cp "$out/render_poc.js" "$out/render_poc_run.cjs"
  t4=$(date +%s%N)
  timeout 60 node "$out/render_poc_run.cjs" > "$out/run.log" 2>&1
  run_rc=$?
  t5=$(date +%s%N)
  echo "run: rc=$run_rc secs=$(( (t5 - t4) / 1000000 ))ms stdout=$(grep -c render_poc "$out/run.log") output=$(grep render_poc "$out/run.log" | head -1)" | tee -a "$out/summary.txt"
  # 判定: 描画後の非ゼロ画素 (bitmap へ書かれた画素) > 0 かつ文字列幅 >= 0。
  after=$(grep -o 'nonzero_after=[0-9]*' "$out/run.log" | head -1 | cut -d= -f2)
  tw=$(grep -o 'text_width=[-0-9.e+]*' "$out/run.log" | head -1 | cut -d= -f2)
  tpx=$(grep -o 'text_px=[0-9]*' "$out/run.log" | head -1 | cut -d= -f2)
  # text_px>0 は追加条件。nonzero_after は黒背景 (drawRect) だけでも >0 になるため、文字が描かれたことを別に確認する。
  if [ -n "$after" ] && [ "$after" -gt 0 ] && [ -n "$tw" ] && awk -v t="$tw" 'BEGIN { exit !(t + 0 >= 0) }' && [ -n "$tpx" ] && [ "$tpx" -gt 0 ]; then
    echo "render: pass (nonzero_after=$after text_width=$tw text_px=$tpx)" | tee -a "$out/summary.txt"
  else
    echo "render: fail (nonzero_after=${after:-none} text_width=${tw:-none} text_px=${tpx:-none})" | tee -a "$out/summary.txt"
    render_rc=1
  fi
else
  echo "run: skipped (no render_poc.js)" | tee -a "$out/summary.txt"
  render_rc=1
fi

# 終了コードは link・run・render の判定。render が fail なら 1。
rc=0
[ "$link_rc" -eq 0 ] || rc=1
[ "${run_rc:-1}" -eq 0 ] || rc=1
[ "${render_rc:-0}" -eq 0 ] || rc=1
exit $rc
