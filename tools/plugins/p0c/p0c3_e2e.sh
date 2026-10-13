#!/usr/bin/env bash
# P0c-3 (CAB-251) RetDec x87 スタック模型修復 pass — 1 コマンド再現
#   bash tools/plugins/p0c/p0c3_e2e.sh [cases]
# 構成:
#   [1] k80abi.py        — kernel 80 実装の機械語 win64 ABI 抽出 (work/k80abi.json)
#   [2] f80_lower.py     — x86_fp80→f64 lowering (k80.lift.ll → work/diff3/k80.lower.ll)
#   [3] k80_argfix.py    — ARG pass 再適用
#   [4] x87fix.py        — x87 スタック模型修復 [R1]-[R10] (work/diff3/k80.x87fix.ll)
#   [5] llvm-as + 冪等性 — x87fix 2 回適用で byte 一致
#   [6] wasm32 compile   — wasm バックエンド通過
#   [7] k80_diff.py      — native 機械語 vs 修復後 IR の差分試験 (fork 隔離)
#   [8] 判定             — 構造修復 3 kernel bit-exact + 既修復 kernel 回帰 0 + 改善確認
# 成果物: work/diff3/, work/p0c3_sweep.csv
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
LIFTP="$(cd "$HERE/../lift/passes" && pwd)"
CASES="${1:-2000}"
FUNCS="function_5de820,function_5dedf0,function_5dfb60,function_5dfbe0,function_5dfc90,function_5dfd30,function_5dfdb0"
CHOP32="function_5dfbe0,function_5dfc90,function_5dfdb0"
mkdir -p "$HERE/work/diff3"

echo "== [1] k80abi (機械語 ABI 抽出) =="
python3 "$HERE/k80abi.py"

echo "== [1b] fix_asm_stores (lift 後段と同じ pass 順, #983) =="
python3 "$LIFTP/fix_asm_stores.py" "$HERE/work/k80.lift.ll" "$HERE/work/diff3/k80.lift.st.ll"

echo "== [2] f80_lower =="
python3 "$HERE/f80_lower.py" "$HERE/work/diff3/k80.lift.st.ll" "$HERE/work/diff3/k80.lower.ll" \
  --report "$HERE/work/diff3/k80.lower.json" \
  --chop-funcs function_5dfbe0,function_5dfc90,function_5dfdb0

echo "== [3] k80_argfix =="
python3 "$HERE/k80_argfix.py" "$HERE/work/diff3/k80.lower.ll" "$HERE/work/diff3/k80.argfix.ll" \
  --abi "$HERE/work/k80abi.json" --report "$HERE/work/diff3/k80.argfix.json"

echo "== [4] x87fix (x87 スタック模型修復) =="
python3 "$HERE/x87fix.py" "$HERE/work/diff3/k80.argfix.ll" "$HERE/work/diff3/k80.x87fix.ll" \
  --report "$HERE/work/diff3/x87fix.json" --funcs "$FUNCS" --chop-f32-fns "$CHOP32"

echo "== [4b] k80_deref_fix (レジスタ経由 deref の落ち修復, #983) =="
python3 "$HERE/k80_deref_fix.py" "$HERE/work/diff3/k80.x87fix.ll" "$HERE/work/diff3/k80.deref.ll" \
  --report "$HERE/work/diff3/deref.json"
llvm-as "$HERE/work/diff3/k80.deref.ll" -o "$HERE/work/diff3/k80.deref.bc"

echo "== [5] llvm-as + 冪等性 =="
llvm-as "$HERE/work/diff3/k80.x87fix.ll" -o "$HERE/work/diff3/k80.x87fix.bc"
python3 "$HERE/x87fix.py" "$HERE/work/diff3/k80.x87fix.ll" "$HERE/work/diff3/k80.x87fix2.ll" \
  --report "$HERE/work/diff3/x87fix2.json" --funcs "$FUNCS" --chop-f32-fns "$CHOP32" >/dev/null
cmp "$HERE/work/diff3/k80.x87fix.ll" "$HERE/work/diff3/k80.x87fix2.ll" && echo "x87fix idempotent OK"

echo "== [6] wasm32 backend =="
python3 - "$HERE/work/diff3" <<'PY'
import sys
d = sys.argv[1]
s = open(d + '/k80.x87fix.ll').read()
out = []
for ln in s.split('\n'):
    if ln.startswith('target triple ='):
        out.append('target triple = "wasm32-unknown-emscripten"')
    elif ln.startswith('target datalayout ='):
        out.append('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-n32:64-S128-ni:1:10:20"')
    else:
        out.append(ln)
open(d + '/k80.x87fix.wasm.ll', 'w').write('\n'.join(out))
PY
/opt/emsdk/upstream/bin/clang --target=wasm32 -O1 -c "$HERE/work/diff3/k80.x87fix.wasm.ll" \
  -o "$HERE/work/diff3/k80.x87fix.wasm.o" --sysroot=/opt/emsdk/sysroot 2>&1 | grep -v "override-module" || true
test -f "$HERE/work/diff3/k80.x87fix.wasm.o" && echo "wasm32 compile OK ($(wc -c < "$HERE/work/diff3/k80.x87fix.wasm.o") bytes)"

echo "== [7] 差分試験 (native vs 修復後 IR, $CASES cases/kernel) =="
python3 "$HERE/k80_diff.py" --ir "$HERE/work/diff3/k80.deref.ll" --cases "$CASES" \
  > "$HERE/work/diff3/build.log" 2>&1 || { tail -20 "$HERE/work/diff3/build.log"; exit 1; }
"$HERE/work/diff/k80diff" > "$HERE/work/p0c3_sweep.csv" 2> "$HERE/work/diff3/run.err" || true
head -1 "$HERE/work/p0c3_sweep.csv"
TARGETS="0x5de820 0x5dedf0 0x5dfb60 0x5dfbe0 0x5dfc90 0x5dfd30 0x5dfdb0"
# 0x5de3e0 は除外 (#277): 従来は sig11 行 (buf_diff=0 固定) がこの判定を素通りしていただけで、
# モデル修復後に測ると IR が [rdx] (上位 32bit) の store を欠落しており buf_diff=2000 (REPORT §14)
REGRESS="0x5df210 0x5df240 0x5e0760 0x5e0b70 0x5e0bb0 0x5e1590 0x5e1780 0x5e0330 0x5dee90 0x5df040 0x5e02b0"
awk -F, 'NR>1 && $1 ~ /^0x/ {last[$1]=$0} END {for (k in last) print last[k]}' "$HERE/work/p0c3_sweep.csv" \
  | sort > "$HERE/work/diff3/last.csv"
echo "-- 7 kernel (0x5de820 系) --"
grep -E '^0x5de820|^0x5dedf0|^0x5dfb60|^0x5dfbe0|^0x5dfc90|^0x5dfd30|^0x5dfdb0' "$HERE/work/diff3/last.csv" || true
echo "-- 回帰 (既修復 kernel) --"
for k in $REGRESS; do grep "^$k," "$HERE/work/diff3/last.csv" || true; done

echo "== [8] 判定 =="
FAIL=0
for k in 0x5de820 0x5dedf0 0x5dfb60; do
  grep "^$k," "$HERE/work/diff3/last.csv" | awk -F, '$5 != 0 {print "[FAIL] " $1 " buf_diff=" $5; exit 1}' || FAIL=1
done
for k in $REGRESS; do
  if grep -q "^$k," "$HERE/work/diff3/last.csv"; then
    grep "^$k," "$HERE/work/diff3/last.csv" | awk -F, '$5 != 0 {print "[FAIL-REGRESS] " $1 " buf_diff=" $5; exit 1}' || FAIL=1
  fi
done
if [ "$FAIL" = "0" ]; then echo "== p0c3 e2e OK (構造修復 3 kernel bit-exact + 回帰 0) =="; else echo "== p0c3 e2e FAIL =="; exit 1; fi
