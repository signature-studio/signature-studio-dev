#!/usr/bin/env bash
# REX (win `REX Shared Library.dll` = block24351_PE.bin) の REXGetCreatorInfo / REXGetInfo 閉包を x64c で lift → C → wasm。
# 元の機械語 (native_ref.c: RWX に VA 0x30000000 へ敷設して直接実行) と同一入力で、戻り値・import 呼出回数・arena・.data を全バイト比較する (T-SH-44 / #2733)。
# RetDec は使わない (D5)。所有者限定 tier の side module (D20)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_x64c.sh [ok|neg-cmp|neg-ctx|all]
#   ok (既定): 本検査。exit 0 = 全 case 一致 + カバレッジ充足。
#   neg-cmp : 比較器のネガティブコントロール (wasm 結果の 1 バイトを反転)。
#   neg-ctx : 入力のネガティブコントロール (wasm 側だけ ctx 大域を 0 にする)。
#   neg-*   : FAIL を検出したら exit 0 / PASS してしまったら exit 1。all = ok + 全 neg-*。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HERE/../.."
FLE="$ROOT/../flelift"
source "$ROOT/env.sh"
MODE="${1:-ok}"
if [ "$MODE" = all ]; then
  for m in ok neg-cmp neg-ctx; do bash "$0" "$m" || exit 1; done
  echo "[rex] ALL OK (本検査 PASS + ネガコン 2 件が期待通り FAIL)"; exit 0
fi
DLL="${REX_DLL:-$FL_WIN64_DIR/extracted/block24351_PE.bin}"
[ -f "$DLL" ] || { echo "[rex] DLL not found: $DLL (FL_WIN64_DIR=${FL_WIN64_DIR:-})"; exit 2; }
W="$ROOT/work/lift/rex"; mkdir -p "$W"
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1
L0="$(cut -d' ' -f1-3 /proc/loadavg)"; T0=$(date +%s)

python3 -c "import json; json.dump({'roots': [0x1800011c0, 0x180001130], 'calltgt': []}, open('$W/entries.json', 'w'))"
rm -rf "$W/lift"
python3 "$FLE/x64c.py" --pe "$DLL" --entries "$W/entries.json" --out "$W/lift" --closure 99 \
  --img 0x180000000 --shift 0x150000000 --img-size 0x6a000 --impbase 0x1D80000
python3 "$HERE/rex_image.py" "$DLL" "$W"
python3 "$HERE/gen_cases.py" "$W/cases.bin" 200

emcc -O1 -ffp-contract=off -fno-fast-math -w -I "$FLE/rt" \
  "$W/lift/fle_lifted.c" "$FLE/rt/fle_cpu.c" "$HERE/rex_glue.c" \
  -sSTANDALONE_WASM=1 -sALLOW_MEMORY_GROWTH=0 -sINITIAL_MEMORY=$((0x31000000)) -sSTACK_SIZE=65536 -sGLOBAL_BASE=268435456 \
  --no-entry -Wl,--no-gc-sections -Wl,--export=rex_run -Wl,--export=rex_reset -Wl,--export=rex_hits_get \
  -o "$W/rex.wasm"
echo "[rex] wasm: $(stat -c %s "$W/rex.wasm") bytes"

gcc -O1 -w -I "$W" -o "$W/native_ref" "$HERE/native_ref.c"
timeout 300 "$W/native_ref" "$W/image_native.bin" "$W/cases.bin" "$W/res_native.bin"

if [ "$MODE" = neg-ctx ]; then REX_NEG=ctx timeout 300 node "$HERE/run_wasm.mjs" "$W"; else timeout 300 node "$HERE/run_wasm.mjs" "$W"; fi
set +e
if [ "$MODE" = neg-cmp ]; then python3 "$HERE/diff_test.py" "$W" --mutate-wasm; RC=$?; else python3 "$HERE/diff_test.py" "$W"; RC=$?; fi
set -e
T1=$(date +%s)
echo "[rex] $MODE elapsed=$((T1-T0))s load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
if [[ "$MODE" == neg-* ]]; then
  if [ $RC -ne 0 ]; then echo "[rex] $MODE: FAIL を検出 (期待通り) rc=$RC"; exit 0; else echo "[rex] $MODE: PASS してしまった = ゲートが効いていない"; exit 1; fi
fi
exit $RC
