#!/usr/bin/env bash
# #5650 (PY-5377): wine64 上の FLEngine_x64.dll の select 後処理 0x12e3a60 と、その呼出し先 0x128f9e0 に gdb で break を張り、
# 命中と引数 (rdx = id, r8 = 3 番目) と戻り先を記録する。VA は REPORT の表記 (= RVA + 0x400000)。
# 前提: s1_wine_probe.sh で $RUNNER_TEMP/fl-install が組立て済み。kernel.yama.ptrace_scope=0。
# 1 コマンド: bash tools/flp/s12_select_post_probe.sh   (出力は $RUNNER_TEMP 配下のみ・commit 対象外)
set -uo pipefail
ART="${RUNNER_TEMP:-/tmp}"
INST="$ART/fl-install"
LOG="$ART/s12_select.log"
OUT="$ART/s12_gdb_session.txt"
WAIT="${WAIT:-120}"
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

POST_RUN=$(python3 -c "print(hex(int('$BASE',16) + 0x12e3a60 - 0x400000))")
ENT_RUN=$(python3 -c "print(hex(int('$BASE',16) + 0x128f9e0 - 0x400000))")
echo "post_runtime=$POST_RUN ent_runtime=$ENT_RUN"

cat > "$ART/s12_gdb_cmds.txt" <<EOF
set pagination off
set architecture i386:x86-64
handle SIGUSR1 nostop noprint pass
break *$POST_RUN
commands 1
silent
printf "HIT post rcx=%lx rdx=%lx r8=%lx r9=%lx ret=%lx\n", \$rcx, \$rdx, \$r8, \$r9, *(unsigned long*)\$rsp
continue
end
break *$ENT_RUN
commands 2
silent
printf "HIT ent rcx=%lx rdx=%lx r8=%lx r9=%lx ret=%lx\n", \$rcx, \$rdx, \$r8, \$r9, *(unsigned long*)\$rsp
continue
end
continue
detach
EOF

timeout "$WAIT" gdb -p "$PID" -batch -x "$ART/s12_gdb_cmds.txt" > "$OUT" 2>&1
GRC=$?
echo "gdb rc=$GRC (124 = $WAIT s 内に終了せず)"
grep -E 'Breakpoint [0-9]+ at|HIT |Cannot|not allowed|Operation not permitted|ptrace' "$OUT" | head -40
echo "hits post=$(grep -c 'HIT post' "$OUT") ent=$(grep -c 'HIT ent' "$OUT")"

kill "$PID" 2>/dev/null
wineserver -k >/dev/null 2>&1 || true
wait "$XPID" 2>/dev/null
echo "done"
