#!/bin/bash
# check-title-collision.sh — 起票された issue の題名の [AREA-n] が、先行 (番号の小さい) issue と重複しないか検出する (CI-197, #4721)。
# 使い方: OC_REPO=<owner/repo> bash .github/scripts/check-title-collision.sh <issue番号>
# 出力: 重複した先行 issue を 1 件 1 行 (`#<番号> <題名>`) で出す。重複が無ければ何も出さない。
#       検出のみで、題名は変えない (自動リネームはしない)。終了: 0 = 検査できた / 2 = 使い方の誤り・gh の読み取り失敗。
set -uo pipefail

N="${1:-}"
case "$N" in ''|*[!0-9]*) echo "usage: OC_REPO=<repo> check-title-collision.sh <issue番号>" >&2; exit 2 ;; esac
[ -n "${OC_REPO:-}" ] || { echo "check-title-collision: OC_REPO が未設定" >&2; exit 2; }

# [AREA-n] (n の後ろの英小文字サフィックスを含む完全一致)。`[HB-H2]` のような非数値の接頭辞は対象外。
TAG_RE='^\[[A-Z][A-Z0-9]*-[0-9]+[a-z]?\]'
tag_of() { grep -oE "$TAG_RE" <<< "$1" | head -n1 || true; }

title="$(gh issue view "$N" --repo "$OC_REPO" --json title --jq '.title')" || { echo "check-title-collision: #$N の題名が取れない" >&2; exit 2; }
tag="$(tag_of "$title")"
[ -n "$tag" ] || exit 0

# 一覧は TSV (番号 TAB 題名)。取得に失敗したら検査できないので 2 で返す (黙って 0 にしない)。
list="$(gh issue list --repo "$OC_REPO" --state all --limit 5000 --json number,title --jq '.[] | "\(.number)\t\(.title)"')" \
  || { echo "check-title-collision: issue 一覧が取れない" >&2; exit 2; }

while IFS=$'\t' read -r num other; do
  [ -n "$num" ] || continue
  [ "$num" -lt "$N" ] 2>/dev/null || continue
  [ "$(tag_of "$other")" = "$tag" ] && printf '#%s %s\n' "$num" "$other"
done <<< "$list"
exit 0
