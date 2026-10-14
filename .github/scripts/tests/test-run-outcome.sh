#!/bin/bash
# test-run-outcome.sh — record-run-outcome.sh (implement 終了時の不変条件) と review-recover.sh (review の打ち切りの即時再起動) を
# fake gh で検証する (#1950)。実行: bash .github/scripts/tests/test-run-outcome.sh
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
reset() { rm -rf "$FIX"; mkdir -p "$FIX"; : > "$LOG"; unset FAKE_FAIL; }
# issue <state> <labels json> [blocked_by]
issue() { fx repos/o/r/issues/42 "{\"state\":\"$1\",\"labels\":$2,\"issue_dependencies_summary\":{\"blocked_by\":${3:-0}}}"; }
prs() { fx 'repos/o/r/pulls?state=open&per_page=100' "$1"; }
# agent の最終回答 (opencode の JSONL。最後の text が回答)
answer() { printf '{"type":"text","part":{"text":"途中経過"}}\n{"type":"step_finish","part":{}}\n' > "$TMP/oc.jsonl"; jq -cn --arg t "$1" '{type:"text",part:{text:$t}}' >> "$TMP/oc.jsonl"; }
ev_issue() { printf '{"issue":{"number":42},"comment":{"body":"x"}}' > "$TMP/ev.json"; }
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

# 4b. 本文の Closes #42 / Refs #42 でも着手済み。#421 は別の issue
reset; ev_issue; issue open '[]'; prs '[{"head":{"ref":"x"},"body":"説明\nRefs #42\n"}]'; answer '完了'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "open PR body Refs #42 -> nothing recorded" $?
reset; ev_issue; issue open '[]'; prs '[{"head":{"ref":"421-y"},"body":"Closes #421"}]'; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && reason_is unknown; }
expect "PR for #421 does not cover #42 (no prefix match)" $?

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
