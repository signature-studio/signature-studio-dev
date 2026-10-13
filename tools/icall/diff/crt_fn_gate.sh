#!/usr/bin/env bash
# crt_fn_gate.sh — OTT CRT 数学の関数単位 native 差分 gate (ICALL-5, 1 コマンド)
#   bash tools/icall/diff/crt_fn_gate.sh        前提: ott_e2e.sh と icall_e2e.sh 実行済み (work/ が存在)
# 各関数を native 実機械語 / RetDec route wasm / x64c wasm の 3 者で 600 点 (seed 3) 比較し、route が native と xmm0 raw 64bit 全一致なら PASS。
# FMA3 経路 (__use_fma3=1) も gate (ICALL-6 #361 で 1801a9be0 の xmm1 戻り ABI を修復)。rax は 1801a9a6c で scratch のため判定しない (REPORT §11.3)。
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
echo "[crt_fn_gate] FMA3 経路 (__use_fma3=1)"
for f in 1801a9be0 1801b4154 1801c1240 1801c12f4; do chk $f --fma 1; done
chk 1801aa1a0 --kernel --fma 1
echo "[crt_fn_gate] 負入力 (--neg: 符号復元経路 [rsp+0x40]; N3 ir_fix_vstore の検出用)"
chk 1801a9be0 --neg
chk 1801a9be0 --neg --fma 1
echo "[crt_fn_gate] override 4/4 (1801c8c00 1801c8cb8 1801a9a6c 1801a9b38)"
python3 - "$HERE/../work/route/override.json" <<'PY' || RC=1
import json, sys
o = json.load(open(sys.argv[1]))
want = {'1801c8c00', '1801c8cb8', '1801a9a6c', '1801a9b38'}
ok = want <= set(o['overridden']) and not o['missing']
print('  overridden %d/4 missing %s' % (len(want & set(o['overridden'])), o['missing']))
sys.exit(0 if ok else 1)
PY
[ "$RC" = "0" ] && echo "[crt_fn_gate] PASS" || echo "[crt_fn_gate] FAIL"
exit $RC
