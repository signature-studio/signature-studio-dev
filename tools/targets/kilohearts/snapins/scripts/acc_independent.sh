#!/usr/bin/env bash
# acc_independent.sh — 独立再計算 (規則 37): 自分で native oracle を生成し、自分の replay で突合する。
#   build.py は vec_<trials>_<seed>.bin が存在すると native_ref を再実行しない (キャッシュ) ため、
#   本スクリプトは別人ファイル名 (myvec_*) で native oracle を作り直し、acc_replay.mjs (別実装) で
#   全バイト bit 突合する。tol gate は CAB-273 で compare.mjs からも撤去済み (exact 比較に統一)。
#   注意: scenario 名と dir 名が一致しないもの (khbase) は個別に処理する。存在しない dir を
#   出力先に渡すと native_ref.c は fopen 失敗を検査せず SIGSEGV する (ハーネスの既知動作)。
#
# usage: acc_independent.sh [TRIALS] [SEED]   (既定 200 1)
set -uo pipefail
cd "$(dirname "$0")/.."
TRIALS=${1:-200}; SEED=${2:-1}
CORE=../work/winpkg/HeartCore.core_64
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
NAT=work/native_ref_acc
KHNAT=work/native_ref_acc_kh
[ -x "$NAT" ] || cc -O1 -Wall -o "$NAT" harness/native_ref.c harness/scenarios.c -Iharness -lm
[ -x "$KHNAT" ] || cc -O1 -Wall -o "$KHNAT" harness/native_ref.c harness/scenarios_kh.c -Iharness -lm
fail=0
for n in matrix gain haas clipper gate quickeq resonator stereo disperser formant phaser delay limiter khmathtmp; do
  v=work/$n/myvec_${TRIALS}_${SEED}.bin
  "$NAT" "$CORE" "$n" "$TRIALS" "$SEED" "$v" || { echo "$n NATIVE_FAIL"; fail=1; continue; }
  r=$(node scripts/acc_replay.mjs "$v" work/$n/s0/mod.cjs work/$n/s0/sigs.json)
  echo "$n $r"
  echo "$r" | grep -q '"firstDiff":null' || { echo "  ^^ $n NOT bit-exact"; fail=1; }
done
# khbase は scenario 名 khmath・成果物 dir は khbase (strict 比較なので tol とは無関係)
v=work/khbase/myvec_${TRIALS}_${SEED}.bin
"$NAT" "$CORE" khmath "$TRIALS" "$SEED" "$v" || { echo "khbase NATIVE_FAIL"; fail=1; }
r=$(node scripts/acc_replay.mjs "$v" work/khbase/s0/mod.cjs work/khbase/s0/sigs.json)
echo "khbase(khmath) $r"
echo "$r" | grep -q '"firstDiff":null' || { echo "  ^^ khbase NOT bit-exact"; fail=1; }
# CAB-56 ハーネス (別バイナリ)
for s in khmrel khmaster khmring; do
  v=work/khbase/myvec_${TRIALS}_${SEED}.bin
  "$KHNAT" "$CORE" "$s" "$TRIALS" "$SEED" "$v" || { echo "$s NATIVE_FAIL"; fail=1; continue; }
  r=$(node scripts/acc_replay.mjs "$v" work/khbase/s0/mod.cjs work/khbase/s0/sigs.json)
  echo "$s $r"
  echo "$r" | grep -q '"firstDiff":null' || { echo "  ^^ $s NOT bit-exact"; fail=1; }
done
echo "FAIL=$fail"
exit $fail
