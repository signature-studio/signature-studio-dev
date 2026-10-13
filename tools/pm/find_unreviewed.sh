#!/bin/bash
# find_unreviewed.sh — head commit に oc-reviewer の review が付いておらず、かつ
# その head の review run が既に終了している ready PR を列挙する (REST、全ページ)。
# 出力: "<PR>|<head7>|<pr_body の oc_artifacts 行 or NONE>"
# これに該当する PR は rerun_review.sh <PR> で再起動する。
set -uo pipefail
R="${REPO:-signature-studio/signature-studio-dev}"
gh api --paginate "repos/$R/pulls?state=open&per_page=100" \
  --jq '.[] | select(.draft|not) | [.number, .head.sha, (((.body // "") | split("\n") | map(select(startswith("oc_artifacts:"))) | first) // "NONE")] | @tsv' |
while IFS=$'\t' read -r n sha art; do
  hit="$(gh api --paginate "repos/$R/pulls/$n/reviews" --jq ".[] | select(.user.login|startswith(\"oc-reviewer\")) | select(.commit_id==\"$sha\") | .id" | wc -l)"
  [ "$hit" = 0 ] && echo "$n|${sha:0:7}|$art"
done
