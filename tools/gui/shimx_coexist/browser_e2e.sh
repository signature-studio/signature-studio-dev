#!/usr/bin/env bash
# shimx × gui 共存の実ブラウザ確認 (#956 / #1159 SHX-T19)。前提: coexist.sh を一度走らせて work/ に obj がある。
#   1. 同じ obj を ENVIRONMENT=web,worker でリンク (wasm 内容は node 版と同一・環境のみ変更)
#   2. gui_hostcall.ts を browser 向けに bundle し、page を置く
#   3. browser_e2e.mjs が headless Chrome で page を開き、CDP の実クリックで main を起動して結果を検査
#   env: EMSDK_ENV (既定 $HOME/emsdk/emsdk_env.sh), CHROME (既定 google-chrome), COEXIST_WORK
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$HERE/.."; SX="$GUI/../shimx"; REPO="$(cd "$GUI/../.." && pwd)"
W="${COEXIST_WORK:-$HERE/work}"
[ -f "$W/gui_obj/gui_adapt_w32.o" ] && [ -f "$W/t_main.o" ] || { echo "[browser] $W に obj が無い。先に bash tools/gui/shimx_coexist/coexist.sh"; exit 2; }
set +u; . "${EMSDK_ENV:-$HOME/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "[browser] emcc が無い"; exit 2; }
source "$SX/flags.sh"
COMMON=(); for a in "${SHIMX_EMCC_COMMON[@]}"; do [[ $a == -sENVIRONMENT=* ]] || COMMON+=("$a"); done
COMMON+=(-sENVIRONMENT=web,worker)
EXPORTS=_main,_gui_headless_attach,_gui_hostcall_ptr,_gui_stage_dir_posix,_gui_drop_files,_gui_shimx_attach,_malloc,_free
WEB="$W/web"; rm -rf "$WEB"; mkdir -p "$WEB"
set +e
emcc "${COMMON[@]}" -pthread -sPTHREAD_POOL_SIZE=8 -sPROXY_TO_PTHREAD=1 -sMODULARIZE=1 -sEXPORT_NAME=coexist -sSTACK_SIZE=1MB \
  -sEXPORTED_RUNTIME_METHODS=FS,UTF8ToString,HEAPU8,wasmMemory -sEXPORTED_FUNCTIONS=$EXPORTS -Wno-pthreads-mem-growth -Wl,--fatal-warnings -Wl,--error-limit=0 \
  "$W"/gui_obj/*.o "$W"/sx_obj/*.o "$W/t_gui.o" "$W/t_main.o" -o "$WEB/coexist.js" > "$WEB/link.log" 2>&1
RC=$?; set -e
echo "[browser] web link rc=$RC (log: $WEB/link.log)"
[ "$RC" -eq 0 ] || { head -30 "$WEB/link.log"; exit 1; }
bun build "$REPO/src/runtime/gui_hostcall.ts" --target=browser --format=esm --outfile "$WEB/hostcall.js" >/dev/null
cp "$HERE/browser_index.html" "$HERE/browser_page.js" "$WEB/"
node "$HERE/browser_e2e.mjs" "$WEB"
