#!/bin/bash
# watchdog.sh — open PR を「レビュー中」か「レビューを受けて修正中」のどちらかに保つ (#719)。
#
# 指示 122/123: 修正もレビューもされていない PR (IDLE) を 1 秒も作らない。主経路はイベント駆動
# (差し戻し -> fix、push -> review) だが、イベントの取りこぼし・run の失敗・main の更新による競合は
# イベントが起きないので、push to main と schedule (5 分) でこのスクリプトが全 open PR を点検して戻す。
#
# 判定 (PR ごと)。まず「カバー済み」か:
#   REVIEWING/FIXING : その PR に紐づく実行中/待機中の run がある (pull_request 系は pull_requests に番号が出る。
#                      PM の /oc コメント起動は run のタイトルが PR タイトルと一致する)
# カバーされていなければ IDLE であり、理由ごとに戻す (updated_at が SETTLE 分以内なら、直前の操作の
# イベントが伝播中とみなして次回に回す):
#   CONFLICT          main と競合 (競合 PR は pull_request run が起動しない) -> reviewer App 名義の CHANGES_REQUESTED で fix 経路へ
#   DRAFT             draft -> ready (ready_for_review で review が起動する)
#   FIX_IDLE          現在の head に CHANGES_REQUESTED があるのに fix run が無い -> CHANGES_REQUESTED を再提出して fix 経路へ
#   APPROVED          approve 済みで未 merge -> merge。失敗したら理由付きの CHANGES_REQUESTED
#   NOREVIEW          現在の head に verdict が無い (copilot-pending の COMMENT が OC_COPILOT_PENDING_MINUTES を
#                     超えたものを含む) -> close -> reopen で review を再起動
# 同じ head に対する復旧が尽きた PR (watchdog の差し戻し OC_WATCHDOG_MAX 回、または review の自動再実行 3 回) は
# oc:stuck ラベルを付けて止める。
# 1 回の点検で行う操作は OC_MAX_ACTIONS 件まで (古い更新の PR から)。残りは次回に回す。
#
# 入力 (env): GH_TOKEN (reviewer App。review の提出・merge・ready・close/reopen に使う), OC_REPO,
#             RUNS_TOKEN (actions:read。省略時は GH_TOKEN), DRY=1 で操作せず計画だけ表示
set -uo pipefail

: "${OC_REPO:?}"
R="$OC_REPO"
DRY="${DRY:-0}"
SETTLE_MIN="${OC_SETTLE_MINUTES:-4}"
PENDING_MIN="${OC_COPILOT_PENDING_MINUTES:-20}"
MAX_ACTIONS="${OC_MAX_ACTIONS:-12}"
WD_MAX="${OC_WATCHDOG_MAX:-6}"
RUNS_TOKEN="${RUNS_TOKEN:-${GH_TOKEN:-}}"
now="$(date -u +%s)"
age_min() { echo $(((now - $(date -u -d "$1" +%s)) / 60)); }

do_it() { # do_it <説明> <コマンド...>
  local what="$1"
  shift
  if [ "$DRY" = 1 ]; then
    echo "  DRY: $what"
  else
    echo "  DO : $what"
    "$@" > /dev/null || echo "::warning::failed: $what"
  fi
}
request_changes() { gh pr review "$1" --repo "$R" --request-changes --body "$2"; }
reopen() {
  gh pr close "$1" --repo "$R" && sleep 3 && gh pr reopen "$1" --repo "$R"
}

# 実行中/待機中の run (pull_requests と タイトル)
active="$(for s in in_progress queued pending waiting; do
  GH_TOKEN="$RUNS_TOKEN" gh api "repos/$R/actions/runs?status=$s&per_page=100" \
    --jq '.workflow_runs[] | {event, title: .display_title, prs: [.pull_requests[].number]}'
done | jq -s '.')"

prs="$(gh api --paginate "repos/$R/pulls?state=open&per_page=100" | jq -s 'add | sort_by(.updated_at)')"
total="$(jq length <<< "$prs")"
covered_n=0
acted=0
deferred=0
declare -A tally=()
summary=""

for i in $(seq 0 $((total - 1))); do
  pr="$(jq -c ".[$i]" <<< "$prs")"
  n="$(jq -r .number <<< "$pr")"
  title="$(jq -r .title <<< "$pr")"
  head="$(jq -r .head.sha <<< "$pr")"
  draft="$(jq -r .draft <<< "$pr")"
  created="$(jq -r .created_at <<< "$pr")"
  upd_age="$(age_min "$(jq -r .updated_at <<< "$pr")")"

  if jq -e --argjson n "$n" --arg t "$title" \
    'any(.[]; ((.prs | index($n)) != null) or ((.event == "issue_comment" or .event == "workflow_dispatch") and .title == $t))' \
    <<< "$active" > /dev/null; then
    covered_n=$((covered_n + 1))
    continue
  fi

  # --- IDLE: 理由を判定する ---
  mergeable=null
  for _ in 1 2 3; do
    mergeable="$(gh api "repos/$R/pulls/$n" --jq .mergeable)"
    [ "$mergeable" != null ] && break
    sleep 2
  done
  rvs="$(gh api --paginate "repos/$R/pulls/$n/reviews" \
    | jq -s --arg h "$head" '[.[][] | select((.user.login | startswith("oc-reviewer")) and .commit_id == $h)]')"
  rv="$(jq -c 'last // {}' <<< "$rvs")"
  st="$(jq -r '.state // "NONE"' <<< "$rv")"
  wd_n="$(jq '[.[] | select((.body // "") | contains("(watchdog)"))] | length' <<< "$rvs")"
  retry_n="$(gh api --paginate "repos/$R/issues/$n/comments" \
    | jq -s --arg m "review-retry:${head:0:12}" '[.[][] | select(.body | contains($m))] | length')"

  reason=""
  if [ "$mergeable" = false ]; then
    reason=CONFLICT
  elif [ "$draft" = true ]; then
    reason=DRAFT
  else
    case "$st" in
      CHANGES_REQUESTED) reason=FIX_IDLE ;;
      APPROVED) reason=APPROVED ;;
      COMMENTED)
        if jq -e '.body | contains("copilot-pending")' <<< "$rv" > /dev/null \
          && [ "$(age_min "$created")" -lt "$PENDING_MIN" ]; then
          reason=COPILOT_WAIT
        else
          reason=NOREVIEW
        fi
        ;;
      *) reason=NOREVIEW ;;
    esac
  fi
  tally[$reason]=$((${tally[$reason]:-0} + 1))
  line="#$n $reason (updated ${upd_age}m ago)"
  summary="$summary- $line"$'\n'
  echo "$line"

  # 復旧に失敗し続ける PR を延々と叩かない。同じ head への watchdog の差し戻しが WD_MAX 回、または
  # review の自動再実行が尽きた (review-retry が 3 回) PR は oc:stuck を付けて止める (人の判断が要る)。
  if { [ "$reason" != NOREVIEW ] && [ "$wd_n" -ge "$WD_MAX" ]; } || { [ "$reason" = NOREVIEW ] && [ "$retry_n" -ge 3 ]; }; then
    echo "  STUCK: automatic recovery exhausted on ${head:0:7} (watchdog=$wd_n review-retry=$retry_n): labelled oc:stuck, no further action"
    if [ "$DRY" != 1 ]; then
      gh label create oc:stuck --repo "$R" --color B60205 --description "automatic review/fix recovery exhausted; needs a human decision" --force > /dev/null 2>&1 || true
      gh pr edit "$n" --repo "$R" --add-label oc:stuck > /dev/null 2>&1 || true
    fi
    continue
  fi
  if [ "$reason" = COPILOT_WAIT ] || [ "$upd_age" -lt "$SETTLE_MIN" ]; then
    echo "  skip: waiting (Copilot review pending, or a recent update is still propagating)"
    continue
  fi
  if [ "$acted" -ge "$MAX_ACTIONS" ]; then
    deferred=$((deferred + 1))
    echo "  deferred (reached OC_MAX_ACTIONS=$MAX_ACTIONS)"
    continue
  fi
  acted=$((acted + 1))

  case "$reason" in
    CONFLICT)
      do_it "request-changes (conflict) on #$n" request_changes "$n" \
        "[conflict] main と競合しています (mergeable=false)。競合 PR は review が起動しないため、この差し戻しで修正 run を起動します。origin/main を merge して競合を解消し、push してください (競合解消以外の変更はしない。main 側の変更を消さない)。競合した箇所と解消方針を PR にコメントで報告してください。(watchdog)"
      ;;
    DRAFT)
      do_it "ready #$n" gh pr ready "$n" --repo "$R"
      ;;
    FIX_IDLE)
      do_it "re-request changes on #$n" request_changes "$n" \
        "[watchdog] 現在の head に対する直前の oc-reviewer の差し戻し (CHANGES_REQUESTED) の指摘を、まだ誰も修正していません。その review・inline コメント・Copilot の指摘を読み、修正して push してください。(watchdog)"
      ;;
    APPROVED)
      if [ "$DRY" = 1 ]; then
        echo "  DRY: merge #$n"
      elif gh pr merge "$n" --repo "$R" --merge --delete-branch > /dev/null 2> "${RUNNER_TEMP:-/tmp}/merge-err.txt"; then
        echo "  DO : merged #$n"
      else
        err="$(head -c 300 "${RUNNER_TEMP:-/tmp}/merge-err.txt")"
        echo "  merge failed: $err"
        do_it "request-changes (merge failed) on #$n" request_changes "$n" \
          "[merge-failed] approve 済みですが merge できませんでした: ${err}。原因を解消して push してください。(watchdog)"
      fi
      ;;
    NOREVIEW)
      do_it "reopen #$n (restart the review)" reopen "$n"
      ;;
  esac
done

echo "open=$total covered(REVIEWING/FIXING)=$covered_n idle=$((total - covered_n)) acted=$acted deferred=$deferred"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## PR watchdog"
    echo
    echo "open=$total / covered(REVIEWING・FIXING)=$covered_n / idle=$((total - covered_n)) / acted=$acted / deferred=$deferred"
    echo
    printf '%s' "$summary"
  } >> "$GITHUB_STEP_SUMMARY"
fi
