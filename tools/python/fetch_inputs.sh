#!/usr/bin/env bash
# 解析入力 (FL 同梱 pyc/py と公開 API stubs) を work/ に配置する。FL 由来ファイルは git 管理しない (work/ は .gitignore)。
#   mac pkg ($FL_MAC_DIR) があればそこから、無ければ win64 の DATA block ($FL_WIN64_DIR/extracted) から取る。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/../shared/env.sh"   # FL_MAC_DIR / FL_WIN64_DIR (docs/REFERENCES.md §4)
W="$HERE/work"; mkdir -p "$W"
FL="$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL"
WB="$FL_WIN64_DIR/extracted"
if [ -d "$FL" ]; then
  cp "$FL/System/Tools/MCP/MCPTools.pyc" "$W/MCPTools.pyc"
  cp "$FL/Shared/Python/Lib/midi.py" "$FL/Shared/Python/Lib/utils.py" "$W/"
  cmp "$W/MCPTools.pyc" "$WB/block25159_DATA.bin" && echo "MCPTools.pyc: mac == win (100674B)"
else
  echo "mac pkg なし ($FL_MAC_DIR): win64 の DATA block から取る" >&2
  head -n1 "$WB/block24429_DATA.bin" | grep -q '^# name=FL Studio (midi) parameters' && head -n1 "$WB/block24430_DATA.bin" | grep -q '^# name=Basic functions' \
    || { echo "block24429/24430 が midi.py/utils.py ではない (FL 版が違う?)" >&2; exit 1; }
  cp "$WB/block25159_DATA.bin" "$W/MCPTools.pyc"
  cp "$WB/block24429_DATA.bin" "$W/midi.py"
  cp "$WB/block24430_DATA.bin" "$W/utils.py"
fi
[ -d "$W/fl-stubs" ] || git clone -q --depth 1 https://github.com/IL-Group/FL-Studio-API-Stubs.git "$W/fl-stubs"
