#!/bin/bash
# verify-review-verdict.sh — review run が verdict を投稿したかを検証し、無ければ review を再起動する (#719)。
# 指示 122/123: reviewer が success で終わっても verdict を出さないと、その PR は「レビューもされず
# 修正もされない」状態になる (PR #462: run 38349343991 は success、oc-reviewer の review は 0 件だった)。
#
# 正当な終わり方:
#   - PR が merge / close された
#   - 現在の head に対する oc-reviewer の review が APPROVED または CHANGES_REQUESTED
#   - この run が見ていた head より PR の head が進んでいる (進んだ push の synchronize が
#     新しい review run を起動済みなので、古い head の欠落は問わない)
# COMMENT だけの review は verdict と認めない (Copilot 待ちの保留は廃止した: Copilot の review は
# 来ないことがあり、保留した PR は誰にも動かされず止まるため)。
# それ以外は reopen-pr.sh (close -> reopen) で review を再起動する。同じ head に
# OC_REVIEW_MAX_ATTEMPTS 回再起動しても verdict が出なければ PR に警告を残して失敗する。
#
# 入力 (env): GH_TOKEN, OC_REPO, OC_PR_NUMBER
set -euo pipefail

# 前提 (OC_REPO / OC_PR_NUMBER) が無い = 「Prepare PR context」が失敗して review 自体が走らなかった。
# 検証する対象が無いので、ここで失敗を重ねず何もせず終わる (失敗の原因は prepare 側の step に出ている)。
if [ -z "${OC_REPO:-}" ] || [ -z "${OC_PR_NUMBER:-}" ]; then
  echo "OC_REPO / OC_PR_NUMBER is unset: no review run to verify"
  exit 0
fi
MAX_ATTEMPTS="${OC_REVIEW_MAX_ATTEMPTS:-3}"
REVIEWER_LOGIN="${OC_REVIEWER_LOGIN:-oc-reviewer-for-signature-studio[bot]}"

pr="$(gh api "repos/$OC_REPO/pulls/$OC_PR_NUMBER")"
state="$(jq -r .state <<< "$pr")"
if [ "$state" != open ]; then
  echo "PR #$OC_PR_NUMBER is $state: nothing to verify"
  exit 0
fi
head="$(jq -r .head.sha <<< "$pr")"

# この run が起動された時点の head (pull_request イベントの payload)。push で進んでいれば、
# その synchronize が起動した review run が現在の head を担当する。
run_head="$(jq -r '.pull_request.head.sha // empty' "${GITHUB_EVENT_PATH:-/dev/null}" 2> /dev/null || true)"
if [ -n "$run_head" ] && [ "$run_head" != "$head" ]; then
  echo "head moved ${run_head:0:7} -> ${head:0:7} during the run: the review run for the new head handles it"
  exit 0
fi

# verdict は APPROVED / CHANGES_REQUESTED だけ。「verdict を持つ最後の review」で判定する
# (APPROVED の後に COMMENTED が付いても、最後の review の state だけで見ると verdict 無しと誤判定する)。
rv="$(gh api --paginate "repos/$OC_REPO/pulls/$OC_PR_NUMBER/reviews" \
  | jq -s --arg h "$head" --arg l "$REVIEWER_LOGIN" '[.[][] | select(.user.login == $l and .commit_id == $h and (.state == "APPROVED" or .state == "CHANGES_REQUESTED"))] | last // {}')"
st="$(jq -r '.state // "NONE"' <<< "$rv")"

# 差し戻し本文の構造化マーカー (reviewer.md 参照) を検査する。警告のみで、verdict と終了コードは変えない (#2320)。
check_review_marker() {
  local body marker known="doc remeasure artifact closes path conflict code pm-decision user-decision" v c k
  body="$(jq -r '.body // ""' <<< "$rv")"
  marker="$(printf '%s\n' "$body" | grep -E '<!-- oc-review:' | tail -n 1 || true)"
  if [ -z "$marker" ]; then
    echo "::warning::CHANGES_REQUESTED on ${head:0:7} has no <!-- oc-review: v=1 ... --> marker"
    return 0
  fi
  if [ "$(printf '%s\n' "$body" | grep -v '^[[:space:]]*$' | tail -n 1)" != "$marker" ]; then
    echo "::warning::oc-review marker on ${head:0:7} is not the last line of the body"
  fi
  v="$(grep -oE 'v=[^ ]*' <<< "$marker" | head -n 1 || true)"
  if [ "$v" != v=1 ]; then
    echo "::warning::oc-review marker on ${head:0:7} has unsupported version: ${v:-none}"
  fi
  c="$(grep -oE 'classes=[^ ]*' <<< "$marker" | head -n 1 | cut -d= -f2- || true)"
  for k in ${c//,/ }; do
    case " $known " in
      *" $k "*) ;;
      *) echo "::warning::oc-review marker on ${head:0:7} has unknown class: ${k:-<empty>}" ;;
    esac
  done
  return 0
}

case "$st" in
  APPROVED)
    echo "verdict on ${head:0:7}: $st"
    exit 0
    ;;
  CHANGES_REQUESTED)
    check_review_marker
    echo "verdict on ${head:0:7}: $st"
    exit 0
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
bash "$(dirname "$0")/reopen-pr.sh"
echo "re-triggered the review for PR #$OC_PR_NUMBER (retry $((tries + 1))/$MAX_ATTEMPTS)"
