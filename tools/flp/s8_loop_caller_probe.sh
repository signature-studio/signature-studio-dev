#!/usr/bin/env bash
# #5718 (PY-5384): wine64 上の FLEngine_x64.dll で、loop 0x12d94f0 の直接呼出し元 2 関数 (0xed2ac0・0x1004a20) の entry に gdb で break を張り、命中と戻り先を記録する。
# 前提: s1_wine_probe.sh で $RUNNER_TEMP/fl-install が組立て済み。kernel.yama.ptrace_scope=0 (sudo sysctl -w kernel.yama.ptrace_scope=0)。
# 1 コマンド: WAIT=90 bash tools/flp/s8_loop_caller_probe.sh   (出力は $RUNNER_TEMP 配下のみ・commit 対象外)
# VA は REPORT の表記 (= RVA + 0x400000)。DLL の実行時 base は mapping 行から取る (ASLR で変わる)。
set -uo pipefail
ART="${RUNNER_TEMP:-/tmp}"
INST="$ART/fl-install"
LOG="$ART/s8_loop.log"
OUT="$ART/s8_gdb_session.txt"
WAIT="${WAIT:-90}"
export WINEPREFIX="$ART/wineprefix" WINEARCH=win64 WINEDEBUG="${WINEDEBUG:--all},+module"
export PATH="/usr/lib/wine:$PATH"

[[ -f "$INST/FL64.exe" ]] || { echo "missing $INST/FL64.exe (s1_wine_probe.sh を先に実行)" >&2; exit 2; }

cd "$INST"
timeout $((WAIT + 150)) xvfb-run -a wine64 FL64.exe > "$LOG" 2>&1 &
XPID=$!

PID=""; BASE=""
for i in $(seq 1 90); do
  PID=$(pgrep -x FL64.exe | head -1)
  BASE=$(grep -oE 'mapping PE file L"[^"]*FLEngine_x64\.dll" at 0x[0-9a-f]+' "$LOG" | grep -oE '0x[0-9a-f]+$' | head -1)
  [[ -n "$PID" && -n "$BASE" ]] && break
  sleep 1
done
echo "pid=$PID dll_base=$BASE"
[[ -n "$PID" && -n "$BASE" ]] || { echo "FAIL: FL64.exe プロセスまたは FLEngine_x64.dll のロードアドレスが取れない"; kill "$XPID" 2>/dev/null; exit 1; }

CALLER_A_RUN=$(python3 -c "print(hex(int('$BASE',16) + 0xed2ac0 - 0x400000))")
CALLER_B_RUN=$(python3 -c "print(hex(int('$BASE',16) + 0x1004a20 - 0x400000))")
echo "callerA_runtime=$CALLER_A_RUN callerB_runtime=$CALLER_B_RUN"

cat > "$ART/s8_gdb_cmds.txt" <<EOF
set pagination off
set architecture i386:x86-64
handle SIGUSR1 nostop noprint pass
break *$CALLER_A_RUN
commands 1
silent
printf "HIT callerA(ed2ac0) rcx=%lx rdx=%lx r8=%lx r9=%lx ret=%lx\n", \$rcx, \$rdx, \$r8, \$r9, *(unsigned long*)\$rsp
continue
end
break *$CALLER_B_RUN
commands 2
silent
printf "HIT callerB(1004a20) rcx=%lx rdx=%lx r8=%lx r9=%lx ret=%lx\n", \$rcx, \$rdx, \$r8, \$r9, *(unsigned long*)\$rsp
continue
end
continue
detach
EOF

date +%T > "$ART/s8_attach_time.txt"
timeout "$WAIT" gdb -p "$PID" -batch -x "$ART/s8_gdb_cmds.txt" > "$OUT" 2>&1
GRC=$?
echo "gdb rc=$GRC (124 = $WAIT s 内に終了せず)"
grep -E 'Breakpoint [0-9]+ at|HIT |Cannot|not allowed|Operation not permitted|ptrace' "$OUT" | head -40
echo "hits callerA=$(grep -c 'HIT callerA' "$OUT") callerB=$(grep -c 'HIT callerB' "$OUT")"

kill "$PID" 2>/dev/null
wineserver -k >/dev/null 2>&1 || true
wait "$XPID" 2>/dev/null
echo "done"
