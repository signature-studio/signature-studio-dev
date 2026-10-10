#!/bin/bash
# Light Ghidra pass (no auto-analysis): functions from .pdata + decompile of auth/network-related targets. ~minutes.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
export MAXMEM=${MAXMEM:-16G}
rm -rf "$HERE/work/ghidraProjL"; mkdir -p "$HERE/work/ghidraProjL" "$HERE/work/ghidra_light"
/opt/ghidra/ghidra_12.1.4_PUBLIC/support/analyzeHeadless "$HERE/work/ghidraProjL" serum2L \
  -import "$HERE/work/Serum2_win64.vst3" -noanalysis \
  -scriptPath "$HERE/ghidra" -postScript SerumLight.java "$HERE/work/ghidra_light" "$HERE/ghidra/targets_auth.txt" \
  > "$HERE/work/ghidra_light/ghidra.log" 2>&1
echo "exit=$?" > "$HERE/work/ghidra_light/DONE"
