#!/usr/bin/env bash
# lift_entry.sh — VST 入口拡張版の lift → C → emcc → wasm (+ native 参照 .so) を 1 回で作る。
#   入口 roots は entry_roots.py (coverage 結果 + VST 入口 VA + audioMaster 仮想入口) から生成。
#   出力: work/entrylift/{ott_lifted.c, ott_data.c, ottl_entry.cjs, libottnatentry.so, entries.json, lift_meta.json}
#   env: ENTRY_CLOSURE (既定 3 — dispatcher の vtbl 経由呼出を追うため DSP 既定 2 より 1 深い)
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
ENTRY="$OTT/entry"
OUT="$OTT/work/entrylift"
DLL=/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll
CLOSURE="${ENTRY_CLOSURE:-3}"
mkdir -p "$OUT"

echo "[lift_entry] [1/4] native 参照ハーネス (.so)"
gcc -O1 -g -fPIC -shared -o "$OUT/libottnatentry.so" "$ENTRY/entry_native.c" "$OTT/native/ms_call.S" -I"$OTT/rt" -I"$ENTRY"

echo "[lift_entry] [2/4] entries.json (DSP coverage + entry coverage + roots)"
python3 "$ENTRY/entry_roots.py" "$OTT/ref/cov_all.json" "${1:-$OUT/cov_entry.json}" "$OUT/entries.json"

echo "[lift_entry] [3/4] lift (x64c) — closure=$CLOSURE"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
python3 "$OTT/lift/x64c.py" --pe "$DLL" --entries "$OUT/entries.json" --out "$OUT" --closure "$CLOSURE" \
  --override 1801c8c00=ovr_handle_error_d --override 1801c8cb8=ovr_handle_error_f \
  --override 1801a9a6c=ovr_sqrt_d --override 1801a9b38=ovr_sqrt_f \
  --override 180120ff0=ovr_editor_null \
  --override 1802f8000=ovr_am_shim

echo "[lift_entry] [4/4] data + emcc"
python3 "$OTT/lift/data_gen.py" "$DLL" "$OUT/ott_data.c" "$OUT/lift_meta.json" >/dev/null
EXPORTS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc,_ott_am_counts
emcc -O1 -ffp-contract=off -fno-fast-math -I"$OTT/rt" -I"$ENTRY" \
  "$OUT/ott_lifted.c" "$OUT/ott_data.c" "$OTT/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c" "$ENTRY/rt_entry.c" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$OUT/ottl_entry.cjs" 2>&1 | tail -8
echo "[lift_entry] OK: $OUT/ottl_entry.cjs"
