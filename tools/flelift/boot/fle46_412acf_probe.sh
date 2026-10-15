#!/usr/bin/env bash
# fle46_412acf_probe.sh — FLE-46 (#5443): f_4096b0 の呼出し元 0x412acf が boot 中に実行されるかを観測する。
# 前提: FLE_EXTRA_ROOTS=0x6a7b70,0x412a90 で fle6_measure.sh を先に実行し work/boot/lift を作る
#   (0x412a90 は 0x412a82〜0x412adf の区間の関数。既定 root には入っていないため追加する)。
# 観測 C 文: 0x412acf (call 0x4096b0 の直前) で [EXITBR-caller] を出す。0x412a0d は陽性対照 (exit の call site)。
# 既定ビルドの挙動は変えない。probe は work/boot/lift_fle46/ のコピーにだけ入れる。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
W="$FLE/work/boot"
LIFT="$W/lift"
DBG="$W/lift_fle46"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[fle46] $LIFT が無い。先に FLE_EXTRA_ROOTS=0x6a7b70,0x412a90 bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

PROBE_CALLER='{ static int n_; if (n_++ < 8) fprintf(stderr, "[EXITBR-caller] site=412acf n=%d rcx=%llx rdx=%llx\n", n_, (unsigned long long)R[RCX], (unsigned long long)R[RDX]); }'
PROBE_ENTRY='{ static int n_; if (n_++ < 8) fprintf(stderr, "[EXITBR-caller] site=412a90 n=%d (f_412a90 entry)\n", n_); }'
PROBE_CTRL='{ static int n_; if (n_++ < 4) fprintf(stderr, "[EXITBR-caller] site=412a0d n=%d (control)\n", n_); }'

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
for k in 0 1 2 3 4 5 6 7; do
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x412acf --c "$PROBE_CALLER" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x412a90 --c "$PROBE_ENTRY" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x412a0d --c "$PROBE_CTRL" || true
done
echo "[fle46] probes: $(grep -c 'EXITBR-caller' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}') (expect 3)"

rm -f "$W"/obj/fle46_*.o
FLE_LIFT_DIR="$DBG" FLE_LABEL=fle46 FLE_SHARDS=8 \
  SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_fle46_probe.log"
FLE_IPP=3 FLE_DIAG_NULLFILL=0 FLE_BOOT_VARIANT=plain timeout "${FLE_BOOT_TIMEOUT:-900}" node "$HERE/fle_boot.mjs" "$W/fleboot_fle46.cjs" "$W/fle46_probe.json" --boot-only > "$LOG" 2>&1 || true
echo "[fle46] EXITBR-caller 行: $(grep -c 'EXITBR-caller' "$LOG" || true)"
grep -E 'EXITBR-caller|FLEBOOT_RESULT' "$LOG" | cut -c1-300
