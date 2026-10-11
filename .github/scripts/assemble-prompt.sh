#!/bin/bash
# assemble-prompt.sh — イベント文脈 (環境変数) から実装エージェント用プロンプトを組み立て、
# $GITHUB_OUTPUT に "prompt<<OCEOF ... OCEOF" として書き出す。
set -euo pipefail

OUT="${GITHUB_OUTPUT:-/dev/stdout}"

emit() {
  echo "prompt<<OCEOF" >> "$OUT"
  cat >> "$OUT"
  echo "OCEOF" >> "$OUT"
}

{
  cat "$(dirname "$0")/../prompts/implementer.md"
  echo ""
  echo "## 起動イベント"
  echo "- event: ${EVENT_NAME:?}"
  echo "- permission: ${PERMISSION:?}"
  echo "- repo: ${REPO:?}"
  echo "- branch: ${GITHUB_REF_NAME:-unknown}"
  echo "- issue/PR number: ${PR_NUMBER:-none}"
  echo ""
  echo "## 依頼内容 (ユーザーのコメント/dispatch プロンプト)"
  echo '```'
  echo "${COMMENT_BODY:-}"
  echo '```'
  echo ""
  echo "## 期待する作業"
  case "${EVENT_NAME}" in
    workflow_dispatch)
      echo "1. 依頼内容を読み、作業ブランチを切って実施する。"
      echo "2. e2e/テストを実行し、結果を REPORT に残す。"
      if [ "${PERMISSION}" = "write" ]; then
        echo "3. コミット・プッシュし、PR を作成する。PR がある場合はコンフリクトを解消する。"
      else
        echo "3. 読み取り専用のため、PR は作らず調査結果のみコメントする。"
      fi
      ;;
    issue_comment)
      echo "1. 依頼内容を読み、対象の Issue/PR を \`gh issue view\` / \`gh pr view\` で確認する。"
      if [ "${PERMISSION}" = "write" ]; then
        echo "2. 作業ブランチで実施 → コミット・プッシュ → PR 作成 (または既存 PR に push)。"
        echo "3. 既存 PR がある場合はその PR に push し、コンフリクトを解消する。"
      else
        echo "2. 読み取り専用のため、調査結果をコメントするのみ。"
      fi
      ;;
  esac
} | emit
