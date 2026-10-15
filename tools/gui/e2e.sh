#!/usr/bin/env bash
# gui_e2e.sh — 1 コマンド E2E:
#   mingw PE -> RetDec lift -> 後処理 -> emcc (pthread wasm) + shim -> tsc (gui.ts/gui_worker.ts)
#   -> headless Chrome (tools/e2e の agent-browser ドライバ経由の実入力; E2E_DRIVER=puppeteer で puppeteer-core)
#   -> OffscreenCanvas 読み戻し/スクリーンショット vs golden (exact) -> 長時間ストレス (e2e/stress.sh)
#   前提: tools/e2e で `npm ci` (agent-browser / puppeteer-core)
#   事前に native 単体テスト (selftest) と native lift 実行 (native_e2e) も流す。SKIP_NATIVE=1 で省略。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; BUILD="$HERE/build"; mkdir -p "$BUILD"
ROOT_REPO="$(cd "$HERE/../.." && pwd)"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v node >/dev/null || { echo "node not found (emsdk env)" >&2; exit 2; }
command -v google-chrome >/dev/null || [ -n "${CHROME:-}" ] || { echo "google-chrome not found" >&2; exit 2; }
E2E_TOOLS="${E2E_TOOLS_DIR:-$HERE/../e2e}"
case "${E2E_DRIVER:-agent-browser}" in
  agent-browser) E2E_DEP="$E2E_TOOLS/node_modules/.bin/agent-browser" ;;
  puppeteer) E2E_DEP="$E2E_TOOLS/node_modules/puppeteer-core/package.json" ;;
  *) echo "[gui-e2e] E2E_DRIVER=${E2E_DRIVER} は未対応 (agent-browser|puppeteer)" >&2; exit 2 ;;
esac
if [ ! -e "$E2E_DEP" ] && [ "${E2E_NO_AUTOINSTALL:-0}" != "1" ]; then
  (cd "$E2E_TOOLS" && npm ci --no-audit --no-fund --ignore-scripts) >&2 || true
fi
[ -e "$E2E_DEP" ] || { echo "[gui-e2e] 前提不足: $E2E_DEP が無い (step 6 のドライバが ENOENT で落ちる)。対処: (cd tools/e2e && npm ci --no-audit --no-fund --ignore-scripts) を実行する" >&2; exit 2; }
echo "[gui-e2e] 0/6 import 解析 + API 面生成"
[ -f "$HERE/analysis/imports_all.json" ] || python3 "$HERE/analysis/gui_imports.py" >/dev/null
python3 "$HERE/gen_api.py"
python3 "$HERE/integ/check_p1_tests.py"
python3 "$HERE/golden/gen_golden.py"
if [ "${SKIP_NATIVE:-0}" != "1" ]; then
  echo "[gui-e2e] 1/6 native 単体テスト (ASan/UBSan)"; bash "$HERE/test/selftest.sh" | tail -2
  echo "[gui-e2e] 1b/6 GUI-5 各 bpp シーン (独立 Python オラクル golden/gen_golden_bpp.py と画素完全一致 + ネガコン 2 本)"; bash "$HERE/test/bpp_golden.sh" | tail -4
  echo "[gui-e2e] 1c0/6 GUI-9 FreeType テキスト (native FreeType 直叩きの独立オラクルと画素/metrics 完全一致 + ネガコン 4 本 / engine の native==wasm32)"
  FTLIB="$HERE/../shared/work/build/freetype/native/src/objs/.libs/libfreetype.a"
  bash "$HERE/test/fetch_fonts.sh" | tail -1
  [ -f "$FTLIB" ] || FONT="$HERE/work/OpenSans-Regular.ttf" bash "$HERE/../shared/oss/freetype/build.sh" | tail -3
  bash "$HERE/test/text_golden.sh" | tail -7; bash "$HERE/test/ft_wasm.sh" | tail -2
  echo "[gui-e2e] 1d/6 GUI-7 popup/tooltip surface・NC 領域・無効領域複数矩形・DPI (独立 Python オラクル golden/gen_golden_nc.py と画素完全一致 + ネガコン 3 本)"; bash "$HERE/test/nc_golden.sh" | tail -6
  echo "[gui-e2e] 1e/6 GUI-7 テスト PE (popup + tooltip + WM_NCPAINT, lift 経由) の golden (独立 Python オラクル golden/gen_golden_ncpe.py と画素完全一致 + ネガコン 2 本: 1 画素改変 / tooltip の TOPMOST 欠陥 PE)"; bash "$HERE/test/nc_pe_golden.sh" | tail -6
  echo "[gui-e2e] 2/6 native lift 実行 (PE->RetDec->gcc, headless host, golden)"; bash "$HERE/test/native_e2e.sh" 2>&1 | grep -E "native_run|\[post\]"
  echo "[gui-e2e] 2a/6 __pe_image の data 実体化 (.reloc DIR64 補正; GUI-12 #566; ネガコン付き。FAIL なら非 0 で停止)"; bash "$HERE/test/pe_image_e2e.sh" 2>&1 | grep -E "PASS|FAIL|done"
  echo "[gui-e2e] 2b/6 結合準備 native (到達 API ログ / wasm32 署名 adapter / ハンドル 31bit / 改名 selftest; CAB-156)"; bash "$HERE/test/reach_test.sh" 2>&1 | grep -E "passed|FAIL"
  echo "[gui-e2e] 2c/6 W 版 Win32 ゲスト (Unicode API): native 通し・統計・EXACT MATCH (独立オラクル) + 到達ログ順序検査 (RegisterClassW < CreateWindowExW < WM_PAINT < BitBlt; ネガコン: 旧 shim で FAIL) (#3460/#3510)"
  bash "$HERE/test/native_w_e2e.sh" 2>&1 | grep -E "native_w|golden_w|reach_order|negctl|FAIL"
fi
echo "[gui-e2e] 1c/6 GUI-5 wasm SIMD128 行カーネル (scalar と画素完全一致 + 故意欠陥 4 種を検出 + v128 命令の有無; bench 省略)"
BENCH=0 bash "$HERE/test/simd_e2e.sh" | grep -E "OK|FAIL|ALL PASS|v128|cases"
echo "[gui-e2e] 3/6 PE -> RetDec lift -> 後処理 (WNDPROC は自動検出)"
bash "$HERE/lift/gui_lift.sh" "$HERE/test/gui_app.c" "$BUILD/lift"
# gui_wasm.sh は既定で libfreetype (wasm32) を要するため、SKIP_NATIVE=1 でも step 4 より前に保証する (build.sh はフォントを要する)
[ -f "$HERE/../shared/work/build/freetype/wasm32/src/objs/.libs/libfreetype.a" ] || { bash "$HERE/test/fetch_fonts.sh" | tail -1; FONT="$HERE/work/OpenSans-Regular.ttf" bash "$HERE/../shared/oss/freetype/build.sh" | tail -3; }
echo "[gui-e2e] 4/6 emcc (pthread wasm + shim)"
bash "$HERE/lift/gui_wasm.sh" "$BUILD/lift/lifted.c" "$BUILD/wasm" | tail -2
echo "[gui-e2e] 4b/6 GUI-13 wasm ビルド (gui_ft.c + libfreetype 組込み) のブラウザ上テキスト描画 (独立オラクルと画素/metrics 全一致 + ネガコン 5 本 + 8x8 経路の回帰; RetDec 不要)"
bash "$HERE/test/text_wasm_e2e.sh" | grep -E "組込み|regression|negctl|PASS|FAIL"
echo "[gui-e2e] 5/6 tsc (src/runtime/gui*.ts -> build/js)"
(cd "$HERE" && "$ROOT_REPO/node_modules/.bin/tsc" -p tsconfig.json)
echo "[gui-e2e] 6/6 headless Chrome E2E (fixed memory)"
node "$HERE/e2e/e2e.mjs"
echo "[gui-e2e] 6a/6 ネガコン: golden を 1 画素改竄すると E2E が exit 1 で落ちる (判定が不合格を握りつぶさない)"
rc=0; E2E_TAMPER=1 node "$HERE/e2e/e2e.mjs" >"$BUILD/e2e/negctl.log" 2>&1 || rc=$?
[ "$rc" -eq 1 ] && grep -q "MISMATCH" "$BUILD/e2e/negctl.log" || { echo "negctl FAIL: tampered golden -> exit=$rc (want 1)" >&2; tail -5 "$BUILD/e2e/negctl.log" >&2; exit 1; }
echo "  negctl OK: tampered golden rejected (exit 1)"
echo "[gui-e2e] 6b/6 headless Chrome E2E (ALLOW_MEMORY_GROWTH variant)"
bash "$HERE/lift/gui_wasm.sh" "$BUILD/lift/lifted.c" "$BUILD/wasm_grow" grow | tail -1
GUI_WASM_DIR="$BUILD/wasm_grow" node "$HERE/e2e/e2e.mjs" | grep -E "EXACT|MISMATCH|memory|PASS|FAIL"
echo "[gui-e2e] 6c/6 fail-fast E2E (未実装 API Ellipse に到達する PE)"
bash "$HERE/lift/gui_lift.sh" "$HERE/test/gui_app_ff.c" "$BUILD/lift_ff" >/dev/null
bash "$HERE/lift/gui_wasm.sh" "$BUILD/lift_ff/lifted.c" "$BUILD/wasm_ff" | tail -1
GUI_WASM_DIR="$BUILD/wasm_ff" E2E_MODE=failfast node "$HERE/e2e/e2e.mjs" | grep -E "fail-fast|FAIL|PASS"
echo "[gui-e2e] 6d/6 reach-log E2E (shim 改名 + wrapper で到達 API を記録; CAB-156)"
bash "$HERE/lift/gui_wasm.sh" "$BUILD/lift/lifted.c" "$BUILD/wasm_reach" reach | tail -1
GUI_WASM_DIR="$BUILD/wasm_reach" E2E_MODE=reach node "$HERE/e2e/e2e.mjs" | grep -E "EXACT|MISMATCH|reach|PASS|FAIL"
echo "[gui-e2e] 6e/6 sigprobe (m11 IR の GUI declare 署名 vs adapter, wasm-ld 署名検査 + 陰性対照)"
bash "$HERE/integ/sigprobe.sh" | tail -1
python3 "$HERE/integ/reach_report.py" "$BUILD/e2e/reach.log" >/dev/null
echo "[gui-e2e] 6f/6 present e2e (GUI-4: WebGL2 golden 一致 / 複数矩形 / rAF / seqlock; 模擬 guest, bench 省略)"
PRESENT_SKIP_BENCH=1 bash "$HERE/present/e2e.sh" | grep -E "^# (pass|fail)|ALL PASS|FAIL"
echo "[gui-e2e] 6g/6 GUI-6 入力品質 e2e (キー配列 / IME / タッチ・ジェスチャ / Pointer Lock; CDP 実入力, 入力リング drop 0; RetDec 不要)"
bash "$HERE/input/e2e.sh" | grep -E "FAIL|ALL PASS|input ring"
echo "[gui-e2e] 6h/6 長時間ストレス (GUI-8: 50000 frames / drop 0 / memory 有界 / surface gen 不変 + ネガコン burst・leak)"
bash "$HERE/e2e/stress.sh"
echo "[gui-e2e] ALL PASS"
