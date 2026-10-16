#!/usr/bin/env bash
# #5310 (KH-149): Delay の void 宣言の関数を呼ぶ 4 呼出し点で、呼出し直後に戻り値 (rax・xmm0・ax) が読まれるかを objdump で示す。
#   bash tools/targets/kilohearts/ghidra_route/void_ret_check.sh <HeartCore.core_64>
# 呼出し点 = 呼出元 VA の call 命令番地 (既定 FX の生成 C での行: 2122・3968・4329・5001)。
# 出力: 各呼出し点の call と直後 6 命令。読む側の判定 (戻り値の利用) は REPORT_APPENDIX_5310.md の表。
set -euo pipefail
CORE=${1:?usage: void_ret_check.sh <HeartCore.core_64>}
objdump -d -M intel --no-show-raw-insn "$CORE" | awk '
BEGIN {
  want["1802ed7c1"] = "180fc4590"   # C 2122: FUN_1802ed790 → FUN_180fc4590 (xmm0)
  want["180fc7004"] = "180fdc880"   # C 3968: FUN_180fc6d70 → FUN_180fdc880 (xmm0)
  want["180fcdc2d"] = "180fd27a8"   # C 4329: FUN_180fcdbfc → FUN_180fd27a8 (ax)
  want["180fd2a64"] = "180fe24b8"   # C 5001: FUN_180fd2a60 → FUN_180fe24b8 (rax)
}
{
  if (rem > 0) { print "    " $0; rem-- }
  key = $1; sub(/:$/, "", key)
  if ((key in want) && $2 == "call" && ($3 == "0x" want[key] || $3 == want[key])) {
    print "== " key " call " want[key]; print "    " $0; rem = 6
  }
}'
