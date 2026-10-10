#!/usr/bin/env bash
# lift2_e2e.sh — CAB-48 (FA-2) Fresh Air Compressor/Filter lift の 1 コマンド検収。
#   1) mlift で Compressor (0x180775220) / Filter (0x180b6f050) closure を lift → emcc → wasm
#   2) native oracle (実機機械語敷設 + IAT shim 差替) との bit-exact 比較 (fma0/fma1)
#   3) ctx-fuzz: 構造化 200 + ランダム 1000 試行 × 2 target × 2 fma
#   4) ABI 検査 (callee-saved GPR) + メモリ閉込 (canary)
#   5) ablation: mlift 意味論の故障注入 (RetDec 欠陥類型との対応の実測)
# 実時間: 約 3 分 (RetDec 不使用のため lift は数秒)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
[ -f "$CORE" ] || { echo "ERROR: $CORE が無い (bash tools/targets/freshair/fetch.sh を先に実行)"; exit 2; }
fail=0
step() { echo; echo "==== $* ===="; }

step "1. build (mlift lift → emcc → wasm + native oracle)"
bash "$HERE/build_comp.sh" 2>&1 | tail -2 || fail=1
bash "$HERE/build_filter.sh" 2>&1 | tail -1 || fail=1

step "2. bit-exact: Compressor process (400 scenarios × fma0/1)"
bash "$HERE/run_comp.sh" 400 | tail -3 || fail=1

step "3. bit-exact: Filter process (200 scenarios × fma0/1)"
bash "$HERE/run_filter.sh" 200 | tail -3 || fail=1

step "4. ctx-fuzz (structured 200 + random 1000) × comp/filter × fma0/1"
bash "$HERE/run_fuzz.sh" 200 1000 | tail -4 || fail=1

step "5. ABI 検査: 静的 (push/pop 対応, closure 全関数) + 実行時 (asm capture/verify, Compressor) + canary (メモリ閉込)"
python3 "$HERE/abi_static_check.py" "$CORE" || fail=1
ABI_OUT=$( cd "$HERE/work/filter" && source "$HERE/env.sh" && clang -O1 -w -o abi_check "$HERE/native/abi_check.c" && timeout 15 ./abi_check "$CORE" 2>&1 )
echo "$ABI_OUT" | grep -E "violations"
echo "$ABI_OUT" | grep -q "violations=0" || { echo "ABI check FAIL"; fail=1; }

step "6. ablation (mlift 意味論の故障注入 → RetDec 欠陥類型の実測)"
bash "$HERE/ablate_comp.sh" 200 | tail -7 || fail=1

echo
if [ $fail -eq 0 ]; then echo "RESULT: lift2_e2e ALL PASS"; else echo "RESULT: lift2_e2e FAILED"; fi
exit $fail
