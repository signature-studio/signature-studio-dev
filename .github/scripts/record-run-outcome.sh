#!/bin/bash
# record-run-outcome.sh — implement run (issue_comment) の終了時の不変条件 (#1950)。
# 依頼者指示: 全ての issue は常に『blocked』『着手済み』『closed』のいずれかであるべき。
# 実測: implement run の約 70% は PR を出さずに終わり (着手報告のみ・停止報告・1 run に収まらない・素材不足)、
# その issue は誰にも扱われないまま宙に浮いていた。
#
# run の最後 (workflow の if: always() の step) で、issue が次のどれかかを判定する:
#   closed                              : 何もしない (oc:no-pr を外す)
#   明示的な終了状態                     : oc:stuck / needs-user-input / blocked (ラベル、または依存 issue が open) -> 何もしない (oc:no-pr を外す)
#   着手済み                            : この issue を指す open PR がある、または run の開始以降に作成・merge された PR がある (ブランチ名 <N>-... か本文の Closes/Refs/Fixes #N。run 中に open→merge まで済んだ PR を含む) -> 何もしない (oc:no-pr を外す)
#   上のどれでもない (PR も push も無い)   : ラベル oc:no-pr と構造化コメントを残す
#       <!-- oc-run-outcome: no-pr reason=<stop|split|blocked|artifact|unknown> [cause=rate_limit] run=<run id> -->
# PM Worker はコメント本文を解析せず、ラベルとマーカーで判断する。oc:no-pr は次の run が PR を出したときこの script が外す。
# 率制限 (opencode の error 行の rate_limit_error / HTTP 429) は detect-rate-limit.sh で判定し、annotation を出して cause=rate_limit を入れる (#2344)。
#
# reason は agent の最終回答 (opencode の JSONL の最後の text) から決める。語彙は tools/pm/launch_issues.py の stop_re / NEED_RE と同じ:
#   artifact : 素材不足 (素材名・oc_artifacts の要求)    blocked : 依存 issue・前提 PR 未 merge・ブロック
#   split    : 1 run に収まらない・分割                  stop    : 判断待ち・停止報告・着手不可
#   unknown  : 上のどれでもない (着手報告のみ・run の失敗/cancel を含む)   優先順は artifact > blocked > split > stop。
#
# この script は run を失敗させない (観測用)。読み取り・書き込みに失敗したら警告だけ出して 0 で終わる。
# 入力 (env): GH_TOKEN (issues:write の App token), OC_REPO, OC_ISSUE_NUMBER, GITHUB_RUN_ID, GITHUB_EVENT_NAME, GITHUB_EVENT_PATH
# 任意 (env): OC_JOB_STATUS (job.status), OC_OUTPUT_FILE (既定 $RUNNER_TEMP/oc-output.jsonl), OC_NOPR_LABEL (既定 oc:no-pr), DRY=1
# コメント本文に agent を起動する語 (行頭の slash + oc 等) を入れない (自分のコメントで implement を起動しないため)。
set -uo pipefail
export LC_ALL=C.UTF-8

NOPR_LABEL="${OC_NOPR_LABEL:-oc:no-pr}"
DRY="${DRY:-0}"
EVENT="${GITHUB_EVENT_NAME:-}"
EV="${GITHUB_EVENT_PATH:-/dev/null}"

if [ "$EVENT" != issue_comment ]; then
  echo "event=$EVENT: not an issue /oc run, nothing to record"
  exit 0
fi
if [ -n "$(jq -r '.issue.pull_request // empty' "$EV" 2> /dev/null)" ]; then
  echo "the comment is on a PR: the PR is the vehicle, nothing to record"
  exit 0
fi
: "${OC_REPO:?}"
R="$OC_REPO"
N="${OC_ISSUE_NUMBER:-}"
case "$N" in '' | *[!0-9]*)
  echo "::notice::no issue number: nothing to record"
  exit 0
  ;;
esac
det="$(bash "$(dirname "$0")/detect-rate-limit.sh")"
[ -n "$det" ] && printf '%s\n' "$det"
cause="$(sed -n 's/^cause=//p' <<< "$det")"
if [ -z "${GH_TOKEN:-}" ]; then
  echo "::warning::no token: the run outcome is not recorded"
  exit 0
fi

classify() { # classify <text> -> reason
  local t="$1"
  if grep -qE '素材不足|素材.{0,12}(無い|ない|不足|未配置|未展開|欠|足りな)|oc_artifacts|素材名' <<< "$t"; then
    echo artifact
  elif grep -qE '依存 ?issue|依存.{0,8}#[0-9]+|前提.{0,20}(未 ?merge|未マージ|未完)|blockedBy|ブロッカー|ブロック|先行 PR|先行.{0,6}#[0-9]+' <<< "$t"; then
    echo blocked
  elif grep -qE '1 ?run に収まらない|収まらない|上限に(達|収)|分割|子 issue' <<< "$t"; then
    echo split
  elif grep -qE '着手不可|着手できません|着手に必要|停止します|停止報告|PM に.*依頼|判断を|判断待ち' <<< "$t"; then
    echo stop
  else
    echo unknown
  fi
}

remove_label() { # 付いていれば外す (外す必要が無ければ API を呼ばない)
  jq -e --arg l "$NOPR_LABEL" '[.labels[].name] | index($l) != null' <<< "$issue" > /dev/null || return 0
  if [ "$DRY" = 1 ]; then
    echo "DRY: remove $NOPR_LABEL from #$N"
  else
    gh api -X DELETE "repos/$R/issues/$N/labels/${NOPR_LABEL//:/%3A}" > /dev/null 2>&1 \
      || echo "::warning::could not remove $NOPR_LABEL from #$N"
    echo "removed $NOPR_LABEL from #$N"
  fi
}

if ! issue="$(gh api "repos/$R/issues/$N")"; then
  echo "::warning::could not read issue #$N: the run outcome is not recorded"
  exit 0
fi

if [ "$(jq -r .state <<< "$issue")" != open ]; then
  echo "issue #$N is closed: nothing to record"
  remove_label
  exit 0
fi

if jq -e '([.labels[].name] | any(. == "oc:stuck" or . == "needs-user-input" or . == "blocked")) or ((.issue_dependencies_summary.blocked_by // 0) > 0)' <<< "$issue" > /dev/null; then
  echo "issue #$N is in an explicit state (oc:stuck / needs-user-input / blocked): nothing to record"
  remove_label
  exit 0
fi

if ! prs_raw="$(gh api --paginate "repos/$R/pulls?state=open&per_page=100")"; then
  echo "::warning::could not list open PRs: the run outcome is not recorded"
  exit 0
fi
if jq -s -e --argjson n "$N" '[.[][] | select(((.head.ref // "") | test("^" + ($n | tostring) + "-")) or ((.body // "") | test("(Closes|Refs|Fixes|Resolves) #" + ($n | tostring) + "([^0-9]|$)"; "i")))] | length > 0' <<< "$prs_raw" > /dev/null; then
  echo "issue #$N has an open PR: started"
  remove_label
  exit 0
fi

# open の一覧には、run 中に open→merge まで済んだ PR (数秒で merge されたもの) が出ない。run の開始 (起動したコメントの created_at。
# 無ければ run の run_started_at) 以降に作成・merge された PR を数える。updated 降順に読み、run の開始より前に更新された PR が
# 出たところで止める (作成・merge された PR は必ず開始以降に更新されている)。読めなければ、上限まで読めなければ、何も書かない。
start="$(jq -r '.comment.created_at // empty' "$EV" 2> /dev/null)"
if [ -z "$start" ]; then
  start="$(gh api "repos/$R/actions/runs/${GITHUB_RUN_ID:-0}" --jq '.run_started_at // empty' 2> /dev/null)" || start=""
fi
if [ -z "$start" ]; then
  echo "::warning::could not read the run start: the run outcome is not recorded"
  exit 0
fi
recent_raw=""
complete=0
for page in 1 2 3 4 5 6 7 8 9 10; do
  if ! p="$(gh api "repos/$R/pulls?state=all&sort=updated&direction=desc&per_page=100&page=$page")"; then
    echo "::warning::could not list recent PRs: the run outcome is not recorded"
    exit 0
  fi
  recent_raw="$recent_raw$p"$'\n'
  if jq -e --arg s "$start" 'length < 100 or ((.[-1].updated_at // "") < $s)' <<< "$p" > /dev/null; then
    complete=1
    break
  fi
done
if [ "$complete" != 1 ]; then
  echo "::warning::more than 1000 PRs were updated since the run started: the run outcome is not recorded"
  exit 0
fi
if jq -s -e --argjson n "$N" --arg start "$start" '[.[][] | select(((.head.ref // "") | test("^" + ($n | tostring) + "-")) or ((.body // "") | test("(Closes|Refs|Fixes|Resolves) #" + ($n | tostring) + "([^0-9]|$)"; "i"))) | select(((.created_at // "") >= $start) or ((.merged_at // "") >= $start))] | length > 0' <<< "$recent_raw" > /dev/null; then
  echo "issue #$N has a PR opened or merged during this run: started"
  remove_label
  exit 0
fi

# --- ここから: PR も push も無く、明示的な終了状態でもない -> oc:no-pr と構造化コメント ---
f="${OC_OUTPUT_FILE:-${RUNNER_TEMP:-/tmp}/oc-output.jsonl}"
text=""
[ -s "$f" ] && text="$(jq -Rrs '[split("\n")[] | fromjson? | select(.type == "text") | .part.text // empty] | last // "" | .[0:6000]' "$f" 2> /dev/null || true)"
reason="$(classify "$text")"
status="${OC_JOB_STATUS:-unknown}"
run="${GITHUB_RUN_ID:-0}"
url="${GITHUB_SERVER_URL:-https://github.com}/$R/actions/runs/$run"
cause_field=""
[ -n "$cause" ] && cause_field="cause=$cause "
marker="<!-- oc-run-outcome: no-pr reason=$reason ${cause_field}run=$run -->"
rl_note=""
[ -n "$cause" ] && rl_note=" opencode の error 行に率制限 (rate_limit_error / HTTP 429) があり、cause=rate_limit を付けました。"
body="[run-outcome] この run ($url, job status: $status) は PR も push も出さずに終了しました。理由の分類: $reason (stop=判断待ち・停止, split=1 run に収まらない, blocked=依存, artifact=素材不足, unknown=不明)。$rl_note この issue は blocked でも着手済みでもないため、ラベル \`$NOPR_LABEL\` を付けました。PM はコメント本文でなく、ラベルとこのマーカーで扱ってください (次の run が PR を出すとラベルは自動で外れます)。
$marker"

echo "issue #$N ended without a PR: reason=$reason status=$status run=$run"
if [ "$DRY" = 1 ]; then
  echo "DRY: label $NOPR_LABEL + comment: $marker"
  exit 0
fi
gh api -X POST "repos/$R/labels" -f name="$NOPR_LABEL" -f color=D93F0B \
  -f description="the last implement run ended without a PR or a push (PM Worker relaunches or decides)" > /dev/null 2>&1 || true
gh api -X POST "repos/$R/issues/$N/labels" -f "labels[]=$NOPR_LABEL" > /dev/null || echo "::warning::could not add $NOPR_LABEL to #$N"
gh api -X POST "repos/$R/issues/$N/comments" -f body="$body" > /dev/null || echo "::warning::could not post the run-outcome comment on #$N"
exit 0
