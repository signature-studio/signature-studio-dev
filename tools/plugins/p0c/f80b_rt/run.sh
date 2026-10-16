#!/usr/bin/env bash
# f80 bitcast 展開 (f80_lower.py の expand_f80_bitcasts) の bit 一致検査。
# host の x87 (long double) を期待値にして、wasm (emcc) 版の結果と 1 件ずつ比べる。
# 生成物は work/f80b_rt/ (gitignore)。 使い方: bash tools/plugins/p0c/f80b_rt/run.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P0C="$(cd "$HERE/.." && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
W="$ROOT/work/f80b_rt"
EMCC="${EMCC:-$(command -v emcc || echo /opt/emsdk/upstream/emscripten/emcc)}"
mkdir -p "$W"
cd "$W"
gcc -O1 -o gen_cases "$HERE/gen_cases.c" -lm
./gen_cases
cp "$HERE/check.c" .
# 参照 IR: 関数 2 本 (double→x87 像 / x87 像→double) を x86_fp80 bitcast で書く
cat > rt.ll <<'EOF'
target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"
target triple = "wasm32-unknown-emscripten"

define i64 @to_mant(double %x) {
entry:
  %f = fpext double %x to x86_fp80
  %b = bitcast x86_fp80 %f to i80
  %t = trunc i80 %b to i64
  ret i64 %t
}

define i64 @to_se(double %x) {
entry:
  %f = fpext double %x to x86_fp80
  %b = bitcast x86_fp80 %f to i80
  %s = lshr i80 %b, 64
  %t = trunc i80 %s to i64
  ret i64 %t
}

define double @from_img(i64 %m, i64 %se) {
entry:
  %a = zext i64 %m to i80
  %b = zext i64 %se to i80
  %c = shl i80 %b, 64
  %d = or i80 %a, %c
  %r = bitcast i80 %d to x86_fp80
  %o = fptrunc x86_fp80 %r to double
  ret double %o
}
EOF
python3 "$P0C/f80_lower.py" rt.ll rt_lower.ll
"$EMCC" -O1 rt_lower.ll check.c -o check.cjs
node check.cjs
