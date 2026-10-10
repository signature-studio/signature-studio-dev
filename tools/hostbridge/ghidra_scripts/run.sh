#!/usr/bin/env bash
# run.sh <project-dir> <project-name> <program> <out> <mode> items...   (既存解析済 project に対して実行; 再解析なし)
set -euo pipefail
PD="$1"; PN="$2"; PROG="$3"; shift 3
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
/opt/ghidra/ghidra_12.1.4_PUBLIC/support/analyzeHeadless "$PD" "$PN" -process "$PROG" -noanalysis -readOnly \
  -scriptPath "$HERE" -postScript Query.java "$@" 2>&1 | grep -E "ERROR|Exception|REPORT: (Process|Script)" | head -5 || true
