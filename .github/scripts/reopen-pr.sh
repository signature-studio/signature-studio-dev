#!/bin/bash
# reopen-pr.sh — PR を close -> reopen して pull_request:reopened を起こし、review を再起動する (#721)。
# 使う場所: verify-review-verdict.sh (verdict 無し) / fix モードの answered (push せず根拠だけをコメント)。
# reopen が失敗すると PR は closed のまま残り、open PR の監視から外れる。そのため reopen は 3 回まで
# 再試行し、なお失敗したら PR に oc:stuck ラベルとコメントを残して非 0 で終わる。
# PR が merge 済み・close 済みなら何もせず 0 で終わる (再 review の対象が無い / 人が閉じた PR は reopen しない)。
# PR の状態が読めないとき、または open のまま close に失敗したときは失敗する。
#
# 入力 (env): GH_TOKEN, OC_REPO, OC_PR_NUMBER
# 任意 (env): OC_STUCK_LABEL (既定 oc:stuck)・OC_REOPEN_WAIT (秒、既定 3。テストで 0 にする)
set -uo pipefail

: "${OC_REPO:?}" "${OC_PR_NUMBER:?}"
STUCK_LABEL="${OC_STUCK_LABEL:-oc:stuck}"
WAIT="${OC_REOPEN_WAIT:-3}"

pr_state() { # PR の状態を open / merged / closed で出す。読めなければ非 0
  local json
  json="$(gh api "repos/$OC_REPO/pulls/$OC_PR_NUMBER")" || return 1
  jq -r 'if .state == "open" then "open" elif .state == "closed" then (if .merged == true then "merged" else "closed" end) else empty end' <<< "$json"
}

state="$(pr_state)" || state=""
case "$state" in
  open) ;;
  merged | closed)
    echo "::notice::PR #$OC_PR_NUMBER is already $state; not reopening it"
    exit 0
    ;;
  *)
    echo "::error::could not read the state of PR #$OC_PR_NUMBER"
    exit 1
    ;;
esac

if ! gh pr close "$OC_PR_NUMBER" --repo "$OC_REPO"; then
  # close が失敗する間に merge / close されていたら、再 review の対象が無いので 0 で終わる (競合)
  state="$(pr_state)" || state=""
  case "$state" in
    merged | closed)
      echo "::notice::PR #$OC_PR_NUMBER became $state while closing; not reopening it"
      exit 0
      ;;
  esac
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
