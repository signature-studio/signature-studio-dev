#!/usr/bin/env bash
# #5649 受入 2: wine64 上の FL64.exe (win64 プロセス) に gdb をアタッチし、PE の任意 VA にブレークを張れることを 1 回実測する。
# 前提: s1_wine_probe.sh と同じインストール木 ($ART/fl-install) が組立て済み (RUNNER_TEMP 配下)。
# gdb のアタッチには kernel.yama.ptrace_scope=0 が要る (runner で sudo sysctl -w kernel.yama.ptrace_scope=0)。
# 1 コマンド: bash tools/flp/s3_gdb_attach_probe.sh   (出力は $RUNNER_TEMP 配下のみ・commit 対象外)
set -uo pipefail
ART="${RUNNER_TEMP:-/tmp}"
INST="$ART/fl-install"
LOG="$ART/s3_gdb.log"
export WINEPREFIX="$ART/wineprefix" WINEARCH=win64 WINEDEBUG="${WINEDEBUG:--all},+module"
export PATH="/usr/lib/wine:$PATH"
TARGET_VA="${TARGET_VA:-0x140006eaf}"

[[ -f "$INST/FL64.exe" ]] || { echo "missing $INST/FL64.exe (s1_wine_probe.sh を先に実行)" >&2; exit 2; }

cd "$INST"
timeout 100 xvfb-run -a wine64 FL64.exe > "$LOG" 2>&1 &
XPID=$!

# wine の PE プロセス (comm が FL64.exe) の出現と、FL64.exe のロードアドレスを待つ (上限 60 回 x 1 s)
PID=""; BASE=""
for i in $(seq 1 60); do
  PID=$(pgrep -x FL64.exe | head -1)
  BASE=$(grep -oE 'mapping PE file L"[^"]*FL64\.exe" at 0x[0-9a-f]+' "$LOG" | grep -oE '0x[0-9a-f]+$' | head -1)
  [[ -n "$PID" && -n "$BASE" ]] && break
  sleep 1
done
echo "pid=$PID base=$BASE"
[[ -n "$PID" && -n "$BASE" ]] || { echo "FAIL: wine の FL64.exe プロセスまたはロードアドレスが取れない"; grep -c . "$LOG"; kill "$XPID" 2>/dev/null; exit 1; }


# ブレークは PE の VA を base からのオフセットで張る。Image base は FL64.exe の PE ヘッダから取る。
IMG=$(python3 - "$INST/FL64.exe" <<'EOF'
import struct, sys
b = open(sys.argv[1], 'rb').read(4096)
e = struct.unpack_from('<I', b, 0x3c)[0]
print(hex(struct.unpack_from('<Q', b, e + 24 + 24)[0]))
EOF
)
echo "image_base(PE)=$IMG target_va=$TARGET_VA"
OFF=$(python3 -c "print(hex(int('$TARGET_VA',16) - int('$IMG',16)))")
ADDR=$(python3 -c "print(hex(int('$BASE',16) + int('$OFF',16)))")
echo "offset=$OFF runtime_addr=$ADDR"

# gdb: アタッチ → ブレーク → 継続。ブレーク hit で停止したら backtrace を出して終了。
timeout 60 gdb -p "$PID" -batch \
  -ex "set pagination off" \
  -ex "set architecture i386:x86-64" \
  -ex "handle SIGUSR1 nostop noprint pass" \
  -ex "break *$ADDR" \
  -ex "info breakpoints" \
  -ex "continue" \
  -ex "info registers rip" \
  -ex "detach" > "$ART/s3_gdb_session.txt" 2>&1
GRC=$?
echo "gdb rc=$GRC"
grep -E 'Breakpoint [0-9]+ at|Breakpoint [0-9]+,|^rip|Cannot|Operation not permitted|ptrace|not allowed' "$ART/s3_gdb_session.txt" | head -20

kill "$PID" 2>/dev/null
wineserver -k >/dev/null 2>&1 || true
wait "$XPID" 2>/dev/null
echo "done"
