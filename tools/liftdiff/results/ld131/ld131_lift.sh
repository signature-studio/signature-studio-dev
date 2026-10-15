#!/usr/bin/env bash
# LD-131 (#2801): liftdiff の vm0/u16 対象 6 関数 (1801ab1d0・1ab258・1c5e84・1c621c・1c682c・1c69cc) を
# x64c (tools/ott/lift/x64c.py) で lift し、命令単位の VA 表 (insn_map_6fn.tsv) を作る。
#   env: LD131_OUT (既定 ${RUNNER_TEMP:-/home/runner/work/_temp/opencode}/ld131 。生成物の置き場。repo の work/ は使わない)
#        前提: 素材 plugins-ott・analysis-ott-binaries が展開済み (PLUGINS_DIR 配下の ott/binaries/OTT_vst2_win64.dll)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
source "$REPO/tools/shared/env.sh"
OUT="${LD131_OUT:-${RUNNER_TEMP:-/home/runner/work/_temp/opencode}/ld131}"
DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
[ -f "$DLL" ] || { echo "ld131_lift: DLL が無い: $DLL (素材 plugins-ott / analysis-ott-binaries を確認)" >&2; exit 2; }
mkdir -p "$OUT/lift"
python3 -c "import json,sys; json.dump({'roots':[int(x,16) for x in sys.argv[1:]],'calltgt':[]}, open('$OUT/entries6.json','w'))" \
  1801ab1d0 1801ab258 1801c5e84 1801c621c 1801c682c 1801c69cc
python3 "$REPO/tools/ott/lift/x64c.py" --pe "$DLL" --entries "$OUT/entries6.json" --out "$OUT/lift" --closure 7
python3 "$HERE/insn_va_map.py" "$OUT/lift/ott_lifted.c" --out "$HERE/insn_map_6fn.tsv"
