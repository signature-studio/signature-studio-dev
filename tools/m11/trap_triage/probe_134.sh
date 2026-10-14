#!/usr/bin/env bash
# #134: unit 56 (VA 0x16fde0) が 8c5eb0 へ渡す this (VMT) の状態を survey 中に採取する. guard の入力 R (件数は R の list から読まれる) ではない (REPORT_134 §4).
# 既定 off の挙動は不変 (M11_PROBE_134 未設定の survey は従来どおり). 前提: m11_e2e.sh 済み (work/m11_boot.cjs・work/m11_image.bin).
# 出力: work/v134/ (n1〜n3 = 同一条件の再現, nc_shift1 = 読み取り先を 1 byte ずらしたネガコン).
set -u
cd "$(dirname "$0")/.."
OUT=work/v134
mkdir -p "$OUT"
for k in 1 2 3; do
  M11_PROBE_134=1 timeout 300 node m11_survey.mjs > "$OUT/n$k.out" 2> "$OUT/n$k.err" || { echo "FAIL: survey n=$k"; exit 1; }
  grep '^\[probe134\]' "$OUT/n$k.err" | cut -c1-600
done
M11_PROBE_134=1 M11_PROBE_134_OBJS=1469801,1470129 timeout 300 node m11_survey.mjs > "$OUT/nc_shift1.out" 2> "$OUT/nc_shift1.err" || { echo "FAIL: survey nc"; exit 1; }
grep '^\[probe134\] unit' "$OUT/nc_shift1.err" | cut -c1-600
