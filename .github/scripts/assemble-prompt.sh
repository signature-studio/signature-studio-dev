#!/bin/bash
# assemble-prompt.sh — イベント文脈から実装エージェント用プロンプトを組み立て、
# ファイルに書き出して $GITHUB_OUTPUT にはそのパスだけを載せる。
#
# 旧実装は $GITHUB_OUTPUT に "prompt<<OCEOF ... OCEOF" の heredoc を書いていた。
# 本文にデリミタと同じ行が含まれると早期終了して以降が別の output として
# 解釈されるため、プロンプトはファイルに出し step output は 1 行に限定する。
# 入力は prepare-event-context.sh が $GITHUB_ENV に置いた値 (OC_* / $GITHUB_ENV) のみ。
set -euo pipefail

: "${RUNNER_TEMP:?RUNNER_TEMP is not set}"

OUT_FILE="${OC_PROMPT_FILE:-$RUNNER_TEMP/opencode-prompt.txt}"
COMMENT_FILE="${OC_COMMENT_FILE:-}"
EVENT_NAME="${OC_EVENT_NAME:-unknown}"
PERMISSION="${OC_PERMISSION:-read}"
REPO="${OC_REPO:-${GITHUB_REPOSITORY:-unknown}}"
PR_NUMBER="${OC_PR_NUMBER:-none}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="${OC_PROMPTS_DIR:-$SCRIPT_DIR/../prompts}"

comment=""
if [ -n "$COMMENT_FILE" ] && [ -f "$COMMENT_FILE" ]; then
  comment="$(cat "$COMMENT_FILE")"
fi

{
  cat "$PROMPTS_DIR/implementer.md"

  printf '\n## 起動イベント\n\n'
  printf -- '- event: %s\n' "$EVENT_NAME"
  printf -- '- permission: %s\n' "$PERMISSION"
  printf -- '- repo: %s\n' "$REPO"
  printf -- '- branch: %s\n' "${GITHUB_REF_NAME:-unknown}"
  printf -- '- issue/PR number: %s\n' "$PR_NUMBER"

  printf '\n## 依頼内容 (ユーザーのコメント / workflow_dispatch プロンプト)\n\n'
  printf '```\n%s\n```\n' "$comment"

  printf '\n## 期待する作業\n\n'
  case "$EVENT_NAME" in
    workflow_dispatch)
      printf '1. 依頼内容を読み、作業ブランチを切って実施する。\n'
      printf '2. e2e/テストを実行し、結果 (所要秒・load・PASS/FAIL) を REPORT に実測で残す。\n'
      if [ "$PERMISSION" = write ]; then
        printf '3. コミット・push し PR を作成する。PR がある場合はコンフリクトを解消する。\n'
      else
        printf '3. 読み取り専用なので PR は作らず、調査結果のみ報告する。\n'
      fi
      ;;
    issue_comment)
      printf '1. 依頼内容を読み、対象の Issue/PR を `gh issue view` / `gh pr view` で確認する。\n'
      if [ "$PERMISSION" = write ]; then
        printf '2. 作業ブランチで実施し、コミット・push して PR を作成する (または既存 PR に push)。\n'
        printf '3. 既存 PR がある場合はその PR に push し、コンフリクトを解消する。\n'
      else
        printf '2. 読み取り専用なので、調査結果をコメントするのみ。\n'
      fi
      ;;
    pull_request)
      printf '1. PR の diff を読み、依頼内容の追加作業を実施する。\n'
      if [ "$PERMISSION" = write ]; then
        printf '2. 作業ブランチで実施し、コミット・push して既存 PR を更新する。\n'
      else
        printf '2. 読み取り専用なので、所見のみ報告する。\n'
      fi
      ;;
    *)
      printf '1. 依頼内容を読み、作業ブランチを切って実施する。\n'
      printf '2. 検証結果を REPORT に実測で残す。\n'
      ;;
  esac
} > "$OUT_FILE"

chmod 600 "$OUT_FILE"

printf 'prompt written to %s\n' "$OUT_FILE"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    printf 'prompt_file=%s\n' "$OUT_FILE"
    printf 'prompt_bytes=%s\n' "$(wc -c < "$OUT_FILE")"
  } >> "$GITHUB_OUTPUT"
fi
