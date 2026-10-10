#!/usr/bin/env bash
# ablate_comp.sh [N=400] — 故障注入 ablation: mlift の意味論から RetDec 欠陥類型を 1 つずつ欠落させ, native との不一致シナリオ数を実測
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/ml"; mkdir -p "$W/abl"; cd "$W"; source "$HERE/env.sh"
POKES=(); while read -r va sz val; do [[ "$va" == \#* || -z "$va" ]] && continue; POKES+=(--poke "$va:$sz:$val"); done < "$HERE/pokes.txt"
N="${1:-400}"
python3 "$HERE/gen_comp_scen.py" comp_scen.txt "$N" >/dev/null
FA_DBG=1 ./native_comp "$CORE" comp_scen.txt 0 > comp_n0.txt 2>/dev/null
echo "# ablation (fault injection; fma=0; $N scenarios; native = SlateCore 機械語直接実行)"
for inj in comis_noflags xmm_args_drop xmm_ret_drop icall_drop cmov_drop; do
  python3 "$HERE/mlift/mlift.py" "$CORE" abl/$inj.ll --inject $inj \
    --root 0x180775220:'void(i64,i64)' --root 0x18103fd60:'f32(f32,f32)' --map 0x181030490=fa_memmove \
    --stub 18103d37c --stub 18103d47c --stub 18102f728 "${POKES[@]}" >/dev/null
  emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math abl/$inj.ll "$HERE/shim/host_wasm.c" \
    -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
    -sEXPORTED_FUNCTIONS=_fa_root_180775220,_fa_root_18103fd60,_fa_va2ptr,_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,stackSave,stackRestore --no-entry -o abl/$inj.js 2>abl/$inj.err && cp abl/$inj.js abl/$inj.cjs
  node "$HERE/native/comp_harness.mjs" ./abl/$inj.cjs comp_scen.txt 0 > abl/$inj.out 2>/dev/null
  m=$(paste -d'\n' comp_n0.txt abl/$inj.out | awk 'NR%2==1{a=$0;next}{ if(a!=$0)c++ }END{print c+0}')
  t=$(grep -c ERR abl/$inj.out)
  echo "inject $inj: mismatch $m / $N scenarios (うち wasm trap/ERR $t)"
done
