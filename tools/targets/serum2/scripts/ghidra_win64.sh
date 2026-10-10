#!/bin/bash
# Ghidra headless full analysis + SerumSurvey on the win64 VST3. Output -> work/ghidra_out/
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
export MAXMEM=${MAXMEM:-32G}
rm -rf "$HERE/work/ghidraProj"; mkdir -p "$HERE/work/ghidraProj" "$HERE/work/ghidra_out"
/opt/ghidra/ghidra_12.1.4_PUBLIC/support/analyzeHeadless "$HERE/work/ghidraProj" serum2 \
  -import "$HERE/work/Serum2_win64.vst3" -analysisTimeoutPerFile 5400 \
  -scriptPath "$HERE/ghidra" -postScript SerumSurvey.java "$HERE/work/ghidra_out" \
  > "$HERE/work/ghidra_out/ghidra.log" 2>&1
echo "exit=$?" > "$HERE/work/ghidra_out/DONE"
