#!/usr/bin/env bash
# ildsp (block24360_PE.bin) PSOLA_CreateInstance の closure を x64c で lift → C → wasm → 元の機械語との差分テスト (T-SH-75 / #3401)。
# lift_wc.sh の harness を環境変数で差し替えて使う (既定値は WC のまま)。
# root = CreateInstance (0x1ab540) と vtable 0x3e0030 の slot 0・4・5。slot 1–3 は thunk で DSP 本体 (0x17f700・0x1804b0・0x180830) へ jmp する。
# DSP 本体の窓には unsup が無く、閉包に入る unsup は呼ばれる先の helper にある (slot 1: 73 site・slot 3: 2,401 site。REPORT_APPENDIX_3401.md §8-3)。
# 差分テストは CreateInstance → slot 0 → slot 4 → slot 5 (WC_CALL_IDX="0 4 5")。
# usage: FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash tools/shared/lift/ildsp/lift_psola.sh [ok|neg-cmp|all]
set -euo pipefail
export WC_ENTRY_RVA=0x1ab540 WC_VTABLE_RVA=0x3e0030 WC_WORK=ildsp-psola
export WC_ROOTS="0x1ab540 0x1ab590 0x1ab6b0 0x1ab800" WC_CALL_IDX="0 4 5" WC_RET_IDX="5"
exec bash "$(dirname -- "$0")/lift_wc.sh" "$@"
