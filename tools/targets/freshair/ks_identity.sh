#!/usr/bin/env bash
# FA-5 (#52): SlateCore (Fresh Air) と HeartCore (Kilohearts) の snapin 実装同一性を機械語で比較する。
# usage: bash tools/targets/freshair/ks_identity.sh [outdir]   (既定: $TMPDIR/ks_identity)
# 前提: tools/targets/freshair/work/win (analyze.sh の展開物) と tools/targets/kilohearts/work/winpkg/HeartCore.core_64
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
t="$here/.."
SC="${SLATECORE:-$here/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
KH="${HEARTCORE:-$t/kilohearts/work/winpkg/HeartCore.core_64}"
out="${1:-${TMPDIR:-/tmp}/ks_identity}"
mkdir -p "$out"
for f in "$SC" "$KH"; do [ -f "$f" ] || { echo "missing: $f" >&2; exit 2; }; done
py() { uv run --with pefile --with numpy --with capstone python "$@"; }
echo "== [1] process slot 比較 (37 共通 Dsp クラス)"; py "$here/ks_identity.py" "$KH" "$SC" "$out/ident.json" | tee "$out/ident.txt"
echo "== [2] 全関数 E 正規化ハッシュ照合 (>=12 命令)"; py "$here/ks_census.py" "$KH" "$SC" "$out/census.json" 12 | head -12
echo "== [3] Fresh Air DSP closure の共有率"; py "$here/ks_closure_share.py" "$KH" "$SC" "$out/share.json"
