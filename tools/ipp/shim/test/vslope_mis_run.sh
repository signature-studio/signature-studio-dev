#!/usr/bin/env bash
# IPP-11 (#473): VectorSlope_64f/_32f を出力先アライメント K=0..16 (64B 境界からのずれ要素数) で実 DLL と突合。
#   1) vslope_verify --mis K (K=0..16): bad_cases=0 であること
#   2) ネガティブコントロール: head 処理を壊した実装で bad_cases が復帰すること
#   3) 自前出力の FNV-1a ハッシュが native / wasm scalar / wasm simd128 で K ごとに一致すること
# 素材は fl-win64 の block24356_PE.bin のみ。env: FL_WIN64_DIR (tools/shared/env.sh)・EMSDK_DIR (既定 /opt/emsdk)。
set -euo pipefail
cd "$(dirname "$0")"; HERE=$PWD; IPP=$(cd ../.. && pwd); W=$IPP/work/vslope_mis; mkdir -p "$W"
source "$IPP/../shared/env.sh"
DLL="$FL_WIN64_DIR/extracted/block24356_PE.bin"
CF="-O1 -I $IPP/src -I $HERE -ffp-contract=off -fno-fast-math"
IMPL64="$IPP/shim/impl/ipp_sig_fill3.c"; IMPL32="$IPP/src/ipp_min.c"
KS=$(seq 0 16)

gcc $CF -w -o "$W/vslope_verify" "$HERE/vslope_verify.c" "$IPP/ref/pe_load.c" $IMPL64 $IMPL32 -lm
echo "== 1) 実 DLL 突合 (K=0..16、各 6 cpu mask x 400 ケース x 64f/32f)"
fail=0
for k in $KS; do
  out=$("$W/vslope_verify" "$DLL" --mis "$k" | tail -1 || true); echo "$out"
  case "$out" in *"bad_cases=0 "*) ;; *) fail=1 ;; esac
done

# ネガコン: 自前実装のコピーに head の誤りを注入して bad_cases が復帰することを確認 (本体は変更しない)
neg() { # $1=名前 $2=対象(64|32) $3=sed 式
  local f dir
  if [ "$2" = 64 ]; then f=$IMPL64; dir=$IPP/shim/impl; else f=$IMPL32; dir=$IPP/src; fi
  (cd "$dir" && sed -e "$3" "$f" | gcc $CF -w -x c - -c -o "$W/neg_$1.o")
  if [ "$2" = 64 ]; then
    gcc $CF -w -o "$W/neg_$1" "$HERE/vslope_verify.c" "$IPP/ref/pe_load.c" "$W/neg_$1.o" $IMPL32 -lm
  else
    gcc $CF -w -o "$W/neg_$1" "$HERE/vslope_verify.c" "$IPP/ref/pe_load.c" $IMPL64 "$W/neg_$1.o" -lm
  fi
  local tot=0
  for k in 1 2 3 5; do
    n=$("$W/neg_$1" "$DLL" --mis "$k" | tail -1 | sed -E 's/.*bad_cases=([0-9]+).*/\1/' || true); echo "  neg[$1] K=$k bad_cases=$n"
    tot=$((tot + n))
  done
  [ "$tot" -gt 0 ] || { echo "  neg[$1] NOT DETECTED"; fail=1; }
}
echo "== 2) ネガティブコントロール (K=1,2,3,5)"
neg 64f_nohead 64 's/while (((uintptr_t)(pDst + i) & 15) != 0)/while (0)/'
neg 32f_nohead 32 's/while (((uintptr_t)(d + i) & 15) != 0)/while (0)/'
neg 64f_peel32B 64 's/while (((uintptr_t)(pDst + i) & 15) != 0)/while (((uintptr_t)(pDst + i) \& 31) != 0)/'
neg 32f_peel32B 32 's/while (((uintptr_t)(d + i) & 15) != 0)/while (((uintptr_t)(d + i) \& 31) != 0)/'
neg 32f_nolaneadv 32 's/for (int j = 0; j < 4; j++) x\[j\] += slope;//'

echo "== 3) native / wasm の自前出力ハッシュ (FNV-1a) が K ごとに一致"
gcc $CF -w -o "$W/vslope_hash" "$HERE/vslope_hash.c" $IMPL64 $IMPL32 -lm
if [ -f "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" ]; then
  source "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" >/dev/null 2>&1
  WCF="-O2 -I $IPP/src -ffp-contract=off -fno-fast-math -sENVIRONMENT=node -sEXIT_RUNTIME=1"
  emcc $WCF -o "$W/vh_scalar.cjs" "$HERE/vslope_hash.c" $IMPL64 $IMPL32 2> "$W/emcc.log"
  emcc $WCF -msimd128 -o "$W/vh_simd.cjs" "$HERE/vslope_hash.c" $IMPL64 $IMPL32 2>> "$W/emcc.log"
  for k in $KS; do
    a=$("$W/vslope_hash" "$k" | awk '{print $3}'); b=$(node "$W/vh_scalar.cjs" "$k" | awk '{print $3}'); c=$(node "$W/vh_simd.cjs" "$k" | awk '{print $3}')
    echo "K=$k native=$a wasm_scalar=$b wasm_simd128=$c"
    [ "$a" = "$b" ] && [ "$a" = "$c" ] || fail=1
  done
else
  echo "emsdk なし: wasm 突合をスキップ"
fi
[ "$fail" = 0 ] && echo "RESULT PASS" || { echo "RESULT FAIL"; exit 1; }
