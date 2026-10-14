#!/bin/bash
# test-watchdog.sh — watchdog.sh の判定と操作を fake gh で検証する (#719)。
# 実行: bash .github/scripts/tests/test-watchdog.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/**・.github/actions/**・opencode.yaml の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r RUNNER_TEMP="$TMP" OC_REOPEN_WAIT=0 OC_MERGEABLE_WAIT=0 GH_TOKEN=x

# fake gh: `gh api [--paginate] repos/... [--jq E]` は $FIX/<path の / を _ にした名前> を返す。
# `gh pr|label ...` は $LOG に記録するだけ (FAKE_MERGE_FAILS=1 なら `gh pr merge` は失敗する)。
# FAKE_FAIL=<部分文字列> を設定すると、path にその文字列を含む `gh api` は失敗する (読み取り失敗の再現)。
FIX="$TMP/fixtures"
LOG="$TMP/gh.log"
mkdir -p "$FIX" "$TMP/bin"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
echo "gh $*" >> "$FAKE_LOG"
if [ "$1" = pr ] || [ "$1" = label ]; then
  if [ "$1 $2" = "pr merge" ] && [ -n "${FAKE_MERGE_FAILS:-}" ]; then
    echo "Pull request is not mergeable" >&2
    exit 1
  fi
  exit 0
fi
shift
path="" jq_expr="" method=GET
while [ $# -gt 0 ]; do
  case "$1" in
    --paginate) ;;
    -X) method="$2"; shift ;;
    --jq) jq_expr="$2"; shift ;;
    repos/*) path="$1" ;;
  esac
  shift
done
[ "$method" = POST ] && exit 0
if [ -n "${FAKE_FAIL:-}" ] && [[ "$path" == *"$FAKE_FAIL"* ]]; then
  echo "fake gh: injected failure for $path" >&2
  exit 1
fi
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

OLD="2020-01-01T00:00:00Z"
REVIEWER="oc-reviewer-for-signature-studio[bot]"

reset() { rm -rf "$FIX"; mkdir -p "$FIX"; : > "$LOG"; : > "$TMP/out"; unset FAKE_MERGE_FAILS FAKE_FAIL; }
fx() { printf '%s' "$2" > "$FIX/${1//\//_}"; } # fx <path> <json>
# runs / PR 一覧は全ケース共通の形。active_runs は workflow_runs の JSON (既定は空)。
base() { # base <prs json> [active runs json]
  local runs="${2:-[]}" s
  for s in in_progress queued pending waiting; do
    fx "repos/o/r/actions/runs?status=$s&per_page=100" "{\"workflow_runs\":$([ "$s" = in_progress ] && echo "$runs" || echo '[]')}"
  done
  fx "repos/o/r/pulls?state=open&per_page=100" "$1"
}
# run <path> <pr番号...>: 実行中 run の JSON (workflow の path と担当 PR)
run() { local p="$1" nums="" ; shift; for n in "$@"; do nums="$nums{\"number\":$n},"; done; printf '{"event":"pull_request","display_title":"x","path":"%s","pull_requests":[%s]}' "$p" "${nums%,}"; }
# run_sha <path> <head_sha> <pr番号...>: head_sha を持つ pull_request run (古い head の担当判定用)
run_sha() { local p="$1" sha="$2" nums="" ; shift 2; for n in "$@"; do nums="$nums{\"number\":$n},"; done; printf '{"event":"pull_request","display_title":"x","path":"%s","head_sha":"%s","pull_requests":[%s]}' "$p" "$sha" "${nums%,}"; }
# pr <n> <head> <draft> <updated_at> <labels json> [body] [head repo full_name (既定 o/r)]
pr() { printf '{"number":%s,"title":"PR %s","head":{"sha":"%s","repo":{"full_name":"%s"}},"draft":%s,"updated_at":"%s","labels":%s,"body":%s}' "$1" "$1" "$2" "${7:-o/r}" "$3" "$4" "${5:-[]}" "$(jq -Rn --arg b "${6:-}" '$b')"; }
# detail <n> <mergeable> <reviews json> <comments json>
detail() {
  fx "repos/o/r/pulls/$1" "{\"mergeable\":$2}"
  fx "repos/o/r/pulls/$1/reviews" "${3:-[]}"
  fx "repos/o/r/issues/$1/comments" "${4:-[]}"
}
review() { printf '{"user":{"login":"%s","type":"%s"},"commit_id":"%s","state":"%s","body":"%s"}' "$1" "${5:-Bot}" "$2" "$3" "${4:-}"; }
wd() { bash "$SCRIPTS/watchdog.sh" > "$TMP/out" 2>&1; }

# 1. 競合 PR は pull_request / pull_request_review でワークフローが起動しない。差し戻しでなく repository_dispatch (oc-fix) で起動する (#731)
reset
base "[$(pr 1 aaa111 false "$OLD" '[]' $'oc_artifacts: toolchain-emsdk (説明文 mingw-w64) bogus-name plugins-ott\n本文')]"
detail 1 false
wd
logged 'api -X POST repos/o/r/dispatches' && logged 'event_type=oc-fix' && logged 'client_payload\[pr\]=1' && logged 'client_payload\[reason\]=conflict' && not_logged 'pr review 1'
expect "conflict -> repository_dispatch oc-fix (no request-changes)" $?

# 1a. dispatch の素材は PR 本文の oc_artifacts 行から allowlist に一致する語だけ (説明文・未知の語は落とす)
logged 'client_payload\[artifacts\]=toolchain-emsdk plugins-ott$'
expect "dispatch artifacts keep only allowlisted names from the PR body" $?

# 1a2. analysis-mac-shared は allowlist に含まれ、競合解消の dispatch に素材として渡る (#761)
reset
base "[$(pr 1 aaa111 false "$OLD" '[]' $'oc_artifacts: fl-win64 analysis-mac-shared\n本文')]"
detail 1 false
wd
logged 'client_payload\[artifacts\]=fl-win64 analysis-mac-shared$'
expect "analysis-mac-shared passes the watchdog allowlist" $?

# 1b. dispatch の前に、試行を数えるマーカー付きのコメントを残す
logged 'pr comment 1 .*oc-dispatch:aaa111'
expect "a counted marker comment precedes the dispatch" $?

# 1c. 同じ head への dispatch が上限 (3 回) に達したら oc:stuck で止める
reset
base "[$(pr 1 aaa111 false "$OLD")]"
detail 1 false "[]" "[$(for _ in 1 2 3; do printf '{"user":{"login":"%s","type":"Bot"},"body":"x <!-- oc-dispatch:aaa111 -->"},' "$REVIEWER"; done | sed 's/,$//')]"
wd
logged 'pr edit 1 .*--add-label oc:stuck' && not_logged 'repos/o/r/dispatches'
expect "dispatch limit reached -> oc:stuck, no more dispatch" $?

# 1c2. 差し戻し (watchdog) が 6 回ある競合 PR は oc:stuck にならず、dispatch される (WD_MAX で止めない)
reset
base "[$(pr 1 aaa111 false "$OLD")]"
detail 1 false "[$(for _ in 1 2 3 4 5 6; do printf '%s,' "$(review "$REVIEWER" aaa111 CHANGES_REQUESTED '[watchdog] x (watchdog)')"; done | sed 's/,$//')]"
wd
logged 'client_payload\[reason\]=conflict' && not_logged 'add-label oc:stuck' && not_logged 'pr review 1'
expect "conflict with 6 watchdog re-requests -> still dispatched, not oc:stuck" $?

# 1g. fork からの競合 PR は dispatch しない (write 権限の run を第三者の入力で動かさない)。oc:stuck も付けず、一覧に出して次へ進む
reset
base "[$(pr 1 aaa111 false "$OLD" '[]' '' fork-user/signature-studio-dev),$(pr 2 bbb222 true "$OLD")]"
detail 1 false
detail 2 true
wd
not_logged 'repos/o/r/dispatches' && not_logged 'oc-dispatch' && not_logged 'add-label oc:stuck' && logged 'pr ready 2' && grep -q 'fork からの PR' "$TMP/out"
expect "fork conflict PR -> no dispatch, no oc:stuck, listed and skipped" $?

# 1h. head.repo が読めない競合 PR も fork とみなして dispatch しない (fail-closed)
reset
base "[$(printf '{"number":1,"title":"PR 1","head":{"sha":"aaa111"},"draft":false,"updated_at":"%s","labels":[],"body":""}' "$OLD")]"
detail 1 false
wd
not_logged 'repos/o/r/dispatches' && not_logged 'add-label oc:stuck'
expect "conflict PR without head.repo -> treated as fork, no dispatch" $?

# 1d. マーカーを偽装した他アカウントのコメントは数えない
reset
base "[$(pr 1 aaa111 false "$OLD")]"
detail 1 false "[]" "[$(for _ in 1 2 3; do printf '{"user":{"login":"someone-else","type":"User"},"body":"<!-- oc-dispatch:aaa111 -->"},'; done | sed 's/,$//')]"
wd
logged 'repos/o/r/dispatches' && not_logged 'oc:stuck'
expect "spoofed markers from another account do not count" $?

# 1e. 実行中の oc-fix run (run-name が『oc-fix #N』) があれば担当ありとして何もしない
reset
base "[$(pr 1 aaa111 false "$OLD")]" '[{"event":"repository_dispatch","display_title":"oc-fix #1","path":".github/workflows/opencode.yaml","pull_requests":[]}]'
detail 1 false
wd
not_logged 'repos/o/r/dispatches'
expect "a running oc-fix run covers the conflicting PR" $?

# 1f. 別の PR の oc-fix run は担当にならない
reset
base "[$(pr 1 aaa111 false "$OLD")]" '[{"event":"repository_dispatch","display_title":"oc-fix #11","path":".github/workflows/opencode.yaml","pull_requests":[]}]'
detail 1 false
wd
logged 'repos/o/r/dispatches'
expect "oc-fix #11 does not cover PR #1" $?

# 2. draft -> ready
reset
base "[$(pr 2 bbb222 true "$OLD")]"
detail 2 true
wd
logged 'pr ready 2'
expect "draft -> ready" $?

# 3. 現在の head に差し戻しがあるのに fix が無い -> [watchdog] 再提出
reset
base "[$(pr 3 ccc333 false "$OLD")]"
detail 3 true "[$(review "$REVIEWER" ccc333 CHANGES_REQUESTED)]"
wd
logged 'pr review 3 .*--request-changes' && logged '\[watchdog\]'
expect "unfixed changes_requested -> [watchdog] re-request" $?

# 4. approve 済みで未 merge -> --match-head-commit 付きで merge
reset
base "[$(pr 4 ddd444 false "$OLD")]"
detail 4 true "[$(review "$REVIEWER" ddd444 APPROVED)]"
wd
logged 'pr merge 4 .*--match-head-commit ddd444'
expect "approved -> merge with --match-head-commit" $?

# 5. merge に失敗したら理由付きの差し戻し
reset
export FAKE_MERGE_FAILS=1
base "[$(pr 5 eee555 false "$OLD")]"
detail 5 true "[$(review "$REVIEWER" eee555 APPROVED)]"
wd
logged 'pr review 5 .*--request-changes' && logged '\[merge-failed\]' && logged 'not mergeable'
expect "merge failure -> [merge-failed] request-changes with the reason" $?

# 6. 現在の head に verdict が無い -> 試行マーカー付きコメント + close -> reopen
reset
base "[$(pr 6 fff666 false "$OLD")]"
detail 6 true "[$(review "$REVIEWER" oldhead COMMENTED)]"
wd
logged 'pr comment 6 .*review-retry:fff666' && logged 'pr close 6' && logged 'pr reopen 6'
expect "no verdict on this head -> marker comment + close/reopen" $?

# 7. 別名の reviewer (前方一致なら通ってしまう login) の差し戻しは verdict と認めない
reset
base "[$(pr 7 ggg777 false "$OLD")]"
detail 7 true "[$(review "oc-reviewer-for-signature-studio-evil[bot]" ggg777 CHANGES_REQUESTED)]"
wd
logged 'pr reopen 7' && not_logged 'pr review 7'
expect "look-alike reviewer login is not a verdict (exact match)" $?

# 8. 同じ名前でも user.type が Bot でなければ verdict と認めない
reset
base "[$(pr 8 hhh888 false "$OLD")]"
detail 8 true "[$(review "$REVIEWER" hhh888 APPROVED "" User)]"
wd
logged 'pr reopen 8' && not_logged 'pr merge 8'
expect "same login but not a Bot is not a verdict" $?

# 9. oc:stuck ラベルの PR は触らない
reset
base "[$(pr 9 iii999 false "$OLD" '[{"name":"oc:stuck"}]')]"
detail 9 false
wd
not_logged 'pr review 9' && not_logged 'pr reopen 9' && not_logged 'pr ready 9' && grep -q 'STUCK_LABELLED' "$TMP/out"
expect "oc:stuck PR is left alone" $?

# 10. watchdog の差し戻しが上限に達した head には oc:stuck を付けて止める
reset
base "[$(pr 10 jjj000 false "$OLD")]"
detail 10 true "[$(for _ in 1 2 3 4 5 6; do printf '%s,' "$(review "$REVIEWER" jjj000 CHANGES_REQUESTED '[watchdog] x (watchdog)')"; done | sed 's/,$//')]"
wd
logged 'pr edit 10 .*--add-label oc:stuck' && not_logged 'pr review 10'
expect "watchdog re-requests exhausted -> oc:stuck, no more re-request" $?

# 11. review の再起動が尽きた (マーカー 3 件) head は oc:stuck で止める
reset
base "[$(pr 11 kkk111 false "$OLD")]"
RETRY_BOT="[{\"user\":{\"login\":\"$REVIEWER\",\"type\":\"Bot\"},\"body\":\"a <!-- review-retry:kkk111 -->\"},{\"user\":{\"login\":\"$REVIEWER\",\"type\":\"Bot\"},\"body\":\"b <!-- review-retry:kkk111 -->\"},{\"user\":{\"login\":\"$REVIEWER\",\"type\":\"Bot\"},\"body\":\"c <!-- review-retry:kkk111 -->\"}]"
detail 11 true "[]" "$RETRY_BOT"
wd
logged 'pr edit 11 .*--add-label oc:stuck' && not_logged 'pr reopen 11'
expect "review retries exhausted -> oc:stuck, no reopen" $?

# 12. 実行中の opencode.yaml の run が PR を担当していれば何もしない
reset
base "[$(pr 12 lll222 false "$OLD")]" "[$(run .github/workflows/opencode.yaml 12)]"
detail 12 true
wd
not_logged 'pr reopen 12' && not_logged 'pr review 12'
expect "PR with a running opencode.yaml run is covered" $?

# 12b. 古い head の pull_request run しか無い PR は担当外 (IDLE)。差し戻し無し・verdict 無しなので review を再起動する (#719)
reset
base "[$(pr 12 lll222 false "$OLD")]" "[$(run_sha .github/workflows/opencode.yaml fff000 12)]"
detail 12 true
wd
logged 'pr reopen 12'
expect "PR whose only running run is on an old head -> not covered, review restarted" $?

# 12c. 現在の head の pull_request run が PR を担当していれば何もしない (#719)
reset
base "[$(pr 12 lll222 false "$OLD")]" "[$(run_sha .github/workflows/opencode.yaml lll222 12)]"
detail 12 true
wd
not_logged 'pr reopen 12' && not_logged 'pr review 12'
expect "PR with a running run on the current head is covered" $?

# 16. 実行中 run の一覧が取れなければ何も操作しない (exit 1)
reset
base "[$(pr 16 rrr160 false "$OLD")]"
detail 16 false
FAKE_FAIL='actions/runs?status=in_progress' wd; rc=$?
[ "$rc" = 1 ] && not_logged '^gh pr ' && not_logged 'gh pr comment'
expect "runs list fails -> no action at all, exit 1" $?

# 17. PR 一覧が取れなければ何も操作しない (exit 1)
reset
base "[$(pr 17 sss170 false "$OLD")]"
detail 17 false
FAKE_FAIL='pulls?state=open' wd; rc=$?
[ "$rc" = 1 ] && not_logged 'gh pr '
expect "PR list fails -> no action at all, exit 1" $?

# 18. reviews の取得が失敗した PR は skip する (承認済みでも NOREVIEW 扱いで reopen しない)
reset
base "[$(pr 18 ttt180 false "$OLD")]"
detail 18 true "[$(review "$REVIEWER" ttt180 APPROVED)]"
FAKE_FAIL='pulls/18/reviews' wd
not_logged 'gh pr ' && grep -q 'failed to read reviews' "$TMP/out"
expect "reviews read fails -> skipped, no action" $?

# 19. scripts-test.yaml の run だけでは PR を担当しているとみなさない
reset
base "[$(pr 19 uuu190 false "$OLD")]" "[$(run .github/workflows/scripts-test.yaml 19)]"
detail 19 true
wd
logged 'pr reopen 19'
expect "scripts-test run alone does not cover the PR -> recovery" $?

# 20. APPROVED の後に reviewer の COMMENTED が付いても verdict は APPROVED -> merge
reset
base "[$(pr 20 vvv200 false "$OLD")]"
detail 20 true "[$(review "$REVIEWER" vvv200 APPROVED),$(review "$REVIEWER" vvv200 COMMENTED)]"
wd
logged 'pr merge 20 .*--match-head-commit vvv200' && not_logged 'pr reopen 20'
expect "APPROVED then COMMENTED -> still merged" $?

# 21. mergeable が null (未確定) の PR は操作せず次回に回す
reset
base "[$(pr 21 www210 false "$OLD")]"
detail 21 null
wd
not_logged 'gh pr ' && grep -q 'mergeability is still unknown' "$TMP/out"
expect "mergeable null -> skipped, no action" $?

# 22. 第三者 (reviewer 以外・Bot 以外) の試行マーカーは数えない
reset
base "[$(pr 22 xxx220 false "$OLD")]"
detail 22 true "[]" '[{"user":{"login":"someone","type":"User"},"body":"a <!-- review-retry:xxx220 -->"},{"user":{"login":"someone","type":"User"},"body":"b <!-- review-retry:xxx220 -->"},{"user":{"login":"someone","type":"User"},"body":"c <!-- review-retry:xxx220 -->"},{"user":{"login":"oc-reviewer-for-signature-studio[bot]","type":"User"},"body":"d <!-- review-retry:xxx220 -->"}]'
wd
logged 'pr reopen 22' && not_logged 'pr edit 22'
expect "third-party retry markers are not counted" $?

# 23. 試行上限の oc:stuck 付与も OC_MAX_ACTIONS の枠を使う (枠を使い切ったら次回へ)
reset
base "[$(pr 23 yyy230 false 2019-01-01T00:00:00Z),$(pr 24 zzz240 true "$OLD")]"
detail 23 true "[$(for _ in 1 2 3 4 5 6; do printf '%s,' "$(review "$REVIEWER" yyy230 CHANGES_REQUESTED '[watchdog] x (watchdog)')"; done | sed 's/,$//')]"
detail 24 true
OC_MAX_ACTIONS=1 wd
logged 'pr edit 23' && not_logged 'pr ready 24' && grep -q 'deferred=1' "$TMP/out"
expect "exhausted oc:stuck counts as an action under OC_MAX_ACTIONS" $?

# 13. 更新直後 (SETTLE 内) の PR は触らない
reset
base "[$(pr 13 mmm333 false "$(date -u +%Y-%m-%dT%H:%M:%SZ)")]"
detail 13 true
wd
not_logged 'pr reopen 13' && grep -q 'still propagating' "$TMP/out"
expect "recently updated PR is skipped (settle window)" $?

# 14. 1 回の点検で動かす PR は OC_MAX_ACTIONS 件まで
reset
base "[$(pr 14 nnn444 true "$OLD"),$(pr 15 ooo555 true "$OLD"),$(pr 16 ppp666 true "$OLD")]"
detail 14 true
detail 15 true
detail 16 true
OC_MAX_ACTIONS=2 wd
[ "$(grep -c 'pr ready' "$LOG")" = 2 ] && grep -q 'deferred=1' "$TMP/out"
expect "at most OC_MAX_ACTIONS actions per run, the rest deferred" $?

# 15. DRY=1 は操作しない
reset
base "[$(pr 17 qqq777 true "$OLD")]"
detail 17 true
DRY=1 wd
not_logged 'pr ready' && grep -q 'DRY: ready #17' "$TMP/out"
expect "DRY=1 plans without acting" $?

# 24. 宙に浮いた issue の集計 (#1950): open issue で、blocked でなく、open PR が無く、実行中の implement run も無く、
#     oc:no-pr / needs-user-input / oc:stuck も無いものを数えて出力する。数えるだけで、何も操作しない。
# iss <n> <title> <labels json> [blocked_by] [pull_request を持つか]
iss() { local pr=""; [ -n "${5:-}" ] && pr=',"pull_request":{"url":"u"}'; printf '{"number":%s,"title":"%s","labels":%s,"issue_dependencies_summary":{"blocked_by":%s}%s}' "$1" "$2" "${3:-[]}" "${4:-0}" "$pr"; }
issues() { fx 'repos/o/r/issues?state=open&per_page=100' "[$1]"; }
floating() { grep -E '^floating-issues=' "$TMP/out"; }

reset
base "[$(pr 30 aaa300 false "$OLD" '[]' $'Closes #102\n' | sed 's/"head":{/"head":{"ref":"102-has-pr",/')]"
detail 30 true
ISS="$(iss 101 'floating issue' '[]'),$(iss 102 'has a PR' '[]'),$(iss 103 'blocked label' '[{"name":"blocked"}]'),$(iss 104 'open blocker' '[]' 2),$(iss 105 'no-pr label' '[{"name":"oc:no-pr"}]'),$(iss 106 'needs input' '[{"name":"needs-user-input"}]'),$(iss 107 'stuck' '[{"name":"oc:stuck"}]'),$(iss 108 'a PR not an issue' '[]' 0 1),$(iss 109 'another floating' '[{"name":"area:x"}]')"
issues "$ISS"
wd
floating | grep -q '^floating-issues=2 ' && floating | grep -q 'first: #101 #109'
expect "floating issues are counted (blocked / PR / oc:no-pr / needs-user-input / oc:stuck / pull requests excluded)" $?
# 集計は GET を 1 回呼ぶだけ。issue への書き込み・ラベル操作・dispatch は無い (PR 30 の点検による pr comment/close/reopen は別)。
! grep -E '^gh (api -X|label|issue)' "$LOG" | grep -q . && not_logged 'repos/o/r/issues/10' && not_logged 'repos/o/r/dispatches' && [ "$(grep -c 'issues?state=open' "$LOG")" = 1 ]
expect "counting floating issues makes no write (one GET of the open issues, no issue/label/dispatch call)" $?

# 24b. 実行中の implement run (issue_comment でタイトルが issue と一致) がある issue は着手済み
reset
base '[]' '[{"event":"issue_comment","display_title":"running issue","path":".github/workflows/opencode.yaml","pull_requests":[]}]'
issues "$(iss 110 'running issue' '[]'),$(iss 111 'idle issue' '[]')"
wd
floating | grep -q '^floating-issues=1 .*#111' && ! floating | grep -q '#110'
expect "an issue with a running implement run is started, not floating" $?

# 24c. 別の workflow の run は担当にならない
reset
base '[]' '[{"event":"issue_comment","display_title":"running issue","path":".github/workflows/scripts-test.yaml","pull_requests":[]}]'
issues "$(iss 110 'running issue' '[]')"
wd
floating | grep -q '^floating-issues=1 '
expect "a run of another workflow does not cover the issue" $?

# 24d. 0 件
reset
base '[]'
issues "$(iss 112 'x' '[{"name":"oc:no-pr"}]')"
wd
floating | grep -q '^floating-issues=0 ' && ! floating | grep -q 'first:'
expect "no floating issue -> floating-issues=0" $?

# 24e. issue 一覧が取れなくても PR の点検は続く (unknown と出す。exit 0)
reset
base "[$(pr 31 bbb310 true "$OLD")]"
detail 31 true
FAKE_FAIL='issues?state=open' wd; rc=$?
[ "$rc" = 0 ] && floating | grep -q 'floating-issues=unknown' && logged 'pr ready 31'
expect "issue list fails -> floating-issues=unknown, the PR pass still runs" $?

# 24f. 集計は step summary にも出る
reset
base '[]'
issues "$(iss 113 'floating' '[]')"
GITHUB_STEP_SUMMARY="$TMP/summary.md" wd
grep -q 'floating-issues=1' "$TMP/summary.md"
expect "floating-issues is written to the step summary" $?

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
