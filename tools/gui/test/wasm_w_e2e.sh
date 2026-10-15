#!/usr/bin/env bash
# wasm_w_e2e.sh — W 版ゲスト (gui_app_w.c) を wasm 化し、既存の tools/gui/e2e ページ・ドライバで読み戻し検証する (#3509 WIN-31)。
#   mingw PE -> RetDec -> 後処理 -> gui_wasm.sh (emcc, pthread + SAB) -> headless Chrome (E2E_MODE=w)。
#   OffscreenCanvas 読み戻しと画面スクリーンショットは独立オラクル (golden/gen_golden_w.py) と画素比較し、
#   読み戻しの RGB 3 バイト列の sha256 は native (native_w_e2e.sh の surface 行) と比べる。ネガコン: 期待画像 1 画素改竄で不一致になること。
#   FL の素材は使わない。FreeType は組み込まない (GUI_NO_FT=1): W 版ゲストは FreeType を使わず、文字は内蔵 8x8 経路。
#   前提: emsdk・google-chrome・mingw-w64・RetDec・tsc。tools/e2e の依存は無ければ npm ci する。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"; REPO="$(cd "$ROOT/../.." && pwd)"
mkdir -p "$BUILD"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v node >/dev/null || { echo "node not found" >&2; exit 2; }
E2E_TOOLS="${E2E_TOOLS_DIR:-$ROOT/../e2e}"
[ -e "$E2E_TOOLS/node_modules/.bin/agent-browser" ] || (cd "$E2E_TOOLS" && npm ci --no-audit --no-fund --ignore-scripts) >&2
TSC="$REPO/node_modules/.bin/tsc"; [ -x "$TSC" ] || TSC="$(command -v tsc)"

# 1. native: surface の sha256 (比較対象) を build/native_w_run.log へ残す
bash "$HERE/native_w_e2e.sh" > "$BUILD/native_w_e2e.log" 2>&1 || { tail -20 "$BUILD/native_w_e2e.log"; echo "[wasm_w_e2e] FAIL: native_w_e2e.sh" >&2; exit 1; }
# 2. lift -> 後処理 -> emcc (pthread wasm + shim; reach 変種で到達ログ・WM_PAINT 配送の GUI-MSG 行を出す)
bash "$ROOT/lift/gui_lift.sh" "$HERE/gui_app_w.c" "$BUILD/lift_w" WndProc SubWndProc
GUI_NO_FT=1 bash "$ROOT/lift/gui_wasm.sh" "$BUILD/lift_w/lifted.c" "$BUILD/wasm_w" reach | tail -1
# 3. JS (gui.ts / gui_worker.ts)
(cd "$ROOT" && "$TSC" -p tsconfig.json)
# 4. 既存ページ・ドライバで読み戻し (期待 EXACT MATCH・native sha256 一致・スクリーンショット一致)
rc=0; GUI_WASM_DIR="$BUILD/wasm_w" E2E_MODE=w node "$ROOT/e2e/e2e.mjs" > "$BUILD/wasm_w_e2e.log" 2>&1 || rc=$?
grep -E 'EXACT|MISMATCH|sha256|exit|PASS|FAIL' "$BUILD/wasm_w_e2e.log" || true
[ "$rc" -eq 0 ] && grep -q '^\[e2e\] PASS$' "$BUILD/wasm_w_e2e.log" || { echo "[wasm_w_e2e] FAIL: e2e rc=$rc" >&2; exit 1; }
# 4b. 到達ログの順序検査 (wasm 側の trace; RegisterClassW < CreateWindowExW < WM_PAINT 配送 < BitBlt) (#3510)
python3 "$HERE/reach_order_check.py" "$BUILD/e2e/w_reach.log" || { echo "[wasm_w_e2e] FAIL: wasm trace の順序検査" >&2; exit 1; }
# 5. ネガコン: 期待画像を 1 画素改竄すると MISMATCH で落ちること
rc=0; E2E_TAMPER=1 GUI_WASM_DIR="$BUILD/wasm_w" E2E_MODE=w node "$ROOT/e2e/e2e.mjs" > "$BUILD/wasm_w_negctl.log" 2>&1 || rc=$?
[ "$rc" -eq 1 ] && grep -q 'MISMATCH' "$BUILD/wasm_w_negctl.log" || { echo "[wasm_w_e2e] FAIL: negctl rc=$rc (want 1 with MISMATCH)" >&2; exit 1; }
echo "[wasm_w_e2e] PASS (negctl: 1 px 改竄で MISMATCH・rc 1)"
