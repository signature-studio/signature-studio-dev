#!/usr/bin/env bash
# #5718 (PY-5384): wine64 上の FLEngine_x64.dll の pred (VA 0x12d8d30) と loop 入口 (VA 0x12d94f0) に gdb で break を張り、命中を記録する。
# 前提: s1_wine_probe.sh で $RUNNER_TEMP/fl-install が組立て済み。kernel.yama.ptrace_scope=0 (sudo sysctl -w kernel.yama.ptrace_scope=0)。
# 1 コマンド: bash tools/flp/s6_pred_hit_probe.sh   (出力は $RUNNER_TEMP 配下のみ・commit 対象外)
# VA は REPORT の表記 (= RVA + 0x400000)。DLL の実行時 base は mapping 行から取る (ASLR で変わる)。
set -uo pipefail
ART="${RUNNER_TEMP:-/tmp}"
INST="$ART/fl-install"
LOG="$ART/s6_pred.log"
OUT="$ART/s6_gdb_session.txt"
WAIT="${WAIT:-180}"
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

PRED_RUN=$(python3 -c "print(hex(int('$BASE',16) + 0x12d8d30 - 0x400000))")
LOOP_RUN=$(python3 -c "print(hex(int('$BASE',16) + 0x12d94f0 - 0x400000))")
echo "pred_runtime=$PRED_RUN loop_runtime=$LOOP_RUN"

cat > "$ART/s6_gdb_cmds.txt" <<EOF
set pagination off
set architecture i386:x86-64
handle SIGUSR1 nostop noprint pass
break *$PRED_RUN
commands 1
silent
printf "HIT pred rcx=%lx rdx=%lx r8=%lx r9=%lx ret=%lx\n", \$rcx, \$rdx, \$r8, \$r9, *(unsigned long*)\$rsp
continue
end
break *$LOOP_RUN
commands 2
silent
printf "HIT loop rcx=%lx rdx=%lx r8=%lx r9=%lx\n", \$rcx, \$rdx, \$r8, \$r9
continue
end
continue
detach
EOF

date +%T > "$ART/s6_attach_time.txt"
timeout "$WAIT" gdb -p "$PID" -batch -x "$ART/s6_gdb_cmds.txt" > "$OUT" 2>&1
GRC=$?
echo "gdb rc=$GRC (124 = $WAIT s 内に終了せず)"
grep -E 'Breakpoint [0-9]+ at|HIT |Cannot|not allowed|Operation not permitted|ptrace' "$OUT" | head -40
echo "hits pred=$(grep -c 'HIT pred' "$OUT") loop=$(grep -c 'HIT loop' "$OUT")"

kill "$PID" 2>/dev/null
wineserver -k >/dev/null 2>&1 || true
wait "$XPID" 2>/dev/null
echo "done"
