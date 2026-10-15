#!/usr/bin/env bash
# py5215_g_init_probe.sh — PY-4887 (#5215): 選択リスト G (`[[[0x15e35c8]]+0xd34]`) の初期化 0xe38870 が
# isPatternSelected 0xd65ff0 より前に通るかを FLEngine boot (既定経路・FLE_IPP 未指定) で観測する。
# 観測点: 0xe38870 (G 初期化)・0xd65ff0 (isPatternSelected)・0xe70800 (0xe38870 の直接の呼出元 0xe7081d を含む関数)・
# 0xd89c70・0x1245ac0 (0xe70800 の直接の呼出元 0xd89cb3・0x1245b00 を含む関数) の入口。
# 制御: 0x12d0cc0 (E の初期化) は PY-4877 で発火したことが既知。同じ bin で 1 件発火すれば probe 機構が動いている。
# 0 件の観測点は「未到達」と読む (発火の順序は stderr のログの順で読む)。
#
#   FL_WIN64_DIR=<展開先> SS_EMSDK_ENV=<emsdk_env.sh> bash tools/flelift/boot/py5215_g_init_probe.sh
#
# 前提: 先に fle6_measure.sh で $FLE_BOOT_WORK/lift を作る (既定 work/boot/lift)。出力は work/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
LIFT="$W/lift"
DBG="$W/lift_dbg5215"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[py5215] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

probe() { echo '{ static int n_; if (n_++ < 8) fprintf(stderr, "['"$1"'] n=%d ret=%llx\n", n_, (unsigned long long)LD64(R[4])); }'; }

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
for k in 0 1 2 3 4 5 6 7; do
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0xe38870 --c "$(probe PY5215-G)" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0xd65ff0 --c "$(probe PY5215-SEL)" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0xe70800 --c "$(probe PY5215-E70800)" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0xd89c70 --c "$(probe PY5215-D89C70)" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x1245ac0 --c "$(probe PY5215-1245AC0)" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x12d0cc0 --c "$(probe PY5215-CTL)" || true
done
echo "[py5215] probe 挿入行数: $(grep -c 'PY5215' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}') (期待 6: G・SEL・E70800・D89C70・1245AC0・CTL 各 1)"

FLE_LIFT_DIR="$DBG" FLE_LABEL=e5215 FLE_SHARDS=8 SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_py5215_probe.log"
FLE_DIAG_NULLFILL=0 FLE_BOOT_VARIANT=plain FLE_BOOT_LOG_CAP=268435456 FLE_BOOT_TIME_CAP=300 FLE_BOOT_QUIET_BIN=1 timeout "${FLE_BOOT_TIMEOUT:-600}" node "$HERE/fle_boot.mjs" "$W/fleboot_e5215.cjs" "$W/py5215_probe.json" --boot-only > "$LOG" 2>&1 || true
echo "[py5215] 観測 (発火数): G=$(grep -c '\[PY5215-G\]' "$LOG" || true) SEL=$(grep -c '\[PY5215-SEL\]' "$LOG" || true) E70800=$(grep -c '\[PY5215-E70800\]' "$LOG" || true) D89C70=$(grep -c '\[PY5215-D89C70\]' "$LOG" || true) 1245AC0=$(grep -c '\[PY5215-1245AC0\]' "$LOG" || true) CTL=$(grep -c '\[PY5215-CTL\]' "$LOG" || true)"
grep -E '\[PY5215|FLEBOOT_RESULT' "$LOG" | cut -c1-300 | head -40
