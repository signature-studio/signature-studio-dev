#!/usr/bin/env bash
# win freetype.dll にあって FreeType 2.7 再ビルドに無い export 17 本 (data/freetype_export_diff.json) が、
# upstream のどの tag の src/ include/ に存在するかを調べる (version 帯の絞り込み)。
# usage: bash oss/freetype/win_version_probe.sh   (要 network: freedesktop gitlab の bare clone を work/ に作る)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
G="$ROOT/work/src/freetype.git"
[ -d "$G" ] || git clone -q --bare --filter=blob:none https://gitlab.freedesktop.org/freetype/freetype.git "$G"
mapfile -t NAMES < <(python3 -c "import json,sys; [print(n) for n in json.load(open('$ROOT/data/freetype_export_diff.json'))['win freetype.dll']['missing']]")
echo "[probe] names=${#NAMES[@]}"
for t in VER-2-3-12 VER-2-4-0 VER-2-4-12 VER-2-5-0 VER-2-5-5 VER-2-6 VER-2-7 VER-2-13-0; do
  n=0; for s in "${NAMES[@]}"; do git -C "$G" grep -q -w "$s" "$t" -- src include 2>/dev/null && n=$((n+1)) || true; done
  echo "[probe] $t: $n/${#NAMES[@]} names present in src/ include/"
done
