#!/usr/bin/env bash
# native_w_e2e.sh — W 版ゲスト (gui_app_w.c: RegisterClassW → CreateWindowExW → メッセージループ → WM_PAINT → GDI → W 文字列往復)
#   を mingw PE → RetDec → 後処理 → gcc native + shim + headless host で走らせ、最終 surface の統計を取る (#3460)。
#   FL の素材は使わない (fl-win64 不要)。出力 PPM は build/ (gitignore) に置く。
#   到達ログ (GUI-REACH / GUI-MSG) の順序検査 (#3510): shim を gui_wasm.sh reach と同じ改名 + wrapper で組み、
#   ネガコンは GUI_REACH_LOG の無い旧 shim (WM_PAINT 配送の行が出ない) で組んで検査が FAIL することを確かめる。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"; mkdir -p "$BUILD/lift_w"
python3 "$ROOT/gen_api.py" >/dev/null
bash "$ROOT/lift/gui_lift.sh" "$HERE/gui_app_w.c" "$BUILD/lift_w" WndProc SubWndProc
gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
  -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=int-to-pointer-cast \
  "$BUILD/lift_w/lifted.c" -c -o "$BUILD/lift_w/lifted.o"
gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$BUILD" -Dmain=gui_lift_app_main -c "$ROOT/lift/gui_lift_main.c" -o "$BUILD/lift_w/lift_main.o"
# shim (gui_core・gui_gdi・gui_stubs) を改名 (gui_rename.h) して gui_wrap_i64.c の到達ログ付き wrapper 経由で公開する。$1 = 出力 dir、以降 = gui_core.c の追加フラグ
build_shim() {
  local out="$1"; shift
  mkdir -p "$out"
  for f in "$ROOT/src/gui_core.c" "$ROOT/src/gui_gdi.c" "$BUILD/gui_stubs.c"; do
    local extra=(); [ "$(basename "$f")" = gui_core.c ] && extra=("$@")
    gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
      ${extra[@]+"${extra[@]}"} -include "$BUILD/gui_rename.h" -c "$f" -o "$out/$(basename "$f" .c).o"
  done
  gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" -c "$BUILD/gui_wrap_i64.c" -o "$out/gui_wrap_i64.o"
}
link_w() {   # $1 = shim の .o dir、$2 = 出力 exe
  gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
    "$BUILD/lift_w/lifted.o" "$BUILD/lift_w/lift_main.o" "$1"/*.o \
    "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$BUILD"/gui_reach_tab.c "$ROOT"/src/gui_headless.c "$ROOT"/src/gui_hl_stats.c \
    "$HERE/native_w_run.c" -o "$2" -lm
}
build_shim "$BUILD/lift_w/shim_reach" -DGUI_REACH_LOG
link_w "$BUILD/lift_w/shim_reach" "$BUILD/native_w_run"
(cd "$BUILD" && timeout 120 ./native_w_run "$BUILD/w_actual.ppm" 2>&1 | tee "$BUILD/native_w_run.log")
# ゲストの ExitProcess が先に走ると native_w_run は FAIL を出す前に終わり rc 0 になる (#3508)。PASS 行を必須にする。
grep -q '^\[native_w_run\] PASS' "$BUILD/native_w_run.log" || { echo "[native_w_e2e] FAIL: PASS 行が無い" >&2; exit 1; }
# 独立オラクル (shim と無関係に描画規約から計算した期待画像) と画素比較。ネガコン: 1 画素改竄した期待画像では必ず不一致 (#3508)
python3 "$ROOT/golden/gen_golden_w.py" compare "$BUILD/w_actual.ppm"
tamper_log="$(python3 "$ROOT/golden/gen_golden_w.py" compare "$BUILD/w_actual.ppm" --tamper || true)"
echo "$tamper_log"
grep -q '^\[golden_w\] MISMATCH' <<< "$tamper_log" || { echo "[native_w_e2e] FAIL: ネガコン (改竄オラクル) が MISMATCH を出さなかった (例外・終了コードだけでは判定しない)" >&2; exit 1; }
# 到達ログの順序検査 (RegisterClassW < CreateWindowExW < WM_PAINT 配送 < BitBlt)。検査自体は合成ログで先に確かめる (#3510)
python3 "$HERE/reach_order_check.py" --selftest
python3 "$HERE/reach_order_check.py" "$BUILD/native_w_run.log"
# ネガコン: WM_PAINT 配送の行を出さない旧 shim (GUI_REACH_LOG なしの gui_core) の trace では順序検査が FAIL (rc 1) になる
build_shim "$BUILD/lift_w/shim_old"
link_w "$BUILD/lift_w/shim_old" "$BUILD/native_w_run_old"
(cd "$BUILD" && timeout 120 ./native_w_run_old "$BUILD/w_old.ppm" > "$BUILD/native_w_run_old.log" 2>&1) || { echo "[native_w_e2e] FAIL: 旧 shim のネガコン実行が失敗" >&2; exit 1; }
rc=0; python3 "$HERE/reach_order_check.py" "$BUILD/native_w_run_old.log" || rc=$?
[ "$rc" -eq 1 ] || { echo "[native_w_e2e] FAIL: ネガコン (旧 shim) で順序検査が FAIL にならなかった (rc=$rc)" >&2; exit 1; }
echo "[native_w_e2e] negctl OK: 旧 shim の trace は順序検査で FAIL (rc 1)"
