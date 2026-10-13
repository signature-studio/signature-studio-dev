#!/bin/bash
# find_silent_runs.sh — success で終わったのに「完了報告」も push も残していない実装 run を列挙する。
# 経緯: PR #411 の修正 run が着手報告だけ投稿して push せず success 終了した (2026-10-13)。
# watch_runs.sh は run の成否しか見ないため、結果の有無はこのスクリプトで確認する。
# 使い方: SINCE=2026-10-13T00:00:00Z bash find_silent_runs.sh
#   出力: <run id> <終了時刻> <対象> (PR/issue 番号) の 1 行ずつ。空なら該当なし。
# 判定: issue_comment 起点の success run のうち、起点コメントの対象 (PR/issue) に、
#   run の**開始後**に bot (opencode-for-signature-studio) の「着手報告」以外の投稿が無いもの。
#   着手報告だけで終わった run (#411) を拾うため、bot の投稿が 1 件でも run 開始後にあれば除外はせず、
#   最後の投稿が『着手報告』『着手します』等の本文で始まる場合を該当とする。
# API 消費: 一覧 1 回 + 対象ごとに 1〜2 回。対象が多い時は MAX (既定 30) で打ち切る。
set -uo pipefail
R="${REPO:-signature-studio/signature-studio-dev}"
SINCE="${SINCE:-$(date -u -d '3 hours ago' +%FT%TZ)}"
MAX="${MAX:-30}"
BOT="${BOT:-opencode-for-signature-studio[bot]}"

gh api "repos/$R/actions/runs?event=issue_comment&status=success&per_page=100" \
  --jq ".workflow_runs[] | select(.created_at >= \"$SINCE\") | select(.display_title | startswith(\"Running\") | not) | \"\(.id)|\(.run_started_at)|\(.display_title)\"" 2>/dev/null \
| head -n "$MAX" | while IFS='|' read -r id start title; do
  # 起点コメントは run の triggering_actor / issue 番号を payload から直接は読めないため、
  # run の jobs の「Prepare event context」ログではなく、title (PR/issue タイトル) で issue を引く。
  num="$(gh api "search/issues?q=$(printf '%s' "$title" | jq -sRr @uri)+repo:$R+in:title&per_page=1" --jq '.items[0].number // empty' 2>/dev/null)"
  [ -n "$num" ] || continue
  # run 開始後の bot 投稿のうち最後の 1 件 (本文の先頭 40 文字も)。
  line="$(gh api "repos/$R/issues/$num/comments?per_page=100" --jq "[.[]|select(.user.login==\"$BOT\" and .created_at >= \"$start\")]|last|if . then \"\(.created_at)|\(.body[0:60]|gsub(\"\\n\";\" \"))\" else \"\" end" 2>/dev/null)"
  if [ -z "$line" ]; then
    echo "$id NO-POST #$num $title"
  elif printf '%s' "$line" | grep -qE '\|(着手報告|着手します|着手\(|着手:|## 着手)'; then
    echo "$id STARTED-ONLY #$num $title"
  fi
done
