#!/usr/bin/env bash
# 実ブラウザ (Chrome) での host 側 browserEnv 確認 (SHX-T19 #1159)。1 コマンド: bash tools/gui/shimx_coexist/browser_e2e.sh
#   1. coexist.sh の objects (work/gui_obj・sx_obj) から ENVIRONMENT=web,worker の wasm を link (INVOKE_RUN=0: main は走らせない)
#   2. src/runtime/gui_hostcall.ts を ES モジュール化 (work/js)
#   3. browser_e2e.mjs が headless Chrome (CDP) で page を開き、wasm の hostcall 要求を browserEnv で処理させて検査
#   env: COEXIST_WORK (既定 work), EMSDK_ENV (既定 /opt/emsdk/emsdk_env.sh), CHROME (既定 google-chrome)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$HERE/.."; SX="$GUI/../shimx"; REPO="$(cd "$GUI/../.." && pwd)"
W="${COEXIST_WORK:-$HERE/work}"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "[browser] emcc が無い"; exit 2; }
source "$SX/flags.sh"
[ -f "$W/gui_obj/gui_adapt_w32.o" ] && [ -f "$W/sx_obj/shell.o" ] || { echo "[browser] objects 無し → coexist.sh を先に実行"; bash "$HERE/coexist.sh" >/dev/null; }
COMMON=(); for x in "${SHIMX_EMCC_COMMON[@]}"; do [[ $x == -sENVIRONMENT=* ]] || COMMON+=("$x"); done
EXPORTS=_main,_gui_headless_attach,_gui_hostcall_ptr,_gui_stage_dir_posix,_gui_drop_files,_gui_shimx_attach,_malloc,_free
rm -rf "$W/web" "$W/js"; mkdir -p "$W/web" "$W/js"
emcc "${COMMON[@]}" -sENVIRONMENT=web,worker -pthread -sPTHREAD_POOL_SIZE=8 -sPROXY_TO_PTHREAD=1 -sMODULARIZE=1 -sEXPORT_NAME=coexistWeb \
  -sINVOKE_RUN=0 -sSTACK_SIZE=1MB -sEXPORTED_RUNTIME_METHODS=FS,wasmMemory -sEXPORTED_FUNCTIONS=$EXPORTS -Wno-pthreads-mem-growth \
  -Wl,--fatal-warnings "$W"/gui_obj/*.o "$W"/sx_obj/*.o "$W/t_gui.o" "$W/t_main.o" -o "$W/web/coexistWeb.js" > "$W/web_link.log" 2>&1
echo "[browser] web link rc=$? (log: $W/web_link.log)"
"$REPO/node_modules/.bin/tsc" --ignoreConfig --target ES2022 --module ES2022 --lib ES2022,DOM,DOM.Iterable --strict --skipLibCheck --outDir "$W/js" "$REPO/src/runtime/gui_hostcall.ts"
node "$HERE/browser_e2e.mjs" "$W/web" "$W/js"
