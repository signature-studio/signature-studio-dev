#!/usr/bin/env bash
# build_guest.sh — 製品ページ結線の検証用ゲスト (tools/gui/test/text_wasm_app.c、GUI_NO_FT=1 = 内蔵 8x8) を wasm 化し、chunked descriptor にする。
#   usage: bash tools/gui/e2e/build_guest.sh <outdir>
#   出力: <outdir>/app.js (emcc glue) ・ <outdir>/app.wasm ・ <outdir>/app.wasm.parts/index.json (+ 64 KiB の part)
#   前提: emcc (EMSDK_ENV = emsdk_env.sh のパス、または PATH 上の emcc)。mingw-w64 は無ければ apt で導入 (gen_api.py の aux_arity が使う)。FreeType 不要。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."
OUT="${1:?usage: build_guest.sh <outdir>}"; mkdir -p "$OUT"
if [ -n "${EMSDK_ENV:-}" ]; then set +u; . "$EMSDK_ENV" >/dev/null 2>&1 || true; set -u; fi
command -v emcc >/dev/null || { echo "emcc が無い (EMSDK_ENV に emsdk_env.sh のパスを指定)" >&2; exit 2; }
if ! command -v x86_64-w64-mingw32-gcc >/dev/null; then
  sudo -n apt-get update -qq >/dev/null 2>&1 || true
  sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends gcc-mingw-w64-x86-64 mingw-w64-x86-64-dev >/dev/null
fi
python3 "$ROOT/gen_api.py" >/dev/null
TMPB="$(mktemp -d)"
GUI_NO_FT=1 bash "$ROOT/lift/gui_wasm.sh" "$ROOT/test/text_wasm_app.c" "$TMPB" | tail -1
cp "$TMPB/app.js" "$TMPB/app.wasm" "$OUT/"
node "$HERE/stage_guest.mjs" "$OUT/app.wasm" 65536
# ネガコン (d): part 0 を 1 バイト改竄したコピー (descriptor の sha256 は元のまま。chunked の検証で止まること)
rm -rf "$OUT/tampered" && mkdir -p "$OUT/tampered" && cp -r "$OUT/app.wasm.parts" "$OUT/tampered/app.wasm.parts"
node -e 'const fs = require("fs"); const d = process.argv[1]; const p = d + "/" + JSON.parse(fs.readFileSync(d + "/index.json", "utf8")).parts[0].name; const b = fs.readFileSync(p); b[0] ^= 0xff; fs.writeFileSync(p, b);' "$OUT/tampered/app.wasm.parts"
