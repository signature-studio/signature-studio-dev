#!/usr/bin/env bash
# SC (SlateCore 0x180b6f050) と KH (HeartCore 0x1804655e0) の Filter を同一シナリオの実機機械語で実行し、L/R と state を比べる。
#   usage: bash tools/targets/freshair/ks_semantic_filter_scen.sh [N=200] [SEED=0xF117E4] [FMA=0]
# 前提: work/win/ (SlateCore) と ../kilohearts/work/winpkg/ (HeartCore) が展開済み (work-liftlib-targets)。出力: work/filter_scen/
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$HERE"
REPO="$(cd -- "$HERE/../../.." && pwd)"
SC="${SC_CORE:-$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
KH="${KH_CORE:-$REPO/tools/targets/kilohearts/work/winpkg/HeartCore.core_64}"
N="${1:-200}"; SEED="${2:-0xF117E4}"; FMA="${3:-0}"
W="$FA/work/filter_scen"; mkdir -p "$W"; cd "$W"
clang -O1 -w -o native_filter "$FA/lift2/native/native_filter.c"
clang -O1 -w -o ks_semantic_filter_kh "$HERE/ks_semantic_filter_kh.c" -lm
python3 "$FA/lift2/gen_filter_scen.py" filter_scen.txt "$N" "$SEED"
cp "$FA/lift2/pokes.txt" pokes.txt
FA_IAT_ALL=1 ./native_filter "$SC" filter_scen.txt "$FMA" > sc.txt 2> sc.err
./ks_semantic_filter_kh "$KH" scen filter_scen.txt > kh.txt
python3 "$HERE/ks_filter_scen_cmp.py" sc.txt kh.txt | tee cmp.txt
