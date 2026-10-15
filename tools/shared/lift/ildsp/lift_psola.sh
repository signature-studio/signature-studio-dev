#!/usr/bin/env bash
# ildsp (block24360_PE.bin) PSOLA_CreateInstance の closure を x64c で lift → C → wasm → 元の機械語との差分テスト (T-SH-75 / #3401)。
# lift_wc.sh の harness を環境変数で差し替えて使う (既定値は WC のまま)。
# root = CreateInstance (0x1ab540) と vtable 0x3e0030 の slot 0・2・4・5。slot 1・3 は thunk で DSP 本体 (0x17f700・0x180830) へ jmp する。
# slot 2 (0x1ab690 → 0x1804b0) は native で単独でも落ちず、閉包の unsup も 0 (REPORT_APPENDIX_3401.md §8-3・本付録 §9)。
# slot 1・3 は native で addr 0 の SIGSEGV になる (復号鍵 [0x3f7ad0] が 0 で、復号済み関数ポインタが不正になる。REPORT_APPENDIX_3401.md §9-3)。ここには入れない。
# 差分テストは CreateInstance → slot 0 → slot 2 → slot 4 → slot 5 (WC_CALL_IDX="0 2 4 5")。
# usage: FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash tools/shared/lift/ildsp/lift_psola.sh [ok|neg-cmp|all]
set -euo pipefail
export WC_ENTRY_RVA=0x1ab540 WC_VTABLE_RVA=0x3e0030 WC_WORK=ildsp-psola
export WC_ROOTS="0x1ab540 0x1ab590 0x1ab690 0x1ab6b0 0x1ab800" WC_CALL_IDX="0 2 4 5" WC_RET_IDX="5"
# T-SH-115 (#4303): WC_COV=1 で到達計測 (basic block)。WC_CASE_MODE=ref で .data の参照窓だけを変える case にする。
# 既定 (WC_COV 未設定) は従来の差分テストのまま。

exec bash "$(dirname -- "$0")/lift_wc.sh" "$@"
