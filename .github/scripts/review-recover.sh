#!/bin/bash
# review-recover.sh — review job が runner の打ち切りで cancelled になったとき、watchdog を待たずに review を再起動する (#1950)。
# verify-review-verdict.sh は review job の step なので、runner が落ちる (shutdown signal・job の 60 分超過) と走らない
# (CI-27 #1420: 同じ head で 7 回連続 cancelled)。別 job (review-recover、needs: review) から、新しい runner で呼ぶ。
#
# PM の stop (gh run cancel) では再起動しない: 打ち切りの原因が『runner の shutdown signal / exit 143 / 実行時間超過』と
# job の annotation で確認できたときだけ再起動する。annotation が読めない・該当しない場合は何もしない (fail-closed。
# 取りこぼしは watchdog が拾う)。
# 再起動は verify-review-verdict.sh に委譲する。そちらが (1) PR が open か (2) 現在の head に verdict が無いか
# (3) 同じ head への再起動 (review-retry:<head12> のマーカー) が OC_REVIEW_MAX_ATTEMPTS (既定 3) 回未満か を確かめる。
# 上限は watchdog と共有 (3 回で oc:stuck) なので、無限ループにならない。
#
# 入力 (env): GH_TOKEN (PR の操作。reviewer App か実装 App), RUNS_TOKEN (actions:read + checks:read。省略時は GH_TOKEN),
#             OC_REPO, GITHUB_RUN_ID, GITHUB_EVENT_PATH (pull_request の payload), DRY=1 で再起動せず判定だけ表示
set -uo pipefail

: "${OC_REPO:?}" "${GITHUB_RUN_ID:?}"
R="$OC_REPO"
DRY="${DRY:-0}"
RUNS_TOKEN="${RUNS_TOKEN:-${GH_TOKEN:-}}"
# job の annotation に出る、runner 側の打ち切りを示す文言
CAUSE_RE='shutdown signal|exit code 143|exceeded the maximum execution time'

pr="$(jq -r '.pull_request.number // empty' "${GITHUB_EVENT_PATH:-/dev/null}" 2> /dev/null || true)"
case "$pr" in '' | *[!0-9]*)
  echo "no pull_request number in the event: nothing to recover"
  exit 0
  ;;
esac

if ! job_id="$(GH_TOKEN="$RUNS_TOKEN" gh api "repos/$R/actions/runs/$GITHUB_RUN_ID/jobs" --jq '[.jobs[] | select(.name == "review")][0].id // empty')" || [ -z "$job_id" ]; then
  echo "::warning::could not find the review job of run $GITHUB_RUN_ID: no recovery (the watchdog covers it)"
  exit 0
fi
if ! notes="$(GH_TOKEN="$RUNS_TOKEN" gh api "repos/$R/check-runs/$job_id/annotations" --jq '.[].message')"; then
  echo "::warning::could not read the annotations of job $job_id: no recovery (the watchdog covers it)"
  exit 0
fi
if ! grep -qiE "$CAUSE_RE" <<< "$notes"; then
  echo "the review job was cancelled without a runner shutdown / timeout annotation (a manual cancel?): no recovery"
  exit 0
fi

echo "the review job of run $GITHUB_RUN_ID was cut off by the runner: re-triggering the review of PR #$pr (bounded by the review-retry marker)"
if [ "$DRY" = 1 ]; then
  echo "DRY: verify-review-verdict.sh for PR #$pr"
  exit 0
fi
OC_REPO="$R" OC_PR_NUMBER="$pr" exec bash "$(dirname "$0")/verify-review-verdict.sh"
