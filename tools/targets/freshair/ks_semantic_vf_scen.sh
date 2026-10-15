#!/usr/bin/env bash
# SC (SlateCore 0x1808e1fa0) と KH (HeartCore 0x18085a730) の VocalFilter を同一シナリオの実機機械語で実行し、L/R と state を比べる (#4071)。
#   usage: bash tools/targets/freshair/ks_semantic_vf_scen.sh [N=200] [SEED=0x5F17E4] [FMA=0]
# 前提: SC_CORE (SlateCore.core_64) と KH_CORE (HeartCore.core_64) を環境変数で指す。出力: work/vf_scen/
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$HERE"
REPO="$(cd -- "$HERE/../../.." && pwd)"
SC="${SC_CORE:-$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
KH="${KH_CORE:-$REPO/tools/targets/kilohearts/work/winpkg/HeartCore.core_64}"
N="${1:-200}"; SEED="${2:-0x5F17E4}"; FMA="${3:-0}"
W="$FA/work/vf_scen"; mkdir -p "$W"; cd "$W"
clang -O1 -w -o native_vf "$FA/lift2/native/native_vocalfilter.c"
clang -O1 -w -o ks_semantic_vf_kh "$HERE/ks_semantic_vf_kh.c" -lm
python3 "$FA/lift2/gen_vf_scen.py" vf_scen.txt "$N" "$SEED"
cp "$FA/lift2/pokes.txt" pokes.txt
FA_IAT_ALL=1 ./native_vf "$SC" vf_scen.txt "$FMA" > sc.txt 2> sc.err
./ks_semantic_vf_kh "$KH" scen vf_scen.txt > kh.txt
python3 "$HERE/ks_filter_scen_cmp.py" sc.txt kh.txt | tee cmp.txt
