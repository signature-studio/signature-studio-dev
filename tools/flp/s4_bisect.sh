#!/usr/bin/env bash
# #3052 §19: FLEngine_x64.dll の関数先頭 4 バイトを `xor eax,eax; ret` (+nop) に置換して 1 回 /R 書き出しし、
# WFBox の RegQueryValueExW の件数と WAV 形式を見る (WFBox の読取り経路の二分探索)。
# 使い方: bash tools/flp/s4_bisect.sh <VA hex | none> [WFBox の値 (既定 1)]
#   VA を none にすると置換しない (基準)。前提: s1_wine_probe.sh 済み・素材展開済み ($RUNNER_TEMP/fl-win64)。
# 出力は $RUNNER_TEMP 配下のみ。結果の要約は tools/flp/REPORT_APPENDIX_3052.md §19。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ART="${RUNNER_TEMP:-/tmp}"
VA="${1:?usage: s4_bisect.sh <VA hex | none> [WFBox value]}"
WFB="${2:-1}"
DLL="$ART/fl-win64/extracted/block00031_PE.bin"
PATCH=""
if [[ "$VA" != none ]]; then
  EXP=$(python3 - "$DLL" "$VA" <<'EOF'
import sys
import pefile
pe = pefile.PE(sys.argv[1], fast_load=True)
off = pe.get_offset_from_rva(int(sys.argv[2], 16) - pe.OPTIONAL_HEADER.ImageBase)
print(open(sys.argv[1], "rb").read()[off:off + 4].hex())
EOF
)
  PATCH="${VA}|${EXP}|31c0c390"
fi
export WINEDLLOVERRIDES="mscoree,mshtml="
S2_TRACE_REG=1 S2_WFBOX="$WFB" S2_PATCH="$PATCH" bash "$ROOT/tools/flp/s2_render_probe.sh" Autogun.flp 1
echo "VA=${VA} WFBox_RegQuery=$(grep -c 'RegQueryValueExW.*L"WFBox"' "$ART/s2/s2_run_1.log" || true)"
