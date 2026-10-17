#!/usr/bin/env bash
# rsi_zero_variant.sh — FLE-51 (#6054): 残骸 (dst+0x18〜+0x27) が既定経路の出力に効くかの対照実験。
# 既定経路 (FLE_IPP 未指定・mode 3) では 0x6b91e8 は実行されない (rsi_4080a2_probe.sh で確認) ので、
# 0x4080a2 の入口で rsi が dst 範囲 [0x12d777d0, +0x28) に当たるときだけ 40 バイトをゼロにする変種 (zero) を作り、既定 (base) と比べる。
# zero は「残骸を消したら何が変わるか」の対照であり、既定経路ではない。
#   bash tools/flelift/boot/rsi_zero_variant.sh   # 前提: 先に fle6_measure.sh で work/boot/lift を作る
# 出力: $W/run_rsizero_{base,zero}.log と $W/rsizero_{base,zero}.json (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
LIFT="$W/lift"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
NODE="$(command -v node)"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[rsizero] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

# 0x4080a2 の入口で、rsi が dst 範囲なら 40 バイトをゼロにする (残骸を消す対照)。既定 (base) は何もしない。
ZERO='{ static int n_; if (R[6] >= 0x12d777d0ull && R[6] < 0x12d777d0ull + 0x28ull) { if (n_++ < 4) fprintf(stderr, "[RSIZERO] rsi=%llx\n", (unsigned long long)R[6]); for (uint32_t i_ = 0; i_ < 0x28; i_++) ST8(R[6] + i_, 0); } }'

run_one() {
  local label="$1" dbg="$W/lift_rsizero_$1"
  rm -rf "$dbg" && cp -r "$LIFT" "$dbg"
  if [ "$label" = zero ]; then
    for k in 0 1 2 3 4 5 6 7; do
      python3 "$HERE/dbg_lift.py" --src "$dbg/fle_lifted_s$k.c" --out "$dbg/fle_lifted_s$k.c" --at 0x4080a2 --c "$ZERO" || true
    done
  fi
  FLE_LIFT_DIR="$dbg" FLE_LABEL="rsizero_$label" FLE_SHARDS=8 SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain
  local log="$W/run_rsizero_$label.log" json="$W/rsizero_$label.json"
  # 既定経路 = FLE_IPP 未指定 (mode 3)。
  FLE_BOOT_VARIANT=plain FLE_BOOT_QUIET_BIN=1 timeout "${FLE_BOOT_TIMEOUT:-600}" "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_rsizero_$label.cjs" "$json" --boot-only > "$log" 2>&1 || true
  grep -a 'RSIZERO\|FLEBOOT_RESULT' "$log" | cut -c1-300 || true
}

run_one base
run_one zero
