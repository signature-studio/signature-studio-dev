#!/bin/bash
# reopen-pr.sh — PR を close -> reopen して pull_request:reopened を起こし、review を再起動する (#721)。
# 使う場所: verify-review-verdict.sh (verdict 無し) / fix モードの answered (push せず根拠だけをコメント)。
# reopen が失敗すると PR は closed のまま残り、open PR の監視から外れる。そのため reopen は 3 回まで
# 再試行し、なお失敗したら PR に oc:stuck ラベルとコメントを残して非 0 で終わる。
#
# close の前に PR の状態を読む (#2597)。merge 済み・close 済み (未 merge) の PR は再 review する対象が無い
# 想定内の状態なので、何もせず 0 で終わる (close 済みの PR を reopen しない: 人が閉じたものを勝手に戻さない)。
# 状態を読めない・open のまま close できない (gh の本当のエラー) は失敗にする。close が失敗したときに限り状態を
# 読み直し、その間に merge された競合だけを 0 とする (close が効いていた可能性がある closed は reopen に進む)。
#
# 入力 (env): GH_TOKEN, OC_REPO, OC_PR_NUMBER
# 任意 (env): OC_STUCK_LABEL (既定 oc:stuck)・OC_REOPEN_WAIT (秒、既定 3。テストで 0 にする)
set -uo pipefail

: "${OC_REPO:?}" "${OC_PR_NUMBER:?}"
STUCK_LABEL="${OC_STUCK_LABEL:-oc:stuck}"
WAIT="${OC_REOPEN_WAIT:-3}"

pr_state() { # open | merged | closed (未 merge)。読めなければ非 0
  gh api "repos/$OC_REPO/pulls/$OC_PR_NUMBER" --jq 'if .merged_at then "merged" else .state end'
}

state="$(pr_state)" || state=""
case "$state" in
  open) ;;
  merged)
    echo "::notice::PR #$OC_PR_NUMBER is already merged: there is no review to re-trigger"
    exit 0
    ;;
  closed)
    echo "::notice::PR #$OC_PR_NUMBER is closed (not merged): it is left closed and not reopened"
    exit 0
    ;;
  *)
    echo "::error::could not read the state of PR #$OC_PR_NUMBER (got '${state}')"
    exit 1
    ;;
esac

if ! gh pr close "$OC_PR_NUMBER" --repo "$OC_REPO"; then
  state="$(pr_state)" || state=""
  case "$state" in
    merged)
      echo "::notice::PR #$OC_PR_NUMBER was merged while it was being closed: there is no review to re-trigger"
      exit 0
      ;;
    closed)
      echo "::warning::gh pr close failed but PR #$OC_PR_NUMBER is closed now: continuing to reopen it"
      ;;
    *)
      echo "::error::could not close PR #$OC_PR_NUMBER"
      exit 1
      ;;
  esac
fi
sleep "$WAIT"
for attempt in 1 2 3; do
  if gh pr reopen "$OC_PR_NUMBER" --repo "$OC_REPO"; then
    echo "reopened PR #$OC_PR_NUMBER (attempt $attempt)"
    exit 0
  fi
  echo "::warning::reopen of PR #$OC_PR_NUMBER failed (attempt $attempt/3)"
  sleep "$WAIT"
done

gh api -X POST "repos/$OC_REPO/issues/$OC_PR_NUMBER/labels" -f "labels[]=$STUCK_LABEL" > /dev/null || true
gh pr comment "$OC_PR_NUMBER" --repo "$OC_REPO" \
  --body "PR を reopen できず、closed のままです (再試行 3 回が失敗)。PM の判断が必要です。ラベル \`${STUCK_LABEL}\` を付けました。" || true
echo "::error::PR #$OC_PR_NUMBER stays closed: reopen failed 3 times"
exit 1
