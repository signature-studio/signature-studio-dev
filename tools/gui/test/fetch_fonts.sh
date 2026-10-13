#!/usr/bin/env bash
# fetch_fonts.sh — GUI-9 (#186) のテスト用 OSS フォントを tools/gui/work/ (gitignore) へ取得し sha256 を検証する。リポジトリへは同梱しない。
#   Open Sans (Apache-2.0 / OFL 1.1: googlefonts/opensans) / Barlow (SIL OFL 1.1: google/fonts ofl/barlow)。ライセンス本文は tools/legal/notices の NOTICES 運用に合流。
set -euo pipefail
D="$(cd -- "$(dirname -- "$0")/.." && pwd)/work"; mkdir -p "$D"; cd "$D"
get() { # file url sha256
  [ -f "$1" ] || curl -fsSL --retry 3 -o "$1" "$2"
  echo "$3  $1" | sha256sum -c - >/dev/null || { echo "sha256 mismatch: $1" >&2; rm -f "$1"; exit 1; }
}
# 台帳 test/fonts.tsv (file<TAB>url<TAB>sha256<TAB>face 名)。ブラウザ e2e (e2e/text_e2e.mjs) も同じ台帳の sha256 で検証する (GUI-13 #615)
while IFS=$'\t' read -r f u h _; do [ -n "$f" ] && get "$f" "$u" "$h"; done < "$D/../test/fonts.tsv"
echo "[fetch_fonts] ok: $D"
