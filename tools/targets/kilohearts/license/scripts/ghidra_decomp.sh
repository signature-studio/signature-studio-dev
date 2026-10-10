#!/usr/bin/env bash
# CAB-59: Ghidra headless 範囲限定 decompile (HeartCore.core_64)
# usage: bash license/scripts/ghidra_decomp.sh <out.txt> <VA...>
set -e
cd "$(dirname "$0")/../.."   # tools/targets/kilohearts
CORE=work/winpkg/HeartCore.core_64
OUT=$1; shift
mkdir -p license/work/ghidra/proj license/work/tmp
JAVA_TOOL_OPTIONS="-Xmx16g -Djava.io.tmpdir=$PWD/license/work/tmp" TMPDIR=$PWD/license/work/tmp \
  /opt/ghidra/ghidra_12.1.4_PUBLIC/support/analyzeHeadless \
  license/work/ghidra/proj kh -import "$CORE" -noanalysis \
  -scriptPath scripts/ghidra -postScript DecompAt.java "$OUT" "$@" -deleteProject \
  > license/work/ghidra/$(basename "$OUT" .txt).log 2>&1
echo "done -> $OUT"
