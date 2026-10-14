#!/bin/bash
# no-pr-outcome.sh — issue の実装 run が PR も push も無く終わったとき、その理由を issue に残す (#1950)。
# 着手報告・停止報告・分割・素材不足だけで終わった issue が「ブロックも着手済みも無い」まま宙に浮くのを防ぐ。
# PM (tools/pm/launch_issues.py) は oc:no-pr と理由マーカーを見て、再着手・停止を決める。
#
# 判定 (対象は issue。PR への /oc は issue JSON の pull_request で除外する):
#   この run が PR を作った・更新した (head ブランチが N- で始まる PR)  -> oc:no-pr を外す
#   oc:stuck / needs-user-input / 開いた blocked_by がある              -> 何もしない (人・PM の判断中)
#   それ以外                                                            -> oc:no-pr を付け、理由付きマーカーのコメントを残す
# reason は run の text から決める。語彙は tools/pm/launch_issues.py の stop_re と揃える:
#   artifact | split | blocked | stop | unknown
# 読み取りに失敗したら何もしない (fail-closed)。push だけで PR を出さなかった run は検出しない (既知の限界)。
#
# 入力 (env): GH_TOKEN, OC_REPO, OC_ISSUE_NUMBER (空なら何もしない),
#             OC_RUN_START (run の開始時刻 UTC、ISO 8601), OC_RUN_ID, OC_RUN_FILE (opencode の JSONL。無くてもよい)
set -uo pipefail

: "${OC_REPO:?}"
R="$OC_REPO"
N="${OC_ISSUE_NUMBER:-}"
LABEL=oc:no-pr
if [ -z "$N" ]; then
  echo "no issue number: nothing to record"
  exit 0
fi

if ! issue_json="$(gh api "repos/$R/issues/$N")"; then
  echo "::warning::failed to read issue #$N; no action"
  exit 0
fi
if jq -e 'has("pull_request")' <<< "$issue_json" > /dev/null; then
  echo "#$N is a pull request: out of scope"
  exit 0
fi

labels=" $(jq -r '[.labels[].name] | join(" ")' <<< "$issue_json") "
has_label() { [[ "$labels" == *" $1 "* ]]; }

# この run が作った・更新した PR (head ブランチは N-<slug>)。開始時刻 (OC_RUN_START) が無ければ数えない (fail-closed)。
if [ -z "${OC_RUN_START:-}" ]; then
  echo "::warning::OC_RUN_START is unset; no action"
  exit 0
fi
if ! pr_n="$(gh api --paginate "repos/$R/pulls?state=all&per_page=100" \
  --jq ".[] | select(.head.ref | startswith(\"$N-\")) | select((.created_at >= \"$OC_RUN_START\") or (.updated_at >= \"$OC_RUN_START\")) | .number")"; then
  echo "::warning::failed to list PRs; no action"
  exit 0
fi
if [ -n "$pr_n" ]; then
  echo "#$N: this run made PR #$(head -n 1 <<< "$pr_n"): not a no-PR outcome"
  if has_label "$LABEL"; then
    gh issue edit "$N" --repo "$R" --remove-label "$LABEL" > /dev/null 2>&1 || true
  fi
  exit 0
fi

if has_label oc:stuck || has_label needs-user-input; then
  echo "#$N has oc:stuck or needs-user-input: a human decision is pending, nothing to record"
  exit 0
fi
if ! open_blockers="$(gh api "repos/$R/issues/$N/dependencies/blocked_by" --jq '[.[] | select(.state == "open")] | length')"; then
  echo "::warning::failed to read blocked_by of #$N; no action"
  exit 0
fi
if [ "$open_blockers" -gt 0 ]; then
  echo "#$N is blocked by $open_blockers open issue(s): nothing to record"
  exit 0
fi

text=""
if [ -s "${OC_RUN_FILE:-/nonexistent}" ]; then
  text="$(jq -Rr 'fromjson? | select(.type == "text") | .part.text // empty' "$OC_RUN_FILE" 2> /dev/null)"
fi
reason=unknown
if grep -qE '素材|oc_artifacts' <<< "$text"; then
  reason=artifact
elif grep -qE '分割|子 ?issue|起票' <<< "$text"; then
  reason=split
elif grep -qE 'ブロック|blocked|依存|先行' <<< "$text"; then
  reason=blocked
elif grep -qE '停止|着手不可|着手できません|判断を|PM に' <<< "$text"; then
  reason=stop
fi

gh label create "$LABEL" --repo "$R" --color FBCA04 \
  --description "the implement run ended without a PR or push" --force > /dev/null 2>&1 || true
if ! gh issue edit "$N" --repo "$R" --add-label "$LABEL" > /dev/null; then
  echo "::warning::failed to add $LABEL to #$N"
  exit 0
fi
gh issue comment "$N" --repo "$R" --body "実装 run (run ${OC_RUN_ID:-unknown}) が PR も push も無く終了したため、\`${LABEL}\` を付けました (reason: ${reason})。次の run が PR を出すと外れます。<!-- oc-run-outcome: no-pr reason=${reason} run=${OC_RUN_ID:-unknown} -->" > /dev/null || true
echo "#$N recorded: no-pr reason=$reason"
