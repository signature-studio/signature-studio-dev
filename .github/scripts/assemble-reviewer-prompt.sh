#!/bin/bash
# assemble-reviewer-prompt.sh — PR 文脈からレビュワー用プロンプトを組み立てる。
#
# implement 版 (assemble-prompt.sh) と同じ契約:
#   - untrusted な値 (PR タイトル・本文・diff) はすべてファイル経由で受け取る。
#     旧 workflow はこれらを ${{ }} で run スクリプトに展開していた。
#   - $GITHUB_OUTPUT には出力ファイルのパス 1 行だけを載せる (heredoc を使わない)。
set -euo pipefail

: "${RUNNER_TEMP:?RUNNER_TEMP is not set}"

OUT_FILE="${OC_REVIEW_PROMPT_FILE:-$RUNNER_TEMP/opencode-review-prompt.txt}"
DIFF_FILE="${OC_DIFF_FILE:-$RUNNER_TEMP/pr.diff}"
TITLE_FILE="${OC_PR_TITLE_FILE:-$RUNNER_TEMP/opencode-pr-title.txt}"
BODY_FILE="${OC_PR_BODY_FILE:-$RUNNER_TEMP/opencode-pr-body.txt}"
PR_NUMBER="${OC_PR_NUMBER:-unknown}"
REPO="${OC_REPO:-${GITHUB_REPOSITORY:-unknown}}"
HAS_REVIEWER_TOKEN="${OC_HAS_REVIEWER_TOKEN:-false}"
MAX_DIFF_BYTES="${OC_MAX_DIFF_BYTES:-100000}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="${OC_PROMPTS_DIR:-$SCRIPT_DIR/../prompts}"

[ -r "$PROMPTS_DIR/reviewer.md" ] || {
  printf '::error::prompt template not found: %s\n' "$PROMPTS_DIR/reviewer.md"
  exit 1
}

title=""
[ -f "$TITLE_FILE" ] && title="$(cat "$TITLE_FILE")"
body=""
[ -f "$BODY_FILE" ] && body="$(cat "$BODY_FILE")"

diff=""
if [ -s "$DIFF_FILE" ]; then
  # codepoint 単位で切ってから出力する。head -c はバイト単位なので UTF-8 境界を壊す。
  diff="$(jq -Rsr --argjson max "$MAX_DIFF_BYTES" '.[0:$max]' < "$DIFF_FILE")"
else
  printf '::warning::%s is empty; the reviewer will have no diff to inspect\n' "$DIFF_FILE"
fi

# untrusted テキストを囲む fence は、本文中の最長バックティック連続より長いものを使う。
# 3 連続未満しか無い場合は既定値 3 のままにする (awk が空を返しても fence は壊れない)。
untrusted_text="$title
$body
$diff"
longest_fence=3
fence_run="$(printf '%s' "$untrusted_text" \
  | grep -o '`\{3,\}' \
  | awk '{ if (length($0) > m) m = length($0) } END { print m + 1 }' || true)"
if [ -n "$fence_run" ] && [ "$fence_run" -gt "$longest_fence" ]; then
  longest_fence="$fence_run"
fi
fence="$(awk -v n="$longest_fence" 'BEGIN { s = ""; while (length(s) < n) s = s "`"; print s }')"

{
  cat "$PROMPTS_DIR/reviewer.md"

  printf '\n## PR\n\n'
  printf -- '- repo: %s\n' "$REPO"
  printf -- '- number: %s\n' "$PR_NUMBER"

  printf '\n### タイトル\n\n%s\n%s\n%s\n' "$fence" "$title" "$fence"

  if [ -n "$body" ]; then
    printf '\n### 説明\n\n%s\n%s\n%s\n' "$fence" "$body" "$fence"
  fi

  printf '\n## diff\n\n%sdiff\n' "$fence"
  if [ -n "$diff" ]; then
    printf '%s\n' "$diff"
  else
    printf '(diff unavailable)\n'
  fi
  printf '%s\n' "$fence"

  printf '\n## 認証状態\n\n'
  if [ "$HAS_REVIEWER_TOKEN" = true ]; then
    printf 'gh はレビュワー App identity で認証済み。approve / merge を実行できる。\n'
  else
    printf 'NOTE: reviewer App identity unavailable; gh is authenticated as the implementer App.\n'
    printf 'You cannot approve your own PR, and you must not approve or merge it (#2600).\n'
    printf 'Post the review as a comment explaining that the reviewer token is unavailable, then stop.\n'
    printf 'If reviewer-token was expected, check that\n'
    printf 'OC_REVIEW_APP_PRIVATE_KEY is set and that the App installation grants\n'
    printf 'contents:write and pull-requests:write.\n'
  fi
} > "$OUT_FILE"

chmod 600 "$OUT_FILE"

printf 'review prompt written to %s (%s bytes)\n' "$OUT_FILE" "$(wc -c < "$OUT_FILE")"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  printf 'prompt_file=%s\n' "$OUT_FILE" >> "$GITHUB_OUTPUT"
fi