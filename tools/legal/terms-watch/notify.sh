#!/usr/bin/env bash
# ci.sh が失敗した時の通知: 同題の open issue があればコメント、無ければ起票する。terms-watch.yaml (tools/legal/terms-watch/workflow/ → .github/workflows/) から呼ぶ。
#   GH_TOKEN=… GITHUB_REPOSITORY=owner/repo bash tools/legal/terms-watch/notify.sh [--negative-control]
# 入力: $TW_OUT/{exit_code,log.txt} (ci.sh の出力。無ければ「実行前に失敗」として通知する)
# 通知に失敗したら非 0 で終わる (通知が黙って落ちない)。規約本文は載せない (ログの状態行のみ)。
set -uo pipefail
OUT="${TW_OUT:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/terms-watch}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"
TITLE='[LGL-5] terms-watch: 規約の差分検出/取得失敗 (週次監視の自動起票)'
if [ "${1:-}" = "--negative-control" ]; then
  TITLE='[LGL-5] terms-watch: ネガコン (workflow_dispatch の動作確認・自動起票。確認後に close)'
fi
code="$(cat "$OUT/exit_code" 2>/dev/null || echo 'なし (ci.sh の実行前/実行中に失敗)')"
case "$code" in
  1) meaning="規約の差分あり (台帳のハッシュと不一致)" ;;
  3) meaning="取得失敗・検証不能 (HTTP エラー・ボット壁・サニティ違反・uv/PyPI 不達など)" ;;
  4) meaning="exit 0 だが対象 4 件が全件 UNCHANGED でない" ;;
  *) meaning="その他の失敗" ;;
esac
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/$GITHUB_REPOSITORY/actions/runs/${GITHUB_RUN_ID:-0}"
BODY="$OUT/notify_body.md"
{
  echo "週次の terms-watch (Web 4 文書) が失敗しました。"
  echo
  echo "- 終了コード: \`$code\` — $meaning"
  echo "- run: $RUN_URL"
  echo "- 日時 (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "### ログ (状態行のみ。末尾 40 行)"
  echo '```'
  tail -n 40 "$OUT/log.txt" 2>/dev/null | cut -c1-300 || echo "(ログなし)"
  echo '```'
  echo
  echo "### 対応"
  echo "1. 差分 (exit 1): 手元で \`pnpm terms-watch -- --only <id>\` を実行し、\`docs/LEGAL.md\` を見直してから \`pnpm terms-watch ack <id>\` で台帳を更新する (FL の規約改定は 30 日で発効)。"
  echo "2. 取得失敗 (exit 3): run のログで HTTP ステータス/サニティ違反を確認。恒常なら \`tools/legal/terms-watch/sources.json\` を直す。"
  echo "3. 手順の正本: \`tools/legal/terms-watch/REPORT.md\`。"
} > "$BODY"

existing="$(gh issue list --repo "$GITHUB_REPOSITORY" --state open --limit 200 --json number,title \
  | jq -r --arg t "$TITLE" '[.[] | select(.title == $t)][0].number // empty')" || { echo "notify.sh: issue 一覧の取得に失敗" >&2; exit 1; }
if [ -n "$existing" ]; then
  gh issue comment "$existing" --repo "$GITHUB_REPOSITORY" --body-file "$BODY" || { echo "notify.sh: コメントに失敗" >&2; exit 1; }
  echo "notify.sh: 既存 issue #$existing にコメント"
else
  gh issue create --repo "$GITHUB_REPOSITORY" --title "$TITLE" --body-file "$BODY" || { echo "notify.sh: 起票に失敗" >&2; exit 1; }
  echo "notify.sh: issue を起票"
fi
