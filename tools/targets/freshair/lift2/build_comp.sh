#!/usr/bin/env bash
# build_comp.sh — mlift で Compressor closure を lift → emcc → wasm (+ native 参照ハーネス) をビルド。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/ml"; mkdir -p "$W"; cd "$W"; source "$HERE/env.sh"
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$HERE/pokes.txt"
python3 "$HERE/mlift/mlift.py" "$CORE" comp_full.ll \
  --root 0x180775220:'void(i64,i64)' --root 0x18103fd60:'f32(f32,f32)' \
  --map 0x181030490=fa_memmove --map 0x1803ded20=fa_vector_grow --map 0x18106a3a0=fa_mxcsr_get --map 0x18106a3ba=fa_mxcsr_set --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report comp_full_rep.json
python3 -c "
import json; r=json.load(open('comp_full_rep.json')); open('iat_slots.txt','w').write('\n'.join('%s %s'%(k[2:],v) for k,v in r['iat_slots'].items())+'\n')"
cp "$HERE/pokes.txt" pokes.txt
emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math comp_full.ll "$HERE/shim/host_wasm.c" \
  -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS=_fa_root_180775220,_fa_root_18103fd60,_fa_va2ptr,_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,stackSave,stackRestore --no-entry -o comp_full.js
cp comp_full.js comp_full.cjs
clang -O1 -w -o native_comp "$HERE/native/native_comp.c"
clang -O1 -w -o native_pow "$HERE/native/native_pow.c"
echo "build ok"
# ---- カバレッジ版 (同一 IR に fa_cov を埋込。結果比較には使わず, シナリオ網羅度の測定専用)
python3 "$HERE/mlift/mlift.py" "$CORE" comp_cov.ll --cov \
  --root 0x180775220:'void(i64,i64)' --root 0x18103fd60:'f32(f32,f32)' \
  --map 0x181030490=fa_memmove --map 0x1803ded20=fa_vector_grow --map 0x18106a3a0=fa_mxcsr_get --map 0x18106a3ba=fa_mxcsr_set --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report comp_cov_rep.json >/dev/null
emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math comp_cov.ll "$HERE/shim/host_wasm.c" \
  -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS=_fa_root_180775220,_fa_root_18103fd60,_fa_va2ptr,_fa_cov_ptr,_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,stackSave,stackRestore --no-entry -o comp_cov.js
cp comp_cov.js comp_cov.cjs
echo "cov build ok"
