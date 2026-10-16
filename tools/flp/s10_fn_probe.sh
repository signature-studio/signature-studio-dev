#!/usr/bin/env bash
# #5601 (L-25): FLEngine_x64.dll の poll 候補 0x604ea0 (GlobalFindAtomW 呼出し元) と 0x817aa0 (FindAtomW 呼出し元) の entry に gdb で break を張り、命中を記録する。s8 の派生。
# 前提: s1_wine_probe.sh で $RUNNER_TEMP/fl-install が組立て済み。kernel.yama.ptrace_scope=0 (sudo sysctl -w kernel.yama.ptrace_scope=0)。
# 1 コマンド: WAIT=90 bash tools/flp/s8_loop_caller_probe.sh   (出力は $RUNNER_TEMP 配下のみ・commit 対象外)
# VA は REPORT の表記 (= RVA + 0x400000)。DLL の実行時 base は mapping 行から取る (ASLR で変わる)。
# 注意: timeout で gdb が落ちた場合、int3 (breakpoint) は外れないまま終わる。後で再利用するなら、終了前に外す処理を入れること。
set -uo pipefail
ART="${RUNNER_TEMP:-/tmp}"
INST="$ART/fl-install"
LOG="$ART/s10_fn.log"
OUT="$ART/s10_gdb_session.txt"
WAIT="${WAIT:-90}"
export WINEPREFIX="$ART/wineprefix" WINEARCH=win64 WINEDEBUG="${WINEDEBUG:--all},+module"
export PATH="/usr/lib/wine:$PATH"

[[ -f "$INST/FL64.exe" ]] || { echo "missing $INST/FL64.exe (s1_wine_probe.sh を先に実行)" >&2; exit 2; }

cd "$INST" || exit 2
timeout $((WAIT + 150)) xvfb-run -a wine64 FL64.exe > "$LOG" 2>&1 &
XPID=$!

PID=""; BASE=""
for _ in $(seq 1 90); do
  PID=$(pgrep -x FL64.exe | head -1)
  BASE=$(grep -oE 'mapping PE file L"[^"]*FLEngine_x64\.dll" at 0x[0-9a-f]+' "$LOG" | grep -oE '0x[0-9a-f]+$' | head -1)
  [[ -n "$PID" && -n "$BASE" ]] && break
  sleep 1
done
echo "pid=$PID dll_base=$BASE"
[[ -n "$PID" && -n "$BASE" ]] || { echo "FAIL: FL64.exe プロセスまたは FLEngine_x64.dll のロードアドレスが取れない"; kill "$XPID" 2>/dev/null; exit 1; }

F_A_RUN=$(python3 -c "print(hex(int('$BASE',16) + 0x604ea0 - 0x400000))")
F_B_RUN=$(python3 -c "print(hex(int('$BASE',16) + 0x817aa0 - 0x400000))")
echo "callerA_runtime=$F_A_RUN callerB_runtime=$F_B_RUN"

cat > "$ART/s10_gdb_cmds.txt" <<EOF
set pagination off
set architecture i386:x86-64
handle SIGUSR1 nostop noprint pass
break *$F_A_RUN
commands 1
silent
printf "HIT fn604ea0 rcx=%lx rdx=%lx r8=%lx r9=%lx ret=%lx\n", \$rcx, \$rdx, \$r8, \$r9, *(unsigned long*)\$rsp
continue
end
break *$F_B_RUN
commands 2
silent
printf "HIT fn817aa0 rcx=%lx rdx=%lx r8=%lx r9=%lx ret=%lx\n", \$rcx, \$rdx, \$r8, \$r9, *(unsigned long*)\$rsp
continue
end
continue
detach
EOF

date +%T > "$ART/s10_attach_time.txt"
timeout "$WAIT" gdb -p "$PID" -batch -x "$ART/s10_gdb_cmds.txt" > "$OUT" 2>&1
GRC=$?
echo "gdb rc=$GRC (124 = $WAIT s 内に終了せず)"
grep -E 'Breakpoint [0-9]+ at|HIT |Cannot|not allowed|Operation not permitted|ptrace' "$OUT" | head -40
echo "hits callerA=$(grep -c 'HIT callerA' "$OUT") callerB=$(grep -c 'HIT callerB' "$OUT")"

kill "$PID" 2>/dev/null
wineserver -k >/dev/null 2>&1 || true
wait "$XPID" 2>/dev/null
echo "done"
