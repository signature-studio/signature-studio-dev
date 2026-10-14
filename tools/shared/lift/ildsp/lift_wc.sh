#!/usr/bin/env bash
# ildsp (block24360_PE.bin) WaveformColouring_CreateInstance の closure を x64c で lift → C → wasm → 元の機械語との差分テスト (T-SH-52 / #3216)。
# root = CreateInstance (0x1ac470) と vtable 0x3e01b0 の 6 slot 先。vcall 0x1a9e2b (`call [rax+0x18]` = slot 3 = 0x1a9de0) は
# x64c の ott_dispatch が実行時に vtable を読んで解決する (静的に 0x1a9de0 へ束縛しない。前提: instance の vptr が 0x3e01b0)。
# 差分テスト: CreateInstance → slot 0 を native (元の機械語) と wasm で実行し、戻り値・import 呼出回数・heap・.data を全バイト比較。
# RetDec は使わない (D5)。生成物は tools/shared/work/lift/ildsp-wc/ (gitignore)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/lift_wc.sh [ok|neg-cmp|all]
#   ok (既定): 本検査。exit 0 = 全 case 一致 (PASS 1 件以上)。
#   neg-cmp : 比較器のネガティブコントロール (wasm 結果の heap 先頭 1 バイトを反転)。FAIL を検出したら exit 0。
#   all     : ok + neg-cmp。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HERE/../.."
FLE="$ROOT/../flelift"
source "$ROOT/env.sh"
MODE="${1:-ok}"
if [ "$MODE" = all ]; then
  for m in ok neg-cmp; do bash "$0" "$m" || exit 1; done
  echo "[ildsp-wc] ALL OK (本検査 PASS + ネガコン 1 件が期待通り FAIL)"; exit 0
fi
DLL="${ILDSP_DLL:-$FL_WIN64_DIR/extracted/block24360_PE.bin}"
[ -f "$DLL" ] || { echo "[ildsp-wc] DLL not found: $DLL (FL_WIN64_DIR=${FL_WIN64_DIR:-})"; exit 2; }
W="$ROOT/work/lift/ildsp-wc"; mkdir -p "$W"
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1
L0="$(cut -d' ' -f1-3 /proc/loadavg)"; T0=$(date +%s)

# 閉包の root: CreateInstance と vtable 0x3e01b0 の slot 先 (ildsp_closure.py の出力と一致する値)
SIZE=$(python3 -c "import pefile,sys; pe=pefile.PE(sys.argv[1], fast_load=True); print(hex(pe.OPTIONAL_HEADER.SizeOfImage))" "$DLL")
python3 - "$W/entries.json" <<'PY'
import json, sys
IMG = 0x180000000
rvas = [0x1ac470, 0x1a9cf0, 0x1a9f10, 0x1a9e10, 0x1a9de0, 0x1aa0b0, 0x1ac460]
json.dump({'roots': [IMG + r for r in rvas], 'calltgt': []}, open(sys.argv[1], 'w'))
PY
rm -rf "$W/lift"
python3 "$FLE/x64c.py" --pe "$DLL" --entries "$W/entries.json" --out "$W/lift" --closure 99 \
  --img 0x180000000 --shift 0x150000000 --img-size "$SIZE" --impbase 0x1D80000 | tee "$W/x64c.log"
echo "[ildsp-wc] unsup sites: $(python3 -c "import json; print(len(json.load(open('$W/lift/lift_meta.json'))['unsup_sites']))")"

python3 "$HERE/wc_image.py" "$DLL" "$W"
python3 "$HERE/wc_cases.py" "$W" "${WC_CASES:-64}"

# runtime (fle_cpu.c) の既定 import は host malloc を使い、ポインタ値が native と一致しない。
# wc_glue.c が定義する imp_* だけ runtime 側を改名してから別オブジェクトにし、決定的 bump heap の定義を使う。
RT_RENAME=$(grep -o 'void imp_[A-Za-z0-9_]*' "$HERE/wc_glue.c" | sed 's/void \(imp_[A-Za-z0-9_]*\)/-D\1=fle_rt_\1/')
emcc -c -O1 -ffp-contract=off -fno-fast-math -w -I "$FLE/rt" $RT_RENAME "$FLE/rt/fle_cpu.c" -o "$W/fle_cpu_rt.o"
emcc -O1 -ffp-contract=off -fno-fast-math -w -I "$FLE/rt" -I "$W" \
  "$W/lift/fle_lifted.c" "$W/fle_cpu_rt.o" "$HERE/wc_glue.c" \
  -sSTANDALONE_WASM=1 -sALLOW_MEMORY_GROWTH=0 -sINITIAL_MEMORY=$((0x31000000)) -sSTACK_SIZE=65536 -sGLOBAL_BASE=268435456 \
  --no-entry -Wl,--no-gc-sections -Wl,--export=wc_run -Wl,--export=wc_reset -Wl,--export=wc_hits_get \
  -o "$W/wc.wasm"
echo "[ildsp-wc] wasm: $(stat -c %s "$W/wc.wasm") bytes"

gcc -O1 -w -I "$W" -o "$W/native_ref" "$HERE/native_ref.c"
timeout 300 "$W/native_ref" "$W/image_native.bin" "$W/cases.bin" "$W/res_native.bin"

if [ "$MODE" = neg-cmp ]; then WC_NEG=arena timeout 300 node "$HERE/run_wasm.mjs" "$W"; else timeout 300 node "$HERE/run_wasm.mjs" "$W"; fi
set +e
python3 "$HERE/diff_test.py" "$W"; RC=$?
set -e
T1=$(date +%s)
echo "[ildsp-wc] $MODE elapsed=$((T1-T0))s load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
if [ "$MODE" = neg-cmp ]; then
  if [ $RC -ne 0 ]; then echo "[ildsp-wc] neg-cmp: FAIL を検出 (期待通り) rc=$RC"; exit 0; else echo "[ildsp-wc] neg-cmp: PASS してしまった = ゲートが効いていない"; exit 1; fi
fi
exit $RC
