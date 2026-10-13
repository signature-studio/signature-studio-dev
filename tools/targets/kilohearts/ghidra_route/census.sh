#!/usr/bin/env bash
# Ghidra decompile 出力 (work/ghidra/out_simd: 10 関数) の「C としてそのままビルドできない構文」の個数を数える。
#   bash ghidra_route/census.sh [dir]
# 列: ファイル | 行数 | SIMD 疑似関数 (rcpps/rsqrtps 等: C 意味なし) | 128bit 演算 (SUB168/ZEXT816/auVar 乗算) | 引数なし FUN_ 呼び (レジスタ渡し) | extraout_ (戻り値以外のレジスタ)
set -euo pipefail
D=${1:-"$(cd -- "$(dirname -- "$0")/.." && pwd)/work/ghidra/out_simd"}
printf '%-14s %5s %6s %6s %8s %9s\n' file lines simd128 int128 noargcall extraout
for f in "$D"/*.c; do
  printf '%-14s %5d %6d %6d %8d %9d\n' "$(basename "$f")" "$(wc -l < "$f")" \
    "$(grep -cE '\b(rcpps|rsqrtps|sqrtps|pmaddwd|pshufb|[a-z]+ps|[a-z]+pd)\(in_' "$f" || true)" \
    "$(grep -cE 'SUB168|ZEXT816|auVar[0-9]+ \* auVar|auVar[0-9]+ \* ' "$f" || true)" \
    "$(grep -cE '\bFUN_[0-9a-f]+\(\)|func_0x[0-9a-f]+\(\)' "$f" || true)" \
    "$(grep -cE 'extraout_' "$f" || true)"
done
