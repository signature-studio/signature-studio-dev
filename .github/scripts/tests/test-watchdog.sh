#!/bin/bash
# test-watchdog.sh — watchdog.sh の判定と操作を fake gh で検証する (#719)。
# 実行: bash .github/scripts/tests/test-watchdog.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/**・.github/actions/**・opencode.yaml の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r RUNNER_TEMP="$TMP" OC_REOPEN_WAIT=0 GH_TOKEN=x

# fake gh: `gh api [--paginate] repos/... [--jq E]` は $FIX/<path の / を _ にした名前> を返す。
# `gh pr|label ...` は $LOG に記録するだけ (FAKE_MERGE_FAILS=1 なら `gh pr merge` は失敗する)。
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
path="" jq_expr=""
while [ $# -gt 0 ]; do
  case "$1" in
    --paginate) ;;
    --jq) jq_expr="$2"; shift ;;
    repos/*) path="$1" ;;
  esac
  shift
done
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

reset() { rm -rf "$FIX"; mkdir -p "$FIX"; : > "$LOG"; : > "$TMP/out"; unset FAKE_MERGE_FAILS; }
fx() { printf '%s' "$2" > "$FIX/${1//\//_}"; } # fx <path> <json>
# runs / PR 一覧は全ケース共通の形。active_runs は workflow_runs の JSON (既定は空)。
base() { # base <prs json> [active runs json]
  local runs="${2:-[]}" s
  for s in in_progress queued pending waiting; do
    fx "repos/o/r/actions/runs?status=$s&per_page=100" "{\"workflow_runs\":$([ "$s" = in_progress ] && echo "$runs" || echo '[]')}"
  done
  fx "repos/o/r/pulls?state=open&per_page=100" "$1"
}
# pr <n> <head> <draft> <updated_at> <labels json>
pr() { printf '{"number":%s,"title":"PR %s","head":{"sha":"%s"},"draft":%s,"updated_at":"%s","labels":%s}' "$1" "$1" "$2" "$3" "$4" "${5:-[]}"; }
# detail <n> <mergeable> <reviews json> <comments json>
detail() {
  fx "repos/o/r/pulls/$1" "{\"mergeable\":$2}"
  fx "repos/o/r/pulls/$1/reviews" "${3:-[]}"
  fx "repos/o/r/issues/$1/comments" "${4:-[]}"
}
review() { printf '{"user":{"login":"%s","type":"%s"},"commit_id":"%s","state":"%s","body":"%s"}' "$1" "${5:-Bot}" "$2" "$3" "${4:-}"; }
wd() { bash "$SCRIPTS/watchdog.sh" > "$TMP/out" 2>&1; }

# 1. 競合 -> reviewer 名義の [conflict] 差し戻し
reset
base "[$(pr 1 aaa111 false "$OLD")]"
detail 1 false
wd
logged 'pr review 1 .*--request-changes' && logged '\[conflict\]'
expect "conflict -> request-changes [conflict]" $?

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
detail 11 true "[]" '[{"body":"a <!-- review-retry:kkk111 -->"},{"body":"b <!-- review-retry:kkk111 -->"},{"body":"c <!-- review-retry:kkk111 -->"}]'
wd
logged 'pr edit 11 .*--add-label oc:stuck' && not_logged 'pr reopen 11'
expect "review retries exhausted -> oc:stuck, no reopen" $?

# 12. 実行中の run が PR を担当していれば何もしない
reset
base "[$(pr 12 lll222 false "$OLD")]" '[{"event":"pull_request","display_title":"PR 12","pull_requests":[{"number":12}]}]'
detail 12 true
wd
not_logged 'pr reopen 12' && not_logged 'pr review 12'
expect "PR with a running run is covered" $?

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

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
