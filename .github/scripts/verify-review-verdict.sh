#!/bin/bash
# verify-review-verdict.sh — review run が verdict を投稿したかを検証し、無ければ review を再起動する (#719)。
# 指示 122/123: reviewer が success で終わっても verdict を出さないと、その PR は「レビューもされず
# 修正もされない」状態になる (PR #462: run 38349343991 は success、oc-reviewer の review は 0 件だった)。
#
# 正当な終わり方:
#   - PR が merge / close された
#   - 現在の head に対する oc-reviewer の review が APPROVED または CHANGES_REQUESTED
#   - COMMENTED で本文に `copilot-pending` を含み、PR 作成から OC_COPILOT_PENDING_MINUTES 分未満
#     (Copilot の review が提出されると pull_request_review で review job が再起動する)
# それ以外は close -> reopen で review を再起動する。同じ head に OC_REVIEW_MAX_ATTEMPTS 回
# 再起動しても verdict が出なければ PR に警告を残して失敗する。
#
# 入力 (env): GH_TOKEN, OC_REPO, OC_PR_NUMBER
set -euo pipefail

: "${OC_REPO:?}" "${OC_PR_NUMBER:?}"
MAX_ATTEMPTS="${OC_REVIEW_MAX_ATTEMPTS:-3}"
PENDING_MINUTES="${OC_COPILOT_PENDING_MINUTES:-20}"

pr="$(gh api "repos/$OC_REPO/pulls/$OC_PR_NUMBER")"
state="$(jq -r .state <<< "$pr")"
if [ "$state" != open ]; then
  echo "PR #$OC_PR_NUMBER is $state: nothing to verify"
  exit 0
fi
head="$(jq -r .head.sha <<< "$pr")"
created="$(jq -r .created_at <<< "$pr")"

rv="$(gh api --paginate "repos/$OC_REPO/pulls/$OC_PR_NUMBER/reviews" \
  | jq -s --arg h "$head" '[.[][] | select((.user.login | startswith("oc-reviewer")) and .commit_id == $h)] | last // {}')"
st="$(jq -r '.state // "NONE"' <<< "$rv")"

case "$st" in
  APPROVED | CHANGES_REQUESTED)
    echo "verdict on ${head:0:7}: $st"
    exit 0
    ;;
  COMMENTED)
    age_min=$((($(date -u +%s) - $(date -u -d "$created" +%s)) / 60))
    if jq -e '.body | contains("copilot-pending")' <<< "$rv" > /dev/null && [ "$age_min" -lt "$PENDING_MINUTES" ]; then
      echo "waiting for Copilot (copilot-pending, PR age ${age_min} min < $PENDING_MINUTES): the Copilot review will re-trigger this job"
      exit 0
    fi
    ;;
esac

marker="review-retry:${head:0:12}"
tries="$(gh api --paginate "repos/$OC_REPO/issues/$OC_PR_NUMBER/comments" \
  | jq -s --arg m "$marker" '[.[][] | select(.body | contains($m))] | length')"

if [ "$tries" -ge "$MAX_ATTEMPTS" ]; then
  gh pr comment "$OC_PR_NUMBER" --repo "$OC_REPO" \
    --body "review run が ${MAX_ATTEMPTS} 回続けて verdict を投稿せずに終了しました (head ${head:0:7})。自動再実行を止めます。PM の判断が必要です。"
  echo "::error::no review verdict after $tries retries on ${head:0:7}"
  exit 1
fi

gh pr comment "$OC_PR_NUMBER" --repo "$OC_REPO" \
  --body "review run が verdict (approve / request-changes) を投稿せずに終了したため、review を再実行します (試行 $((tries + 1))/${MAX_ATTEMPTS}、head ${head:0:7})。<!-- $marker -->"
gh pr close "$OC_PR_NUMBER" --repo "$OC_REPO"
sleep 3
gh pr reopen "$OC_PR_NUMBER" --repo "$OC_REPO"
echo "re-triggered the review for PR #$OC_PR_NUMBER (retry $((tries + 1))/$MAX_ATTEMPTS)"
