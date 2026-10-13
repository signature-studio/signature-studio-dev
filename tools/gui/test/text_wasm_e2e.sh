#!/usr/bin/env bash
# text_wasm_e2e.sh — GUI-13 (#615): gui_wasm.sh の wasm ビルド (gui_ft.c + libfreetype 組込み) をブラウザ (headless Chrome) で走らせ、
#   フォントを host call で遅延取得 (sha256 検証) → GDI テキスト描画 → 独立オラクル (native FreeType 直叩き) と画素/metrics 全一致 + ネガコン 4 本。
# 1 コマンド: bash tools/gui/test/text_wasm_e2e.sh   前提: tools/shared/oss/freetype/build.sh 済み (native + wasm32 libfreetype)・emsdk・google-chrome・tsc。RetDec 不要。
# 追加検査: 既定 wasm は gui_ft_add_face を export し GUI_NO_FT=1 のビルドは export しない (組込みの有無)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; B="$ROOT/build"; mkdir -p "$B"
FTW="$ROOT/../shared/work"; FONTDIR="${FONTDIR:-$ROOT/work}"
REPO="$(cd "$ROOT/../.." && pwd)"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v google-chrome >/dev/null || [ -n "${CHROME:-}" ] || { echo "google-chrome not found" >&2; exit 2; }
FTSRC="$FTW/src/freetype-2.7"; FTLIB="$FTW/build/freetype/native/src/objs/.libs/libfreetype.a"
[ -f "$FTLIB" ] || { echo "native libfreetype.a missing: run tools/shared/oss/freetype/build.sh" >&2; exit 2; }
bash "$HERE/fetch_fonts.sh" | tail -1
python3 "$ROOT/gen_api.py" >/dev/null
echo "[text-wasm-e2e] 1/4 独立オラクル (native FreeType 直叩き)"
gcc -O1 -w -I "$FTSRC/include" "$ROOT/golden/ft_oracle.c" "$FTLIB" -o "$B/ft_oracle" -lm
"$B/ft_oracle" "$FONTDIR" "$B/text_oracle.ppm" "$B/text_oracle.tsv"
echo "[text-wasm-e2e] 2/4 wasm ビルド (text_wasm_app.c + shim + gui_ft.c + libfreetype wasm32 pthread)"
rm -rf "$B/text_app"; mkdir -p "$B/text_app"
bash "$ROOT/lift/gui_wasm.sh" "$HERE/text_wasm_app.c" "$B/text_app" | tail -2
# 組込み確認 (ネガコン): GUI_NO_FT=1 のビルドは gui_ft_add_face を export しない。既定ビルドは export する (strings で検査)
rm -rf "$B/text_app_noft"; GUI_NO_FT=1 bash "$ROOT/lift/gui_wasm.sh" "$HERE/text_wasm_app.c" "$B/text_app_noft" | tail -1
if grep -q "gui_ft_add_face" "$B/text_app/app.js" && ! grep -q "gui_ft_add_face" "$B/text_app_noft/app.js"; then echo "[text-wasm-e2e] 組込み OK: 既定 wasm は gui_ft_add_face を export / GUI_NO_FT=1 は export しない (wasm $(stat -c %s "$B/text_app/app.wasm") B vs $(stat -c %s "$B/text_app_noft/app.wasm") B)"
else echo "FAIL: FT export presence check"; exit 1; fi
echo "[text-wasm-e2e] 3/4 tsc (src/runtime/gui*.ts -> build/js)"
(cd "$ROOT" && "${TSC:-$(command -v tsc || echo "$REPO/node_modules/.bin/tsc")}" -p tsconfig.json)
echo "[text-wasm-e2e] 4/4 headless Chrome: 本番 + ネガコン 5 本 + 8x8 経路の回帰 (従来ビルドと画素一致)"
node "$ROOT/e2e/text_e2e.mjs" "$B/text_oracle.ppm" "$B/text_oracle.tsv" "$FONTDIR" "$B/text_app" "$B/text_app_noft"
