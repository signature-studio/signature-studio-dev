#!/usr/bin/env bash
# lift_build.sh: DLL 機械語 → (x64c.py) C → emcc → wasm.  RetDec 不要。
#   env: LIFT_ENTRIES (default work/entries.json), LIFT_OUT (default work/lift), LIFT_CLOSURE (default 0), LIFT_NAME (default ottl)
#        LIFT_PROFILE (default std) 標準ビルド設定 = tools/liftlib/data/std_build.json (PERF-P1 / #155): std = -O3 -flto + gc-sections + 最小 export。
#                     dev = 旧 -O1。LIFT_CFLAGS は追加フラグ (std に -O1 / -msimd128 等の禁止フラグを足すと stdbuild.py check で失敗)
#        LIFT_GUARD=1 署名ガード: -O0 (ref) 版も作り、ott_x64c_bench の出力署名が両版で一致しなければ失敗 (LIFT_EXPECT_SIG で期待署名も固定)
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
source "$OTT/../shared/env.sh"
DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
ENT="${LIFT_ENTRIES:-$OTT/work/entries.json}"
OUT="${LIFT_OUT:-$OTT/work/lift}"
NAME="${LIFT_NAME:-ottl}"
source "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" >/dev/null 2>&1
mkdir -p "$OUT"
python3 "$OTT/lift/x64c.py" --pe "$DLL" --entries "$ENT" --out "$OUT" --closure "${LIFT_CLOSURE:-2}" \
  --override 1801c8c00=ovr_handle_error_d --override 1801c8cb8=ovr_handle_error_f --override 1801a9a6c=ovr_sqrt_d --override 1801a9b38=ovr_sqrt_f
python3 "$OTT/lift/data_gen.py" "$DLL" "$OUT/ott_data.c" "$OUT/lift_meta.json" >/dev/null
EXPORTS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc
STDB="$OTT/../liftlib/liftlib/stdbuild.py"
build_one() {   # build_one <profile> <out.cjs>
  local flags; flags="$(python3 "$STDB" flags "$1")"
  # shellcheck disable=SC2086
  python3 "$STDB" check "$1" -- $flags ${LIFT_CFLAGS:-} >/dev/null
  # shellcheck disable=SC2086
  emcc $flags -I"$OTT/rt" ${LIFT_CFLAGS:-} \
    "$OUT/ott_lifted.c" "$OUT/ott_data.c" "$OTT/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c" \
    -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
    -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
    -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
    -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
    -o "$2" 2>&1 | tail -20
}
PROFILE="${LIFT_PROFILE:-std}"
build_one "$PROFILE" "$OUT/$NAME.cjs"
if [ "${LIFT_GUARD:-0}" = "1" ]; then
  build_one ref "$OUT/${NAME}_ref.cjs"
  python3 "$STDB" guard --probe "node $OTT/../perf/harness/ott_x64c_bench.mjs {cjs}" --regex '"sig":"(\w+)"' --env SIG_ONLY=1 \
    ${LIFT_EXPECT_SIG:+--expect "$LIFT_EXPECT_SIG"} "$OUT/$NAME.cjs" "$OUT/${NAME}_ref.cjs"
fi
echo "[lift_build] OK: $OUT/$NAME.cjs (profile=$PROFILE)"
