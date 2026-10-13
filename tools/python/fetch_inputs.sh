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
if [ -f "$FL/System/Tools/MCP/MCPTools.pyc" ]; then
  cp "$FL/System/Tools/MCP/MCPTools.pyc" "$W/MCPTools.pyc"
  cp "$FL/Shared/Python/Lib/midi.py" "$FL/Shared/Python/Lib/utils.py" "$W/"
  cmp "$W/MCPTools.pyc" "$WB/block25159_DATA.bin" && echo "MCPTools.pyc: mac == win (100674B)"
  # PY-6 (#76): 同梱 device script (MIDI scripting)。tests/midi_bundled_device.mjs の入力。パスは scripts_inventory.json のキー (FL/ からの相対) 由来
  DEV="$FL/System/Hardware specific/Forward CCs to current plugin Port 10/device_Forward CCs to current plugin Port 10.py"
  if [ -f "$DEV" ]; then cp "$DEV" "$W/"; else echo "WARN: device script not found: $DEV" >&2; fi
else
  echo "mac pkg なし、または MCPTools.pyc 無し ($FL_MAC_DIR): win64 の DATA block から取る" >&2
  head -n1 "$WB/block24429_DATA.bin" | grep -q '^# name=FL Studio (midi) parameters' && head -n1 "$WB/block24430_DATA.bin" | grep -q '^# name=Basic functions' \
    || { echo "block24429/24430 が midi.py/utils.py ではない (FL 版が違う?)" >&2; exit 1; }
  cp "$WB/block25159_DATA.bin" "$W/MCPTools.pyc"
  cp "$WB/block24429_DATA.bin" "$W/midi.py"
  cp "$WB/block24430_DATA.bin" "$W/utils.py"
  # PY-6 (#76): 同梱 device script は win64 の block24618 (FL 26.1.7.5653 で実測)。先頭ヘッダで同定する
  head -n1 "$WB/block24618_DATA.bin" | tr -d '\r' | grep -qx '# name=Forward CCs to current plugin Port 10' \
    || { echo "block24618 が device script 'Forward CCs to current plugin Port 10' ではない (FL 版が違う?)" >&2; exit 1; }
  cp "$WB/block24618_DATA.bin" "$W/device_Forward CCs to current plugin Port 10.py"
fi
[ -d "$W/fl-stubs" ] || git clone -q --depth 1 https://github.com/IL-Group/FL-Studio-API-Stubs.git "$W/fl-stubs"
