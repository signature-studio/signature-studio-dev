#!/usr/bin/env bash
# fetch_fonts.sh — GUI-9 (#186) のテスト用 OSS フォントを tools/gui/work/ (gitignore) へ取得し sha256 を検証する。リポジトリへは同梱しない。
#   Open Sans (Apache-2.0 / OFL 1.1: googlefonts/opensans) / Barlow (SIL OFL 1.1: jpt/barlow)。ライセンス本文は tools/legal/notices の NOTICES 運用に合流。
set -euo pipefail
D="$(cd -- "$(dirname -- "$0")/.." && pwd)/work"; mkdir -p "$D"; cd "$D"
get() { # file url sha256
  [ -f "$1" ] || curl -fsSL --retry 3 -o "$1" "$2"
  echo "$3  $1" | sha256sum -c - >/dev/null || { echo "sha256 mismatch: $1" >&2; rm -f "$1"; exit 1; }
}
get OpenSans-Regular.ttf https://github.com/googlefonts/opensans/raw/main/fonts/ttf/OpenSans-Regular.ttf c53aceea2dcf5b4098099c0c4d0a061d17e178a049317b42a422b1a9f7f8eb59
get Barlow-Regular.ttf https://github.com/google/fonts/raw/main/ofl/barlow/Barlow-Regular.ttf 95aa02c7c43096e0dd44d787ba6216864a67157e402adab59b35572e0c1577ea
echo "[fetch_fonts] ok: $D"
