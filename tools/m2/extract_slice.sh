#!/usr/bin/env bash
# M2-1: mac FLEEngine universal2 から x86_64 slice を抽出し work/ へ正本複製する。
#
#   bash tools/m2/extract_slice.sh
#
# - lipo を使わない (環境に無い前提)。universal2 (FAT Mach-O) のヘッダ解析と
#   slice 切出しは extract_slice.py (python struct) が行う。
# - 成果物: tools/m2/work/FLEngine_x86_64.dylib (x86_64 slice) + slice_inventory.json
# - analysis/ は読み取り専用として扱うため、切出し先は work/ 配下に限定する。
#
# 成功: exit 0 / 失敗: stderr + 非ゼロ終了

set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
WORK="$HERE/work"

# mac 版 FLEngine universal2 の実パス (analysis/mac/REPORT.md §2 より変更なし)。
source "$HERE/../shared/env.sh"
FAT_INPUT="${FAT_INPUT:-$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Libs/FLEngine_x64.dylib}"

[ -f "$FAT_INPUT" ] || { echo "[M2] FAIL: 入力 universal2 が見つかりません: $FAT_INPUT" >&2; exit 1; }

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null || { echo "[M2] FAIL: python3 が見つかりません" >&2; exit 1; }

"$PYTHON" "$HERE/extract_slice.py" \
  --input "$FAT_INPUT" \
  --output-dir "$WORK" \
  --arch x86_64
