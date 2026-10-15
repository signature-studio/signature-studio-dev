#!/usr/bin/env bash
# P20 (#2963) ネガティブコントロール: lift C の 1 命令 (0x180afe195 `addss xmm0, xmm1` → 減算) を壊した wasm を作り、
# fa_native_diff.py が FAIL すること (不一致 > 0) と署名が変わることを確認する。
#   usage: bash tools/perf/p20/fa_negctl.sh   (前提: bash tools/perf/p20/build_fa_gain.sh 済み)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
SRC="$HERE/work/fa"
DST="$HERE/work/fa_neg"
RT="$ROOT/tools/flelift/rt"
[ -f "$SRC/lift/fle_lifted.c" ] || { echo "[fa_negctl] 前提が無い: $SRC/lift (build_fa_gain.sh を先に)" >&2; exit 2; }
if ! command -v emcc >/dev/null 2>&1 && [ -n "${EMSDK:-}" ]; then source "$EMSDK/emsdk_env.sh" >/dev/null 2>&1; fi
rm -rf "$DST" && mkdir -p "$DST" && cp -r "$SRC/lift" "$DST/"
LN=$(grep -n '180afe195: addss xmm0, xmm1' "$DST/lift/fle_lifted.c" | cut -d: -f1)
LN=$((LN + 1))
sed -i "${LN}s/X\[0\]\.f\[0\] = a_ + b_;/X[0].f[0] = a_ - b_;/" "$DST/lift/fle_lifted.c"
grep -q 'a_ - b_' <(sed -n "${LN}p" "$DST/lift/fle_lifted.c") || { echo "[fa_negctl] 置換に失敗" >&2; exit 1; }
emcc -O0 -ffp-contract=off -fno-fast-math -I "$RT" "$DST/lift/fle_lifted.c" "$DST/lift/fle_data.c" \
  "$RT/fle_cpu.c" "$RT/fle_glue.c" -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) -o "$DST/fa.cjs" > "$DST/link.log" 2>&1
echo "broken line: $LN"
echo "sig(broken): $(node "$HERE/fa_gain_sig.mjs" "$DST/fa.cjs" 400 64030 | grep -o '"sig":"[0-9a-f]*"')"
python3 "$HERE/fa_native_diff.py" --n 400 --seed 64030 --cjs "$DST/fa.cjs" --out "$DST/diff"
