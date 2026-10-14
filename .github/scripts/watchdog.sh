#!/bin/bash
# watchdog.sh — open PR を「レビュー中」か「レビューを受けて修正中」のどちらかに保つ (#719)。
#
# 指示 122/123: 修正もレビューもされていない PR (IDLE) を 1 秒も作らない。主経路はイベント駆動
# (差し戻し -> fix、push -> review) だが、イベントの取りこぼし・run の失敗・main の更新による競合は
# イベントが起きないので、push to main と schedule (5 分) でこのスクリプトが全 open PR を点検して戻す。
#
# 判定 (PR ごと)。まず「カバー済み」か:
#   REVIEWING/FIXING : その PR に紐づく実行中/待機中の opencode.yaml の run がある (pull_request 系は pull_requests に番号が出る。
#                      PM の /oc コメント起動は run のタイトルが PR タイトルと一致する)
# カバーされていなければ IDLE であり、理由ごとに戻す (updated_at が SETTLE 分以内なら、直前の操作の
# イベントが伝播中とみなして次回に回す):
#   CONFLICT          main と競合。競合 PR は pull_request も pull_request_review も起動しないため、差し戻しでは fix を動かせない
#                     (往復回数だけ消費して oc:stuck に近づく)。差し戻しは出さず、repository_dispatch (type oc-fix) で fix モードの
#                     実装 run を起動する (同じ head へは DISPATCH_MAX 回まで。超えたら oc:stuck。#731)。
#                     fork からの PR は dispatch しない (write 権限の run を第三者の入力で動かさないため。oc:stuck も付けず一覧に出すだけ)
#   DRAFT             draft -> ready (ready_for_review で review が起動する)
#   FIX_IDLE          現在の head に CHANGES_REQUESTED があるのに fix run が無い -> CHANGES_REQUESTED を再提出して fix 経路へ
#   APPROVED          approve 済みで未 merge -> merge。失敗したら理由付きの CHANGES_REQUESTED
#   NOREVIEW          現在の head に verdict (APPROVED / CHANGES_REQUESTED) が無い。COMMENT だけの review も含む
#                     (Copilot 待ちの保留は廃止した) -> close -> reopen で review を再起動
# 同じ head に対する復旧が尽きた PR (watchdog の差し戻し OC_WATCHDOG_MAX 回、または review の自動再実行 3 回) は
# oc:stuck ラベルを付けて止める。fix-progress.sh が差し戻しの上限 (OC_MAX_FIX_REVIEWS) で付けるラベルも同じで、ラベル付きの PR は
# 人 (PM) の判断待ちとして一切触らない (ラベルを外すと再開する)。
# merge は --match-head-commit で、点検した head 以外 (その後に push された未レビューの commit) を巻き込まない。
# 1 回の点検で行う操作 (oc:stuck の付与を含む) は OC_MAX_ACTIONS 件まで (古い更新の PR から)。残りは次回に回す。
# 読み取りに失敗した PR・mergeable が未確定の PR は、その回は何も操作せず次回に回す (fail-closed)。
# fork からの PR (head.repo が本リポジトリでない) は CONFLICT でも dispatch しない (write 権限の run を第三者の入力で動かさない)。一覧に出して人が判断する。
#
# 宙に浮いた issue (blocked でも着手済みでもない open issue) は、最後に floating-issues=N として数えて出力する (数えるだけ。#1950)。
#
# 入力 (env): GH_TOKEN (reviewer App。review の提出・merge・ready・close/reopen に使う), OC_REPO,
#             RUNS_TOKEN (actions:read。省略時は GH_TOKEN), DRY=1 で操作せず計画だけ表示
set -uo pipefail

: "${OC_REPO:?}"
R="$OC_REPO"
DRY="${DRY:-0}"
REVIEWER_LOGIN="${OC_REVIEWER_LOGIN:-oc-reviewer-for-signature-studio[bot]}"
SETTLE_MIN="${OC_SETTLE_MINUTES:-4}"
MAX_ACTIONS="${OC_MAX_ACTIONS:-12}"
WD_MAX="${OC_WATCHDOG_MAX:-6}"
# 同じ head に対する競合解消の dispatch の上限 (超えたら oc:stuck)
DISPATCH_MAX="${OC_DISPATCH_MAX:-3}"
ARTIFACT_RE='^(fl-win64|plugins-(ott|freshair|serum2|massivex|kilohearts)|toolchain-(retdec|emsdk)|work-(m11|liftdiff|m6-ott|liftlib-targets|liftlib|icall|fw-stage1)|analysis-(ott-binaries|mac-shared)|apt-mingw)$'
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
reopen() { # reopen <PR> <head>: 試行を数えるマーカー付きのコメントを残してから reopen する (verify-review-verdict.sh と同じ書式)
  local marker="review-retry:${2:0:12}"
  gh pr comment "$1" --repo "$R" \
    --body "[watchdog] 現在の head (${2:0:7}) に verdict が無いため、review を再起動します。<!-- $marker -->" || true
  OC_REPO="$R" OC_PR_NUMBER="$1" bash "$(dirname "$0")/reopen-pr.sh"
}
dispatch_fix() { # dispatch_fix <PR> <head> <reason> <artifacts>: 試行を数えるマーカー付きのコメント -> repository_dispatch (oc-fix)
  local marker="oc-dispatch:${2:0:12}"
  gh pr comment "$1" --repo "$R" \
    --body "[watchdog] この PR は main と競合しています。競合 PR は review イベントでワークフローが起動しないため、repository_dispatch で競合解消の実装 run を起動します (head ${2:0:7})。<!-- $marker -->" || true
  gh api -X POST "repos/$R/dispatches" -f event_type=oc-fix \
    -F "client_payload[pr]=$1" -f "client_payload[reason]=$3" -f "client_payload[artifacts]=$4"
}
pr_artifacts() { # pr_artifacts <PR JSON>: PR 本文の oc_artifacts 行から、allowlist に一致する語だけを取り出す
  local line name out=""
  line="$(jq -r '.body // ""' <<< "$1" | grep -m1 -E '^[[:space:]]*oc_artifacts:' || true)"
  for name in $(printf '%s' "${line#*oc_artifacts:}" | tr -cd 'a-z0-9 -'); do
    printf '%s' "$name" | grep -qE "$ARTIFACT_RE" && out="${out:+$out }$name"
  done
  printf '%s' "$out"
}
mark_stuck() { # mark_stuck <PR>
  gh label create oc:stuck --repo "$R" --color B60205 --description "automatic review/fix recovery exhausted; needs a human decision" --force > /dev/null 2>&1 || true
  gh pr edit "$1" --repo "$R" --add-label oc:stuck > /dev/null 2>&1 || true
}

# 実行中/待機中の run (pull_requests・タイトル・workflow のファイル)。一覧が取れなければ何も操作しない。
active_raw=""
for s in in_progress queued pending waiting; do
  if ! out="$(GH_TOKEN="$RUNS_TOKEN" gh api "repos/$R/actions/runs?status=$s&per_page=100" \
    --jq '.workflow_runs[] | {event, title: .display_title, path, sha: (.head_sha // ""), prs: [.pull_requests[].number]}')"; then
    echo "::error::failed to list $s runs; no action this pass"
    exit 1
  fi
  active_raw+="$out"$'\n'
done
active="$(jq -s '.' <<< "$active_raw")"

if ! pr_raw="$(gh api --paginate "repos/$R/pulls?state=open&per_page=100")"; then
  echo "::error::failed to list open PRs; no action this pass"
  exit 1
fi
prs="$(jq -s 'add // [] | sort_by(.updated_at)' <<< "$pr_raw")"
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
  upd_age="$(age_min "$(jq -r .updated_at <<< "$pr")")"

  # pull_request 系の run は head が現在の head と一致するものだけ担当にする (古い head の run で IDLE を隠さない)。
  # head_sha を持たない run (dispatch・comment 等) は従来どおり番号・タイトルで判定する。
  if jq -e --argjson n "$n" --arg t "$title" --arg h "$head" \
    'any(.[]; .path == ".github/workflows/opencode.yaml" and (((.prs | index($n)) != null and ((.sha // "") == "" or .sha == $h)) or ((.event == "issue_comment" or .event == "workflow_dispatch") and .title == $t) or (.event == "repository_dispatch" and .title == ("oc-fix #" + ($n | tostring)))))' \
    <<< "$active" > /dev/null; then
    covered_n=$((covered_n + 1))
    continue
  fi

  if jq -e '[.labels[].name] | index("oc:stuck") != null' <<< "$pr" > /dev/null; then
    echo "#$n STUCK_LABELLED: oc:stuck is set, waiting for a human decision"
    tally[STUCK_LABELLED]=$((${tally[STUCK_LABELLED]:-0} + 1))
    continue
  fi

  # --- IDLE: 理由を判定する。読めなかった PR・未確定の mergeable は操作せず次回に回す ---
  mergeable=null
  for _ in 1 2 3; do
    if ! detail="$(gh api "repos/$R/pulls/$n")"; then
      echo "#$n skip: failed to read the PR (no action this pass)"
      continue 2
    fi
    mergeable="$(jq -r .mergeable <<< "$detail")"
    [ "$mergeable" != null ] && break
    sleep "${OC_MERGEABLE_WAIT:-2}"
  done
  if [ "$mergeable" = null ]; then
    echo "#$n skip: mergeability is still unknown (checked next pass)"
    continue
  fi
  if ! rvs_raw="$(gh api --paginate "repos/$R/pulls/$n/reviews")"; then
    echo "#$n skip: failed to read reviews (no action this pass)"
    continue
  fi
  if ! cm_raw="$(gh api --paginate "repos/$R/issues/$n/comments")"; then
    echo "#$n skip: failed to read comments (no action this pass)"
    continue
  fi
  rvs="$(jq -s --arg h "$head" --arg who "$REVIEWER_LOGIN" \
    '[.[][] | select(.user.login == $who and .user.type == "Bot" and .commit_id == $h)]' <<< "$rvs_raw")"
  # verdict を持つ最後の review で判定する (verify-review-verdict.sh と同じ。COMMENTED は verdict ではない)
  rv="$(jq -c '[.[] | select(.state == "APPROVED" or .state == "CHANGES_REQUESTED")] | last // {}' <<< "$rvs")"
  st="$(jq -r '.state // "NONE"' <<< "$rv")"
  wd_n="$(jq '[.[] | select((.body // "") | contains("(watchdog)"))] | length' <<< "$rvs")"
  retry_n="$(jq -s --arg m "review-retry:${head:0:12}" --arg who "$REVIEWER_LOGIN" \
    '[.[][] | select(.user.login == $who and .user.type == "Bot" and (.body | contains($m)))] | length' <<< "$cm_raw")"

  disp_n="$(jq -s --arg m "oc-dispatch:${head:0:12}" --arg who "$REVIEWER_LOGIN" \
    '[.[][] | select(.user.login == $who and .user.type == "Bot" and (.body | contains($m)))] | length' <<< "$cm_raw")"

  reason=""
  if [ "$mergeable" = false ]; then
    reason=CONFLICT
  elif [ "$draft" = true ]; then
    reason=DRAFT
  else
    case "$st" in
      CHANGES_REQUESTED) reason=FIX_IDLE ;;
      APPROVED) reason=APPROVED ;;
      *) reason=NOREVIEW ;;
    esac
  fi
  tally[$reason]=$((${tally[$reason]:-0} + 1))
  line="#$n $reason (updated ${upd_age}m ago)"
  summary="$summary- $line"$'\n'
  echo "$line"

  # fork からの PR は dispatch しない: dispatch の run は write 権限で動き、fork の本文・コメント・ブランチ内容は第三者が書ける。
  # head.repo が読めない (削除された fork など) 場合も fork とみなす。oc:stuck は付けず、人が判断する。
  if [ "$reason" = CONFLICT ] && [ "$(jq -r '.head.repo.full_name // ""' <<< "$pr")" != "$R" ]; then
    echo "  skip: fork からの PR は自動対応しない (人が判断する。oc:stuck は付けない)"
    continue
  fi

  if [ "$upd_age" -lt "$SETTLE_MIN" ]; then
    echo "  skip: a recent update is still propagating"
    continue
  fi
  if [ "$acted" -ge "$MAX_ACTIONS" ]; then
    deferred=$((deferred + 1))
    echo "  deferred (reached OC_MAX_ACTIONS=$MAX_ACTIONS)"
    continue
  fi
  acted=$((acted + 1))

  # 復旧に失敗し続ける PR を延々と叩かない。同じ head への watchdog の差し戻しが WD_MAX 回、または
  # review の自動再実行が尽きた (review-retry が 3 回) PR は oc:stuck を付けて止める (人の判断が要る)。
  if { [ "$reason" != NOREVIEW ] && [ "$reason" != CONFLICT ] && [ "$wd_n" -ge "$WD_MAX" ]; } || { [ "$reason" = NOREVIEW ] && [ "$retry_n" -ge 3 ]; } || { [ "$reason" = CONFLICT ] && [ "$disp_n" -ge "$DISPATCH_MAX" ]; }; then
    echo "  STUCK: automatic recovery exhausted on ${head:0:7} (watchdog=$wd_n review-retry=$retry_n dispatch=$disp_n): labelled oc:stuck, no further action"
    do_it "oc:stuck on #$n" mark_stuck "$n"
    continue
  fi

  case "$reason" in
    CONFLICT)
      # 競合 PR は pull_request / pull_request_review のどちらでも起動しないので、差し戻しでは fix を動かせない (#731)。
      # repository_dispatch は競合に左右されない。
      do_it "dispatch oc-fix (conflict) for #$n" dispatch_fix "$n" "$head" conflict "$(pr_artifacts "$pr")"
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
      elif gh pr merge "$n" --repo "$R" --merge --delete-branch --match-head-commit "$head" > /dev/null 2> "${RUNNER_TEMP:-/tmp}/merge-err.txt"; then
        echo "  DO : merged #$n"
      else
        err="$(head -c 300 "${RUNNER_TEMP:-/tmp}/merge-err.txt")"
        echo "  merge failed: $err"
        do_it "request-changes (merge failed) on #$n" request_changes "$n" \
          "[merge-failed] approve 済みですが merge できませんでした: ${err}。原因を解消して push してください。(watchdog)"
      fi
      ;;
    NOREVIEW)
      do_it "reopen #$n (restart the review)" reopen "$n" "$head"
      ;;
  esac
done

# --- 宙に浮いた issue の集計 (数えるだけ。何も操作しない。launch は PM Worker の責務) (#1950) ---
# 依頼者指示: 全ての issue は常に『blocked』『着手済み』『closed』のいずれかであるべき。
# 宙に浮いている = open issue で、次のどれにも当たらないもの:
#   blocked   : ラベル blocked、または GitHub の issue dependencies に open な blocker がある (issue_dependencies_summary.blocked_by > 0)
#   着手済み   : この issue を指す open PR がある (ブランチ名 <N>-... か本文の Closes/Refs/Fixes #N)、または実行中の implement run がある
#               (issue_comment / workflow_dispatch の run で、run のタイトルが issue のタイトルと一致する)
#   明示的な終了状態 : ラベル oc:no-pr (implement run が PR も push も出さずに終了した印。record-run-outcome.sh)、needs-user-input、oc:stuck
# 本文の『依存: #N』『親: #N』による待ちは見ない (PM Worker の分類の責務)。そのため、これは上限値の目安である。
# 一覧が取れなければ警告だけ出し、PR の点検結果には影響させない。
floating_line="floating-issues=unknown (could not list open issues)"
if iss_raw="$(gh api --paginate "repos/$R/issues?state=open&per_page=100" 2> /dev/null)"; then
  floating="$(jq -s --argjson prs "$prs" --argjson active "$active" '
    [ .[][] | select(.pull_request == null)
      | . as $i
      | select(([$i.labels[].name] | any(. == "blocked" or . == "oc:no-pr" or . == "needs-user-input" or . == "oc:stuck")) | not)
      | select((($i.issue_dependencies_summary.blocked_by // 0) > 0) | not)
      | select(any($prs[]; ((.head.ref // "") | test("^" + ($i.number | tostring) + "-")) or ((.body // "") | test("(Closes|Refs|Fixes|Resolves) #" + ($i.number | tostring) + "([^0-9]|$)"; "i"))) | not)
      | select(any($active[]; .path == ".github/workflows/opencode.yaml" and (.event == "issue_comment" or .event == "workflow_dispatch") and (.title | gsub("^\\s+|\\s+$"; "")) == ($i.title | gsub("^\\s+|\\s+$"; ""))) | not)
      | $i.number ] | sort' <<< "$iss_raw" 2> /dev/null)" || floating=""
  if [ -n "$floating" ]; then
    floating_n="$(jq length <<< "$floating")"
    floating_line="floating-issues=$floating_n (open, not blocked, no open PR, no running implement run, none of oc:no-pr / needs-user-input / oc:stuck)"
    [ "$floating_n" -gt 0 ] && floating_line="$floating_line first: $(jq -r '.[0:20] | map("#" + tostring) | join(" ")' <<< "$floating")"
  fi
fi
echo "$floating_line"

echo "open=$total covered(REVIEWING/FIXING)=$covered_n idle=$((total - covered_n)) acted=$acted deferred=$deferred"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## PR watchdog"
    echo
    echo "open=$total / covered(REVIEWING・FIXING)=$covered_n / idle=$((total - covered_n)) / acted=$acted / deferred=$deferred"
    echo
    echo "$floating_line"
    echo
    printf '%s' "$summary"
  } >> "$GITHUB_STEP_SUMMARY"
fi
