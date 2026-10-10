#!/usr/bin/env bash
# build_filter.sh — Filter snapin process (0x180b6f050) + その closure を mlift → wasm
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/filter"; mkdir -p "$W"; cd "$W"; source "$HERE/env.sh"
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$HERE/pokes.txt"
python3 "$HERE/mlift/mlift.py" "$CORE" filter.ll \
  --root 0x180b6f050:'void(i64,i64)' --root 0x180b6f390:'void(i64)' --map 0x181030490=fa_memmove \
  --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report filter_rep.json
python3 -c "
import json; r=json.load(open('filter_rep.json')); open('iat_slots.txt','w').write('\n'.join('%s %s'%(k[2:],v) for k,v in r['iat_slots'].items())+'\n')"
cp "$HERE/pokes.txt" pokes.txt
emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math filter.ll "$HERE/shim/host_wasm.c" \
  -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS=_fa_root_180b6f050,_fa_root_180b6f390,_fa_va2ptr,_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,stackSave,stackRestore --no-entry -o filter.js
cp filter.js filter.cjs
echo "filter build ok"
