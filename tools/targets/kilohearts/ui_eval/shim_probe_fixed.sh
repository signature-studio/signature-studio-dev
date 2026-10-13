#!/usr/bin/env bash
# KH-7 (#59): G1 の修正案 (g1_shim_fix.patch) を tools/gui の作業コピーに当て、同じプローブを流す。tools/gui 本体は変更しない。
# 期待: 修正前 exit 2 (5/7 不一致) → 修正後 exit 0 (7/7 一致)。修正が当たらない/効かないときは exit 1 または 2。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
WORK="${KH_UI_WORK:-$HERE/work}"; mkdir -p "$WORK"
rm -rf "$WORK/gui_fixed"; mkdir -p "$WORK/gui_fixed"
cp -r "$HERE/../../../gui/src" "$HERE/../../../gui/include" "$WORK/gui_fixed/"
( cd "$WORK/gui_fixed" && patch -p1 --dry-run < "$HERE/g1_shim_fix.patch" >/dev/null && patch -p1 < "$HERE/g1_shim_fix.patch" )
KH_GUI_DIR="$WORK/gui_fixed" bash "$HERE/shim_probe.sh"
