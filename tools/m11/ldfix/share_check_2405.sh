#!/usr/bin/env bash
# #2405 (LD-113): 2019-03-03 の share の代替候補の照合を再現する。対象は avast/retdec v3.3 (タグ ae298572) の
# バイナリ release 同梱 share、2019-03-08 の retdec-support archive、タグ v3.3 の install-share.py、retdec-support の commit 履歴。
# 結果と解釈は REPORT_2405.md §1。gv 分岐の測定 (retdec2019_gv_2405.sh) とは独立。
#
# 使い方: bash tools/m11/ldfix/share_check_2405.sh {zip|archive|tag|all}
#   zip     : v3.3 zip の sha256・version.txt・types 5 本 (v5.0 と cmp)・ords の件数と v5.0 ordinals との diff 行数
#   archive : 2019-03-08 archive の sha256・version.txt・types 5 本 (v5.0 と cmp)・static-code pe の名前照合 (v3.3 と)
#   tag     : タグ v3.3 の install-share.py の内容と所在、301f4e64 の rename、retdec-support の commit 件数 (gh api)
# env:
#   WORK         作業先 (既定 ${RUNNER_TEMP:-/tmp}/share2405)
#   RETDEC_ROOT  [RETDEC] (v5.0) の root。比較元 (既定 /opt/retdec。docs/REFERENCES.md §4)
# 前提: curl・unzip・tar (xz)・gh (認証済み)。
set -euo pipefail

WORK="${WORK:-${RUNNER_TEMP:-/tmp}/share2405}"
RETDEC_ROOT="${RETDEC_ROOT:-/opt/retdec}"
V5="$RETDEC_ROOT/share/retdec/support"
ZIP_URL=https://github.com/avast/retdec/releases/download/v3.3/retdec-v3.3-ubuntu-64b.zip
ZIP_SHA=83b8e45bd4d405dbe4f79035de9acc153f56c3dc3188dcc83d22274646dbfe3c
ARC_URL=https://github.com/avast/retdec-support/releases/download/2019-03-08/retdec-support_2019-03-08.tar.xz
ARC_SHA=629351609bca0f4b8edbd4e53789192305256aeb908e953f5546e121a911d54e
TYPES="cstdlib windows linux arm windrivers"

fetch() { # fetch <url> <sha256> <file>: 無ければ取得し、sha256 を検証する
  mkdir -p "$(dirname "$3")"
  [ -f "$3" ] || curl -sSL --max-time 300 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c -
}

v33_extract() {
  fetch "$ZIP_URL" "$ZIP_SHA" "$WORK/v33.zip"
  [ -d "$WORK/v33/retdec/share/retdec/support" ] || unzip -q "$WORK/v33.zip" 'retdec/share/retdec/support/*' -d "$WORK/v33"
}

cmp_types() { # cmp_types <support 直下>: types 5 本を v5.0 と比べる
  local f
  for f in $TYPES; do
    if cmp -s "$1/generic/types/$f.json" "$V5/generic/types/$f.json"; then echo "types/$f.json: v5.0 と一致"; else echo "types/$f.json: 差あり"; fi
  done
}

do_zip() {
  v33_extract
  local V="$WORK/v33/retdec/share/retdec/support" a
  echo "v3.3 version.txt: $(cat "$V/version.txt")"
  cmp_types "$V"
  for a in x86 arm; do
    echo "ords/$a: $(find "$V/$a/ords" -type f | wc -l) 件、v5.0 ordinals/$a との diff 行数: $(diff -rq "$V/$a/ords" "$V5/ordinals/$a" | wc -l)"
  done
}

do_archive() {
  v33_extract
  fetch "$ARC_URL" "$ARC_SHA" "$WORK/support_2019-03-08.tar.xz"
  local A="$WORK/support_2019-03-08" V="$WORK/v33/retdec/share/retdec/support"
  rm -rf "$A"; mkdir -p "$A"; tar -xJf "$WORK/support_2019-03-08.tar.xz" -C "$A"
  echo "archive version.txt: $(cat "$A/version.txt")"
  cmp_types "$A"
  rel() { find "$1" -path '*/static-code/pe/*' -type f -name "*.$2" | sed -E 's#.*/static-code/pe/##' | LC_ALL=C sort; }
  rel "$V" yarac > "$WORK/v33_pe.txt"
  rel "$A" yara > "$WORK/arc_pe.txt"
  echo "static-code pe: v3.3 .yarac $(wc -l < "$WORK/v33_pe.txt") 件、2019-03-08 .yara $(wc -l < "$WORK/arc_pe.txt") 件"
  echo "  完全なファイル名 (拡張子込み) の一致: $(comm -12 "$WORK/v33_pe.txt" "$WORK/arc_pe.txt" | wc -l) 件"
  echo "  拡張子を除いた相対パスの一致: $(comm -12 <(sed 's/\.yarac$//' "$WORK/v33_pe.txt" | LC_ALL=C sort) <(sed 's/\.yara$//' "$WORK/arc_pe.txt" | LC_ALL=C sort) | wc -l) 件"
}

do_tag() {
  local src
  echo "tag v3.3: $(gh api repos/avast/retdec/git/ref/tags/v3.3 --jq .object.sha)"
  src="$(gh api 'repos/avast/retdec/contents/support/install-share.py?ref=ae298572' --jq .content | base64 -d)"
  echo "support/install-share.py (ae298572): $(grep -E '^(version|sha256hash_ref) = ' <<< "$src" | tr '\n' ' ')"
  if gh api 'repos/avast/retdec/contents/cmake/install-share.py?ref=ae298572' >/dev/null 2>&1; then echo "cmake/install-share.py (ae298572): あり"; else echo "cmake/install-share.py (ae298572): 無し"; fi
  echo "301f4e64: $(gh api repos/avast/retdec/commits/301f4e64 --jq '.files[] | select(.filename == "support/install-share.py") | "\(.status) from \(.previous_filename)"')"
  echo "retdec-support の commit (2019-02-01〜03-20): $(gh api 'repos/avast/retdec-support/commits?since=2019-02-01T00:00:00Z&until=2019-03-20T23:59:59Z&per_page=100' --jq 'length') 件"
}

case "${1:-all}" in
  zip) do_zip ;;
  archive) do_archive ;;
  tag) do_tag ;;
  all) do_zip; do_archive; do_tag ;;
  *) echo "usage: $0 {zip|archive|tag|all}" >&2; exit 2 ;;
esac
