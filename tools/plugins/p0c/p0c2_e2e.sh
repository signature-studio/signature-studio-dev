#!/usr/bin/env bash
# P0c-2 (CAB-241) f80→f64 lowering pass — 1 コマンド再現
#   bash tools/plugins/p0c/p0c2_e2e.sh [cases]
# 構成:
#   [1] k80abi.py        — kernel 80 実装の機械語 win64 ABI 抽出 (work/k80abi.json)
#   [2] f80_lower.py     — x86_fp80→f64 lowering (k80.lift.ll → work/diff/k80.lower.ll)
#   [3] k80_argfix.py    — ARG pass 再適用 (xmm 引数接続 / spill 初期化修復)
#   [4] llvm-as + 冪等性 — pass 出力の llvm-as 通過 + 2 回適用で byte 一致
#   [5] wasm32 compile   — lowering 後モジュールの wasm バックエンド通過 (emcc_base.log の 20 error 解消)
#   [6] k80_diff.py      — native 機械語 vs lift IR の差分試験 (kernel 毎 CSV, fork 隔離)
#   [7] f80_micro        — CAB-196 の model level 実測 (回帰確認)
# 成果物: work/diff/{k80.lower.ll,k80.argfix.ll,k80diff}, work/p0c2_sweep.csv
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../shared/env.sh"
LIFTP="$(cd "$HERE/../lift/passes" && pwd)"
CASES="${1:-2000}"
PE="$FL_WIN64_DIR/extracted/block18983_PE.bin"
mkdir -p "$HERE/work/diff"

echo "== [1] k80abi (機械語 ABI 抽出) =="
python3 "$HERE/k80abi.py"

echo "== [2] f80_lower =="
python3 "$HERE/f80_lower.py" "$HERE/work/k80.lift.ll" "$HERE/work/diff/k80.lower.ll" \
  --report "$HERE/work/diff/k80.lower.json" \
  --chop-funcs function_5dfbe0,function_5dfc90,function_5dfdb0

echo "== [3] k80_argfix (ARG pass 再適用) =="
python3 "$HERE/k80_argfix.py" "$HERE/work/diff/k80.lower.ll" "$HERE/work/diff/k80.argfix.ll" \
  --abi "$HERE/work/k80abi.json" --report "$HERE/work/diff/k80.argfix.json"

echo "== [4] llvm-as + 冪等性 =="
llvm-as "$HERE/work/diff/k80.argfix.ll" -o "$HERE/work/diff/k80.argfix.bc"
python3 "$HERE/f80_lower.py" "$HERE/work/diff/k80.argfix.ll" "$HERE/work/diff/k80.argfix2.ll" \
  --chop-funcs function_5dfbe0,function_5dfc90,function_5dfdb0 >/dev/null
cmp "$HERE/work/diff/k80.argfix.ll" "$HERE/work/diff/k80.argfix2.ll" && echo "idempotent OK"
python3 "$HERE/k80_argfix.py" "$HERE/work/diff/k80.argfix.ll" "$HERE/work/diff/k80.argfix3.ll" \
  --abi "$HERE/work/k80abi.json" >/dev/null
cmp "$HERE/work/diff/k80.argfix.ll" "$HERE/work/diff/k80.argfix3.ll" && echo "argfix idempotent OK"

echo "== [5] wasm32 backend =="
python3 - "$HERE/work/diff" <<'PY'
import sys
d = sys.argv[1]
s = open(d + '/k80.argfix.ll').read()
out = []
for ln in s.split('\n'):
    if ln.startswith('target triple ='):
        out.append('target triple = "wasm32-unknown-emscripten"')
    elif ln.startswith('target datalayout ='):
        out.append('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-n32:64-S128-ni:1:10:20"')
    else:
        out.append(ln)
open(d + '/k80.argfix.wasm.ll', 'w').write('\n'.join(out))
PY
/opt/emsdk/upstream/bin/clang --target=wasm32 -O1 -c "$HERE/work/diff/k80.argfix.wasm.ll" \
  -o "$HERE/work/diff/k80.argfix.wasm.o" --sysroot=/opt/emsdk/sysroot 2>&1 | grep -v "override-module" || true
test -f "$HERE/work/diff/k80.argfix.wasm.o" && echo "wasm32 compile OK ($(wc -c < "$HERE/work/diff/k80.argfix.wasm.o") bytes)"

echo "== [6] 差分試験 (native vs lift IR, $CASES cases/kernel) =="
python3 "$HERE/k80_diff.py" --ir "$HERE/work/diff/k80.argfix.ll" --cases "$CASES" \
  > "$HERE/work/diff/build.log" 2>&1 || { tail -20 "$HERE/work/diff/build.log"; exit 1; }
"$HERE/work/diff/k80diff" > "$HERE/work/p0c2_sweep.csv" 2> "$HERE/work/diff/run.err" || true
echo "-- sweep 結果 (kernel 毎: ret/buf 差分) --"
head -1 "$HERE/work/p0c2_sweep.csv"
grep -E '^0x' "$HERE/work/p0c2_sweep.csv" | awk -F, '!seen[$1]++' | head -40
echo "(全行: $(grep -cE '^0x' "$HERE/work/p0c2_sweep.csv") / crash 込み — 詳細は work/p0c2_sweep.csv)"

echo "== [7] f80_micro (model level 回帰) =="
cc -O2 -ffp-contract=off -o "$HERE/work/diff/f80_micro" "$HERE/f80_micro.c" -lm
"$HERE/work/diff/f80_micro" "$PE" 2000000 | head -12

echo "== p0c2 e2e OK =="
