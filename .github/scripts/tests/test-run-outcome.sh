#!/bin/bash
# test-run-outcome.sh — record-run-outcome.sh (implement 終了時の不変条件) と review-recover.sh (review の打ち切りの即時再起動) を
# fake gh で検証する (#1950、run 中に merge まで済んだ PR は #2590)。実行: bash .github/scripts/tests/test-run-outcome.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r RUNNER_TEMP="$TMP" OC_REOPEN_WAIT=0 GH_TOKEN=x GITHUB_RUN_ID=555 GITHUB_SERVER_URL=https://github.com

# fake gh: `gh api [--paginate] [-X M] repos/... [-f k=v] [--jq E]` の GET は $FIX/<path の / を _ にした名前> を返す。
# POST / DELETE と `gh pr ...` は $LOG に記録するだけ。FAKE_FAIL=<部分文字列> で、path にそれを含む GET を失敗させる。
FIX="$TMP/fixtures"
LOG="$TMP/gh.log"
mkdir -p "$FIX" "$TMP/bin"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
echo "gh $*" >> "$FAKE_LOG"
[ "$1" = pr ] && exit 0
shift
path="" jq_expr="" method=GET
while [ $# -gt 0 ]; do
  case "$1" in
    --paginate) ;;
    -X) method="$2"; shift ;;
    --jq) jq_expr="$2"; shift ;;
    -f | -F) shift ;;
    repos/*) path="$1" ;;
  esac
  shift
done
[ "$method" != GET ] && exit 0
if [ -n "${FAKE_FAIL:-}" ] && [[ "$path" == *"$FAKE_FAIL"* ]]; then exit 1; fi
f="$FAKE_FIX/${path//\//_}"
[ -f "$f" ] || { echo "fake gh: no fixture for $path" >&2; exit 1; }
if [ -n "$jq_expr" ]; then jq -r "$jq_expr" < "$f"; else cat "$f"; fi
EOF
chmod +x "$TMP/bin/gh"
export PATH="$TMP/bin:$PATH" FAKE_LOG="$LOG" FAKE_FIX="$FIX"

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }
expect() { if [ "$2" = 0 ]; then ok "$1"; else ng "$1"; fi; }
logged() { grep -q -- "$1" "$LOG"; }
not_logged() { ! grep -q -- "$1" "$LOG"; }
fx() { printf '%s' "$2" > "$FIX/${1//\//_}"; }

# ------------------------------------------------------------------ record-run-outcome.sh
RUN0=2026-10-14T10:00:00Z # run を起動したコメントの時刻 (run の開始)
# recent <json> [page] [created|updated]: run の開始以降の PR の一覧 (pulls?state=all を作成順 / 更新順で)。既定は更新順の 1 頁目。どちらも既定は空
recent() { fx "repos/o/r/pulls?state=all&sort=${3:-updated}&direction=desc&per_page=30&page=${2:-1}" "$1"; }
# rpr <head> <body> <created> <merged|空> <updated>: 一覧の 1 件
rpr() { jq -cn --arg h "$1" --arg b "$2" --arg c "$3" --arg m "$4" --arg u "$5" '{head: {ref: $h}, body: $b, created_at: $c, merged_at: (if $m == "" then null else $m end), updated_at: $u}'; }
# filler <時刻> [n]: この issue と関係の無い PR を n 件 (既定 30)。作成・更新とも <時刻> (run の開始より後なら、頁はまだ run の開始に届かない)
filler() { jq -cn --arg u "$1" --argjson n "${2:-30}" '[range($n) | {head: {ref: "other"}, body: "", created_at: $u, merged_at: null, updated_at: $u}]'; }
reset() { rm -rf "$FIX"; mkdir -p "$FIX"; : > "$LOG"; unset FAKE_FAIL; recent '[]' 1 created; recent '[]' 1 updated; }
# issue <state> <labels json> [blocked_by]
issue() { fx repos/o/r/issues/42 "{\"state\":\"$1\",\"labels\":$2,\"issue_dependencies_summary\":{\"blocked_by\":${3:-0}}}"; }
prs() { fx 'repos/o/r/pulls?state=open&per_page=100' "$1"; }
# agent の最終回答 (opencode の JSONL。最後の text が回答)
answer() { printf '{"type":"text","part":{"text":"途中経過"}}\n{"type":"step_finish","part":{}}\n' > "$TMP/oc.jsonl"; jq -cn --arg t "$1" '{type:"text",part:{text:$t}}' >> "$TMP/oc.jsonl"; }
ev_issue() { printf '{"issue":{"number":42},"comment":{"body":"x","created_at":"%s"}}' "$RUN0" > "$TMP/ev.json"; }
ev_issue_nots() { printf '{"issue":{"number":42},"comment":{"body":"x"}}' > "$TMP/ev.json"; }
ev_pr() { printf '{"issue":{"number":42,"pull_request":{"url":"u"}},"comment":{"body":"x"}}' > "$TMP/ev.json"; }
outcome() { # outcome [env...]: 結果は $TMP/out と $RC
  GITHUB_EVENT_NAME="${EVENT:-issue_comment}" GITHUB_EVENT_PATH="$TMP/ev.json" OC_ISSUE_NUMBER="${NUM-42}" OC_OUTPUT_FILE="$TMP/oc.jsonl" OC_JOB_STATUS=success \
    bash "$SCRIPTS/record-run-outcome.sh" > "$TMP/out" 2>&1
  RC=$?
}
reason_is() { logged "oc-run-outcome: no-pr reason=$1 run=555 -->"; }

echo "== record-run-outcome.sh"

# 1. PR も push も無い着手報告 -> oc:no-pr ラベル + マーカー付きコメント (reason=unknown)
reset; ev_issue; issue open '[]'; prs '[]'; answer '着手しました。調査を始めます。'
outcome
{ [ $RC = 0 ] && logged 'api -X POST repos/o/r/issues/42/labels' && logged 'labels\[\]=oc:no-pr' && reason_is unknown && logged 'api -X POST repos/o/r/labels -f name=oc:no-pr'; }
expect "no PR, plain progress report -> label oc:no-pr + marker (reason=unknown), label created" $?

# 2. reason の分類 (launch_issues.py の stop_re / NEED_RE と同じ語彙)
for pair in '素材不足のため着手できません。plugins-ott が必要です|artifact' \
  '依存 issue #12 が未完了のため着手できません|blocked' \
  '1 run に収まらないため、ここで停止します|split' \
  '着手不可。PM に判断を依頼します|stop' \
  '停止報告: 判断待ちです|stop'; do
  reset; ev_issue; issue open '[]'; prs '[]'; answer "${pair%|*}"
  outcome
  reason_is "${pair#*|}"
  expect "answer '${pair%|*}' -> reason=${pair#*|}" $?
done

# 2b. 優先順 artifact > blocked > split > stop
reset; ev_issue; issue open '[]'; prs '[]'; answer '素材不足で、依存 issue もあり、1 run に収まらないので停止します'
outcome
reason_is artifact
expect "priority: artifact wins over blocked/split/stop" $?

# 3. 出力ファイルが無い (setup 失敗・cancel) でも記録する (reason=unknown)
reset; ev_issue; issue open '[]'; prs '[]'; rm -f "$TMP/oc.jsonl"
outcome
{ [ $RC = 0 ] && reason_is unknown && logged 'labels\[\]=oc:no-pr'; }
expect "no agent output (setup failed / cancelled) -> still recorded (reason=unknown)" $?

# 4. この issue を指す open PR がある (ブランチ名) -> 何もしない
reset; ev_issue; issue open '[]'; prs '[{"head":{"ref":"42-fix-x"},"body":""}]'; answer '完了'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "open PR with branch 42-... -> nothing recorded (started)" $?
reset; ev_issue; issue open '[]'; prs '[{"head":{"ref":"42-fix-x"},"body":""}]'; answer '完了'
outcome
not_logged 'state=all'
expect "open PR found -> the recent PR list is not read" $?

# 4b. 本文の Closes #42 / Refs #42 でも着手済み。#421 は別の issue
reset; ev_issue; issue open '[]'; prs '[{"head":{"ref":"x"},"body":"説明\nRefs #42\n"}]'; answer '完了'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "open PR body Refs #42 -> nothing recorded" $?
reset; ev_issue; issue open '[]'; prs '[{"head":{"ref":"421-y"},"body":"Closes #421"}]'; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && reason_is unknown; }
expect "PR for #421 does not cover #42 (no prefix match)" $?

# 4c. run の最中に open から merge まで済んだ PR (open->merge 12 秒。#2303 型)。run の最後には open の PR が無い -> 着手済み (#2590)
# 作成順の一覧 (run の最中に作られた PR を確実に見つける) に出る
Q="$(rpr 42-x 'Refs #42' 2026-10-14T10:00:30Z 2026-10-14T10:00:42Z 2026-10-14T10:00:50Z)"
reset; ev_issue; issue open '[]'; prs '[]'; answer '着手しました'
recent "[$Q]" 1 created
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'created or merged since the run started' "$TMP/out"; }
expect "PR opened and merged within the run (12 s) -> nothing recorded (started)" $?
reset; ev_issue; issue open '[{"name":"oc:no-pr"}]'; prs '[]'
recent "[$Q]" 1 created
outcome
{ [ $RC = 0 ] && logged 'api -X DELETE repos/o/r/issues/42/labels/oc%3Ano-pr' && not_logged 'api -X POST'; }
expect "PR merged within the run + stale oc:no-pr -> the label is removed" $?
# 更新順の一覧だけに出る場合も同じ (作成順の一覧が混んでいても)
reset; ev_issue; issue open '[]'; prs '[]'
recent "$(filler 2026-10-14T10:30:00Z)" 1 created
recent "[$Q]" 1 updated
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "the PR is only on the updated-order list (created-order page 1 is full of other PRs) -> started" $?
# 本文だけで指す PR (ブランチ名は別) も、ブランチ名だけで指す PR (本文は空) も数える
reset; ev_issue; issue open '[]'; prs '[]'
recent "[$(rpr feature-y 'Closes #42' 2026-10-14T10:00:30Z 2026-10-14T10:00:40Z 2026-10-14T10:00:50Z)]" 1 created
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "merged PR whose body says Closes #42 -> started" $?
reset; ev_issue; issue open '[]'; prs '[]'
recent "[$(rpr 42-z '' 2026-10-14T10:00:30Z 2026-10-14T10:00:40Z 2026-10-14T10:00:50Z)]" 1 created
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "merged PR on branch 42-... with an empty body -> started" $?
# run の最中に作成され、merge せず閉じた PR も『PR を出した』
reset; ev_issue; issue open '[]'; prs '[]'
recent "[$(rpr 42-w 'Refs #42' 2026-10-14T10:00:20Z '' 2026-10-14T10:01:00Z)]" 1 created
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "PR created in the run and closed unmerged -> started (a PR was produced)" $?
# 先行する run の PR が、この run の最中に merge された (作成は run の前。更新順の一覧で見つかる)
reset; ev_issue; issue open '[]'; prs '[]'
recent "[$(rpr 42-v 'Refs #42' 2026-10-14T09:50:00Z 2026-10-14T10:03:00Z 2026-10-14T10:03:00Z)]" 1 updated
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "PR created before the run but merged during it -> started" $?

# 4d. 数えない PR: 別 issue の PR、run の開始より前に作成・merge 済みの PR
O="$(rpr 99-z 'Refs #99' 2026-10-14T08:00:00Z 2026-10-14T08:00:05Z 2026-10-14T09:00:00Z)"
reset; ev_issue; issue open '[]'; prs '[]'; answer '着手報告のみ'
recent "[$(rpr 421-y 'Closes #421' 2026-10-14T10:00:30Z 2026-10-14T10:00:42Z 2026-10-14T10:00:50Z), $(rpr 43-q 'Refs #43' 2026-10-14T10:00:31Z 2026-10-14T10:00:41Z 2026-10-14T10:00:49Z), $O]" 1 created
outcome
{ [ $RC = 0 ] && reason_is unknown && logged 'labels\[\]=oc:no-pr'; }
expect "merged PRs of other issues (#421 by prefix, #43) do not count -> recorded" $?
reset; ev_issue; issue open '[]'; prs '[]'; answer '着手報告のみ'
recent "[$(rpr 42-old 'Refs #42' 2026-10-14T08:00:00Z 2026-10-14T08:00:10Z 2026-10-14T09:00:00Z)]" 1 created
recent "[$(rpr 42-old 'Refs #42' 2026-10-14T08:00:00Z 2026-10-14T08:00:10Z 2026-10-14T09:00:00Z)]" 1 updated
outcome
{ [ $RC = 0 ] && reason_is unknown && logged 'labels\[\]=oc:no-pr' && not_logged 'page=2'; }
expect "PR created and merged before the run started does not count -> recorded (no older page is read)" $?

# 4e. 頁送り: 30 件の頁が全て run 開始以降で、対象は 2 頁目 -> 数える。3 頁読んでも run の開始に届かなければ PR 無しとして扱う
reset; ev_issue; issue open '[]'; prs '[]'
recent "$(filler 2026-10-14T10:30:00Z)" 1 created
recent "[$Q]" 2 created
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && logged 'sort=created&direction=desc&per_page=30&page=2'; }
expect "the matching PR is on page 2 of the created-order list -> started" $?
reset; ev_issue; issue open '[]'; prs '[]'; answer '着手報告のみ'
for sort in created updated; do for pg in 1 2 3; do recent "$(filler 2026-10-14T10:30:00Z)" $pg $sort; done; done
outcome
{ [ $RC = 0 ] && reason_is unknown && not_logged 'page=4' && [ "$(grep -c '3 pages of PRs by' "$TMP/out")" = 2 ]; }
expect "3 pages never reach the run start (both orders) -> at most 3 pages each, treated as no PR" $?

# 4f. run の開始: 起動コメントの時刻が無ければ run の run_started_at。どちらも分からなければ書かない
reset; ev_issue_nots; issue open '[]'; prs '[]'; fx repos/o/r/actions/runs/555 '{"run_started_at":"2026-10-14T10:00:05Z"}'
recent "[$Q]" 1 created
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "no comment time in the event -> run_started_at is used" $?
reset; ev_issue_nots; issue open '[]'; prs '[]'; answer '着手報告のみ'
recent "[$Q]" 1 created
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'could not tell when the run started' "$TMP/out"; }
expect "run start unknown (no comment time, run lookup fails) -> no write, exit 0" $?

# 5. 明示的な終了状態 (oc:stuck / needs-user-input / blocked ラベル、open な依存) -> 何もしない
for lab in oc:stuck needs-user-input blocked; do
  reset; ev_issue; issue open "[{\"name\":\"$lab\"}]"; prs '[]'; answer '停止します'
  outcome
  { [ $RC = 0 ] && not_logged 'api -X POST'; }
  expect "label $lab -> explicit state, nothing recorded" $?
done
reset; ev_issue; issue open '[]' 1; prs '[]'; answer '停止します'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "open blocker (issue dependencies) -> blocked, nothing recorded" $?

# 6. closed の issue -> 何もしない
reset; ev_issue; issue closed '[]'; prs '[]'; answer '完了'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "closed issue -> nothing recorded" $?

# 7. oc:no-pr は、次の run が PR を出したら外す (着手済み・closed・明示的な状態でも外す)
reset; ev_issue; issue open '[{"name":"oc:no-pr"}]'; prs '[{"head":{"ref":"42-z"},"body":""}]'; answer '完了'
outcome
{ [ $RC = 0 ] && logged 'api -X DELETE repos/o/r/issues/42/labels/oc%3Ano-pr'; }
expect "oc:no-pr is removed once the issue has an open PR" $?
reset; ev_issue; issue closed '[{"name":"oc:no-pr"}]'; prs '[]'
outcome
logged 'api -X DELETE repos/o/r/issues/42/labels/oc%3Ano-pr'
expect "oc:no-pr is removed when the issue is closed" $?
reset; ev_issue; issue open '[{"name":"oc:no-pr"},{"name":"needs-user-input"}]'; prs '[]'
outcome
logged 'api -X DELETE repos/o/r/issues/42/labels/oc%3Ano-pr'
expect "oc:no-pr is removed when the issue moves to an explicit state" $?
reset; ev_issue; issue open '[]'; prs '[{"head":{"ref":"42-z"},"body":""}]'
outcome
not_logged 'api -X DELETE'
expect "no oc:no-pr label -> no DELETE call" $?

# 8. 既に oc:no-pr が付いた issue で再び PR 無しに終わったら、新しい run のマーカーを残す (ラベルは付け直し = 冪等)
reset; ev_issue; issue open '[{"name":"oc:no-pr"}]'; prs '[]'; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && reason_is unknown; }
expect "second no-PR run -> a new marker with the new run id" $?

# 9. PR 上のコメント / issue_comment 以外のイベント / issue 番号無し -> 何もしない
reset; ev_pr; issue open '[]'; prs '[]'
outcome
{ [ $RC = 0 ] && not_logged 'repos/o/r'; }
expect "comment on a PR -> nothing (the PR is the vehicle)" $?
reset; ev_issue; EVENT=workflow_dispatch outcome
{ [ $RC = 0 ] && not_logged 'repos/o/r'; }
expect "workflow_dispatch -> nothing" $?
reset; ev_issue; NUM='' outcome
{ [ $RC = 0 ] && not_logged 'repos/o/r'; }
expect "no issue number -> nothing" $?

# 10. 読み取りに失敗したら何も書かず、run を失敗させない (観測用)
reset; ev_issue; issue open '[]'; prs '[]'
FAKE_FAIL='issues/42' outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "issue read fails -> no write, exit 0" $?
reset; ev_issue; issue open '[]'; prs '[]'
FAKE_FAIL='pulls?state=open' outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "open PR list fails -> no write (cannot tell started from floating), exit 0" $?
reset; ev_issue; issue open '[]'; prs '[]'
FAKE_FAIL='pulls?state=all' outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "recent PR list fails -> no write (cannot tell started from floating), exit 0" $?

# 11. DRY=1 は書かない
reset; ev_issue; issue open '[]'; prs '[]'; answer '停止します'
DRY=1 outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'DRY: label oc:no-pr' "$TMP/out"; }
expect "DRY=1 plans without writing" $?

# 12. コメント本文は agent を起動する語 (行頭の slash + oc) を含まない (自分のコメントで implement を起動しない)
reset; ev_issue; issue open '[]'; prs '[]'; answer '着手報告'
outcome
body="$(grep 'issues/42/comments' "$LOG" | head -1)"
! printf '%s' "$body" | grep -qE '(^|[[:space:]])/(oc|opencode)([[:space:]]|$)'
expect "the outcome comment never contains a /oc command" $?

# ------------------------------------------------------------------ review-recover.sh
echo "== review-recover.sh"
rreset() { reset; printf '{"pull_request":{"number":7}}' > "$TMP/ev.json"; fx repos/o/r/actions/runs/555/jobs '{"jobs":[{"id":9001,"name":"review"},{"id":9002,"name":"other"}]}'; }
annot() { fx repos/o/r/check-runs/9001/annotations "$1"; }
recover() { GITHUB_EVENT_PATH="$TMP/ev.json" bash "$SCRIPTS/review-recover.sh" > "$TMP/out" 2>&1; RC=$?; }
# verify-review-verdict.sh が読む fixture: PR (open) と review / comments
vsetup() { # vsetup <head> <retry markers>
  fx repos/o/r/pulls/7 "{\"state\":\"open\",\"head\":{\"sha\":\"$1\"}}"
  fx repos/o/r/pulls/7/reviews '[]'
  local c="[" i
  for ((i = 0; i < $2; i++)); do c="$c{\"body\":\"x <!-- review-retry:${1:0:12} -->\"},"; done
  fx repos/o/r/issues/7/comments "${c%,}]"
}

rreset; vsetup hhh0000 0
annot '[{"annotation_level":"failure","message":"Process completed with exit code 143."}]'
recover
{ [ $RC = 0 ] && logged 'pr comment 7' && logged 'review-retry:hhh0000' && logged 'pr close 7' && logged 'pr reopen 7'; }
expect "runner cut-off (exit 143), no verdict -> review re-triggered (comment + close/reopen)" $?

rreset; vsetup hhh0000 0
annot '[{"annotation_level":"error","message":"The runner has received a shutdown signal."}]'
recover
{ [ $RC = 0 ] && logged 'pr reopen 7'; }
expect "runner shutdown signal -> review re-triggered" $?

rreset; vsetup hhh0000 0
annot '[{"annotation_level":"error","message":"The job running on runner X has exceeded the maximum execution time of 60 minutes."}]'
recover
{ [ $RC = 0 ] && logged 'pr reopen 7'; }
expect "job exceeded the maximum execution time -> review re-triggered" $?

rreset; vsetup hhh0000 0
annot '[{"annotation_level":"notice","message":"The operation was canceled."}]'
recover
{ [ $RC = 0 ] && not_logged 'pr ' && grep -q 'no recovery' "$TMP/out"; }
expect "cancelled without a runner cut-off annotation (manual cancel) -> not re-triggered" $?

rreset; vsetup hhh0000 3
annot '[{"annotation_level":"failure","message":"Process completed with exit code 143."}]'
recover
{ [ $RC = 1 ] && not_logged 'pr reopen' && not_logged 'pr close'; }
expect "bound: 3 retry markers already on this head -> no more re-trigger (verify warns and fails)" $?

rreset; vsetup hhh0000 2
annot '[{"annotation_level":"failure","message":"Process completed with exit code 143."}]'
recover
{ [ $RC = 0 ] && logged 'pr reopen 7' && logged '試行 3/3'; }
expect "bound: the 3rd (last) attempt is still allowed" $?

rreset; vsetup hhh0000 0
fx repos/o/r/pulls/7/reviews '[{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"APPROVED","commit_id":"hhh0000"}]'
annot '[{"annotation_level":"failure","message":"Process completed with exit code 143."}]'
recover
{ [ $RC = 0 ] && not_logged 'pr reopen' && not_logged 'pr close'; }
expect "the head already has a verdict -> not re-triggered" $?

rreset; vsetup hhh0000 0
fx repos/o/r/pulls/7 '{"state":"closed","head":{"sha":"hhh0000"}}'
annot '[{"annotation_level":"failure","message":"Process completed with exit code 143."}]'
recover
{ [ $RC = 0 ] && not_logged 'pr reopen'; }
expect "PR already closed/merged -> not re-triggered" $?

rreset; vsetup hhh0000 0
annot '[{"annotation_level":"failure","message":"Process completed with exit code 143."}]'
FAKE_FAIL='annotations' recover
{ [ $RC = 0 ] && not_logged 'pr '; }
expect "annotations unreadable -> no action (fail-closed, the watchdog covers it)" $?

rreset; vsetup hhh0000 0
FAKE_FAIL='actions/runs/555/jobs' recover
{ [ $RC = 0 ] && not_logged 'pr '; }
expect "jobs unreadable -> no action (fail-closed)" $?

rreset; vsetup hhh0000 0
annot '[{"annotation_level":"failure","message":"Process completed with exit code 143."}]'
printf '{}' > "$TMP/ev.json"
recover
{ [ $RC = 0 ] && not_logged 'pr '; }
expect "no pull_request number in the event -> no action" $?

rreset; vsetup hhh0000 0
annot '[{"annotation_level":"failure","message":"Process completed with exit code 143."}]'
DRY=1 recover
{ [ $RC = 0 ] && not_logged 'pr ' && grep -q 'DRY: verify-review-verdict' "$TMP/out"; }
expect "DRY=1 plans without acting" $?

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
