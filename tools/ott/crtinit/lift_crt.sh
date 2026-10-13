#!/usr/bin/env bash
# lift_crt.sh — CAB-138: CRT 初期化版の lift → C → emcc → wasm (+ native 参照 .so) を 1 回で作る。
#   entry 版 (entry/lift_entry.sh) との差分:
#     - override 4 件 (CRT 数學エラー報告 / sqrt wrapper) を外し、DLL 自身の機械語を lift して置換
#     - CRT api-set trampoline override 6 件を追加 (crtinit/crt_roots.py TRAMP)
#     - crtinit/ott_crt.c (init tables + imp_* + ovr_*) を link
#     - 関数集合は crt_roots.py (DSP+entry+CRT coverage の和集合 + roots)
#   usage: lift_crt.sh [CRT_COV.json]  (既定 work/crtlift/cov_crt.json — crt_e2e.sh が先に作る)
#   出力: work/crtlift/{ott_lifted.c, ott_data.c, ottl_crt.cjs, libottnatcrt.so, entries.json, lift_meta.json}
#   env: CRT_CLOSURE (既定 3 — entry 版と同じ深さ)
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
CRT="$OTT/crtinit"
OUT="$OTT/work/crtlift"
source "$OTT/../shared/env.sh"
DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
CLOSURE="${CRT_CLOSURE:-3}"
mkdir -p "$OUT"

echo "[lift_crt] [1/4] native 参照ハーネス (.so — CRT init 入り)"
gcc -O1 -g -fPIC -shared -o "$OUT/libottnatcrt.so" "$CRT/crt_native.c" "$OTT/native/ms_call.S" -I"$OTT/rt" -I"$OTT/native" -I"$OTT/entry"

echo "[lift_crt] [2/4] entries.json (DSP coverage + entry coverage + CRT coverage + roots)"
CRTCOV="${1:-$OUT/cov_crt.json}"
python3 "$CRT/crt_roots.py" "$OTT/ref/cov_all.json" "$OTT/work/entrylift/cov_entry.json" "$CRTCOV" "$OUT/entries.json"

mapfile -t OVR_LIST < <(python3 -c "import sys; sys.path.insert(0, '$CRT'); import crt_roots; print('\n'.join('%x=%s' % kv for kv in sorted(crt_roots.overrides().items())))")
OVR_ARGS=()
for kv in "${OVR_LIST[@]}"; do OVR_ARGS+=(--override "$kv"); done

echo "[lift_crt] [3/4] lift (x64c) — closure=$CLOSURE, overrides ${#OVR_ARGS[@]}"
source "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" >/dev/null 2>&1
python3 "$OTT/lift/x64c.py" --pe "$DLL" --entries "$OUT/entries.json" --out "$OUT" --closure "$CLOSURE" \
  "${OVR_ARGS[@]}"

echo "[lift_crt] [4/4] data + emcc"
python3 "$OTT/lift/data_gen.py" "$DLL" "$OUT/ott_data.c" "$OUT/lift_meta.json" >/dev/null
EXPORTS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc,_ott_am_counts,_ott_crt_init_tables
emcc -O1 -ffp-contract=off -fno-fast-math -I"$OTT/rt" -I"$OTT/entry" -I"$CRT" \
  "$OUT/ott_lifted.c" "$OUT/ott_data.c" "$OTT/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c" "$OTT/entry/rt_entry.c" "$CRT/ott_crt.c" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$OUT/ottl_crt.cjs" 2>&1 | tail -8
echo "[lift_crt] OK: $OUT/ottl_crt.cjs"
