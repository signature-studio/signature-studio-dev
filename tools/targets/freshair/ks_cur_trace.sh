#!/usr/bin/env bash
# Gain ramp の逐次 cur を SC/KH で照合する (#1617 / FA-23)。
#   usage: bash tools/targets/freshair/ks_cur_trace.sh [N=200] [SEED=7]
# 前提: ks_semantic_gain.sh と同じ素材 (work-liftlib-targets) が展開済み。出力: work/cur_trace/
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$HERE"
REPO="$(cd -- "$HERE/../../.." && pwd)"
SC="${SC_CORE:-$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
KH="${KH_CORE:-$REPO/tools/targets/kilohearts/work/winpkg/HeartCore.core_64}"
N="${1:-200}"; SEED="${2:-7}"
W="$FA/work/cur_trace"; mkdir -p "$W"; cd "$W"
cc -O1 -ffp-contract=off -o ks_semantic_gain "$HERE/ks_semantic_gain.c" -lm
./ks_semantic_gain sc "$SC" "$N" "$SEED" > default_sc.txt
./ks_semantic_gain kh "$KH" "$N" "$SEED" > default_kh.txt
CUR_PROBE=1 ./ks_semantic_gain sc "$SC" "$N" "$SEED" > probe_sc.txt 2> probe_sc.err
CUR_PROBE=1 ./ks_semantic_gain kh "$KH" "$N" "$SEED" > probe_kh.txt 2> probe_kh.err
python3 "$HERE/ks_cur_trace.py" default_sc.txt default_kh.txt probe_sc.txt probe_kh.txt probe_sc.err probe_kh.err > trace.json
python3 -c "import json,sys; s=json.load(open('trace.json'))['summary']; print(json.dumps({k:v for k,v in s.items()}, ensure_ascii=False))"
