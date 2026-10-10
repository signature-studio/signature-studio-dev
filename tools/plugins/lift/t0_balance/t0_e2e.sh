#!/usr/bin/env bash
# T0 検証 (Fruity Balance の SIMD kernel 2 本) を 1 コマンドで再現: lift → wasm → node ⟷ native 機械語 bit 比較
#   bash tools/plugins/lift/t0_balance/t0_e2e.sh      (exit 0 = 全 case bit-exact)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"                 # tools/plugins
PE=/home/ubuntu/work/analysis/win64/extracted/block18983_PE.bin   # Fruity Balance_x64.dll (NSIS block 18983)
W="$ROOT/work/balance"
mkdir -p "$W"
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
# kernel: mix 0x5dee90 (432B) / peak 0x5df940 (248B)
echo "0x5dee90-0x5df03f,0x5df940-0x5dfa37" > "$W/k_ranges.txt"
PLUG_ORCOND_FUNCS=function_5dee90 bash "$ROOT/lift/lift_ranges.sh" "$PE" "$W/k_ranges.txt" "$W" k
bash "$HERE/build_wasm.sh" "$W" k function_5dee90,function_5df940
cc -O1 -w -o "$W/native_ref" "$HERE/native_ref.c"
rc=0
for seed in 305441741 1 2863311530; do
  T0_SEED=$seed node "$HERE/run_t0.mjs" "$W" "$PE" > "$W/t0_seed_$seed.json" || rc=1
  echo "seed=$seed: $(python3 -c "import json;r=json.load(open('$W/t0_seed_$seed.json'));print('cases',r['cases'],'pass',r['pass'],'fail',r['fail'])")"
done
exit $rc
