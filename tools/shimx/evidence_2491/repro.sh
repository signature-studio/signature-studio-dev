#!/usr/bin/env bash
# SHX-T9i (#2491) の再現: clean rebuild → unit 1〜23 の probe → 保存済み出力と diff (差分 0 行が期待値)。
# 前提: tools/m11/work/ (work-m11 の展開) がある。
set -euo pipefail
cd "$(dirname "$0")/../../.."
rm -rf tools/m11/work/shimx_link
bash tools/m11/shimx_link/build.sh --trace --soft --fix
SHIMX_TRACE=1 node tools/m11/shimx_link/probe_unit23.mjs tools/m11/work/shimx_link/m11_sx_trace_soft_fix.cjs > tools/m11/work/shimx_link/probe_u23.txt 2>&1
diff tools/shimx/evidence_2491/probe_u23_shimx_site.txt tools/m11/work/shimx_link/probe_u23.txt && echo "probe: SAME"
