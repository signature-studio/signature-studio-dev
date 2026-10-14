#!/usr/bin/env bash
# Gain の意味同一性 (SlateCore 0x180afe090 ⇄ HeartCore 0x1804b0380) を同一入力の native 差分で測る。
#   usage: bash tools/targets/freshair/ks_semantic_gain.sh [N=200] [SEED=7]
# 前提: work/win/ (SlateCore) と ../kilohearts/snapins/ の HeartCore が展開済み。出力: work/semantic_gain/
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$HERE"
REPO="$(cd -- "$HERE/../../.." && pwd)"
SC="${SC_CORE:-$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
KH="${KH_CORE:-$REPO/tools/targets/kilohearts/work/winpkg/HeartCore.core_64}"
N="${1:-200}"; SEED="${2:-7}"
W="$FA/work/semantic_gain"; mkdir -p "$W"; cd "$W"
cc -O1 -o ks_semantic_gain "$HERE/ks_semantic_gain.c" -lm
IN_DUMP=1 ./ks_semantic_gain sc "$SC" "$N" "$SEED" > sc.txt 2> sc_in.txt
IN_DUMP=1 ./ks_semantic_gain kh "$KH" "$N" "$SEED" > kh.txt 2> kh_in.txt
python3 "$HERE/ks_semantic_gain_cmp.py" sc.txt kh.txt | tee cmp.json
python3 "$HERE/ks_semantic_gain_ulp.py" sc.txt kh.txt | tee ulp.json
python3 "$HERE/ks_gain_model.py" sc.txt kh.txt sc_in.txt kh_in.txt | tee model.json
