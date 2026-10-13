#!/usr/bin/env bash
# gq.sh <out> <mode> items...   — 解析済み Fruity Wrapper project (h10/work/ghidra, program fw_a.dll) への読取クエリ.
# mode / items は tools/hostbridge/ghidra_scripts/Query.java に同じ (decomp / disasm / xrefstr / refsto / callees / grepins / decompall).
# env: GHIDRA_HOME (既定 /opt/ghidra/ghidra_12.1.4_PUBLIC → $RUNNER_TEMP/ghidra/...)・JAVA_HOME (Ghidra 12 は JDK 21 以上)
set -euo pipefail
H10="$(cd -- "$(dirname -- "$0")/.." && pwd)"
HB="$(cd -- "$H10/.." && pwd)"
for g in "${GHIDRA_HOME:-}" /opt/ghidra/ghidra_12.1.4_PUBLIC "${RUNNER_TEMP:-/nonexistent}/ghidra/ghidra_12.1.4_PUBLIC"; do
  [ -n "$g" ] && [ -x "$g/support/analyzeHeadless" ] && { GHIDRA_HOME="$g"; break; }
done
: "${GHIDRA_HOME:?Ghidra 12.1.4 not found (set GHIDRA_HOME)}"
if [ -z "${JAVA_HOME:-}" ] && [ -d /usr/lib/jvm/temurin-21-jdk-amd64 ]; then export JAVA_HOME=/usr/lib/jvm/temurin-21-jdk-amd64; fi
[ -n "${JAVA_HOME:-}" ] && export PATH="$JAVA_HOME/bin:$PATH"
PROG="${GQ_PROGRAM:-fw_a.dll}"; PN="${GQ_PROJECT:-fw}"
"$GHIDRA_HOME/support/analyzeHeadless" "$H10/work/ghidra" "$PN" -process "$PROG" -noanalysis -readOnly \
  -scriptPath "$HB/ghidra_scripts" -postScript Query.java "$@" > "$H10/work/ghidra/last_query.log" 2>&1 || {
  echo "gq.sh: analyzeHeadless failed; tail of log:" >&2; tail -20 "$H10/work/ghidra/last_query.log" >&2; exit 1; }
