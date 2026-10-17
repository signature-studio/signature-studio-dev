#!/usr/bin/env bash
# trap114_c_watch_5280.sh (#5280 受入 1 の残り・診断): global 18787504 (0x11EACB0) への C 側の書込みを監視する.
#   m11_ov.c の M11_WATCH_C5695 (m11_cwatch) を、監視範囲 [0x11EACB0, 0x11EACB8) で有効にして prod fix の stage4 を 1 回流す.
#   IR store 側の監視 (trap114_w_probe_5280.py) は 0 件だった (REPORT_APPENDIX_3608 §8-8) ため、C 側の直接 store を見る.
#   監視は読取りのみ (IR の値・分岐は不変). 出力は work/stage4/c114/e2e_full.err の `[a1c] line=<m11_ov.c の行> addr= n= hit=`.
#   前提: work/ldfix_fixed.ll (ldfix_e2e.sh の 1/5 の生成物)・FL_WIN64_DIR・/opt/emsdk.
#   usage: bash tools/m11/ldfix/trap114_c_watch_5280.sh
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
[ -f work/ldfix_fixed.ll ] || { echo "work/ldfix_fixed.ll が無い (bash ldfix_e2e.sh を先に実行)"; exit 1; }
S4_EXTRA_CF="-DM11_OV_NO_450560 -DM11_WATCH_C5695=1 -DM11_WATCH_LO=0x11EACB0 -DM11_WATCH_HI=0x11EACB8" bash stage4.sh work/ldfix_fixed.ll c114 > work/stage4_c114.log 2>&1
rc=$?
grep -a "STAGE4_RESULT" work/stage4_c114.log
echo "[trap114_c_watch_5280] stage4 rc=$rc"
echo "[trap114_c_watch_5280] hits: $(grep -a -c '\[a1c\]' work/stage4/c114/e2e_full.err)"
grep -a '\[a1c\]' work/stage4/c114/e2e_full.err
