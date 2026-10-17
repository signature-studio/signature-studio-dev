#!/usr/bin/env bash
# Filter の係数計算関数を SC (0x180b7fa80) と KH (0x180469d40) で同一シナリオ入力の下で記録し、入口引数と出口の係数ブロックを比べる。
#   usage: bash tools/targets/freshair/ks_coef_scen.sh [N=200] [SEED=0xF117E4] [FMA=0]
# 前提: work/win/ (SlateCore) と ../kilohearts/work/winpkg/ (HeartCore) が展開済み。出力: work/coef_scen/
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$HERE"
REPO="$(cd -- "$HERE/../../.." && pwd)"
SC="${SC_CORE:-$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
KH="${KH_CORE:-$REPO/tools/targets/kilohearts/work/winpkg/HeartCore.core_64}"
N="${1:-200}"; SEED="${2:-0xF117E4}"; FMA="${3:-0}"
W="$FA/work/coef_scen"; mkdir -p "$W"; cd "$W"
clang -O1 -w -o coef_probe "$FA/lift2/native/coef_probe.c"
python3 "$FA/lift2/gen_filter_scen.py" filter_scen.txt "$N" "$SEED"
cp "$FA/lift2/pokes.txt" pokes.txt
FA_IAT_ALL=1 timeout 300 ./coef_probe sc "$SC" filter_scen.txt sc_coef.txt "$FMA"
timeout 300 ./coef_probe kh "$KH" filter_scen.txt kh_coef.txt
python3 "$HERE/ks_coef_cmp.py" sc_coef.txt kh_coef.txt | tee coef_cmp.txt
