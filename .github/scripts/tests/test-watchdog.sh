#!/bin/bash
# test-watchdog.sh — watchdog.sh の判定と操作を fake gh で検証する (#719)。
# 実行: bash .github/scripts/tests/test-watchdog.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/**・.github/actions/**・opencode.yaml の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r RUNNER_TEMP="$TMP" OC_REOPEN_WAIT=0 OC_MERGEABLE_WAIT=0 GH_TOKEN=x OC_WORKER_URL_FILE="$TMP/no-worker-url"

# fake gh: `gh api [--paginate] repos/... [--jq E]` は $FIX/<path の / を _ にした名前> を返す。
# `gh pr|label|issue ...` は $LOG に記録するだけ (FAKE_MERGE_FAILS=1 なら `gh pr merge` は失敗する)。
# `gh issue list` / `gh pr list` は擬似 path (issue-list?state=S&label=L / pr-list?state=S) の fixture を返す (--limit は $LOG に残る)。
# fake curl は引数を $FAKE_CURL_LOG に記録し、$FAKE_STATUS の内容を返す (FAKE_CURL_FAIL=<終了コード> で失敗。28 は timeout)。
# FAKE_FAIL=<部分文字列> を設定すると、path (擬似 path を含む) にその文字列を含む読み取りは失敗する (読み取り失敗の再現)。
FIX="$TMP/fixtures"
LOG="$TMP/gh.log"
mkdir -p "$FIX" "$TMP/bin"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
echo "gh $*" >> "$FAKE_LOG"
if { [ "$1" = issue ] || [ "$1" = pr ]; } && [ "$2" = list ]; then
  kind="$1" state="" label=""
  shift 2
  while [ $# -gt 0 ]; do
    case "$1" in
      --state) state="$2"; shift ;;
      --label) label="$2"; shift ;;
    esac
    shift
  done
  key="$kind-list?state=$state${label:+&label=$label}"
  if [ -n "${FAKE_FAIL:-}" ] && [[ "$key" == *"$FAKE_FAIL"* ]]; then
    echo "fake gh: injected failure for $key" >&2
    exit 1
  fi
  f="$FAKE_FIX/${key//\//_}"
  [ -f "$f" ] || { echo "fake gh: no fixture for $key" >&2; exit 1; }
  cat "$f"
  exit 0
fi
if [ "$1" = pr ] || [ "$1" = label ] || [ "$1" = issue ]; then
  if [ "$1 $2" = "pr merge" ] && [ -n "${FAKE_MERGE_FAILS:-}" ]; then
    echo "Pull request is not mergeable" >&2
    exit 1
  fi
  if [ "$1 $2" = "issue comment" ] && [ -n "${FAKE_COMMENT_FAILS:-}" ]; then
    echo "fake gh: injected comment failure" >&2
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
cat > "$TMP/bin/curl" << 'EOF'
#!/bin/bash
echo "curl $*" >> "$FAKE_CURL_LOG"
if [ -n "${FAKE_CURL_FAIL:-}" ]; then
  echo "curl: ($FAKE_CURL_FAIL) fake curl failure" >&2
  exit "$FAKE_CURL_FAIL"
fi
cat "$FAKE_STATUS"
EOF
chmod +x "$TMP/bin/curl"
export PATH="$TMP/bin:$PATH" FAKE_LOG="$LOG" FAKE_FIX="$FIX" FAKE_CURL_LOG="$TMP/curl.log" FAKE_STATUS="$TMP/status.json"

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }
expect() { if [ "$2" = 0 ]; then ok "$1"; else ng "$1"; fi; }
logged() { grep -q -- "$1" "$LOG"; }
not_logged() { ! grep -q -- "$1" "$LOG"; }

OLD="2020-01-01T00:00:00Z"
REVIEWER="oc-reviewer-for-signature-studio[bot]"

reset() { rm -rf "$FIX"; mkdir -p "$FIX"; : > "$LOG"; : > "$TMP/out"; : > "$FAKE_CURL_LOG"; unset FAKE_MERGE_FAILS FAKE_COMMENT_FAILS FAKE_FAIL FAKE_CURL_FAIL; export OC_WORKER_URL_FILE="$TMP/no-worker-url"; }
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
  fx "repos/o/r/pulls/$1" "{\"state\":\"open\",\"merged_at\":null,\"mergeable\":$2}" # state / merged_at は reopen-pr.sh が読む (#2597)
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

# 1i. fork からの差し戻し PR (FIX_IDLE) も dispatch しない (write 権限の run を第三者の入力で動かさない)。oc:stuck も付けず、一覧に出して次へ進む
reset
base "[$(pr 1 aaa111 false "$OLD" '[]' '' fork-user/signature-studio-dev),$(pr 2 bbb222 true "$OLD")]"
detail 1 true "[$(review "$REVIEWER" aaa111 CHANGES_REQUESTED)]"
detail 2 true
wd
not_logged 'repos/o/r/dispatches' && not_logged 'oc-dispatch' && not_logged 'add-label oc:stuck' && logged 'pr ready 2' && grep -q 'fork からの PR' "$TMP/out"
expect "fork changes_requested PR -> no dispatch, no oc:stuck, listed and skipped" $?

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

# 3. 現在の head に差し戻しがあるのに fix が無い -> repository_dispatch (oc-fix, changes-requested)。差し戻しは再提出しない (#719)
reset
base "[$(pr 3 ccc333 false "$OLD")]"
detail 3 true "[$(review "$REVIEWER" ccc333 CHANGES_REQUESTED)]"
wd
logged 'client_payload\[pr\]=3' && logged 'client_payload\[reason\]=changes-requested' && not_logged 'pr review 3'
expect "unfixed changes_requested -> repository_dispatch oc-fix (no re-request)" $?

# 3b. 同じ head の差し戻しの fix dispatch が上限 (3 回) に達したら oc:stuck で止める (#719)
reset
base "[$(pr 3 ccc333 false "$OLD")]"
detail 3 true "[$(review "$REVIEWER" ccc333 CHANGES_REQUESTED)]" "[$(for _ in 1 2 3; do printf '{"user":{"login":"%s","type":"Bot"},"body":"x <!-- oc-dispatch:ccc333 -->"},' "$REVIEWER"; done | sed 's/,$//')]"
wd
logged 'pr edit 3 .*--add-label oc:stuck' && not_logged 'repos/o/r/dispatches'
expect "changes_requested dispatch limit reached -> oc:stuck, no more dispatch" $?

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
! grep -E '^gh (api -X|label|issue (create|close|comment|reopen|edit))' "$LOG" | grep -q . && not_logged 'repos/o/r/issues/10' && not_logged 'repos/o/r/dispatches' && [ "$(grep -c 'issues?state=open' "$LOG")" = 1 ]
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

# 25. 許可されない素材名 (fetchsh) を含む本文で review が打ち切られた PR -> 名前を除いて本文を直し、コメントして review を再起動する (#CI-45)
reset
base "[$(pr 40 a40abc false "$OLD" '[]' $'oc_artifacts: fl-win64 fetchsh\n本文')]"
detail 40 true
wd
logged 'pr edit 40 .*--body-file' && grep -q '^oc_artifacts: fl-win64$' "$TMP/oc-artifacts-40.md" && logged 'pr comment 40 .*oc-artifacts-fixed:a40abc' && logged 'pr close 40' && logged 'pr reopen 40'
expect "bad oc_artifacts name -> body repaired, marker comment, review restarted" $?

# 26. ネガコン: 許可名のみの本文は補正しない (通常の review 再起動だけ)
reset
base "[$(pr 41 b41bcd false "$OLD" '[]' $'oc_artifacts: fl-win64 toolchain-emsdk\n本文')]"
detail 41 true
wd
logged 'pr reopen 41' && not_logged 'body-file' && not_logged 'oc-artifacts-fixed'
expect "allowlisted names only -> no repair" $?

# 27. ネガコン: 補正済みマーカーがある head の 2 回目は、本文を再度書き換えず oc:stuck で止める (同じ head は 1 回まで)
reset
base "[$(pr 42 c42cde false "$OLD" '[]' $'oc_artifacts: fetchsh\n本文')]"
detail 42 true "[]" "[$(printf '{"user":{"login":"%s","type":"Bot"},"body":"x <!-- oc-artifacts-fixed:c42cde -->"}' "$REVIEWER")]"
wd
not_logged 'body-file' && not_logged 'pr reopen 42' && logged 'pr edit 42 .*--add-label oc:stuck'
expect "second repair on the same head -> no rewrite, oc:stuck" $?

# 28. ネガコン: fork の PR は本文を書き換えない
reset
base "[$(pr 43 d43def false "$OLD" '[]' $'oc_artifacts: fetchsh\n本文' fork-user/signature-studio-dev)]"
detail 43 true
wd
not_logged 'body-file' && not_logged 'pr reopen 43' && grep -q 'fork からの PR' "$TMP/out"
expect "fork PR with a bad name -> not touched" $?

# 29. 差し戻し上限で oc:stuck になった PR (oc-pm-intent: stuck) は、入力不正があっても補正しない (ネガコン)
reset
base "[$(pr 44 e44efa false "$OLD" '[{"name":"oc:stuck"}]' $'oc_artifacts: fetchsh\n本文')]"
detail 44 true "[]" "[$(printf '{"user":{"login":"%s","type":"Bot"},"body":"stop <!-- oc-pm-intent: stuck pr=44 reason=reset -->"}' "$REVIEWER")]"
wd
not_logged 'body-file' && not_logged 'remove-label' && not_logged 'pr reopen 44' && grep -q 'STUCK_LABELLED' "$TMP/out"
expect "review-limit oc:stuck PR is not repaired (negative control)" $?

# 30. oc:stuck が review 打ち切り (入力不正) で付いた PR は、補正して oc:stuck を外し review を再起動する
reset
base "[$(pr 45 f45fab false "$OLD" '[{"name":"oc:stuck"}]' $'oc_artifacts: plugins-ott fetchsh\n本文')]"
detail 45 true
wd
logged 'pr edit 45 .*--remove-label oc:stuck' && logged 'pr reopen 45' && grep -q '^oc_artifacts: plugins-ott$' "$TMP/oc-artifacts-45.md"
expect "stuck by input error -> repaired, label removed, review restarted" $?

# 31. stuck の滞留時間: events の labeled (oc:stuck) から max / p50 を出す (固定の events。p50 は下側中央値)
reset
base "[$(pr 50 g50aa0 false "$OLD" '[{"name":"oc:stuck"}]'),$(pr 51 g51aa1 false "$OLD" '[{"name":"oc:stuck"}]'),$(pr 52 g52aa2 false "$OLD" '[{"name":"oc:stuck"}]')]"
fx 'repos/o/r/issues/50/events' '[{"event":"labeled","label":{"name":"oc:stuck"},"created_at":"2020-01-01T00:00:00Z"}]'
fx 'repos/o/r/issues/51/events' '[{"event":"labeled","label":{"name":"oc:stuck"},"created_at":"2020-01-02T00:00:00Z"}]'
fx 'repos/o/r/issues/52/events' '[{"event":"unlabeled","label":{"name":"oc:stuck"},"created_at":"2019-12-31T00:00:00Z"},{"event":"labeled","label":{"name":"oc:stuck"},"created_at":"2020-01-03T00:00:00Z"}]'
wd
grep -q '^stuck=3 ' "$TMP/out" && a="$(sed -n 's/.*stuck-age-max=\([0-9]*\) .*/\1/p' "$TMP/out")" && p="$(sed -n 's/.*stuck-age-p50=\([0-9]*\).*/\1/p' "$TMP/out")" && [ $((a - p)) = 1440 ] && [ "$p" -gt 0 ]
expect "stuck age: stuck=3, max - p50 = 1440 min (labeled from events, latest labeled used)" $?

# 32. 本文の補正は DRY=1 では何もしない
reset
base "[$(pr 46 h46bc0 false "$OLD" '[]' $'oc_artifacts: fetchsh\n本文')]"
detail 46 true
DRY=1 wd
not_logged 'body-file' && not_logged 'pr reopen 46' && grep -q 'DRY: repair oc_artifacts' "$TMP/out"
expect "DRY=1 plans the repair without acting" $?

# 33〜. PM Worker の停止検知 (#CI-49)。fake curl が /status を返し、fake gh が障害 issue の一覧・起票を記録する。
ago() { date -u -d "$1 minutes ago" +%Y-%m-%dT%H:%M:%S.123Z; } # ago <分前>: Worker の last_tick の形 (ミリ秒付き)
agoz() { date -u -d "$1 minutes ago" +%Y-%m-%dT%H:%M:%SZ; }    # agoz <分前>: GitHub API の時刻の形
# worker <configured> <installed> <fresh> <last_tick または null> [追加のキー json 片]: fake /status と URL ファイルを用意する
worker() {
  local tick="$4"
  [ "$tick" = null ] || tick="\"$tick\""
  printf '{"mode":"dry-run","active_runs":3,"configured":%s,"installed":%s,"fresh":%s,"last_tick":%s,"pm_bot_login":"pm[bot]"%s}' "$1" "$2" "$3" "$tick" "${5:+,$5}" > "$FAKE_STATUS"
  printf 'https://pm.example.test\n' > "$TMP/worker_url"
  export OC_WORKER_URL_FILE="$TMP/worker_url"
}
# open_down / closed_down: gh issue list (ラベル pm-worker-down の open / closed。複数は , 区切り)。
# ci_titles: [CI-n] の採番に読む gh issue list (state=all) と gh pr list (state=all)。
# 実 repo の REST 一覧 (repos/.../issues?state=...) は PR だけを返すので、REST の fixture は既定では置かない (使われないことを下で確かめる)。
open_down() { fx 'issue-list?state=open&label=pm-worker-down' "[$1]"; }
closed_down() { fx 'issue-list?state=closed&label=pm-worker-down' "[$1]"; }
ci_titles() {
  fx 'issue-list?state=all' '[{"number":2324,"title":"[CI-45] a"},{"number":2328,"title":"[CI-49] b"},{"number":2400,"title":"[CI-5] c"},{"number":2401,"title":"[DOCS-99] d"},{"number":2402,"title":"[CI-12b] e"}]'
  fx 'pr-list?state=all' '[{"number":2403,"title":"[CI-61] a pull request"}]'
}
note() { printf '{"user":{"login":"%s","type":"%s"},"created_at":"%s","body":"[watchdog] note <!-- oc-worker-down-note -->"}' "${2:-$REVIEWER}" "${3:-Bot}" "$(agoz "$1")"; } # note <分前> [login] [type]
TODAY="$(date -u +%Y-%m-%d)"
BODY="$TMP/oc-worker-down-body.md"
no_worker_writes() { ! grep -qE 'gh (issue (create|close|comment|reopen|edit)|label) ' "$LOG"; } # 読み取り (issue list) は数えない
worker_setup() { reset; base '[]'; open_down ''; closed_down ''; ci_titles; }

# 33a. configured:false (現在の本番の状態) -> 起票しない。ネガコン (fake curl は呼ばれており、gh の issue/label 操作は 0 件)
worker_setup
worker false false false null
wd; rc=$?
[ "$rc" = 0 ] && grep -q -- '-fsS -m 10 https://pm.example.test/status' "$FAKE_CURL_LOG" && no_worker_writes && grep -q '^worker=not-set-up' "$TMP/out"
expect "configured:false installed:false (production state) -> no issue, status was read" $?

# 33a2. configured / installed の片方だけが false でも起票しない
worker_setup
worker true false false "$(ago 60)"
wd
no_worker_writes
expect "configured:true installed:false -> no issue" $?
worker_setup
worker false true false "$(ago 60)"
wd
no_worker_writes
expect "configured:false installed:true -> no issue" $?

# 33b. configured:true + installed:true + fresh:false -> ラベルを作って、題名 [CI-<最大+1>] の障害 issue を起票する
worker_setup
worker true true false "$(ago 3)"
wd; rc=$?
[ "$rc" = 0 ] && logged 'label create pm-worker-down' && logged "issue create --repo o/r --title \[CI-62\] PM Worker 停止 ($TODAY) --body-file .* --label pm-worker-down" && not_logged 'needs-user-input' && not_logged 'issue comment' && not_logged 'issue reopen'
expect "fresh:false on a live worker -> issue [CI-62] (max CI-61 incl. PR titles, +1) with label pm-worker-down" $?
grep -q '@pycabbage' "$BODY" && grep -q '"fresh": false' "$BODY" && grep -q '"configured": true' "$BODY"
expect "the issue body has @pycabbage and a copy of /status" $?

# 33b2. fresh:true でも last_tick が 15 分より古い (16 分前) -> 起票する
worker_setup
worker true true true "$(ago 16)"
wd
logged 'issue create .*--label pm-worker-down' && grep -q '^worker=down' "$TMP/out"
expect "fresh:true but last_tick 16 min old -> issue" $?

# 33b3. 起票の本文に秘密を示す名前のキーは写さない (トップレベルも入れ子も)
worker_setup
worker true true false "$(ago 20)" '"webhook_secret":"s3cr3t-value","nested":{"private_key":"pk-value","runs":2}'
wd
logged 'issue create' && ! grep -qE 's3cr3t-value|pk-value' "$BODY" && grep -q '"runs": 2' "$BODY"
expect "secret-looking keys are not copied into the issue body" $?

# 33b4. 一覧が取れない (dedup の根拠が無い) ときは起票しない
worker_setup
worker true true false "$(ago 20)"
FAKE_FAIL='label=pm-worker-down' wd
not_logged 'issue create' && grep -q 'failed to list' "$TMP/out"
expect "open-issue list fails -> nothing is filed (fail-closed)" $?
worker_setup
worker true true false "$(ago 20)"
FAKE_FAIL='issue-list?state=all' wd
not_logged 'issue create' && grep -q 'failed to count' "$TMP/out"
expect "CI title list (gh issue list) fails -> nothing is filed (fail-closed)" $?
worker_setup
worker true true false "$(ago 20)"
FAKE_FAIL='pr-list?state=all' wd
not_logged 'issue create' && grep -q 'failed to count' "$TMP/out"
expect "CI title list (gh pr list) fails -> nothing is filed (fail-closed)" $?

# 33b5. DRY=1 は起票の計画だけを出す
worker_setup
worker true true false "$(ago 20)"
DRY=1 wd
not_logged 'issue create' && not_logged 'label create' && grep -q "DRY: file '\[CI-62\] PM Worker 停止 ($TODAY)'" "$TMP/out"
expect "DRY=1 plans the issue without filing" $?

# 33b6. 実 repo の REST 一覧 (repos/.../issues?state=...) は PR だけを返す。採番と dedup はそれを読まず gh issue list / gh pr list を読む
worker_setup
fx 'repos/o/r/issues?state=all&per_page=100' '[{"number":2403,"title":"[CI-99] a pull request","pull_request":{"url":"u"}}]'
fx 'repos/o/r/issues?state=open&labels=pm-worker-down&per_page=100' '[{"number":2404,"title":"x","created_at":"2020-01-01T00:00:00Z","pull_request":{"url":"u"}}]'
worker true true false "$(ago 20)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' '[]'
wd
logged 'issue comment 77' && not_logged 'issue create' && not_logged 'issues?state=all' && not_logged 'labels=pm-worker-down'
expect "REST lists return only pull requests -> the open outage issue (from gh issue list) gets the note, no new issue" $?
worker_setup
fx 'repos/o/r/issues?state=all&per_page=100' '[{"number":2403,"title":"[CI-99] a pull request","pull_request":{"url":"u"}}]'
worker true true false "$(ago 20)"
wd
logged "issue create --repo o/r --title \[CI-62\] PM Worker 停止" && not_logged 'issues?state=all'
expect "REST PR-only list (CI-99) does not count: number from gh issue/pr lists -> [CI-62]" $?

# 33b7. gh issue list / gh pr list は --limit を明示する (既定値では足りない)
worker_setup
worker true true false "$(ago 20)"
wd
logged 'issue list --repo o/r --state all --limit 3000' && logged 'pr list --repo o/r --state all --limit 3000' && logged 'issue list --repo o/r --state open --label pm-worker-down --limit 200' && logged 'issue list --repo o/r --state closed --label pm-worker-down --limit 200'
expect "gh lists pass an explicit --limit (3000 titles, 200 labelled issues)" $?

# 33b8. PR の題名の最大が issue より大きければ、その +1 (採番は issue と PR の両方)
worker_setup
fx 'pr-list?state=all' '[{"number":2500,"title":"[CI-70] a pull request"}]'
worker true true false "$(ago 20)"
wd
logged "issue create --repo o/r --title \[CI-71\] PM Worker 停止" && not_logged 'issue reopen'
expect "a PR title [CI-70] is counted -> [CI-71]" $?

# 33b9. 題名の一覧が上限 (3000 件) に達したら、欠けているかもしれないので起票しない (fail-closed)
worker_setup
fx 'issue-list?state=all' "$(jq -n '[range(3000) | {title: "[DOCS-1] x"}]')"
worker true true false "$(ago 20)"
wd
not_logged 'issue create' && grep -q 'reached the limit' "$TMP/out"
expect "title list at the 3000 limit -> nothing is filed (may be truncated)" $?

# 33c. open の障害 issue がある -> 追記のみ。新規 0 件 (ネガコン)
worker_setup
worker true true false "$(ago 20)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' '[]'
wd
logged 'issue comment 77 .*--body-file' && [ "$(grep -c 'issue create' "$LOG")" = 0 ] && not_logged 'label create' && not_logged 'issue reopen' && grep -q 'oc-worker-down-note' "$BODY"
expect "open pm-worker-down issue -> note only, 0 new issues" $?

# 33c2. 直近 (10 分前) に reviewer が追記済みなら、追記も見送る (5 分ごとの点検でコメントを水増ししない)
worker_setup
worker true true false "$(ago 20)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' "[$(note 10)]"
wd
not_logged 'issue comment' && not_logged 'issue create'
expect "a note 10 min ago -> no further note (throttled), no new issue" $?

# 33c3. 60 分より前の追記なら、また追記する
worker_setup
worker true true false "$(ago 20)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' "[$(note 61)]"
wd
logged 'issue comment 77' && not_logged 'issue create'
expect "a note 61 min ago -> another note" $?

# 33c4. ネガコン: 別アカウントが偽装したマーカーは数えない
worker_setup
worker true true false "$(ago 20)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' "[$(note 1 someone-else User)]"
wd
logged 'issue comment 77' && not_logged 'issue create'
expect "a spoofed note marker from another account does not throttle" $?

# 33c5. 起票して間もない (10 分前) issue は、追記マーカーが無くても追記しない
worker_setup
worker true true false "$(ago 20)"
open_down "{\"number\":77,\"createdAt\":\"$(agoz 10)\"}"
fx 'repos/o/r/issues/77/comments' '[]'
wd
not_logged 'issue comment' && not_logged 'issue create'
expect "an issue filed 10 min ago -> no note yet" $?

# 33c6. PR (pull_request を持つ項目) はラベルが付いていても障害 issue とみなさない
worker_setup
worker true true false "$(ago 20)"
open_down '{"number":78,"createdAt":"2020-01-01T00:00:00Z","pull_request":{"url":"u"}}'
wd
logged 'issue create' && not_logged 'issue comment'
expect "a labelled pull request is not an outage issue" $?

# 33c7. 24 時間以内に close された同ラベルの issue -> reopen して追記 (新規 0 件)
worker_setup
worker true true false "$(ago 20)"
closed_down "{\"number\":88,\"closedAt\":\"$(agoz 120)\"}"
wd
logged 'issue reopen 88' && logged 'issue comment 88' && not_logged 'issue create' && grep -q 'oc-worker-down-note' "$BODY"
expect "issue closed 2h ago -> reopened with a note, 0 new issues" $?

# 33c8. 25 時間前に close された issue は reopen せず、新規に起票する。PR は対象外
worker_setup
worker true true false "$(ago 20)"
closed_down "{\"number\":88,\"closedAt\":\"$(agoz 1500)\"},{\"number\":89,\"closedAt\":\"$(agoz 5)\",\"pull_request\":{\"url\":\"u\"}}"
wd
not_logged 'issue reopen' && logged 'issue create'
expect "closed 25h ago (and a closed PR) -> not reopened, a new issue" $?

# 33d. 回復 (fresh:true + last_tick 1 分前) -> open の障害 issue にコメントして close する
worker_setup
worker true true true "$(ago 1)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"},{"number":76,"createdAt":"2019-01-01T00:00:00Z"}'
wd
logged 'issue close 77 .*--comment .*回復.*oc-worker-recovered' && logged 'issue close 76' && not_logged 'issue create'
expect "recovered (fresh:true, last_tick 1 min) -> comment + close on every open outage issue" $?

# 33d2. ネガコン: fresh:true でも last_tick が 10 分前 (5 分より古い) なら close しない。起票もしない (中間域)
worker_setup
worker true true true "$(ago 10)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' '[]'
wd
not_logged 'issue close' && not_logged 'issue create' && not_logged 'issue comment'
expect "fresh:true but last_tick 10 min old -> neither closed nor filed (hysteresis)" $?

# 33d3. ネガコン: fresh:false なら last_tick が新しくても close しない
worker_setup
worker true true false "$(ago 1)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' '[]'
wd
not_logged 'issue close'
expect "fresh:false -> an open outage issue is not closed" $?

# 33d4. 障害 issue が無ければ、健全な Worker では gh の issue / label 操作は無い
worker_setup
worker true true true "$(ago 1)"
wd
no_worker_writes
expect "healthy worker without outage issue -> no write" $?

# 33d5. 回復時の DRY=1 は close の計画だけを出す
worker_setup
worker true true true "$(ago 1)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
DRY=1 wd
not_logged 'issue close' && grep -q 'DRY: close #77' "$TMP/out"
expect "DRY=1 plans the close without acting" $?

# 33e. curl の timeout -> 何もしない (ネガコン)。終了コードも変えない
worker_setup
worker true true false "$(ago 60)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
FAKE_CURL_FAIL=28 wd; rc=$?
[ "$rc" = 0 ] && no_worker_writes && grep -q 'could not read' "$TMP/out" && grep -q 'curl -fsS -m 10' "$FAKE_CURL_LOG"
expect "curl timeout -> warning only, no issue/label/comment, exit 0" $?

# 33e2. URL のファイルが無い -> 警告だけ
worker_setup
wd; rc=$?
[ "$rc" = 0 ] && no_worker_writes && [ ! -s "$FAKE_CURL_LOG" ] && grep -q 'worker_url not found' "$TMP/out"
expect "no worker_url file -> warning only, curl not called" $?

# 33e3. JSON 不正 (HTML・必須キー欠落・型違い・配列) -> 警告だけ
for bad in '<html>502</html>' '{"configured":true,"installed":true,"last_tick":null}' '{"configured":"true","installed":true,"fresh":false,"last_tick":null}' '[]'; do
  worker_setup
  worker true true false null
  printf '%s' "$bad" > "$FAKE_STATUS"
  wd; rc=$?
  [ "$rc" = 0 ] && no_worker_writes && grep -q 'not the expected JSON' "$TMP/out"
  expect "bad /status JSON ($bad) -> warning only" $?
done

# 33e4. fresh:true で last_tick が読めない (null / 日時でない) -> 判定できないので何もしない
for t in null tomorrow; do
  worker_setup
  worker true true true "$t"
  wd
  no_worker_writes
  expect "fresh:true with unreadable last_tick ($t) -> nothing" $?
done

# 33f. last_tick が 14 分前 (fresh:true) -> 起票しない (境界。15 分より古くない)
worker_setup
worker true true true "$(ago 14)"
wd
no_worker_writes && grep -q '^worker=ok' "$TMP/out"
expect "last_tick 14 min ago -> no issue (boundary)" $?

# 33g. 既定の URL は tools/pm/worker_url (リポジトリ内の 1 行)。watchdog.sh はそのファイルの URL の /status を読む
reset
base '[]'
printf '{"configured":false,"installed":false,"fresh":false,"last_tick":null}' > "$FAKE_STATUS"
unset OC_WORKER_URL_FILE
wd
grep -q -- '-fsS -m 10 https://signature-studio-pm.pycabbage.workers.dev/status$' "$FAKE_CURL_LOG"
expect "default URL file is tools/pm/worker_url (curl -fsS -m 10 <url>/status)" $?
[ "$(cat "$SCRIPTS/../../tools/pm/worker_url")" = https://signature-studio-pm.pycabbage.workers.dev ] && [ "$(wc -l < "$SCRIPTS/../../tools/pm/worker_url")" = 1 ]
expect "tools/pm/worker_url is one line with no trailing slash" $?
export OC_WORKER_URL_FILE="$TMP/no-worker-url"

# 33h. 結果は step summary に出る
worker_setup
worker true true true "$(ago 1)"
GITHUB_STEP_SUMMARY="$TMP/summary-w.md" wd
grep -q '^worker=ok' "$TMP/summary-w.md"
expect "worker status is written to the step summary" $?

# 33i〜. launch の停止 (#CI-135)。/status の launch_halted (reason・since) と launch_halted_overdue を読み、overdue なら障害 issue に理由と起点を追記する
lh() { printf '"launch_halted":{"reason":"%s","since":"%s"},"launch_halted_overdue":%s' "$1" "$2" "$3"; } # lh <reason> <since> <overdue>: /status に足す launch_halted の JSON 片
S20="$(agoz 20)"

# 33i. 健全な Worker で launch が 15 分以上止まっている (overdue)・障害 issue が無い -> [CI-62] PM Worker launch 停止 を起票する。理由と起点を本文に書く
worker_setup
worker true true true "$(ago 1)" "$(lh no-import "$S20" true)"
wd; rc=$?
[ "$rc" = 0 ] && logged 'label create pm-worker-down' && logged "issue create --repo o/r --title \[CI-62\] PM Worker launch 停止 ($TODAY) --body-file .* --label pm-worker-down" && not_logged 'issue close' && not_logged 'issue reopen' && grep -q 'launch=halted (reason=no-import' "$TMP/out"
expect "launch overdue on a healthy worker, no outage issue -> [CI-62] PM Worker launch 停止 (label pm-worker-down)" $?
grep -q 'launch が止まっています' "$BODY" && grep -q '"reason": "no-import"' "$BODY" && grep -q "$S20" "$BODY" && grep -q '@pycabbage' "$BODY"
expect "the launch issue body has the reason, the start time and @pycabbage" $?

# 33i2. 障害 issue が開いていれば、理由と起点を追記するだけ。新規 0 件・close しない
worker_setup
worker true true true "$(ago 1)" "$(lh no-import "$S20" true)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' '[]'
wd
logged 'issue comment 77 .*--body-file' && not_logged 'issue create' && not_logged 'issue close' && grep -q 'launch はまだ止まっています' "$BODY" && grep -q 'reason=no-import' "$BODY" && grep -q "$S20" "$BODY" && grep -q 'oc-worker-down-note' "$BODY"
expect "launch overdue + open outage issue -> note with reason and start, no new issue, not closed" $?

# 33i3. 止まってから 5 分 (overdue でない) -> 追記も close もしない。止まっている間は回復としない
worker_setup
worker true true true "$(ago 1)" "$(lh rate-guard "$(agoz 5)" false)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' '[]'
wd
not_logged 'issue close' && not_logged 'issue comment' && not_logged 'issue create'
expect "launch halted 5 min (not overdue) -> the open outage issue is kept (no close, no note)" $?

# 33i4. review-only は意図した停止なので障害として扱わない。overdue でも追記・起票しない。開いた障害 issue は回復として close する
worker_setup
worker true true true "$(ago 1)" "$(lh review-only "$(agoz 60)" true)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' '[]'
wd
logged 'issue close 77' && not_logged 'issue create' && not_logged 'issue comment'
expect "review-only (overdue) -> no note and no new issue; an open outage issue is recovered (closed)" $?
worker_setup
worker true true true "$(ago 1)" "$(lh review-only "$(agoz 60)" true)"
wd
no_worker_writes
expect "review-only (overdue) with no open outage issue -> no write" $?

# 33i5. launch_halted が null に戻った -> 既存の回復の規則のまま、開いた障害 issue に回復を書いて close する
worker_setup
worker true true true "$(ago 1)" '"launch_halted":null,"launch_halted_overdue":false'
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
wd
logged 'issue close 77 .*--comment .*回復.*oc-worker-recovered' && not_logged 'issue create'
expect "launch_halted back to null -> recovery comment and close on the open outage issue" $?

# 33i6. 追記の間隔は CI-49 と同じ (直近 10 分に追記済みなら追記しない。同じ marker を数える)
worker_setup
worker true true true "$(ago 1)" "$(lh stale "$S20" true)"
open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/77/comments' "[$(note 10)]"
wd
not_logged 'issue comment' && not_logged 'issue create'
expect "launch overdue, a note 10 min ago -> no further note (shared throttle)" $?

# 33i7. launch_halted の形が読めない -> 警告だけ。追記も起票もせず、開いた障害 issue も回復とみなして close しない
for bad in '"launch_halted":"no-import","launch_halted_overdue":true' '"launch_halted":{"reason":"no-import","since":"x"},"launch_halted_overdue":"yes"'; do
  worker_setup
  worker true true true "$(ago 1)" "$bad"
  open_down '{"number":77,"createdAt":"2020-01-01T00:00:00Z"}'
  wd; rc=$?
  [ "$rc" = 0 ] && not_logged 'issue close' && not_logged 'issue create' && not_logged 'issue comment' && grep -q 'unexpected shape' "$TMP/out"
  expect "unreadable launch_halted ($bad) -> warning only, the open issue is kept" $?
done

# 33i8. ネガコン: /status が読めなければ launch の判定はせず、PR の点検は続く
worker_setup
base "[$(pr 6 fff666 false "$OLD")]"
detail 6 true "[$(review "$REVIEWER" oldhead COMMENTED)]"
worker true true true "$(ago 1)" "$(lh no-import "$S20" true)"
FAKE_CURL_FAIL=28 wd; rc=$?
[ "$rc" = 0 ] && logged 'pr reopen 6' && grep -q 'could not read' "$TMP/out" && not_logged 'issue create' && not_logged 'issue comment'
expect "status unreadable -> no launch action, the PR pass still reopens #6 (exit 0)" $?

# 34〜. 暫定の oc-pm 起動 (#CI-50)。停止 PR (oc:stuck) は issues/<N>/comments、oc:no-pr の issue は issue list、記録の一覧は issues/comments (fixture)。
tcm() { jq -nc --arg l "$1" --arg t "$2" --arg b "$3" '{user:{login:$l,type:$t},body:$b}'; } # tcm <login> <type> <body>
ago_s() { date -u -d "@$(($(date -u +%s) - $1))" +%Y-%m-%dT%H:%M:%SZ; }                    # ago_s <秒前>: GitHub の時刻の形
mk() { tcm "$REVIEWER" Bot "<!-- oc-pm-dispatch:$1 ts=$(ago_s "$2") -->"; }                  # mk <ref> <秒前>: reviewer の記録 (oc-pm-dispatch)
LIMIT_INTENT='差し戻しが上限に達したため停止します。<!-- oc-fix-limit --> <!-- oc-pm-intent: stuck pr=60 reason=ceiling -->'
limit_for() { printf '差し戻しが上限に達したため停止します。<!-- oc-fix-limit --> <!-- oc-pm-intent: stuck pr=%s reason=ceiling -->' "$1"; } # limit_for <PR 番号>: その PR の停止印
OPENCODE='opencode-for-signature-studio[bot]'
MARK='github-actions[bot]' # 窓の印 (oc-fix-limit) の作者 = job の GITHUB_TOKEN (#2622)
nopr() { fx 'issue-list?state=open&label=oc:no-pr' "[$1]"; }  # nopr <issue の JSON (,区切り)>: gh issue list --label oc:no-pr
nrow() { printf '{"number":%s,"labels":[%s]}' "$1" "$2"; }   # nrow <番号> <labels の中身>
ledger() { fx 'repos/o/r/issues/comments' "[$1]"; }          # ledger <記録の comment JSON (,区切り)>: 実 repo の REST (since 付き) の代わり
pm_status() { # pm_status <mode> <fresh>: fake /status と URL ファイル
  printf '{"mode":"%s","configured":true,"installed":true,"fresh":%s,"last_tick":"%s"}' "$1" "$2" "$(ago 1)" > "$FAKE_STATUS"
  printf 'https://pm.example.test\n' > "$TMP/worker_url"
  export OC_WORKER_URL_FILE="$TMP/worker_url"
}
pm_base() { # 既定: oc:stuck の PR 60 (最新の停止印に intent あり)、oc:no-pr は無し、記録は無し
  base "[$(pr 60 a60 false "$OLD" '[{"name":"oc:stuck"}]')]"
  fx 'repos/o/r/issues/60/comments' "[$(tcm "$MARK" Bot "$LIMIT_INTENT")]"
  nopr ''
  ledger ''
}

# 34. oc:stuck の PR で、最新の oc-fix-limit に oc-pm-intent: stuck がある -> oc-pm (kind=stuck ref=60)。送る前に記録のコメントを残す
reset
pm_base
wd
logged 'api -X POST repos/o/r/dispatches -f event_type=oc-pm' && logged 'client_payload\[kind\]=stuck' && logged 'client_payload\[ref\]=60'
expect "stuck PR with oc-pm-intent -> repository_dispatch oc-pm (kind=stuck ref=60)" $?

# 34a. 記録のコメント (oc-pm-dispatch:<ref> ts=) は送信より前に残す
[ "$(grep -n 'issue comment 60 ' "$LOG" | head -n 1 | cut -d: -f1)" -lt "$(grep -n 'api -X POST repos/o/r/dispatches' "$LOG" | head -n 1 | cut -d: -f1)" ] && logged 'oc-pm-dispatch:60 ts='
expect "the dispatch record comment is written before the dispatch" $?

# 34b. payload は kind と ref の 2 つだけ (自由文を入れない)
[ "$(grep -o 'client_payload\[[a-z_]*\]' "$LOG" | sort -u | tr '\n' ' ')" = 'client_payload[kind] client_payload[ref] ' ]
expect "payload keys are exactly kind and ref" $?

# 34c. ネガコン: oc-pm-intent が無い停止 PR は送らない
reset
base "[$(pr 61 a61 false "$OLD" '[{"name":"oc:stuck"}]')]"
fx 'repos/o/r/issues/61/comments' "[$(tcm "$MARK" Bot '差し戻しが上限に達しました。<!-- oc-fix-limit -->')]"
nopr ''; ledger ''
wd
not_logged 'dispatches' && not_logged 'oc-pm-dispatch'
expect "ネガコン: stuck PR without oc-pm-intent is not dispatched" $?

# 34d. 最新の oc-fix-limit だけを見る: 古い停止印に intent があっても、最新に無ければ送らない。逆なら送る
reset
base "[$(pr 62 a62 false "$OLD" '[{"name":"oc:stuck"}]'),$(pr 63 a63 false "$OLD" '[{"name":"oc:stuck"}]')]"
fx 'repos/o/r/issues/62/comments' "[$(tcm "$MARK" Bot '<!-- oc-fix-limit -->'),$(tcm "$MARK" Bot "$(limit_for 62)")]"
fx 'repos/o/r/issues/63/comments' "[$(tcm "$MARK" Bot "$(limit_for 63)"),$(tcm "$MARK" Bot '<!-- oc-fix-limit -->')]"
nopr ''; ledger ''
wd
logged 'client_payload\[ref\]=62' && not_logged 'client_payload\[ref\]=63'
expect "only the latest oc-fix-limit decides the intent (ref 62 sent, ref 63 not)" $?

# 34e. ネガコン: 実装 App の login でも Bot でない投稿の停止印の intent は数えない
reset
base "[$(pr 64 a64 false "$OLD" '[{"name":"oc:stuck"}]')]"
fx 'repos/o/r/issues/64/comments' "[$(tcm "$OPENCODE" User "$(limit_for 64)")]"
nopr ''; ledger ''
wd
not_logged 'dispatches'
expect "ネガコン: an intent from a non-bot account is not trusted" $?

# 34f. ネガコン: reviewer の Bot が投稿した停止印は数えない (停止印は実装 App が書く)
reset
base "[$(pr 74 a74 false "$OLD" '[{"name":"oc:stuck"}]')]"
fx 'repos/o/r/issues/74/comments' "[$(tcm "$REVIEWER" Bot '<!-- oc-fix-limit --> <!-- oc-pm-intent: stuck pr=74 reason=ceiling -->')]"
nopr ''; ledger ''
wd
not_logged 'dispatches'
expect "ネガコン: a stop mark posted by the reviewer bot is not counted" $?

# 34g. ネガコン (#2622): 実装 App (agent と同じ token) 名義の偽の停止印は intent として数えない
reset
base "[$(pr 65 a65 false "$OLD" '[{"name":"oc:stuck"}]')]"
fx 'repos/o/r/issues/65/comments' "[$(tcm "$OPENCODE" Bot "$(limit_for 65)")]"
nopr ''; ledger ''
wd
not_logged 'dispatches'
expect "ネガコン: a forged stop mark posted under the implementer App is not trusted" $?

# 34g. ネガコン: 別の PR 番号を指すコピーの停止印は数えない (pr=60 は #6 の接頭辞ではなく、#75 とも別)
reset
base "[$(pr 6 a6 false "$OLD" '[{"name":"oc:stuck"}]'),$(pr 75 a75 false "$OLD" '[{"name":"oc:stuck"}]')]"
fx 'repos/o/r/issues/6/comments' "[$(tcm "$MARK" Bot "$LIMIT_INTENT")]"
fx 'repos/o/r/issues/75/comments' "[$(tcm "$MARK" Bot "$LIMIT_INTENT")]"
nopr ''; ledger ''
wd
not_logged 'dispatches'
expect "ネガコン: an intent naming another PR (pr=60 copied to #6 and #75) is not counted" $?

# 35. oc:no-pr の issue で最後の oc-run-outcome の reason が split / stop -> oc-pm (kind=no_pr)。artifact と、後から変わった issue は送らない
reset
base '[]'
nopr "$(nrow 70 '{"name":"oc:no-pr"}'),$(nrow 71 '{"name":"oc:no-pr"}'),$(nrow 72 '{"name":"oc:no-pr"}'),$(nrow 73 '{"name":"oc:no-pr"}')"
fx 'repos/o/r/issues/70/comments' "[$(tcm "$OPENCODE" Bot '<!-- oc-run-outcome: no-pr reason=split run=1 -->')]"
fx 'repos/o/r/issues/71/comments' "[$(tcm "$OPENCODE" Bot '<!-- oc-run-outcome: no-pr reason=artifact run=2 -->')]"
fx 'repos/o/r/issues/72/comments' "[$(tcm "$OPENCODE" Bot '<!-- oc-run-outcome: no-pr reason=stop run=3 -->')]"
fx 'repos/o/r/issues/73/comments' "[$(tcm "$OPENCODE" Bot '<!-- oc-run-outcome: no-pr reason=split run=4 -->'),$(tcm "$OPENCODE" Bot '<!-- oc-run-outcome: no-pr reason=artifact run=5 -->')]"
ledger ''
wd
logged 'client_payload\[kind\]=no_pr' && logged 'client_payload\[ref\]=70' && logged 'client_payload\[ref\]=72' && not_logged 'client_payload\[ref\]=71' && not_logged 'client_payload\[ref\]=73'
expect "no_pr: reason=split/stop is dispatched, reason=artifact and a later artifact are not" $?

# 35a. ネガコン: pm-apply / needs-user-input の付いた oc:no-pr の issue は、reason が split でも dispatch / コメントが 0 回
reset
base '[]'
nopr "$(nrow 80 '{"name":"oc:no-pr"},{"name":"pm-apply"}'),$(nrow 81 '{"name":"oc:no-pr"},{"name":"needs-user-input"}')"
fx 'repos/o/r/issues/80/comments' "[$(tcm "$OPENCODE" Bot '<!-- oc-run-outcome: no-pr reason=split run=1 -->')]"
fx 'repos/o/r/issues/81/comments' "[$(tcm "$OPENCODE" Bot '<!-- oc-run-outcome: no-pr reason=split run=2 -->')]"
ledger ''
wd
not_logged 'dispatches' && not_logged 'issue comment 8[01] '
expect "ネガコン: pm-apply / needs-user-input issues get no dispatch and no comment" $?

# 35b. oc:no-pr の一覧が上限 (200 件) に達したら、取りこぼしを警告する (送るかどうかは変えない)
reset
base '[]'
rows=(); for i in $(seq 1 200); do rows+=("$(nrow "$i" '{"name":"oc:no-pr"}')"); done
nopr "$(IFS=,; echo "${rows[*]}")"
ledger ''
wd
grep -q 'oc:no-pr list reached the limit (200)' "$TMP/out"
expect "oc:no-pr list at the limit (200) -> warning" $?

# 36. ネガコン: Worker が mode=live かつ fresh=true なら送らない (partial・fresh=false・取れない は送る)
reset
pm_base
pm_status live true
wd
not_logged 'dispatches' && grep -q 'oc-pm sent=0 (PM Worker is live' "$TMP/out"
expect "ネガコン: PM Worker live and fresh -> no dispatch" $?

reset
pm_base
pm_status partial true
wd
logged 'client_payload\[ref\]=60'
expect "PM Worker partial (not both live) -> dispatch" $?

reset
pm_base
pm_status live false
wd
logged 'client_payload\[ref\]=60'
expect "PM Worker live but not fresh -> dispatch" $?

reset
pm_base
pm_status live true
FAKE_CURL_FAIL=28 wd
logged 'client_payload\[ref\]=60'
expect "/status unreachable -> treated as not live -> dispatch" $?

# 37. 同じ ref は 24 時間で 3 回まで (記録のコメントを数える)。2 回と 25 時間前の 1 回は数えない
reset
pm_base
ledger "$(mk 60 600),$(mk 60 3000),$(mk 60 90000)"
wd
logged 'client_payload\[ref\]=60'
expect "same ref: 2 records in 24h (and one older than 24h) -> still dispatched" $?

# 37a. ネガコン: 24 時間に 3 回済みの ref は送らない
reset
pm_base
ledger "$(mk 60 600),$(mk 60 3000),$(mk 60 20000)"
wd
not_logged 'dispatches' && grep -q 'oc-pm: stuck #60 skipped (dispatched 3 times' "$TMP/out"
expect "ネガコン: a ref already dispatched 3 times in 24h is skipped" $?

# 37b. ネガコン: 記録の偽装 (reviewer 以外の第三者の oc-pm-dispatch) は数えない
reset
pm_base
ledger "$(tcm "$OPENCODE" Bot '<!-- oc-pm-dispatch:60 ts=2026-10-14T14:00:00Z -->'),$(tcm "$REVIEWER" User '<!-- oc-pm-dispatch:60 ts=2026-10-14T14:00:00Z -->'),$(mk 60 3000),$(mk 60 600)"
wd
logged 'client_payload\[ref\]=60'
expect "ネガコン: records by others are not counted (only the 2 by the reviewer bot count)" $?

# 38. 1 時間に 12 件まで。12 件済みなら次は送らない (ネガコン)。11 件なら送る
reset
pm_base
m=(); for i in $(seq 900 911); do m+=("$(mk "$i" 600)"); done
ledger "$(IFS=,; echo "${m[*]}")"
wd
not_logged 'dispatches' && grep -q 'deferred (reached 12 in the last hour)' "$TMP/out"
expect "12 dispatches in the last hour -> no dispatch (deferred)" $?

reset
pm_base
m=(); for i in $(seq 900 910); do m+=("$(mk "$i" 600)"); done
ledger "$(IFS=,; echo "${m[*]}")"
wd
logged 'client_payload\[ref\]=60'
expect "11 dispatches in the last hour -> still dispatched" $?

# 39. 1 回の点検で送るのは 3 件まで。17 件の停止 PR を DRY=1 で点検すると 3 件だけ計画され、何も送らない
reset
rows=()
for i in $(seq 101 117); do
  rows+=("$(pr "$i" "a$i" false "$OLD" '[{"name":"oc:stuck"}]')")
  fx "repos/o/r/issues/$i/comments" "[$(tcm "$MARK" Bot "$(limit_for "$i")")]"
done
base "[$(IFS=,; echo "${rows[*]}")]"
nopr ''; ledger ''
DRY=1 wd
[ "$(grep -c 'DRY: dispatch oc-pm kind=stuck' "$TMP/out")" = 3 ] && grep -q 'oc-pm candidates=17 planned=3 deferred=14' "$TMP/out" && not_logged 'dispatches' && not_logged 'issue comment'
expect "17 stopped PRs: DRY=1 plans only 3 dispatches (the rest deferred), no write" $?

# 39a. DRY=1 は送らない (計画だけ)
reset
pm_base
DRY=1 wd
grep -q 'DRY: dispatch oc-pm kind=stuck for #60' "$TMP/out" && not_logged 'dispatches' && not_logged 'issue comment'
expect "DRY=1 plans the oc-pm dispatch without sending or recording" $?

# 39a2. 記録のコメントが残せなければ送らない (記録が無いと上限が効かない)。終了コードは変わらない
reset
pm_base
FAKE_COMMENT_FAILS=1 wd; rc=$?
[ "$rc" = 0 ] && logged 'issue comment 60 ' && not_logged 'dispatches' && grep -q 'failed: dispatch oc-pm kind=stuck for #60' "$TMP/out"
expect "the record comment cannot be written -> no dispatch (fail-closed), exit 0" $?

# 39b. 記録の一覧が読めなければ送らない (fail-closed)。終了コードは変わらない
reset
pm_base
FAKE_FAIL='issues/comments' wd; rc=$?
[ "$rc" = 0 ] && not_logged 'dispatches' && grep -q 'failed to read the oc-pm dispatch records' "$TMP/out"
expect "dispatch records unreadable -> no dispatch (fail-closed), exit 0" $?

# 39c. 停止 PR の comments が読めなければ、その PR だけ候補から外す (他は続く)
reset
base "[$(pr 65 a65 false "$OLD" '[{"name":"oc:stuck"}]'),$(pr 66 a66 false "$OLD" '[{"name":"oc:stuck"}]')]"
fx 'repos/o/r/issues/66/comments' "[$(tcm "$MARK" Bot "$(limit_for 66)")]"
nopr ''; ledger ''
wd
logged 'client_payload\[ref\]=66' && grep -q '#65 oc-pm: failed to read comments' "$TMP/out"
expect "a stuck PR whose comments cannot be read is skipped, the others continue" $?

# 40〜. PM Worker の率制限 alert (#CI-142)。rate_limit_alert (true) か rest_remaining (1500 未満) で、ラベル oc:rate-limit の issue に載せる。
#       fresh=false の値は古いかもしれないので使わない。open があれば追記のみ (60 分に 1 回まで)。open が無くても 6 時間以内に閉じた issue があれば起票しない。
rate_setup() { # rate_setup <open の oc:rate-limit issue の JSON (無ければ空)> [閉じた issue の JSON (無ければ空)]
  worker_setup
  fx 'issue-list?state=open&label=oc:rate-limit' "[${1:-}]"
  fx 'issue-list?state=closed&label=oc:rate-limit' "[${2:-}]"
}
RATE_BODY="$TMP/oc-rate-limit-body.md"
rnote() { printf '{"user":{"login":"%s","type":"%s"},"created_at":"%s","body":"[watchdog] x <!-- oc-rate-limit-note -->"}' "${2:-$REVIEWER}" "${3:-Bot}" "$(agoz "$1")"; } # rnote <分前> [login] [type]
no_rate_calls() { ! grep -q 'oc:rate-limit' "$LOG"; } # 何もしない判定では、oc:rate-limit を含む gh 呼び出し (読みも書きも) が 0 件

# 40a. rate_limit_alert=true (fresh) で open の oc:rate-limit が無い -> ラベルを用意して [CI-62] の issue を起票する
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1800'
wd; rc=$?
[ "$rc" = 0 ] && logged 'api -X POST repos/o/r/labels' && logged "issue create --repo o/r --title \[CI-62\] PM Worker 率制限 alert ($TODAY) --body-file .* --label oc:rate-limit" && grep -q '^rate=alert (rate_limit_alert=true)' "$TMP/out"
expect "rate_limit_alert=true (fresh) -> issue [CI-62] with label oc:rate-limit" $?
grep -q '@pycabbage' "$RATE_BODY" && grep -q '"rest_remaining": 1800' "$RATE_BODY" && grep -q 'rate-guard' "$RATE_BODY"
expect "the rate issue body has @pycabbage, the /status rate fields and the rate-guard note" $?

# 40b. rest_remaining が 1499 (1500 未満) なら、rate_limit_alert が false でも起票する
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":false,"rest_remaining":1499'
wd
logged "issue create --repo o/r --title \[CI-62\] PM Worker 率制限 alert" && grep -q 'rest_remaining=1499 (< 1500)' "$TMP/out"
expect "rest_remaining 1499 (< 1500) with no alert -> issue" $?

# 40c. ネガコン (境界): rest_remaining が 1500 ちょうどで rate_limit_alert が false なら何もしない
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":false,"rest_remaining":1500'
wd
no_rate_calls && grep -q '^rate=ok (rate_limit_alert=false, rest_remaining=1500)' "$TMP/out"
expect "ネガコン: rest_remaining 1500 (boundary, not below) -> nothing" $?

# 40d. ネガコン: 値が null (未観測) なら起票しない。rate の項目が無い古い Worker も同じ
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":false,"rest_remaining":null'
wd
no_rate_calls && grep -q '^rate=ok (rate_limit_alert=false, rest_remaining=null)' "$TMP/out"
expect "ネガコン: rest_remaining null and no alert -> nothing" $?
rate_setup ''
worker true true true "$(ago 1)"
wd
no_rate_calls && grep -q '^rate=ok' "$TMP/out"
expect "ネガコン: no rate fields at all (older Worker) -> nothing" $?

# 40e. ネガコン: rate_limit_alert が真偽値の true でない (文字列) なら alert と認めない
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":"true","rest_remaining":null'
wd
no_rate_calls
expect "ネガコン: rate_limit_alert as a string is not an alert" $?

# 40f. ネガコン: fresh=false の値は古いかもしれないので使わない (alert でも rate の呼び出しは無い)
rate_setup ''
worker true true false "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1000'
wd
no_rate_calls && grep -q '^rate=skipped (fresh=false' "$TMP/out"
expect "ネガコン: fresh=false -> the stale rate values are not used" $?

# 40g. ネガコン: /status が取れない・JSON 不正なら何もしない (終了コードは 0)
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":100'
FAKE_CURL_FAIL=28 wd; rc=$?
[ "$rc" = 0 ] && no_rate_calls && grep -q '^rate=skipped (no status)' "$TMP/out"
expect "ネガコン: /status unreachable -> nothing for rate, exit 0" $?
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":true'
printf '<html>502</html>' > "$FAKE_STATUS"
wd; rc=$?
[ "$rc" = 0 ] && no_rate_calls && grep -q '^rate=skipped (no status)' "$TMP/out"
expect "ネガコン: /status is not JSON -> nothing for rate, exit 0" $?

# 40h. 既存の open の oc:rate-limit issue があれば追記のみ。新規 0 件
rate_setup '{"number":91,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/91/comments' '[]'
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
wd
logged 'issue comment 91 .*--body-file' && [ "$(grep -c 'issue create' "$LOG")" = 0 ] && grep -q 'oc-rate-limit-note' "$RATE_BODY"
expect "open oc:rate-limit issue -> note only, 0 new issues" $?

# 40i. ネガコン: 直近 10 分に追記 (oc-rate-limit-note) があれば、追記も見送る (5 分ごとの点検でコメントを水増ししない)
rate_setup '{"number":91,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/91/comments' "[$(rnote 10)]"
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
wd
not_logged 'issue comment 91' && [ "$(grep -c 'issue create' "$LOG")" = 0 ] && grep -q 'already reported' "$TMP/out"
expect "ネガコン: a note 10 min ago -> no further note (throttled)" $?

# 40j. 61 分前の追記なら、また追記する。別アカウントが偽装した追記は数えない
rate_setup '{"number":91,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/91/comments' "[$(rnote 61)]"
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
wd
logged 'issue comment 91 ' && [ "$(grep -c 'issue create' "$LOG")" = 0 ]
expect "a note 61 min ago -> another note" $?
rate_setup '{"number":91,"createdAt":"2020-01-01T00:00:00Z"}'
fx 'repos/o/r/issues/91/comments' "[$(rnote 1 someone-else User)]"
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
wd
logged 'issue comment 91 '
expect "ネガコン: a spoofed note from another account does not throttle" $?

# 40k. ネガコン: 起票して間もない (10 分前) open の issue は、追記マーカーが無くても追記しない
rate_setup "{\"number\":91,\"createdAt\":\"$(agoz 10)\"}"
fx 'repos/o/r/issues/91/comments' '[]'
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
wd
not_logged 'issue comment 91' && [ "$(grep -c 'issue create' "$LOG")" = 0 ]
expect "ネガコン: an open issue created 10 min ago -> no note yet" $?

# 40l. ネガコン (fail-closed): 一覧が取れなければ何もしない。起票も追記もしない
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
FAKE_FAIL='issue-list?state=open&label=oc:rate-limit' wd; rc=$?
[ "$rc" = 0 ] && [ "$(grep -c 'issue create' "$LOG")" = 0 ] && grep -q 'failed to list oc:rate-limit issues' "$TMP/out"
expect "ネガコン: open oc:rate-limit list fails -> nothing filed (fail-closed), exit 0" $?
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
FAKE_FAIL='issue-list?state=all' wd
[ "$(grep -c 'issue create' "$LOG")" = 0 ] && grep -q 'failed to count' "$TMP/out"
expect "ネガコン: CI title list fails -> nothing filed (fail-closed)" $?

# 40m. DRY=1 は起票の計画だけを出す (ラベル作成も起票もしない)
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
DRY=1 wd
not_logged 'issue create' && not_logged 'api -X POST repos/o/r/labels' && grep -q "DRY: file '\[CI-62\] PM Worker 率制限 alert ($TODAY)' with label oc:rate-limit" "$TMP/out"
expect "DRY=1 plans the rate-limit issue without filing" $?

# 40n. 健全な値 (alert false・rest_remaining 1500 以上) では oc:rate-limit の gh 呼び出しが 0 件
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":false,"rest_remaining":4000'
wd
no_rate_calls && grep -q '^rate=ok' "$TMP/out"
expect "healthy rate values -> no rate call at all" $?

# 40o. 題名の採番 (pm-worker-down と同じ [CI-n]) が上限に達したら、起票しない (fail-closed)
rate_setup ''
fx 'issue-list?state=all' "$(jq -n '[range(3000) | {title: "[DOCS-1] x"}]')"
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
wd
[ "$(grep -c 'issue create' "$LOG")" = 0 ] && grep -q 'reached the limit' "$TMP/out"
expect "ネガコン: title list at the limit -> rate-limit issue not filed" $?

# 40p. 結果は step summary にも出る
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":false,"rest_remaining":1200'
GITHUB_STEP_SUMMARY="$TMP/summary-rate.md" wd
grep -q '^rate=alert (rest_remaining=1200 (< 1500))' "$TMP/summary-rate.md"
expect "rate result is written to the step summary" $?

# 40q. 閾値の一致: watchdog の REST_REMAINING_MIN は ratelimit.ts と一致し、5 件・30%・2 回連続は ratealert.ts の値 (Worker が判定する)
grep -q '^REST_REMAINING_MIN=1500$' "$SCRIPTS/watchdog.sh" && grep -qx 'export const REST_REMAINING_MIN = 1500;' "$SCRIPTS/../../infra/pm-worker/src/ratelimit.ts" &&
  grep -qx 'export const RATE_MIN_COUNT = 5;' "$SCRIPTS/../../infra/pm-worker/src/ratealert.ts" && grep -qx 'export const RATE_MIN_PERCENT = 30;' "$SCRIPTS/../../infra/pm-worker/src/ratealert.ts" && grep -qx 'export const RATE_STREAK = 2;' "$SCRIPTS/../../infra/pm-worker/src/ratealert.ts"
expect "thresholds match infra/pm-worker (REST 1500; alert 5 runs / 30% / 2 streak)" $?

# 40r. ネガコン: 人が close した oc:rate-limit issue が 1 時間前にあれば、alert が続いても起票しない (再起票の抑止。reopen もしない)
rate_setup '' "{\"number\":90,\"closedAt\":\"$(agoz 60)\"}"
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
wd; rc=$?
[ "$rc" = 0 ] && [ "$(grep -c 'issue create' "$LOG")" = 0 ] && not_logged 'issue reopen' && not_logged 'issue comment' && grep -q 'was closed within 6 hours' "$TMP/out"
expect "ネガコン: a rate issue closed 1 hour ago -> no new issue, no reopen (6-hour hold)" $?

# 40s. 25 時間前に閉じた oc:rate-limit issue なら、もう新しい issue を起票する
rate_setup '' "{\"number\":90,\"closedAt\":\"$(agoz 1500)\"}"
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
wd; rc=$?
[ "$rc" = 0 ] && logged "issue create --repo o/r --title \[CI-62\] PM Worker 率制限 alert ($TODAY) --body-file .* --label oc:rate-limit"
expect "a rate issue closed 25 hours ago -> a new [CI-62] issue is filed" $?

# 40t. ネガコン (fail-closed): 閉じた oc:rate-limit issue の一覧が取れなければ起票しない。終了コードは 0
rate_setup ''
worker true true true "$(ago 1)" '"rate_limit_alert":true,"rest_remaining":1200'
FAKE_FAIL='issue-list?state=closed&label=oc:rate-limit' wd; rc=$?
[ "$rc" = 0 ] && [ "$(grep -c 'issue create' "$LOG")" = 0 ] && grep -q 'failed to list closed oc:rate-limit issues' "$TMP/out"
expect "ネガコン: closed oc:rate-limit list fails -> nothing filed (fail-closed), exit 0" $?

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
