#!/usr/bin/env bash
# rsi_4080a2_probe.sh — FLE-51 (#6054): 0x4080a2 (call 0x409c80・戻り 0x4080a7) の呼出し時 rsi と、
# 0x4080af (戻り後) の dst 残骸を記録する診断。0x6b91e8 の未適用 (ゼロ埋め飛ばし) が後続に流れるかの前段。
#   1. 0x4080a2 の直前で rsi (= R[6]) と [rsi, rsi+0x28) の非 0 バイト数を出す。
#   2. 0x4080af の直前で rbx (= R[3]・返り値) と [rbx, rbx+0x28) の非 0 バイト数、rsi を出す。
#   3. boot を 1 回回し、結果の行を出す。
#
#   bash tools/flelift/boot/rsi_4080a2_probe.sh   # 前提: 先に fle6_measure.sh で work/boot/lift を作る
#
# 出力: $W/run_rsiprobe.log。既定ビルド (work/boot/lift) は変えない (lift をコピーして使う)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
LIFT="$W/lift"
DBG="$W/lift_rsiprobe"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
NODE="$(command -v node)"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[rsiprobe] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

# 40 バイトの非 0 数を数える (LD8 は読出し監視にも入るので、この数え方は診断専用)。
# 件数上限で打ち切られないよう、dst (0x12d777d0 から 0x28 バイト) に当たるものだけを 1 件ずつ出し、総数は別に数える。
DST=0x12d777d0ull
NZ40() { echo "({ int nz_ = 0; for (int i_ = 0; i_ < 0x28; i_++) nz_ += (LD8((uint64_t)($1) + i_) != 0); nz_; })"; }
ENTRY_A="{ static int tot_, hit_; tot_++; if (R[6] >= $DST && R[6] < $DST + 0x28ull) { if (hit_++ < 64) fprintf(stderr, \"[RSI-4080a2] rsi=%llx nz40=%d tot=%d\\n\", (unsigned long long)R[6], $(NZ40 'R[6]'), tot_); } }"
EXIT_B="{ static int tot_, hit_; tot_++; if (R[3] >= $DST && R[3] < $DST + 0x28ull) { if (hit_++ < 64) fprintf(stderr, \"[RSI-4080af] rbx=%llx rsi=%llx nz40=%d tot=%d\\n\", (unsigned long long)R[3], (unsigned long long)R[6], $(NZ40 'R[3]'), tot_); } }"

# 0x6b91e6 (call qword ptr [rax]・ippsZero_8u 呼出しの直前)。呼出し時の dst は R[1]・len は R[2] (lift 107890-107898 で確認)。
RET_6B="{ static int n_; if (n_++ < 64) { uint64_t d_ = R[1]; int nz_ = 0; if (d_ && R[2] <= 0x28) for (int i_ = 0; i_ < 0x28; i_++) nz_ += (LD8(d_ + i_) != 0); fprintf(stderr, \"[RSI-6b91e8] dst=%llx len=%llx nz40=%d\\n\", (unsigned long long)d_, (unsigned long long)R[2], nz_); } }"

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
for k in 0 1 2 3 4 5 6 7; do
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x4080a2 --c "$ENTRY_A" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x4080af --c "$EXIT_B" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x6b91e6 --c "$RET_6B" || true
done
echo "[rsiprobe] probes: $(grep -c 'RSI-' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}')"

FLE_LIFT_DIR="$DBG" FLE_LABEL=rsiprobe FLE_SHARDS=8 SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_rsiprobe.log"
FLE_IPP="${FLE_IPP-}" FLE_BOOT_VARIANT=plain FLE_BOOT_QUIET_BIN=1 timeout "${FLE_BOOT_TIMEOUT:-600}" "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_rsiprobe.cjs" "$W/rsiprobe.json" --boot-only > "$LOG" 2>&1 || true
echo "[rsiprobe] RSI 行: $(grep -c 'RSI-' "$LOG" || true)"
grep -E 'RSI-|FLEBOOT_RESULT' "$LOG" | cut -c1-400
