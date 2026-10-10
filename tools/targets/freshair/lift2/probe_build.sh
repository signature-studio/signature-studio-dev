#!/usr/bin/env bash
# probe_build.sh — Filter 数値チェーンの関数単位 probe 用 wasm (追加 root 付き) を build。
#   roots: 0x180d235b0 (多段係数設計) / 0x180d22850 (2次係数設計)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="${WDIR:-$HERE/work/filter}"; cd "$W"; source "$HERE/env.sh"
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$HERE/pokes.txt"
python3 "$HERE/mlift/mlift.py" "$CORE" filter_probe.ll \
  --root 0x180b7fa80:'void(i64,i32,i32,f32,f32,f32,f32)' \
  --root 0x180d235b0:'i64(i64,f64,f64,f64,f64,i64,i64)' \
  --root 0x180d22850:'i64(i64,i64,f64,f64,f64,f64,f64,f64)' \
  --root 0x18104ad90:'f64(f64)' \
  --root 0x18104f698:'f64(f64)' \
  --root 0x181046890:'f64(f64)' \
  --root 0x18105d170:'f64(f64)' \
  --root 0x18105cf80:'f64(f64)' \
  --trace 180d235b0:180d23e05 \
  --map 0x181030490=fa_memmove --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}"
emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math filter_probe.ll "$HERE/shim/host_wasm.c" \
  -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS=_fa_root_180b7fa80,_fa_root_180d235b0,_fa_root_180d22850,_fa_root_18104ad90,_fa_root_18104f698,_fa_root_181046890,_fa_root_18105d170,_fa_root_18105cf80,_fa_trace_ptr,_fa_trace_count,_fa_va2ptr,_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8 --no-entry -o filter_probe.js
cp filter_probe.js filter_probe.cjs
clang -O1 -w -o probe235 "$HERE/native/probe235.c"
clang -O1 -w -o probe7fa80 "$HERE/native/probe7fa80.c"
clang -O1 -w -o trigprobe "$HERE/native/trigprobe.c"
echo "probe build ok"
