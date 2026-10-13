#!/bin/bash
# find_unreviewed.sh — head commit に oc-reviewer の review が付いておらず、かつ
# その head の review run が既に終了している ready PR を列挙する (GraphQL 1 回)。
# 出力: "<PR>|<head7>|<pr_body の oc_artifacts 行 or NONE>"
# これに該当する PR は rerun_review.sh <PR> で再起動する。
set -uo pipefail
R="${REPO:-signature-studio/signature-studio-dev}"
owner="${R%/*}"; name="${R#*/}"
gh api graphql -f query="{repository(owner:\"$owner\",name:\"$name\"){pullRequests(states:OPEN,first:100){nodes{number isDraft headRefOid body reviews(last:20){nodes{author{login} commit{oid}}}}}}}" \
  --jq '.data.repository.pullRequests.nodes[]
    | select(.isDraft|not)
    | . as $p
    | select(([$p.reviews.nodes[] | select(.author.login|startswith("oc-reviewer")) | select(.commit.oid == $p.headRefOid)] | length) == 0)
    | "\(.number)|\(.headRefOid[0:7])|\((.body | split("\n") | map(select(startswith("oc_artifacts:"))) | first) // "NONE")"'
