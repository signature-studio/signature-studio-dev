#!/bin/bash
# fix-progress.sh — reviewer の差し戻しを受けた fix モードの進捗を検証する (#719)。
# 指示 122/123: 差し戻された PR が「修正もレビューもされていない」状態に戻らないようにする。
#
#   record        起動時点の PR head と時刻を $GITHUB_ENV に記録する
#   check         head が進んだか / 根拠コメントを投稿したかを判定し、result を $GITHUB_OUTPUT に出す
#                   pushed   : head が進んだ (push が synchronize を起こし、review が再起動する)
#                   answered : push せず PR にコメントした (review は起動しないので reopen が要る)
#                   none     : どちらもしていない
#   retry-prompt  none だったときの再試行用プロンプトを作る
#   reopen        close -> reopen で pull_request:reopened を起こす
#
# 入力 (env): GH_TOKEN, OC_REPO, OC_PR_NUMBER, RUNNER_TEMP, GITHUB_ENV, GITHUB_OUTPUT
# 実装 App は PR の comment を投稿する時 user.login が opencode-for-signature-studio[bot] になる。
set -euo pipefail

: "${OC_REPO:?}" "${OC_PR_NUMBER:?}"
pr_head() { gh api "repos/$OC_REPO/pulls/$OC_PR_NUMBER" --jq .head.sha; }

case "${1:-}" in
  record)
    {
      printf 'OC_HEAD_BEFORE=%s\n' "$(pr_head)"
      printf 'OC_START_TS=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$GITHUB_ENV"
    ;;
  check)
    : "${OC_HEAD_BEFORE:?}" "${OC_START_TS:?}"
    if [ "$(pr_head)" != "$OC_HEAD_BEFORE" ]; then
      result=pushed
    else
      n="$(gh api --paginate "repos/$OC_REPO/issues/$OC_PR_NUMBER/comments" \
        | jq -s --arg t "$OC_START_TS" '[.[][] | select(.created_at > $t and (.user.login | startswith("opencode-for-signature-studio")))] | length')"
      if [ "$n" -gt 0 ]; then result=answered; else result=none; fi
    fi
    echo "fix progress: $result (head before ${OC_HEAD_BEFORE:0:10})"
    echo "result=$result" >> "$GITHUB_OUTPUT"
    ;;
  retry-prompt)
    : "${OC_PROMPT_SRC:?}"
    out="$RUNNER_TEMP/opencode-prompt-retry.txt"
    {
      cat "$OC_PROMPT_SRC"
      printf '\n## 再試行 (前回は何もせずに終了した)\n\n'
      printf '前回の試行は commit を push せず、PR にコメントも投稿せずに終了した。これは禁止されている。\n'
      printf '今回は必ず次のどちらかを行うこと。\n'
      printf '1. reviewer の指摘を修正して PR ブランチへ push する。\n'
      printf '2. 修正しない指摘ごとに根拠を PR コメントへ書く (`gh pr comment`)。\n'
    } > "$out"
    chmod 600 "$out"
    echo "prompt_file=$out" >> "$GITHUB_OUTPUT"
    ;;
  reopen)
    gh pr close "$OC_PR_NUMBER" --repo "$OC_REPO"
    gh pr reopen "$OC_PR_NUMBER" --repo "$OC_REPO"
    ;;
  *)
    echo "usage: $0 record|check|retry-prompt|reopen" >&2
    exit 2
    ;;
esac
