#!/usr/bin/env bash
# present e2e (GUI-4 / #180): tsc -> mergeRects 単体テスト -> headless Chrome で WebGL2/CPU の golden 画素一致・rAF・seqlock・bench。
# FL / lift / wasm / mingw / RetDec 不要 (模擬 guest)。PRESENT_SKIP_BENCH=1 で bench を省略。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$(cd "$HERE/.." && pwd)"; ROOT="$(cd "$GUI/../.." && pwd)"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v node >/dev/null || { echo "node not found" >&2; exit 2; }
command -v google-chrome >/dev/null || [ -n "${CHROME_BIN:-}" ] || { echo "google-chrome not found" >&2; exit 2; }
(cd "$GUI" && "$ROOT/node_modules/.bin/tsc" -p tsconfig.json)
node --test "$HERE/dirty.test.mjs" 2>&1 | grep -E "^(# |ℹ )(tests|pass|fail)"
node "$HERE/present_e2e.mjs"
