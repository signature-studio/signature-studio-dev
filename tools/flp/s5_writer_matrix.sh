#!/usr/bin/env bash
# #3052 §21: Autogun の 32-bit float 書出し経路 (WAV ヘッダの書き手) を、FLEngine_x64.dll の即値・return・int3 の置換で切り分ける。
# 試行は 1 本ずつ直列に実行する (同じ $INST と wineprefix を共有するため、並列にすると結果が壊れる)。
# 前提: bash tools/flp/s1_wine_probe.sh 済み (インストール木 $RUNNER_TEMP/fl-install)、素材 fl-win64 展開済み。
# 使い方: bash tools/flp/s5_writer_matrix.sh   (出力は 1 試行 1 行。結果の要約は tools/flp/REPORT_APPENDIX_3052.md §21)
# 置換は全て oracle ローカルコピーの FLEngine_x64.dll に当たる (s2_imm_patch.py が期待バイトを検査する)。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ART="${RUNNER_TEMP:-/tmp}"
INST="$ART/fl-install"
WORKDIR="$ART/s2"

run() {
  local label="$1" patch="$2" dbg="${3:--all}" line bp=0
  line=$(S2_WINEDEBUG="$dbg" S2_PATCH="$patch" bash "$ROOT/tools/flp/s2_render_probe.sh" Autogun.flp 1 2>&1 | grep '^run=' || echo "run=? (失敗)")
  if [[ "$dbg" == "+seh" ]]; then bp=$(grep -c 'code=80000003' "$WORKDIR/s2_run_1.log" || true); fi
  echo "$label | $line | breakpoint=$bp"
}

run "B  基準 (WFBox=2・置換なし)" ""
run "X1 call 0x6721c8 (0x670fd0 直接呼出し) を nop" $'6721c8|e803eeffff|9090909090'
run "X2 0x6721c8 の 6 番目の引数 = 0" $'6721bd|0fb685a8000000|31c09090909090'
run "X3 call 0x672412 を nop" $'672412|e8b9ebffff|9090909090'
run "X4 call 0xa64b6b を nop" $'a64b6b|e860c4c0ff|9090909090'
run "X5 0x670fd0 入口を ret" $'670fd0|554156|31c0c3'
run "X6 0x674800 入口を ret" $'674800|555348|31c0c3'
run "X7 0x674e10 入口を ret" $'674e10|66c7010100|31c0c39090'
run "X8 0x670fd0 入口に int3 (SEH)" $'670fd0|554156|cc4156' "+seh"
run "X9 0x674620 入口に int3 (SEH)" $'674620|555653|cc5653' "+seh"
run "X10 0x674800 入口に int3 (SEH)" $'674800|555348|cc5348' "+seh"
run "C1 対照: 0xd1dd61 (WFBox 読取り) を nop" $'d1dd61|e8ea83e8ff|9090909090'

mv "$INST/speaker_x64.dll" "$ART/speaker_x64.dll.bak"
run "S1 speaker_x64.dll を退避" ""
mv "$ART/speaker_x64.dll.bak" "$INST/speaker_x64.dll"
