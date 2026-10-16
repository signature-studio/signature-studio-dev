#!/usr/bin/env bash
# #5614 受入 1 (cfg の型・所属 VMT): 0x737560 の命中時に this (rcx) 周辺のメモリをダンプする。
# 前提: s1_wine_probe.sh でインストール木 ($RUNNER_TEMP/fl-install) が組立て済み。
# kernel.yama.ptrace_scope=0 が要る。出力は $RUNNER_TEMP 配下のみ (commit 対象外)。
set -uo pipefail
ART="${RUNNER_TEMP:-/tmp}"
HERE="$(cd "$(dirname "$0")" && pwd)"
INST="$ART/fl-install"
LOG="$ART/s11_gdb.log"
SESSION="$ART/s11_gdb_session.txt"
export WINEPREFIX="$ART/wineprefix" WINEARCH=win64 WINEDEBUG="${WINEDEBUG:--all},+module"
export PATH="/usr/lib/wine:$PATH"
DLL_VA="${DLL_VA:-0x737560}"
WAIT_SEC="${WAIT_SEC:-200}"

[[ -f "$INST/FL64.exe" ]] || { echo "missing $INST/FL64.exe (s1_wine_probe.sh を先に実行)" >&2; exit 2; }

cd "$INST"
timeout $((WAIT_SEC + 60)) xvfb-run -a wine64 FL64.exe > "$LOG" 2>&1 &
XPID=$!

PID=""; BASE=""
for i in $(seq 1 60); do
  PID=$(pgrep -x FL64.exe | head -1)
  BASE=$(grep -oE 'mapping PE file L"[^"]*FLEngine_x64\.dll" at 0x[0-9a-f]+' "$LOG" | grep -oE '0x[0-9a-f]+$' | head -1)
  [[ -n "$PID" && -n "$BASE" ]] && break
  sleep 1
done
echo "pid=$PID flengine_base=$BASE"
[[ -n "$PID" && -n "$BASE" ]] || { echo "FAIL: FL64.exe プロセスまたは FLEngine_x64.dll のロードアドレスが取れない"; kill "$XPID" 2>/dev/null; exit 1; }

IMG=0x400000
OFF=$(python3 -c "print(hex(int('$DLL_VA',16) - int('$IMG',16)))")
ADDR=$(python3 -c "print(hex(int('$BASE',16) + int('$OFF',16)))")
echo "offset=$OFF runtime_addr=$ADDR"

SCRIPT="$ART/s11_setter_obj.gdb"
sed "s/__ADDR__/$ADDR/" "$HERE/s11_setter_obj.gdb" > "$SCRIPT"
timeout "$WAIT_SEC" gdb -p "$PID" -batch -x "$SCRIPT" > "$SESSION" 2>&1
GRC=$?
echo "gdb rc=$GRC"
grep -E '^HIT |Breakpoint [0-9]+ at|Cannot|not allowed|ptrace' "$SESSION" | head -20
echo "hits=$(grep -c '^HIT ' "$SESSION")"

kill "$PID" 2>/dev/null
wineserver -k >/dev/null 2>&1 || true
wait "$XPID" 2>/dev/null
echo "done"
