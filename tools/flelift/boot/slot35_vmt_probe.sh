#!/usr/bin/env bash
# slot35_vmt_probe.sh — #5897 (PY-5398): slot 35 (`call qword ptr [reg+0x118]`) の箇所で、
# 実行時の受け手オブジェクトの VMT (`*(reg)`) を採取する probe。
#   bash tools/flelift/boot/slot35_vmt_probe.sh     # 前提: 先に fle6_measure.sh (RUNS=default) で work/boot/lift を作る
#
# 手順: pe_slot35_sites.py の箇所 (151 件) の lift 行 `/* <va>: call qword ptr [<reg> + 0x118] */` の直前に、
# <reg> の指す値 (VMT) を出す。呼出しの直前で R[k] は未変更なので、LD64(R[k]) が受け手の先頭 8 バイト (VMT) に等しい。
# 出力: work/boot/run_slot35.log (gitignore)。採取行は `[S35] site=<VA> reg=<reg> vmt=<hex>`。既定ビルド (work/boot/lift) は変えない。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
LIFT="$W/lift"
DBG="$W/lift_slot35"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
NODE="$(command -v node)"
SITES="$W/slot35_sites.txt"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[slot35] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

mkdir -p "$W"
python3 "$FLE/../python/analysis/flapi/pe_slot35_sites.py" | awk '/^[0-9a-f]+ fn=/{print $1}' > "$SITES"
N=$(wc -l < "$SITES")
[ "$N" = 151 ] || { echo "[slot35] 箇所数 $N (期待 151)"; exit 3; }

# レジスタ名 -> R[] 添字 (x64c.py の並び: rax rcx rdx rbx rsp rbp rsi rdi = 0..7、r8..r15 = 8..15)
reg_index() {
  case "$1" in
    rax) echo 0;; rcx) echo 1;; rdx) echo 2;; rbx) echo 3;; rsp) echo 4;; rbp) echo 5;; rsi) echo 6;; rdi) echo 7;;
    r8|r9|r10|r11|r12|r13|r14|r15) echo "${1#r}";;
    *) return 1;;
  esac
}

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
for k in 0 1 2 3 4 5 6 7; do
  f="$DBG/fle_lifted_s$k.c"
  while read -r va; do
    line=$(grep -E "^  /\* ${va}: call qword ptr \[r[a-z0-9]+ \+ 0x118\] \*/" "$f" || true)
    [ -n "$line" ] || continue
    reg=$(sed -E 's/.*\[(r[a-z0-9]+) \+ 0x118\].*/\1/' <<< "$line")
    idx=$(reg_index "$reg") || { echo "[slot35] 未知のレジスタ $reg ($va)"; exit 4; }
    python3 "$HERE/dbg_lift.py" --src "$f" --out "$f" --at "0x$va" \
      --c "{ static int n_; if (n_++ < 64) fprintf(stderr, \"[S35] site=$va reg=$reg vmt=%llx\\n\", (unsigned long long)LD64(R[$idx])); }" > /dev/null
  done < "$SITES"
  # 陽性対照: 既知に通る exit 直前 (0x412a0d・run の [EXITBR-412a0d] で発火を確認済み)。probe 機構が動くことを示す。
  python3 "$HERE/dbg_lift.py" --src "$f" --out "$f" --at 0x412a0d \
    --c '{ static int n_; if (n_++ < 64) fprintf(stderr, "[S35-control] site=412a0d\n"); }' > /dev/null || true
done
echo "[slot35] probes: $(grep -c 'S35' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}') / 151 (lift に載った箇所)"

FLE_LIFT_DIR="$DBG" FLE_LABEL=slot35 FLE_SHARDS=8 SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_slot35.log"
FLE_BOOT_VARIANT=plain FLE_BOOT_QUIET_BIN=1 timeout "${FLE_BOOT_TIMEOUT:-900}" "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_slot35.cjs" "$W/slot35.json" --boot-only > "$LOG" 2>&1 || true
echo "[slot35] S35 行: $(grep -c 'S35' "$LOG" || true)"
grep -E 'S35|FLEBOOT_RESULT' "$LOG" | cut -c1-400
