#!/usr/bin/env bash
# P20 (#2963): Fresh Air GainDsp::process (SlateCore 0x180afe090) を flelift の x64c で lift し、emcc で wasm (単独 instance) にする。
#   usage: bash tools/perf/p20/build_fa_gain.sh
#   入力: tools/targets/freshair/work/win/ (bash tools/targets/freshair/fetch.sh の展開物。FA_DL で plugins-freshair の展開先を指定)
#   emcc: PATH に無ければ EMSDK (docs/REFERENCES.md §4 の [EMSDK] の展開先) の emsdk_env.sh を読む
#   出力: tools/perf/p20/work/fa/fa.cjs・fa.wasm (gitignore の work/。commit しない)
#   手順は tools/targets/kilohearts/scripts/build_closure_x64c.sh と同じ (IMG/SHIFT のみ FA の値)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
FLE="$ROOT/tools/flelift"
RT="$FLE/rt"
CORE="$ROOT/tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
OUT="$HERE/work/fa"
LIFT="$OUT/lift"
IMG=0x180000000
SHIFT=0x17E000000
SIZE=0x2319000
GAIN_VA=0x180afe090
[ -f "$CORE" ] || { echo "[build_fa_gain] 入力が無い: $CORE (bash tools/targets/freshair/fetch.sh を先に)" >&2; exit 2; }
if ! command -v emcc >/dev/null 2>&1 && [ -n "${EMSDK:-}" ]; then source "$EMSDK/emsdk_env.sh" >/dev/null 2>&1; fi
mkdir -p "$LIFT"
python3 -c "import json,sys; json.dump({'roots': [int(sys.argv[1], 16)]}, open(sys.argv[2], 'w'))" "$GAIN_VA" "$OUT/entries.json"
python3 "$FLE/x64c.py" --pe "$CORE" --entries "$OUT/entries.json" --out "$LIFT" --closure 60 \
  --img "$IMG" --shift "$SHIFT" --img-size "$SIZE" --impbase 0x1D80000 | tail -c 300
python3 "$FLE/fle_data_gen.py" "$CORE" "$LIFT/fle_data.c" "$LIFT/lift_meta.json" "$SHIFT"
emcc -c -O0 -ffp-contract=off -fno-fast-math -I "$RT" "$LIFT/fle_lifted.c" -o /dev/null > "$OUT/compile.log" 2>&1
echo "compile: warnings=$(grep -c 'warning:' "$OUT/compile.log") errors=$(grep -c 'error:' "$OUT/compile.log")"
EXPORTS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc
emcc -O0 -ffp-contract=off -fno-fast-math -I "$RT" "$LIFT/fle_lifted.c" "$LIFT/fle_data.c" \
  "$RT/fle_cpu.c" "$RT/fle_glue.c" -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) -o "$OUT/fa.cjs" > "$OUT/link.log" 2>&1
ls -la "$OUT/fa.wasm" | awk '{print "wasm bytes:", $5}'
