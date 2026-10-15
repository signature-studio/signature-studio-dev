#!/usr/bin/env bash
# ildsp (block24360_PE.bin) PSOLA_CreateInstance の 7 root 閉包 (基準 4 root + vtable slot 1・2・3 の thunk 先) を x64c で lift し、
# 差分テストは CreateInstance → slot 0 → slot 4 → slot 5 (lift_psola.sh と同じ呼出し)。slot 1–3 は差分の呼出しに入れない (T-SH-81 の子で扱う)。
# 測定の範囲: 閉包 lift の unsup と、閉包を広げた lift で基準の差分が保たれるか (#3427)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash tools/shared/lift/ildsp/lift_psola_closure.sh [ok|neg-cmp|all]
set -euo pipefail
export WC_ENTRY_RVA=0x1ab540 WC_VTABLE_RVA=0x3e0030 WC_WORK=ildsp-psola-closure7
export WC_ROOTS="0x1ab540 0x1ab590 0x1ab680 0x1ab690 0x1ab6a0 0x1ab6b0 0x1ab800" WC_CALL_IDX="0 4 5" WC_RET_IDX="5"
exec bash "$(dirname -- "$0")/lift_wc.sh" "$@"
