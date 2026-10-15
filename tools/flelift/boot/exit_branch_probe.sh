#!/usr/bin/env bash
# exit_branch_probe.sh — #5028 (FLE-42): ExitProcess(0) の枝を確定する診断。
#   1. f_412a40 (0x13a5000 に非 0 のエラー番号を書く関数) の入口で、呼出し元の戻り番地 (= [R[4]]) と ecx を記録する。
#      戻り番地 0x409554 / 0x409723 / 0x40c842 / 0x412ad0 のどれかで、f_4096b0 の 4 呼出し元 (0x409553・0x409722・0x40c841・0x412acf) を区別する。
#   2. 0x412a0d (exit 呼出し直前) で [0x15eac80]・[0x15e6068]・[0x13a5000] を出す。
#   3. boot を 1 回回し、結果の行を出す。
#
#   bash tools/flelift/boot/exit_branch_probe.sh     # 前提: 先に fle6_measure.sh で work/boot/lift を作る
#
# 出力: work/boot/run_exitbranch.log (gitignore)。既定ビルド (work/boot/lift) は変えない (lift をコピーして使う)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
LIFT="$W/lift"
DBG="$W/lift_exitbranch"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
NODE="$(command -v node)"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[exitbranch] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

# f_412a40 の入口: 戻り番地 (呼出し元 +5) と ecx (エラー番号)。件数上限 64。
CALLER='{ static int n_; if (n_++ < 64) fprintf(stderr, "[EXITBR-412a40] ret=%llx ecx=%llx\n", (unsigned long long)LD64(R[4]), (unsigned long long)(R[1] & 0xffffffffULL)); }'
# f_4096b0 の入口と、その 4 呼出し元。4 呼出し元は call 命令の直前で、VA を含めて出す。
ENTRY4096='{ static int n_; if (n_++ < 64) fprintf(stderr, "[EXITBR-4096b0] ret=%llx\n", (unsigned long long)LD64(R[4])); }'
# f_4128b0 の入口: 呼出し元 (戻り番地)。ExitProcess に至る枝の入口。
ENTRY4128='{ static int n_; if (n_++ < 64) fprintf(stderr, "[EXITBR-4128b0] ret=%llx\n", (unsigned long long)LD64(R[4])); }'
# exit 呼出し直前 (0x412a0d): exit 時点の分岐条件と終了コード。
EXITC='{ fprintf(stderr, "[EXITBR-412a0d] w15eac80=%llx w15e6068=%llx w13a5000=%llx b15eacb0=%x q15eaca0=%llx q15eadb0=%llx q15e60a0=%llx b15eacb0_raw=%x\n", (unsigned long long)LD64(0x15eac80ULL), (unsigned long long)LD64(0x15e6068ULL), (unsigned long long)LD64(0x13a5000ULL), (unsigned)LD8(0x15eacb0ULL), (unsigned long long)LD64(0x15eaca0ULL), (unsigned long long)LD64(0x15eadb0ULL), (unsigned long long)LD64(0x15e60a0ULL), (unsigned)LD8(0x15eacb0ULL)); }'

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
for k in 0 1 2 3 4 5 6 7; do
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x412a40 --c "$CALLER" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x412a0d --c "$EXITC" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x4128b0 --c "$ENTRY4128" || true
  # f_4096b0 の 4 呼出し元 (call 命令の直前に入れる)。実行されたものは [EXITBR-caller] 行で出る。
  for site in 409553 409722 40c841 412acf; do
    python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x$site --c "{ static int n_; if (n_++ < 64) fprintf(stderr, \"[EXITBR-caller] site=$site\\n\"); }" || true
  done
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x4096b0 --c "$ENTRY4096" || true
done
echo "[exitbranch] probes: $(grep -c 'EXITBR' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}')"

FLE_LIFT_DIR="$DBG" FLE_LABEL=exitbranch FLE_SHARDS=8 SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_exitbranch.log"
FLE_BOOT_VARIANT=plain FLE_BOOT_QUIET_BIN=1 timeout "${FLE_BOOT_TIMEOUT:-600}" "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_exitbranch.cjs" "$W/exitbranch.json" --boot-only > "$LOG" 2>&1 || true
echo "[exitbranch] EXITBR 行: $(grep -c 'EXITBR' "$LOG" || true)"
grep -E 'EXITBR|\[exit-branch\]|\[fleboot\]\[exit\]|FLEBOOT_RESULT' "$LOG" | cut -c1-400
