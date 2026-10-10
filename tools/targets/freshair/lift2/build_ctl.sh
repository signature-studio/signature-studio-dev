#!/usr/bin/env bash
# build_ctl.sh — FA-2c: FreshAirDsp 制御層 (slot12 0x1803dfc10) closure を mlift lift → emcc → wasm
#   + native oracle (native_freshair.c) をビルド。
# vtable 間接 call 先 (DspModel 17 slot の comp/filter/gain 分) を --icall で fa_icall switch に登録。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/ctl"; mkdir -p "$W"; cd "$W"; source "$HERE/env.sh"
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$HERE/pokes.txt"

# ---- fa_icall 登録: DspModel vtable (comp 0x1810E1BE8 / filter 0x1810FAAD0 / gain 0x1810F8870) の
#      slot[5]+0x28 process driver, slot[7]+0x38 latency, slot[8]+0x40, slot[9]+0x48 active,
#      slot[10]+0x50 param, slot[11]+0x58 bypass, slot[12]+0x60 process (FA-2b roots),
#      slot[13]+0x68 post, slot[15]+0x78, slot[16]+0x80 shouldProcess
ICALLS=(
  1803df070 1803df050 1803df060 1803df010 1803b4070 1803df040
  1807750a0 1807750e0 180775220 1807758b0 1807758a0 180774ee0
  180460e60 180b6efb0 180b6f050 180b6f390
  180afdfd0 180afe090 180afe260 180afe250
)
IC=(); for v in "${ICALLS[@]}"; do IC+=(--icall "$v"); done

python3 "$HERE/mlift/mlift.py" "$CORE" ctl_full.ll \
  --root 0x1803dfc10:'void(i64,i64)' --root 0x18103fd60:'f32(f32,f32)' \
  "${IC[@]}" \
  --map 0x181030490=fa_memmove --map 0x18106a3a0=fa_mxcsr_get --map 0x18106a3ba=fa_mxcsr_set \
  --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" --report ctl_rep.json
python3 -c "
import json; r=json.load(open('ctl_rep.json')); open('iat_slots.txt','w').write('\n'.join('%s %s'%(k[2:],v) for k,v in r['iat_slots'].items())+'\n')"
cp "$HERE/pokes.txt" pokes.txt

EXP=(_fa_root_1803dfc10 _fa_root_18103fd60 _fa_va2ptr _malloc _free)
emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math ctl_full.ll "$HERE/shim/host_wasm.c" \
  -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS="$(IFS=,; echo "${EXP[*]}")" \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,stackSave,stackRestore --no-entry -o ctl_full.js
cp ctl_full.js ctl_full.cjs
clang -O1 -w -o native_freshair "$HERE/native/native_freshair.c"
echo "build_ctl ok"
