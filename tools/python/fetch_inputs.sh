#!/usr/bin/env bash
# 解析入力 (FL 同梱 pyc/py と公開 API stubs) を work/ に配置する。FL 由来ファイルは git 管理しない (work/ は .gitignore)。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
W="$HERE/work"; mkdir -p "$W"
FL="/home/ubuntu/work/analysis/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL"
cp "$FL/System/Tools/MCP/MCPTools.pyc" "$W/MCPTools.pyc"
cp "$FL/Shared/Python/Lib/midi.py" "$FL/Shared/Python/Lib/utils.py" "$W/"
[ -d "$W/fl-stubs" ] || git clone -q --depth 1 https://github.com/IL-Group/FL-Studio-API-Stubs.git "$W/fl-stubs"
cmp "$W/MCPTools.pyc" /home/ubuntu/work/analysis/win64/extracted/block25159_DATA.bin && echo "MCPTools.pyc: mac == win (100674B)"
