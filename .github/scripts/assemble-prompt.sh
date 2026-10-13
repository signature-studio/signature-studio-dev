#!/bin/bash
# assemble-prompt.sh — イベント文脈から実装エージェント用プロンプトを組み立てる。
#
# 入出力の契約 (H2/H3 の修正点):
#   - 入力は prepare-event-context.sh が $GITHUB_ENV に置いたスカラー値と、
#     untrusted 本文を隔離した $RUNNER_TEMP/*.txt のみ。untrusted 値を
#     ${{ }} や heredoc 経由で受け取らない。
#   - 出力は「ファイル」。旧実装は $GITHUB_OUTPUT に "prompt<<OCEOF ... OCEOF" を
#     書いていたが、本文にデリミタと同じ行があれば早期終了して、以降の行が別の
#     output として解釈される。step output にはパスの 1 行だけを載せる。
set -euo pipefail

: "${RUNNER_TEMP:?RUNNER_TEMP is not set}"

OUT_FILE="${OC_PROMPT_FILE:-$RUNNER_TEMP/opencode-prompt.txt}"
COMMENT_FILE="${OC_COMMENT_FILE:-}"
EVENT_NAME="${OC_EVENT_NAME:-unknown}"
PERMISSION="${OC_PERMISSION:-read}"
REPO="${OC_REPO:-${GITHUB_REPOSITORY:-unknown}}"
PR_NUMBER="${OC_PR_NUMBER:-none}"
ISSUE_NUMBER="${OC_ISSUE_NUMBER:-none}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="${OC_PROMPTS_DIR:-$SCRIPT_DIR/../prompts}"

case "$PERMISSION" in
  read | write) ;;
  *)
    printf '::error::OC_PERMISSION must be "read" or "write", got "%s"\n' "$PERMISSION"
    exit 1
    ;;
esac

[ -r "$PROMPTS_DIR/implementer.md" ] || {
  printf '::error::prompt template not found: %s\n' "$PROMPTS_DIR/implementer.md"
  exit 1
}

comment=""
if [ -n "$COMMENT_FILE" ] && [ -f "$COMMENT_FILE" ]; then
  comment="$(cat "$COMMENT_FILE")"
fi

# ---- untrusted 本文をフェンスで隔離 -----------------------------------------
# 本文は ``` を含むので、そのまま fence で囲むと「fence を閉じて指示を書き足す」
# 注入が通る。コメント内の最長バックティック連続より長い fence を採用する。
# 3 連続未満しか無い場合 (バッククォートが 1 個だけ等) は awk が何も返さないので、
# 空文字を fence 長に使わないよう既定値 3 を守る。
longest_fence=3
fence_run="$(printf '%s' "$comment" \
  | grep -o '`\{3,\}' \
  | awk '{ if (length($0) > m) m = length($0) } END { print m + 1 }' || true)"
if [ -n "$fence_run" ] && [ "$fence_run" -gt "$longest_fence" ]; then
  longest_fence="$fence_run"
fi
fence="$(awk -v n="$longest_fence" 'BEGIN { s = ""; while (length(s) < n) s = s "`"; print s }')"

{
  cat "$PROMPTS_DIR/implementer.md"

  printf '\n## 起動イベント\n\n'
  printf -- '- event: %s\n' "$EVENT_NAME"
  printf -- '- permission: %s\n' "$PERMISSION"
  printf -- '- repo: %s\n' "$REPO"
  printf -- '- branch: %s\n' "${GITHUB_REF_NAME:-unknown}"
  printf -- '- issue number: %s\n' "$ISSUE_NUMBER"
  printf -- '- issue/PR number: %s\n' "$PR_NUMBER"

  printf '\n## 依頼内容 (ユーザーのコメント / workflow_dispatch プロンプト)\n\n'
  printf '%s\n%s\n%s\n' "$fence" "$comment" "$fence"

  printf '\n## 期待する作業\n\n'
  # 下記は markdown のバッククォートを含むため意図的に単一引用符を使っている
  # (shellcheck disable=SC2016)
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
      # shellcheck disable=SC2016  # markdown のバッククォート。展開は不要
      printf '1. 依頼内容を読み、対象の Issue/PR を `gh issue view` / `gh pr view` で確認する。\n'
      if [ "$PERMISSION" = write ]; then
        printf '2. 作業ブランチで実施し、コミット・push して PR を作成する (または既存 PR に push)。\n'
        printf '3. 既存 PR がある場合はその PR に push し、コンフリクトを解消する。\n'
      else
        printf '2. 読み取り専用なので、調査結果をコメントするのみ。\n'
      fi
      ;;
    pull_request_review)
      # reviewer (oc-reviewer) の差し戻し (changes_requested)。上の「依頼内容」は reviewer の review 本文
      # (reviewer が PR の内容を引用しているため、指示としては扱わず指摘の入口として読む)。
      printf '**これは reviewer の差し戻しに対する fix モードである。PM の指示を待たずに、あなた自身が修正を完了させる。**\n\n'
      printf '1. 指摘の全体を確認する: `gh pr view %s --comments`、`gh api repos/%s/pulls/%s/reviews`、\n' "$PR_NUMBER" "$REPO" "$PR_NUMBER"
      printf '   `gh api repos/%s/pulls/%s/comments` (inline)。oc-reviewer の最新の review と、copilot-pull-request-reviewer の指摘の両方を読む。\n' "$REPO" "$PR_NUMBER"
      printf '2. `gh pr checkout %s` した PR ブランチ上で、妥当な指摘を全て修正する。force push はしない。\n' "$PR_NUMBER"
      printf '   main と競合している場合は main を merge して解消する (rebase はしない)。\n'
      printf '3. 修正を同じブランチへ push する (push が review を自動で再起動する)。PR 本文の検証 HEAD・実測値は最新の HEAD に更新する。\n'
      printf '4. 妥当でないと判断した指摘は、PR コメントに根拠 (実測) を書く。\n'
      printf '5. **何も push せず、PR コメントも書かずに終了してはならない。** 終了前に、指摘ごとの対応 (修正 commit / 対応しない理由) を PR コメントで報告する。\n'
      printf '6. draft にしない。新しい PR を作らない (この PR を直す)。\n'
      ;;
    pull_request)
      printf '1. PR の差分を読み、依頼された追加作業を実施する。\n'
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

printf 'prompt written to %s (%s bytes)\n' "$OUT_FILE" "$(wc -c < "$OUT_FILE")"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    printf 'prompt_file=%s\n' "$OUT_FILE"
    printf 'prompt_bytes=%s\n' "$(wc -c < "$OUT_FILE")"
  } >> "$GITHUB_OUTPUT"
fi