#!/usr/bin/env bash
# recount_shim.sh — #784 Win32 shim の数え方の再計算. 試験本体は test_shim.mjs (単体 + ネガコン).
#   数え方 (REPORT §5): checks = test_shim の real 実装の OK 件数 (S1〜S8 の各 check). ネガコン = mutant 件数 (6).
#   ネガコン caught = mutant のうち対応試験が 1 件以上 FAIL した数 (= 期待 6/6).
set -euo pipefail
HB="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$HB"
out="$(node poc/test_shim.mjs)"
real_ok=$(printf '%s\n' "$out" | grep -cE '^OK +S[0-9]+[a-z]? ' || true)
real_fail=$(printf '%s\n' "$out" | grep -cE '^FAIL S[0-9]+[a-z]? ' || true)
neg_caught=$(printf '%s\n' "$out" | sed -n 's/^\[shim\] negative controls caught \([0-9]*\/[0-9]*\)$/\1/p')
echo "real checks OK=${real_ok} FAIL=${real_fail}; negative controls caught=${neg_caught}"
printf '%s\n' "$out" | tail -1
