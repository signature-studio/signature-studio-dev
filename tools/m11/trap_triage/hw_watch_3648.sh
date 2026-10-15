#!/usr/bin/env bash
# #3648 (LD-171): page 保護を変えない書込み監視 (LD_WATCH_MODE=hw・ptrace の DR0/DR1) の boot 状態比較。
# 使い方: hw_watch_3648.sh <tag> <mode: hw|xx> <addr hex> [CPU 番号 (既定 0)]   (FL_WIN64_DIR は REPORT_APPENDIX_3648.md の §1 参照)
#   mode=hw: DR 方式で <addr> の 8 byte と <addr>-8 の 8 byte を監視。mode=xx: 監視なし (page 方式も arm しない値)。
#   mode=xx で <addr> を page 方式の窓 (LD_WATCH_ADDR) として渡すと page 方式 (従来の LD-129 監視) になる。
# 環境は env -i で固定する。環境変数の総長で initial rsp (16 byte 単位) が決まり、guest の boot 状態が変わるため
# (rsp 0x7fffffffbbe0 と 0x7fffffffbbd0 の組で 9〜10 byte 差。REPORT_APPENDIX_3648.md §3)。
# 出力: work/probe3648/<tag>.json (boot state), <tag>.out (hw/wp 行), <tag>.log
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/../../liftdiff" && pwd)"
tag=$1; mode=$2; addr=$3; pin=${4:-0}
W="$HERE/work/probe3648"; mkdir -p "$W"
rm -f "$W/out.txt" "$W/$tag.json" "$W/$tag.out" "$HERE/work/m11/boot_state_hybrid.json"
cd "$HERE" || exit 1
env -i PATH="$PATH" HOME="$HOME" FL_WIN64_DIR="${FL_WIN64_DIR:-$RUNNER_TEMP/fl-win64}" LD_PIN_CPU="$pin" \
  LD_WATCH_MODE="$mode" LD_WATCH_ADDR="$addr" LD_WATCH_OUT="$W/out.txt" \
  timeout 300 python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild > "$W/$tag.log" 2>&1
rc=$?
[ -f work/m11/boot_state_hybrid.json ] && cp work/m11/boot_state_hybrid.json "$W/$tag.json"
[ -f "$W/out.txt" ] && mv "$W/out.txt" "$W/$tag.out"
exit $rc
