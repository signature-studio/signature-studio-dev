#!/usr/bin/env bash
# GUI-6 (#182) 入力品質 e2e: tsc → input_app.c を emcc → headless Chrome + CDP 入力。RetDec / FL 不要。FAIL があれば非 0 で終了。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$(cd "$HERE/.." && pwd)"; ROOT="$(cd "$GUI/../.." && pwd)"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v node >/dev/null || { echo "node not found" >&2; exit 2; }
command -v google-chrome >/dev/null || [ -n "${CHROME_BIN:-}" ] || { echo "google-chrome not found" >&2; exit 2; }
(cd "$GUI" && "$ROOT/node_modules/.bin/tsc" -p tsconfig.json)
bash "$GUI/lift/gui_wasm.sh" "$HERE/input_app.c" "$GUI/build/input_wasm" | tail -1
node "$HERE/e2e.mjs"
