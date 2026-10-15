#!/usr/bin/env bash
# SR-61 #4231: drawArc・drawPoint・drawGraphicsPath を追加。SR-55 #3422: 描画命令 (drawLine・drawLines・drawPolygon・drawEllipse・drawBitmap) を draw_ops_main.cpp で bitmap へ直接描き、
# 各命令が画素を書いたこと (rc=1 かつ nonzero>0) を判定する。fail なら rc=1。
# 前提: work/vstgui4 (vstgui4_14_3)、work/emsdk/upstream/emscripten (toolchain-emsdk の展開)、node。
# 出力: work/draw_ops/ (gitignore)。
# usage: bash check_draw_ops.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
gui="$(dirname "$here")"
work="$gui/work"
out="$work/draw_ops"
export EM_IGNORE_SANITY=1
export PATH="$work/emsdk/upstream/emscripten:$PATH"

cd "$work/vstgui4" || exit 2
for p in vstguibase_emscripten platformfwd_emscripten platformfactory_emscripten; do
  if git apply --reverse --check "$gui/patches/$p.patch" 2>/dev/null; then
    echo "$p: 適用済み (patch 適用済み扱い)"
  else
    git apply "$gui/patches/$p.patch" || exit 2
  fi
done

rm -rf "$out" && mkdir -p "$out/obj"
# 描画 harness は vstgui の lib (CDrawContext・CViewContainer 等) と canvas 層の両方を要るので、check_render_poc.sh と同じ対象を使う。
{ ls vstgui/lib/*.cpp; ls vstgui/lib/controls/*.cpp; ls vstgui/lib/animation/*.cpp; echo vstgui/lib/platform/platformfactory.cpp; } > "$out/upstream_cpp.txt"
{ ls "$here"/canvas_*.cpp | grep -v render_poc; echo "$here/draw_ops_main.cpp"; } > "$out/canvas_cpp.txt"
cat "$out/upstream_cpp.txt" "$out/canvas_cpp.txt" > "$out/all_cpp.txt"

compile_one () {
	local src="$1"
	local obj="$OUT/obj/$(echo "$src" | tr '/' '_').o"
	timeout 300 em++ -std=c++17 -O0 -g -c -I. -I"$HERE" "$src" -o "$obj" > "$obj.log" 2>&1
	echo "$? $src"
}
export -f compile_one
export OUT="$out" HERE="$here"

xargs -P 4 -n 1 bash -c 'compile_one "$0"' < "$out/all_cpp.txt" > "$out/compile_rc.txt"
objs=$(awk '$1==0 {print $2}' "$out/compile_rc.txt" | while read -r s; do echo "$out/obj/$(echo "$s" | tr '/' '_').o"; done)
timeout 600 em++ -std=c++17 -O0 -g $objs -o "$out/draw_ops.js" \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1 > "$out/link.log" 2>&1
link_rc=$?
echo "link: rc=$link_rc" | tee "$out/summary.txt"

rc=0
[ "$link_rc" -eq 0 ] || rc=1
# コンパイルに失敗した src があれば fail (失敗したものを外して link すると、そのまま通ってしまうため)。
n_compile_fail=$(awk '$1!=0' "$out/compile_rc.txt" | wc -l)
echo "compile: fail=$n_compile_fail" | tee -a "$out/summary.txt"
[ "$n_compile_fail" -eq 0 ] || rc=1
if [ -f "$out/draw_ops.js" ]; then
  cp "$out/draw_ops.js" "$out/draw_ops_run.cjs"
  timeout 60 node "$out/draw_ops_run.cjs" > "$out/run.log" 2>&1
  run_rc=$?
  echo "run: rc=$run_rc" | tee -a "$out/summary.txt"
  [ "$run_rc" -eq 0 ] || rc=1
  # 期待する命令数 (SR-55 の 5 件 + SR-61 の 3 件 + SR-62 の 4 件 = 12 件、drawBitmap 含む。SR-78 の拡大縮小 3 件を足して 15 件) が揃わなければ fail (欠けた命令が無判定で通るのを防ぐ)。
  n_ops=$(grep -c '^draw_op ' "$out/run.log")
  [ "$n_ops" -eq 15 ] || { echo "ops: fail (draw_op lines=$n_ops, expected 15)" | tee -a "$out/summary.txt"; rc=1; }
  while read -r _ name ok nz; do
    n=${nz#nonzero=}
    if [ "$ok" = "rc=1" ] && [ "${n:-0}" -gt 0 ]; then
      echo "op $name: pass ($nz)" | tee -a "$out/summary.txt"
    else
      echo "op $name: fail ($ok $nz)" | tee -a "$out/summary.txt"
      rc=1
    fi
  done < <(grep '^draw_op ' "$out/run.log")
  # SR-78 #4551: 拡大縮小と bilinear は画素数で判定する。
  # 8x8 → 32x32 の拡大は 1024 画素、9 分割 (dest 20x20) は 400 画素。bilinear は中間階調が出て、最近傍は出ない。
  expect_exact () {
    local name="$1" want="$2"
    local got
    got=$(grep "^draw_op name=$name " "$out/run.log" | sed -E 's/.*nonzero=([0-9]+).*/\1/')
    if [ "${got:-x}" = "$want" ]; then
      echo "op $name: pass (nonzero=$got, want=$want)" | tee -a "$out/summary.txt"
    else
      echo "op $name: fail (nonzero=${got:-none}, want=$want)" | tee -a "$out/summary.txt"
      rc=1
    fi
  }
  expect_exact fillRectWithBitmap_scale 1024
  expect_exact drawBitmapNinePartTiled_scale 400
  bil=$(grep '^draw_op name=fillRectWithBitmap_bilinear ' "$out/run.log" | sed -E 's/.*nonzero=([0-9]+).*/\1/')
  nea=$(grep '^mid_tone name=fillRectWithBitmap_nearest ' "$out/run.log" | sed -E 's/.*count=([0-9]+).*/\1/')
  if [ "${bil:-0}" -gt 0 ] && [ "${nea:-1}" -eq 0 ]; then
    echo "op fillRectWithBitmap_interp: pass (bilinear_mid=$bil, nearest_mid=$nea)" | tee -a "$out/summary.txt"
  else
    echo "op fillRectWithBitmap_interp: fail (bilinear_mid=${bil:-none}, nearest_mid=${nea:-none})" | tee -a "$out/summary.txt"
    rc=1
  fi
  # gradient は一様な色で塗られていないこと (異なる色が 2 以上)。nonzero>0 だけでは一色の塗りを通してしまう。
  while read -r _ name distinct; do
    d=${distinct#distinct=}
    case "$name" in
      name=fillLinearGradient|name=fillRadialGradient)
        if [ "${d:-0}" -ge 2 ]; then
          echo "color $name: pass ($distinct)" | tee -a "$out/summary.txt"
        else
          echo "color $name: fail ($distinct)" | tee -a "$out/summary.txt"
          rc=1
        fi ;;
    esac
  done < <(grep '^draw_color ' "$out/run.log")
else
  echo "run: skipped (no draw_ops.js)" | tee -a "$out/summary.txt"
  rc=1
fi
exit $rc
