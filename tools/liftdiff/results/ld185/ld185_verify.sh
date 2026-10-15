#!/usr/bin/env bash
# LD-185 (#3988): x64c の命令単位 trace 計装の検証を一括で行う。
#   (1) 既定 off の lift 出力が ld131_lift.sh の出力とバイト一致 (sha256 比較)
#   (2) 計装 on (OTT_INSNTRACE=1) の 6 root lift → emcc (-DOTT_INSNTRACE) ビルドが通る
#   (3) 計装 wasm で 1801c5e84 の vm0・u16 を 1 回ずつ実行し、命令 VA 列を取る
#   env: PLUGINS_DIR (既定 tools/shared/env.sh の値)・LD185_OUT (既定 ${RUNNER_TEMP:-/tmp}/ld185)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
source "$REPO/tools/shared/env.sh"
OUT="${LD185_OUT:-${RUNNER_TEMP:-/tmp}/ld185}"
DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
[ -f "$DLL" ] || { echo "ld185_verify: DLL が無い: $DLL" >&2; exit 2; }
mkdir -p "$OUT/base" "$OUT/insn/lift"
ROOTS="1801ab1d0 1801ab258 1801c5e84 1801c621c 1801c682c 1801c69cc"
python3 -c "import json,sys; json.dump({'roots':[int(x,16) for x in sys.argv[1:]],'calltgt':[]}, open('$OUT/entries6.json','w'))" $ROOTS

# (1) 既定 off: ld131 と同じ呼出し
python3 "$REPO/tools/ott/lift/x64c.py" --pe "$DLL" --entries "$OUT/entries6.json" --out "$OUT/base" --closure 6
sha256sum "$OUT/base/ott_lifted.c"

# (2) 計装 on
OTT_INSNTRACE=1 python3 "$REPO/tools/ott/lift/x64c.py" --pe "$DLL" --entries "$OUT/entries6.json" --out "$OUT/insn/lift" --closure 6
echo "insn_hit_calls=$(grep -c OTT_INSN_HIT "$OUT/insn/lift/ott_lifted.c")"
python3 "$REPO/tools/ott/lift/data_gen.py" "$DLL" "$OUT/insn/lift/ott_data.c" "$OUT/insn/lift/lift_meta.json" >/dev/null
RT="$REPO/tools/ott/rt"
STDB="$REPO/tools/liftlib/liftlib/stdbuild.py"
# shellcheck disable=SC1091
source "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" >/dev/null 2>&1 || true
flags="$(python3 "$STDB" flags std)"
# shellcheck disable=SC2086
emcc $flags -DOTT_INSNTRACE -I"$RT" "$OUT/insn/lift/ott_lifted.c" "$OUT/insn/lift/ott_data.c" \
  "$RT/ott_cpu.c" "$RT/ott_glue.c" "$RT/ott_ovr.c" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc,_ott_set_gbase \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$OUT/ottl_insn.cjs"
ls -la "$OUT/ottl_insn.cjs" "$OUT/ottl_insn.wasm"

# (3) 計装 wasm で vm0 / u16 を 1 回ずつ
node "$HERE/ld185_trace.mjs" "$OUT/ottl_insn.cjs" "$OUT/trace.json"
python3 "$HERE/ld185_summarize.py" "$OUT/trace.json"
