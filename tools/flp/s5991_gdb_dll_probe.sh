#!/usr/bin/env bash
# #5991: FLEngine_x64.dll の絶対 VA (image base 0x400000) に gdb でブレークを張り、命中を観測する (FL64.exe 起動後にアタッチ)。
# 前提: s1_wine_probe.sh で $RUNNER_TEMP/fl-install を組立て済み・kernel.yama.ptrace_scope=0。使い方: WAIT_SEC=60 bash tools/flp/s5991_gdb_dll_probe.sh 0xd82dc6 0x1330c70
set -uo pipefail
ART="${RUNNER_TEMP:-/tmp}"
INST="$ART/fl-install"
LOG="$ART/s5991_gdb_run.log"
SESS="$ART/s5991_gdb_session.txt"
export WINEPREFIX="$ART/wineprefix" WINEARCH=win64 WINEDEBUG="-all,+module"
export PATH="/usr/lib/wine:$PATH"
WAIT_SEC="${WAIT_SEC:-60}"
VAS=("$@")
[[ ${#VAS[@]} -gt 0 ]] || VAS=(0xd82dc6 0x1330c70)

cd "$INST"
timeout $((WAIT_SEC + 90)) xvfb-run -a wine64 FL64.exe > "$LOG" 2>&1 &
XPID=$!

PID=""; DLLBASE=""
for i in $(seq 1 90); do
  PID=$(pgrep -x FL64.exe | head -1)
  DLLBASE=$(grep -oE 'mapping PE file L"[^"]*FLEngine_x64\.dll" at 0x[0-9a-f]+' "$LOG" | grep -oE '0x[0-9a-f]+$' | head -1)
  [[ -n "$PID" && -n "$DLLBASE" ]] && break
  sleep 1
done
echo "pid=$PID dll_base=$DLLBASE"
if [[ -z "$PID" || -z "$DLLBASE" ]]; then
  echo "FAIL: FL64.exe プロセスまたは FLEngine_x64.dll のロードが取れない"
  grep -c . "$LOG"
  grep -i 'FLEngine' "$LOG" | head -5
  kill "$XPID" 2>/dev/null
  exit 1
fi

ARGS=()
for va in "${VAS[@]}"; do
  rt=$(python3 -c "print(hex(int('$DLLBASE',16) + (int('$va',16) - 0x400000)))")
  echo "va=$va runtime=$rt"
  ARGS+=(-ex "break *$rt")
done

timeout "$WAIT_SEC" gdb -p "$PID" -batch \
  -ex "set pagination off" \
  -ex "set architecture i386:x86-64" \
  -ex "handle SIGUSR1 nostop noprint pass" \
  "${ARGS[@]}" \
  -ex "info breakpoints" \
  -ex "continue" \
  -ex "info registers rip" \
  -ex "bt 8" \
  -ex "detach" > "$SESS" 2>&1
GRC=$?
echo "gdb rc=$GRC (124 = $WAIT_SEC s 内に命中せず)"
grep -E 'Breakpoint [0-9]+ at|Breakpoint [0-9]+,|^rip|Cannot|not permitted|ptrace' "$SESS" | head -20

kill "$PID" 2>/dev/null
wineserver -k >/dev/null 2>&1 || true
wait "$XPID" 2>/dev/null
echo done
