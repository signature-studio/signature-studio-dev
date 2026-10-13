#!/usr/bin/env bash
# PLG-F1 (#198) Fruity Phase Inverter Eff_Render 差分試験: lift → wasm → node ⟷ native 機械語 (1 コマンド)
#   bash tools/plugins/f1/pi/pi_e2e.sh      (出力: tools/plugins/work/f1/19065/pi_result.json)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
F1="$(cd "$HERE/.." && pwd)"
ROOT="$(cd "$F1/.." && pwd)"                       # tools/plugins
source "$F1/env.sh"
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
BLOCK=19065
PE="$FL_WIN64_DIR/extracted/block$BLOCK""_PE.bin"
W="$ROOT/work/f1/$BLOCK"
mkdir -p "$W"
( cd "$ROOT" && python3 "$F1/f1_plan.py" $BLOCK >/dev/null )          # Eff_Render 経路の ranges → $W/ranges.txt
bash "$ROOT/lift/lift_ranges.sh" "$PE" "$W/ranges.txt" "$W" pi 600 > "$W/lift.log" 2>&1 || { tail -20 "$W/lift.log"; exit 1; }
bash "$ROOT/lift/t0_balance/build_wasm.sh" "$W" pi function_6ba930
cc -O1 -w -o "$W/native_pi" "$HERE/native_pi.c"
sumjson() { python3 -c 'import json,sys;r=json.load(sys.stdin);print("cases",r["cases"],"pass",r["pass"],"fail",r["fail"])'; }
python3 "$HERE/pi_repair_oracle.py" "$W/pi.final.ll" "$W/pir.final.ll" "$W/pi_simd.c" "$W/pir_simd.c"      # ablation: 脱落した indirect call を oracle で手で書き戻した版 (lift pass ではない)
PI_NEGCTL=1 python3 "$HERE/pi_repair_oracle.py" "$W/pi.final.ll" "$W/pin.final.ll" "$W/pi_simd.c" "$W/pin_simd.c"   # 陰性対照: コピー長 -4 byte
bash "$ROOT/lift/t0_balance/build_wasm.sh" "$W" pir function_6ba930 >/dev/null
bash "$ROOT/lift/t0_balance/build_wasm.sh" "$W" pin function_6ba930 >/dev/null
for seed in ${PI_SEEDS:-305441741 1 2863311530}; do
  for tag in pi pir pin; do
    echo "seed=$seed $tag: $(PI_TAG=$tag PI_SEED=$seed node "$HERE/run_pi.mjs" "$W" "$PE" | sumjson)"
  done
done
