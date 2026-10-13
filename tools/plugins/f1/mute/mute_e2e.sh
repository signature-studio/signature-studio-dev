#!/usr/bin/env bash
# PLG-F1 (#198) Fruity Mute 2 Eff_Render 差分試験: lift → wasm → node ⟷ native 機械語 (1 コマンド)
#   bash tools/plugins/f1/mute/mute_e2e.sh      (出力: tools/plugins/work/f1/19049/mu_result.json ほか)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
F1="$(cd "$HERE/.." && pwd)"
ROOT="$(cd "$F1/.." && pwd)"
source "$F1/env.sh"
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
BLOCK=19049
PE="$FL_WIN64_DIR/extracted/block$BLOCK""_PE.bin"
W="$ROOT/work/f1/$BLOCK"
mkdir -p "$W"
( cd "$ROOT" && python3 "$F1/f1_plan.py" $BLOCK >/dev/null )
bash "$ROOT/lift/lift_ranges.sh" "$PE" "$W/ranges.txt" "$W" mu 600 > "$W/lift.log" 2>&1 || { tail -20 "$W/lift.log"; exit 1; }
bash "$ROOT/lift/t0_balance/build_wasm.sh" "$W" mu function_6baaf0,function_5df490
cc -O1 -w -o "$W/native_mute" "$HERE/native_mute.c"
sumjson() { python3 -c 'import json,sys;r=json.load(sys.stdin);print("cases",r["cases"],"pass",r["pass"],"fail",r["fail"],r["groups"])'; }
python3 "$HERE/mute_repair_oracle.py" "$W/mu.final.ll" "$W/mur.final.ll" "$W/mu_simd.c" "$W/mur_simd.c"
MU_NEGCTL=1 python3 "$HERE/mute_repair_oracle.py" "$W/mu.final.ll" "$W/mun.final.ll" "$W/mu_simd.c" "$W/mun_simd.c"
bash "$ROOT/lift/t0_balance/build_wasm.sh" "$W" mur function_6baaf0,function_5df490 >/dev/null
bash "$ROOT/lift/t0_balance/build_wasm.sh" "$W" mun function_6baaf0,function_5df490 >/dev/null
for seed in ${MU_SEEDS:-305441741 1 2863311530}; do
  for tag in mu mur mun; do
    echo "seed=$seed $tag: $(MU_TAG=$tag MU_SEED=$seed node "$HERE/run_mute.mjs" "$W" "$PE" | sumjson)"
  done
done
