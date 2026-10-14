#!/usr/bin/env bash
# #134: unit 56 (VA 0x16fde0) の 8c5eb0 の guard 入力を trap 時点で採取する (n=3 + NC)。
#   採るもの: arg2 (dl・bit 7) / R = 410320 の戻り / list = 8c67a0(R) の戻り / R と list の +0x14・先頭 qword・[先頭 qword - 0x50]。
#   IR probe (trap_triage/probe134_ir.py) は M11_PROBE_134=1 の build でだけ入る。既定 build は変えない (REPORT_134 §5)。
#   補助として this (VMT, linear 1469800/1470128) の状態も採る (guard の入力ではない)。
# 前提: m11_gen_ir2.sh 済み (work/boot_final.ll・ir_conditions.json)・素材 (FL_WIN64_DIR)。
# 出力: work/v134/ (n1〜n3 = 同一条件の再現, nc_shift1 = VMT の読み取り先を 1 byte ずらしたネガコン)。
set -u
cd "$(dirname "$0")/.."
OUT=work/v134
mkdir -p "$OUT"
M11_PROBE_134=1 bash m11_build.sh > "$OUT/build.log" 2>&1 || { echo "FAIL: build (M11_PROBE_134=1)"; tail -5 "$OUT/build.log"; exit 1; }
for k in 1 2 3; do
  M11_PROBE_134=1 timeout 300 node m11_survey.mjs > "$OUT/n$k.out" 2> "$OUT/n$k.err" || { echo "FAIL: survey n=$k"; exit 1; }
  grep '^\[probe134\]' "$OUT/n$k.err" | cut -c1-2000
done
M11_PROBE_134=1 M11_PROBE_134_OBJS=1469801,1470129 timeout 300 node m11_survey.mjs > "$OUT/nc_shift1.out" 2> "$OUT/nc_shift1.err" || { echo "FAIL: survey nc"; exit 1; }
grep '^\[probe134\] unit' "$OUT/nc_shift1.err" | cut -c1-600
