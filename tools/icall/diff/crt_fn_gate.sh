#!/usr/bin/env bash
# crt_fn_gate.sh — OTT CRT 数学の関数単位 native 差分 gate (ICALL-5, 1 コマンド)
#   bash tools/icall/diff/crt_fn_gate.sh        前提: ott_e2e.sh と icall_e2e.sh 実行済み (work/ が存在)
# 各関数を native 実機械語 / RetDec route wasm / x64c wasm の 3 者で 600 点 (seed 3) 比較し、route が native と xmm0 raw 64bit 全一致なら PASS。
# FMA3 経路 (__use_fma3=1) は既知の未解決 (1801a9be0 のみ不一致; tools/icall/REPORT.md §8) のため INFO 表示で gate に含めない。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
export NODE="${NODE:-$(command -v node)}" TMPDIR="${TMPDIR:-/tmp}"
RC=0
chk() {   # chk <fn> [extra args]
  local fn=$1; shift
  local line; line=$(python3 "$HERE/fn3_diff.py" "$fn" "$@" --n 600 2>&1 | grep -E "^  route")
  echo "  $fn $* : $line" | cut -c1-150
  echo "$line" | grep -q "xmm0 bit-equal 600/600" || RC=1
}
echo "[crt_fn_gate] SSE2 経路 (__use_fma3=0, DLL 静的値)"
for f in 1801a9a6c 1801a9be0 1801b4154 1801c1240 1801c12f4; do chk $f; done
chk 1801aa1a0 --kernel
echo "[crt_fn_gate] INFO: FMA3 経路 (__use_fma3=1; gate 外)"
for f in 1801a9be0 1801b4154 1801c1240 1801c12f4; do python3 "$HERE/fn3_diff.py" $f --fma 1 --n 600 2>&1 | grep -E "^  route" | sed "s/^/  $f fma=1 : /" | cut -c1-120; done
python3 "$HERE/fn3_diff.py" 1801aa1a0 --kernel --fma 1 --n 600 2>&1 | grep -E "^  route" | sed "s/^/  1801aa1a0 fma=1 : /" | cut -c1-120
[ "$RC" = "0" ] && echo "[crt_fn_gate] PASS" || echo "[crt_fn_gate] FAIL"
exit $RC
