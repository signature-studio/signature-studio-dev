#!/bin/bash
# reopen-pr.sh — PR を close -> reopen して pull_request:reopened を起こし、review を再起動する (#721)。
# 使う場所: verify-review-verdict.sh (verdict 無し) / fix モードの answered (push せず根拠だけをコメント)。
# reopen が失敗すると PR は closed のまま残り、open PR の監視から外れる。そのため reopen は 3 回まで
# 再試行し、なお失敗したら PR に oc:stuck ラベルとコメントを残して非 0 で終わる。
#
# 入力 (env): GH_TOKEN, OC_REPO, OC_PR_NUMBER
# 任意 (env): OC_STUCK_LABEL (既定 oc:stuck)・OC_REOPEN_WAIT (秒、既定 3。テストで 0 にする)
set -uo pipefail

: "${OC_REPO:?}" "${OC_PR_NUMBER:?}"
STUCK_LABEL="${OC_STUCK_LABEL:-oc:stuck}"
WAIT="${OC_REOPEN_WAIT:-3}"

if ! gh pr close "$OC_PR_NUMBER" --repo "$OC_REPO"; then
  echo "::error::could not close PR #$OC_PR_NUMBER"
  exit 1
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
