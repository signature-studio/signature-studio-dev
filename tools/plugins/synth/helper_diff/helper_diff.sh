#!/usr/bin/env bash
# #535 helper 差分試験 (native 機械語 vs lift 側実装) + ネガティブコントロール。 1 コマンド: bash tools/plugins/synth/helper_diff/helper_diff.sh [N]
#   本体 (control) が rc 0、各ネガコン (実装を 1 箇所壊す) が rc 1 かつ mismatch > 0 でなければ exit 1。
# 前提: AVX2 対応 CPU (native 側で vaddps ymm 等を実行する)。 無ければ exit 2 (「未検証」であり合格にしない)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
P="$HERE/../../lift/passes"
W="${HELPER_DIFF_WORK:-$HERE/../../work/synth/helper_diff}"
N="${1:-200000}"
mkdir -p "$W"
grep -q ' avx2 ' /proc/cpuinfo || { echo "[helper_diff] AVX2 無し: 差分試験できない (exit 2)" >&2; exit 2; }

build() {  # build <tag> <ll> <simd.c>  -> $W/<tag>.bin
  clang -O1 -mavx2 -fno-fast-math -ffp-contract=off -w -I"$P" -o "$W/$1.bin" "$HERE/helper_diff.c" "$3" "$2" -lm
}
gen() {  # gen <tag>: synth.ll -> fix_avx256 -> m11_simd2
  python3 "$P/fix_avx256.py" "$HERE/synth.ll" "$W/$1.ll" 2> "$W/$1.fix.log"
  python3 "$P/m11_simd2.py" "$W/$1.ll" 2> "$W/$1.simd.log" | sed 's#"\.\./msimd11_core\.h"#"msimd11_core.h"#' > "$W/$1.simd.c"
}
gen ctl
cat "$W/ctl.fix.log" "$W/ctl.simd.log"
# 生成物が「未実装 0 / i256 trap 0」であること (宣言した helper が実装されている)
grep -q 'unimplemented 0, i256 trap 0' "$W/ctl.simd.log" || { echo "[helper_diff] FAIL: ctl に未実装 helper / i256 trap が残る" >&2; exit 1; }
build ctl "$W/ctl.ll" "$W/ctl.simd.c"
"$W/ctl.bin" "$N" | tee "$W/ctl.out"

rc=0
nc() {  # nc <name> <file-to-mutate: ll|simd.c> <sed-expr>
  local name="$1" f="$2" expr="$3"
  gen "$name"
  cp "$W/$name.$f" "$W/$name.$f.orig"
  sed -i -e "$expr" "$W/$name.$f"
  cmp -s "$W/$name.$f" "$W/$name.$f.orig" && { echo "[helper_diff] NC $name: 変異が当たっていない (sed 不発) -> FAIL" >&2; rc=1; return; }
  build "$name" "$W/$name.ll" "$W/$name.simd.c"
  set +e; "$W/$name.bin" "$N" > "$W/$name.out"; local r=$?; set -e
  local mm; mm=$(sed -n 's/.*mismatches=\([0-9]*\).*/\1/p' "$W/$name.out" | tail -1)
  if [ "$r" = 1 ] && [ "${mm:-0}" -gt 0 ]; then echo "[helper_diff] NC $name: rc=1 mismatches=$mm (期待通り FAIL)"; else echo "[helper_diff] NC $name: rc=$r mismatches=${mm:-?} (FAIL すべきなのに通った) -> NG" >&2; rc=1; fi
}
nc nc_cmpnltps   simd.c 's/!(x < y)/(x >= y)/'                      # NaN の扱いを変える
nc nc_movmskps   simd.c 's/>> 31)/>> 30)/'                           # sign bit の位置
nc nc_stosb_len  simd.c 's/memset(a, (int)(u8)b, (size_t)c)/memset(a, (int)(u8)b, (size_t)(c ? c - 1 : 0))/'
nc nc_movsd_ovlp simd.c 's/if (d <= s || d >= s + (size_t)c \* 4u)/if (1)/'   # 重なり (dst>src) でも memmove にする
nc nc_min        ll     's/fcmp olt <8 x float>/fcmp ogt <8 x float>/'
nc nc_ext1       ll     's/lshr i256 \(%[A-Za-z0-9_]*\), 128/lshr i256 \1, 0/'
nc nc_store128   ll     's/store i128 %new, ptr %p/store i256 0, ptr %p/'
if [ "$rc" = 0 ]; then echo "[helper_diff] OK: control 0 mismatch / NC 7 件すべて期待通り FAIL"; exit 0; fi
echo "[helper_diff] FAIL" >&2; exit 1
