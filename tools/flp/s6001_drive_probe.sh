#!/usr/bin/env bash
# #6001: FL64.exe を起動し、X 上のウィンドウを列挙・スクリーンショットして入力注入 (xdotool) の届き方を実測する。
# 前提: s1_wine_probe.sh で $RUNNER_TEMP/fl-install を組立て済み・kernel.yama.ptrace_scope=0。
# 使い方: WAIT_SEC=90 bash tools/flp/s6001_drive_probe.sh
# 出力は $RUNNER_TEMP 配下のみ (commit 対象外)。
set -uo pipefail
ART="${RUNNER_TEMP:-/tmp}"
INST="$ART/fl-install"
LOG="$ART/s6001_drive.log"
OUT="$ART/s6001_shots"
export WINEPREFIX="$ART/wineprefix" WINEARCH=win64 WINEDEBUG="${WINEDEBUG:--all}"
export PATH="/usr/lib/wine:$PATH"
WAIT_SEC="${WAIT_SEC:-90}"
mkdir -p "$OUT"

[[ -f "$INST/FL64.exe" ]] || { echo "missing $INST/FL64.exe (s1_wine_probe.sh を先に実行)" >&2; exit 2; }

cd "$INST"
export DISPLAY_NUM=99
xvfb-run -a -s "-screen 0 1920x1080x24" bash -c "
  wine64 FL64.exe > '$LOG' 2>&1 &
  WPID=\$!
  sleep $WAIT_SEC
  export DISPLAY=\$DISPLAY
  xdotool mousemove 1035 560 click 1
  sleep 3
  xwd -root -silent | convert xwd:- '$OUT/after_nothanks.png' 2>/dev/null
  xdotool mousemove 1383 268 click 1
  sleep 3
  xwd -root -silent | convert xwd:- '$OUT/after_close.png' 2>/dev/null
  xdotool search --name '.' 2>/dev/null | head -50 > '$OUT/windows.txt'
  for w in \$(xdotool search --name 'FL Studio' 2>/dev/null | head -3); do
    xdotool getwindowname \$w > '$OUT/name_'\$w.txt 2>/dev/null
    xwd -root -silent | convert xwd:- '$OUT/root.png' 2>/dev/null
    break
  done
  xwd -root -silent | convert xwd:- '$OUT/root.png' 2>/dev/null
  echo \"wine_pid=\$WPID\" > '$OUT/pid.txt'
  kill \$WPID 2>/dev/null
  wineserver -k >/dev/null 2>&1 || true
" > "$ART/s6001_xvfb.out" 2>&1
echo "rc=$?"
ls -la "$OUT"
grep -cE '.' "$OUT/windows.txt" 2>/dev/null || true
echo done
