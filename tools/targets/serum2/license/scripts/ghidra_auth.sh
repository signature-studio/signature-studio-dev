#!/bin/bash
# CAB-71: Ghidra light decompile of auth/demo-related targets into license/work/.
# Reuses ghidra/SerumLight.java (import + .pdata functions + decompile listed targets).
set -e
HERE="$(cd "$(dirname "$0")/../.." && pwd)"        # tools/targets/serum2
export MAXMEM=${MAXMEM:-24G}
# /tmp (tmpfs 3.7G, 共有) の圧迫で EDQUOT が出るため tmp を担当 dir 配下へ
mkdir -p "$HERE/license/work/tmp"
export TMPDIR="$HERE/license/work/tmp"
export JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=$HERE/license/work/tmp"
rm -rf "$HERE/license/work/ghidraProjA"; mkdir -p "$HERE/license/work/ghidraProjA" "$HERE/license/work/ghidra_auth"
/opt/ghidra/ghidra_12.1.4_PUBLIC/support/analyzeHeadless "$HERE/license/work/ghidraProjA" serum2A \
  -import "$HERE/work/Serum2_win64.vst3" -noanalysis \
  -scriptPath "$HERE/ghidra" -postScript SerumLight.java "$HERE/license/work/ghidra_auth" "$HERE/license/targets_auth.txt" \
  > "$HERE/license/work/ghidra_auth/ghidra.log" 2>&1
echo "exit=$?" > "$HERE/license/work/ghidra_auth/DONE"
grep -E "PDATA_FUNCS|DONE|TOTAL" "$HERE/license/work/ghidra_auth/ghidra.log" || true
