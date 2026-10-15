#!/usr/bin/env bash
# wval_measure.sh — #3771: 値 0x6bbc20 を書く store の VA と宛先を実測する (診断・boot/ 内だけ)。
#
#   FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> bash tools/flelift/boot/wval_measure.sh
#
# 前提: 同じ FLE_BOOT_WORK で fle6_measure.sh (FLE_EXTRA_ROOTS= FLE_BOOT_RUNS=diag_shim) を先に走らせ、
#       lift 出力 ($W/lift) を作っておく。本スクリプトは lift を作り直さない。
# 工程: wval_lift.py (lift 出力の store 文を監視版に書換えた copy を $W/lift_wv に作る)
#       → build.sh plain (FLE_LIFT_DIR=$W/lift_wv・FLE_LABEL=wval。rt と boot の C は既定のまま)
#       → fle_boot.mjs (FLE_IPP=1・FLE_DIAG_NULLFILL=1・--boot-only) → [wval] 行を集計。
# 出力: $W/run_wval.log (stderr 含む)・$W/wval_boot.json。判定は boot の units_run と停止点を見る。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
VAL="${WVAL_VALUE:-0x6bbc20}"
LIFT="$W/lift"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[wval] lift 出力が無い ($LIFT)。先に fle6_measure.sh を走らせる"; exit 2; }
export TMPDIR="$W/tmp"
mkdir -p "$W/tmp"
NODE="$(command -v node)"

T=$(date +%s)
python3 "$HERE/wval_lift.py" --src "$LIFT" --out "$W/lift_wv" --value "$VAL"
echo "[wval] patch done in $(( $(date +%s) - T ))s"

T=$(date +%s)
FLE_LIFT_DIR="$W/lift_wv" FLE_LABEL=wval FLE_SHARDS="${FLE_SHARDS:-8}" bash "$HERE/build.sh" plain
echo "[wval] build done in $(( $(date +%s) - T ))s load=$(cut -d' ' -f1-3 /proc/loadavg)"

LOG="$W/run_wval.log"
rc=0
FLE_IPP="${WVAL_IPP-1}" FLE_DIAG_NULLFILL="${WVAL_NULLFILL-1}" FLE_BOOT_VARIANT=plain "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_wval.cjs" "$W/wval_boot.json" --boot-only > "$LOG" 2>&1 || rc=$?
grep 'FLEBOOT_RESULT' "$LOG" || true
echo "[wval] boot rc=$rc log=$LOG"
echo "[wval] 一致 (store [wval] と間接呼出し [wval-call]): $(grep -c '^\[wval' "$LOG" || true) 件"
grep '^\[wval' "$LOG" | head -60 || true
