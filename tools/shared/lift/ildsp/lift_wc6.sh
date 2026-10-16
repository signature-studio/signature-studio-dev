#!/usr/bin/env bash
# ildsp (block24360_PE.bin) WaveformColouring_CreateInstance の vtable slot 0–5 を全部呼ぶ差分テスト (T-SH-100 / #4170)。
# lift_wc.sh の harness を環境変数で差し替えて使う (既定の lift_wc.sh は変えない)。
# 引数 (RDX R8 R9 S5 の組を slot ごとに指定): slot 1 は R8=出力 (#4169 §4)、slot 4 は S5=出力・R8=frame 数 0 (#4169 §4)。
# slot 4 の戻り値は ABI 上未定義のため畳み込まない (WC_RET_IDX="0 1 2 3 5"・REPORT_APPENDIX_3401.md §8-4)。
# 実引数 (FL 本体の呼出側) は未確認。ここの値は native が落ちない最小条件 (REPORT_APPENDIX_4170.md §1)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash tools/shared/lift/ildsp/lift_wc6.sh [ok|neg-cmp|all]
set -euo pipefail
export WC_CALL_SLOTS=6 WC_CALL_IDX="0 1 2 3 4 5" WC_RET_IDX="0 1 2 3 5" WC_WORK=ildsp-wc6
export WC_CALL_ARGS="IN 0 0 0;IN OUT 0 0;IN 0 0 0;IN 0 0 0;IN 0 0 OUT;IN 0 0 0"

exec bash "$(dirname -- "$0")/lift_wc.sh" "$@"
