#!/usr/bin/env bash
# REX 中核閉包 (REXCreate / REXGetInfoFromBuffer / REXRenderSlice) を x64c で lift → C → wasm (コンパイル確認まで)。T-SH-45 (#2734)。
# 差分テスト (元の機械語との比較) は REX 入力素材が無いため未実施 (REPORT §8.5)。RetDec は使わない (D5)。
# 出力は所有者限定 tier 専用 (D20)。生成物は tools/shared/work/lift/rex-core/ (gitignore・commit しない)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_core.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HERE/../.."
FLE="$ROOT/../flelift"
source "$ROOT/env.sh"
DLL="${REX_DLL:-$FL_WIN64_DIR/extracted/block24351_PE.bin}"
[ -f "$DLL" ] || { echo "[rex-core] DLL not found: $DLL (FL_WIN64_DIR=${FL_WIN64_DIR:-})"; exit 2; }
W="$ROOT/work/lift/rex-core"; mkdir -p "$W"
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1
L0="$(cut -d' ' -f1-3 /proc/loadavg)"; T0=$(date +%s)

# REXCreate 0x1800010b0 / REXGetInfoFromBuffer 0x180001170 / REXRenderSlice 0x180001280 (export RVA 0x10b0 / 0x1170 / 0x1280)
python3 -c "import json; json.dump({'roots': [0x1800010b0, 0x180001170, 0x180001280], 'calltgt': []}, open('$W/entries.json', 'w'))"
rm -rf "$W/lift"
python3 "$FLE/x64c.py" --pe "$DLL" --entries "$W/entries.json" --out "$W/lift" --closure 99 \
  --img 0x180000000 --shift 0x150000000 --img-size 0x6a000 --impbase 0x1D80000 | tee "$W/x64c.log"
echo "[rex-core] indirect register dispatch sites (ott_dispatch): $(grep -c 'ott_dispatch(t_)' "$W/lift/fle_lifted.c")"
echo "[rex-core] unsup sites (lift_meta.json): $(python3 -c "import json; print(len(json.load(open('$W/lift/lift_meta.json'))['unsup_sites']))")"

emcc -O1 -ffp-contract=off -fno-fast-math -w -I "$FLE/rt" \
  "$W/lift/fle_lifted.c" "$FLE/rt/fle_cpu.c" "$HERE/rex_glue.c" \
  -sSTANDALONE_WASM=1 -sALLOW_MEMORY_GROWTH=0 -sINITIAL_MEMORY=$((0x31000000)) -sSTACK_SIZE=65536 -sGLOBAL_BASE=268435456 \
  --no-entry -Wl,--no-gc-sections -Wl,--export=rex_run -Wl,--export=rex_reset -Wl,--export=rex_hits_get \
  -o "$W/rex_core.wasm"
echo "[rex-core] wasm: $(stat -c %s "$W/rex_core.wasm") bytes"

T1=$(date +%s)
echo "[rex-core] elapsed=$((T1-T0))s load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
