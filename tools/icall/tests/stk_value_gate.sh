#!/usr/bin/env bash
# stk_value_gate.sh — stack 引数 12 語の値一致を icall_e2e.sh の gate として再現する (ICALL-115 / #5339)。
#   bash tools/icall/tests/stk_value_gate.sh
# 判定 (exit 0 = PASS): ① 正常注入で 12/12 一致 ② 1 語ずらしのネガコンで FAIL (matched=0/12) かつ rc=1
# 素材: gcc のみ (OTT 実行経路に依らない)。出力は tools/icall/work/ (gitignore)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/../.."
W="$T/icall/work"
mkdir -p "$W"
BIN="$W/stk_value_check"
gcc -O1 -g -Wall -Wextra -o "$BIN" "$HERE/stk_value_check.c" "$T/ott/native/ms_call.S" || { echo "[stk_value_gate] FAIL: build"; exit 1; }
RC=0
POS=$("$BIN" 2>&1); PRC=$?
echo "$POS" | tail -1
[ "$PRC" = "0" ] && echo "$POS" | grep -q "RESULT PASS matched=12/12" || { echo "[stk_value_gate] FAIL: 正常注入が 12/12 一致しない"; RC=1; }
NEG_OUT=$(NEG=1 "$BIN" 2>&1); NRC=$?
echo "$NEG_OUT" | tail -1
[ "$NRC" = "1" ] && echo "$NEG_OUT" | grep -q "RESULT FAIL (negative control) matched=0/12" || { echo "[stk_value_gate] FAIL: ネガコンが FAIL にならない (判定が偽陽性の疑い)"; RC=1; }
[ "$RC" = "0" ] && echo "[stk_value_gate] PASS" || echo "[stk_value_gate] FAIL"
exit $RC
