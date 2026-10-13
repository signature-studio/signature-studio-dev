#!/usr/bin/env bash
# build_setter.sh — FA-8: Filter model ctor (0x180b4c040) + setter (0x1803debc0) + Filter process (0x180b6f050/0x180b6f390) の closure を mlift → wasm
#   setter は descriptor の range object (vtable 0x1810ca8a0 等) を間接 call するため、各 vtable の slot0/slot11 を --icall 登録する。
#   icall_extra.py (制御層 rva 0x3c000..0x3f000 全関数を seed) は kernel32 import まで引き込み wasm-ld が失敗する (実測) ため使わず、
#   build_ctrl.sh 実績の CFG stub 0x1810806a0 と ctor の lea 関数ポインタ 4 VA だけを追加する。未解決 icall は fa_host_icall が fail-fast するので取りこぼしは run 時に FAIL する。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/fa8"; mkdir -p "$W"; cd "$W"; source "$HERE/env.sh"
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$HERE/pokes.txt"
ROOTS=(--root 0x1803debc0:'void(i64,i32,i32)' --root 0x180b4c040:'i64(i64,i64)' --root 0x180b6f050:'void(i64,i64)' --root 0x180b6f390:'void(i64)')
# descriptor range object の vtable 5 本 (0x1810ca8a0/ca910/ca980/cead8/fa958) の全 slot 先を vt_slots.py で自動列挙 (固定 12 slot では slot 12 以降が未解決だった = 実測)
VT_ICALLS=$(python3 "$HERE/vt_slots.py" "$CORE" 1810ca8a0 1810ca910 1810ca980 1810cead8 1810fa958)
# 1810806a0 = CFG stub (build_ctrl.sh 実績) / 1803e0650..18105d9dc = ctor が r9 に載せる関数ポインタ (build_ctrl.sh 実績) / 180db6320 = Filter ctor 由来 (FA_ICALL_SOFT=1 実測)
ICALLS=($VT_ICALLS); for v in 1810806a0 1803e0650 1803ddb60 1803ddba0 18105d9dc 180db6320; do ICALLS+=(--icall "$v"); done
COMMON=(--map 0x181030490=fa_memmove --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}")
python3 "$HERE/mlift/mlift.py" "$CORE" fset.ll "${ROOTS[@]}" "${ICALLS[@]}" "${COMMON[@]}" --report fset_rep.json
python3 -c "
import json; r=json.load(open('fset_rep.json')); open('iat_slots.txt','w').write('\n'.join('%s %s'%(k[2:],v) for k,v in r['iat_slots'].items())+'\n')"
cp "$HERE/pokes.txt" pokes.txt
emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math fset.ll "$HERE/shim/host_wasm.c" \
  -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS=_fa_root_1803debc0,_fa_root_180b4c040,_fa_root_180b6f050,_fa_root_180b6f390,_fa_va2ptr,_malloc,_free \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,stackSave,stackRestore --no-entry -o fset.js
cp fset.js fset.cjs
echo "setter build ok"
