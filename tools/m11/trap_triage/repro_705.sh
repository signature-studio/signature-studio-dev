#!/usr/bin/env bash
# #705 再現スクリプト (未実行・未検証): 413060 の D4 OFF 実害 (受入条件 1) の survey 比較を 1 本にまとめる。
# 前提: (1) tools/m11/work/ が work-m11 の生成物 + ir_conditions.json (ldfix=applied) を持つこと
#        (無ければ先に bash tools/m11/m11_gen_ir2.sh)
#       (2) FL_WIN64_DIR に extracted/block00031_PE.bin があること (fl-win64 素材)
#       (3) /opt/emsdk が有ること (toolchain-emsdk)。capstone・pefile が入っていること
# 比較対象: A = 既定 (M11_OV_CLASSCREATE=0) / B = 413060 の C 転記を有効化した構成 (未実装: 下の TODO 参照)
# 出力: tools/m11/work/trap_triage/{A,B}.json と survey_diff の表
# TODO: B 構成は m11_ov.c の 413060 を独立ゲート (例 M11_OV_413060) で切り替える改修が要る。未実装のため本スクリプトは A 側の survey と到達数の計数までを行う。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/../.." && pwd)"; cd "$HERE"
mkdir -p work/trap_triage
bash m11_build.sh > work/trap_triage/build_A.log 2>&1
node trap_triage/survey_units.mjs work/trap_triage/A.json > work/trap_triage/survey_A.log 2>&1
tail -1 work/trap_triage/build_A.log
python3 - <<'PY'
import json
d = json.load(open('work/trap_triage/A.json'))
print('units total:', len(d), 'kinds:', {k: sum(1 for r in d if r['kind'] == k) for k in sorted({r['kind'] for r in d})})
PY
