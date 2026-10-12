#!/usr/bin/env bash
# build_avx.sh — CAB-135: VEX/AVX lift 有効 build (crt 版と同系, 出力を work/avx に分離)。
#   lift (x64c + VEX) → data → emcc。override は crt_roots.py と同一。
#   env: AVX_VEXCOV=1 で -DOTT_VEXCOV (wasm 側 VEX 命令実行 coverage 付き probe build)
#   usage: build_avx.sh [ENTRIES.json]  (既定 work/avx/entries.json — 無ければ生成)
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
source "$OTT/../shared/env.sh"
AVX="$OTT/avx"
OUT="$OTT/work/avx"
DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
CLOSURE="${AVX_CLOSURE:-3}"
NAME="${AVX_OUT:-ottl_avx}"
mkdir -p "$OUT"

if [ ! -f "${1:-$OUT/entries.json}" ]; then
  echo "[build_avx] entries.json 生成 (coverage: ref/cov_all + entrylift + crtlift)"
  python3 "$AVX/../crtinit/crt_roots.py" "$OTT/ref/cov_all.json" "$OTT/work/entrylift/cov_entry.json" \
    "$OTT/work/crtlift/cov_crt.json" "$OUT/entries.json"
fi
ENT="${1:-$OUT/entries.json}"

mapfile -t OVR_LIST < <(python3 -c "import sys; sys.path.insert(0, '$AVX/../crtinit'); import crt_roots; print('\n'.join('%x=%s' % kv for kv in sorted(crt_roots.overrides().items())))")
OVR_ARGS=()
for kv in "${OVR_LIST[@]}"; do OVR_ARGS+=(--override "$kv"); done

echo "[build_avx] [1/3] lift (x64c + VEX) — closure=$CLOSURE"
OTT_VEXCOV="${AVX_VEXCOV:-0}" python3 "$OTT/lift/x64c.py" --pe "$DLL" --entries "$ENT" --out "$OUT" --closure "$CLOSURE" "${OVR_ARGS[@]}"

echo "[build_avx] [2/3] data"
python3 "$OTT/lift/data_gen.py" "$DLL" "$OUT/ott_data.c" "$OUT/lift_meta.json" >/dev/null

echo "[build_avx] [3/3] emcc"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
EXPORTS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc,_ott_am_counts,_ott_crt_init_tables
VEXCOV=(); [ "${AVX_VEXCOV:-0}" = "1" ] && VEXCOV=(-DOTT_VEXCOV)
emcc -O1 -ffp-contract=off -fno-fast-math -I"$OTT/rt" -I"$OTT/entry" -I"$OTT/crtinit" "${VEXCOV[@]}" \
  "$OUT/ott_lifted.c" "$OUT/ott_data.c" "$OTT/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c" "$OTT/entry/rt_entry.c" "$OTT/crtinit/ott_crt.c" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$OUT/$NAME.cjs" 2>&1 | tail -8
echo "[build_avx] OK: $OUT/$NAME.cjs"
