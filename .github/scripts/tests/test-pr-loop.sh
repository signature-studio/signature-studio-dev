#!/bin/bash
# test-pr-loop.sh — fix-progress.sh / verify-review-verdict.sh / reopen-pr.sh の分岐を fake gh で検証する (#719, #721)。
# 実行: bash .github/scripts/tests/test-pr-loop.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/**・.github/actions/**・opencode.yaml の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r OC_PR_NUMBER=7 RUNNER_TEMP="$TMP" OC_REOPEN_WAIT=0

# fake gh: `gh api [--paginate] [-X M] repos/... [--jq E]` は $FIX/<path の / を _ にした名前> を返す。
# `gh pr comment|close|reopen` と POST は $LOG に記録するだけ。
# FAKE_REOPEN_FAILS=N なら、最初の N 回の `gh pr reopen` を失敗させる。
FIX="$TMP/fixtures"
LOG="$TMP/gh.log"
mkdir -p "$FIX" "$TMP/bin"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
echo "gh $*" >> "$FAKE_LOG"
if [ "$1" = pr ]; then
  if [ "$2" = reopen ] && [ -n "${FAKE_REOPEN_FAILS:-}" ]; then
    n=$(($(cat "$FAKE_FIX/reopen_calls" 2> /dev/null || echo 0) + 1))
    echo "$n" > "$FAKE_FIX/reopen_calls"
    [ "$n" -le "$FAKE_REOPEN_FAILS" ] && exit 1
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
    -f) shift ;;
    repos/*) path="$1" ;;
  esac
  shift
done
[ "$method" = POST ] && exit 0
f="$FAKE_FIX/${path//\//_}"
[ -f "$f" ] || { echo "fake gh: no fixture for $path" >&2; exit 1; }
if [ -n "$jq_expr" ]; then jq -r "$jq_expr" < "$f"; else cat "$f"; fi
EOF
chmod +x "$TMP/bin/gh"
export PATH="$TMP/bin:$PATH" FAKE_LOG="$LOG" FAKE_FIX="$FIX"

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }
expect() { # <name> <condition exit code>
  if [ "$2" = 0 ]; then ok "$1"; else ng "$1"; fi
}
logged() { grep -q -- "$1" "$LOG"; }

reset() { rm -rf "$FIX"; mkdir -p "$FIX"; : > "$LOG"; : > "$TMP/out"; : > "$TMP/env"; }
fx() { printf '%s' "$2" > "$FIX/${1//\//_}"; } # fx <path> <json>
setup() { # <head> <labels json> <n changes_requested reviews>
  reset
  fx repos/o/r/pulls/7 "{\"state\":\"open\",\"head\":{\"sha\":\"$1\"}}"
  fx repos/o/r/issues/7 "{\"labels\":$2}"
  local r="[" i
  for ((i = 0; i < $3; i++)); do
    r="$r{\"user\":{\"login\":\"oc-reviewer-for-signature-studio[bot]\"},\"state\":\"CHANGES_REQUESTED\",\"commit_id\":\"c$i\",\"submitted_at\":\"2026-02-01T00:00:00Z\"},"
  done
  fx repos/o/r/pulls/7/reviews "${r%,}]"
  fx repos/o/r/issues/7/comments '[]'
}
reviews() { # <submitted_at> <count> [<submitted_at> <count> ...]: oc-reviewer の CHANGES_REQUESTED review の JSON 配列
  local s="" i
  while [ $# -ge 2 ]; do
    for ((i = 0; i < $2; i++)); do
      s="$s{\"user\":{\"login\":\"oc-reviewer-for-signature-studio[bot]\"},\"state\":\"CHANGES_REQUESTED\",\"commit_id\":\"c\",\"submitted_at\":\"$1\"},"
    done
    shift 2
  done
  printf '[%s]' "${s%,}"
}
stop_at() { # <created_at> [login]: 停止コメント (マーカー付き) の JSON 配列
  printf '[{"created_at":"%s","user":{"login":"%s"},"body":"上限 <!-- oc-fix-limit -->"}]' "$1" "${2:-opencode-for-signature-studio[bot]}"
}
run_fix() { GITHUB_ENV="$TMP/env" GITHUB_OUTPUT="$TMP/out" bash "$SCRIPTS/fix-progress.sh" "$@"; }

echo "== fix-progress.sh record (往復の上限 5 件)"
setup aaa '[]' 3
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "3 件の差し戻し -> stop=false" $?
grep -qx 'OC_HEAD_BEFORE=aaa' "$TMP/env"; expect "起動時の head を記録する" $?

setup aaa '[]' 5
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "5 件で stop=true" $?
logged 'issues/7/labels'; expect "oc:stuck ラベルを付ける" $?
logged 'pr comment 7'; expect "PR に停止のコメントを残す" $?

# 停止コメント (oc-fix-limit) より前の差し戻しは数えない: ラベルを外して再開できる
setup aaa '[]' 5
fx repos/o/r/issues/7/comments '[{"created_at":"2026-03-01T00:00:00Z","user":{"login":"opencode-for-signature-studio[bot]"},"body":"stop <!-- oc-fix-limit -->"}]'
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "停止コメントの後に差し戻し 0 件 (ラベルを外した直後) -> stop=false" $?

setup aaa '[]' 5
fx repos/o/r/issues/7/comments '[{"created_at":"2026-03-01T00:00:00Z","user":{"login":"opencode-for-signature-studio[bot]"},"body":"stop <!-- oc-fix-limit -->"}]'
fx repos/o/r/pulls/7/reviews "$(jq -c '. + [{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"CHANGES_REQUESTED","commit_id":"n1","submitted_at":"2026-04-01T00:00:00Z"}]' < "$FIX/repos_o_r_pulls_7_reviews")"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "停止コメントの後の差し戻し 1 件 -> stop=false (数え直し)" $?

setup aaa '[]' 5
fx repos/o/r/issues/7/comments '[{"created_at":"2026-03-01T00:00:00Z","user":{"login":"opencode-for-signature-studio[bot]"},"body":"stop <!-- oc-fix-limit -->"}]'
fx repos/o/r/pulls/7/reviews "$(jq -c '. + [range(0;5)|{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"CHANGES_REQUESTED","commit_id":"n","submitted_at":"2026-04-01T00:00:00Z"}]' < "$FIX/repos_o_r_pulls_7_reviews")"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "停止コメントの後に再び 5 件 -> stop=true" $?

# 起動主体は完全一致: 名前が似ているだけの bot の差し戻しは数えない
setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(jq -nc '[range(0;9)|{"user":{"login":"oc-reviewer-evil[bot]"},"state":"CHANGES_REQUESTED","commit_id":"x","submitted_at":"2026-02-01T00:00:00Z"}]')"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "前方一致するだけの別アカウントの差し戻しは数えない" $?

setup aaa '[{"name":"oc:stuck"}]' 0
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ラベル済みなら stop=true" $?
! logged 'pr comment'; expect "ラベル済みなら再コメントしない" $?

echo "== fix-progress.sh record (上限は直前の停止コメント以降の差し戻しを数える)"
setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(reviews 2026-01-01T00:00:00Z 5 2026-01-03T00:00:00Z 1)"
fx repos/o/r/issues/7/comments "$(stop_at 2026-01-02T00:00:00Z)"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "停止コメントの後の差し戻し 1 件 -> stop=false (ラベルを外して再開)" $?
! logged 'issues/7/labels' && ! logged 'pr comment'; expect "再開時に停止のラベル・コメントを付け直さない" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(reviews 2026-01-01T00:00:00Z 5 2026-01-03T00:00:00Z 5)"
fx repos/o/r/issues/7/comments "$(stop_at 2026-01-02T00:00:00Z)"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "停止コメントの後に上限ぶん差し戻し -> stop=true" $?
logged 'pr comment 7'; expect "再度の停止で PR にコメントする" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(reviews 2026-01-01T00:00:00Z 5 2026-01-03T00:00:00Z 1)"
fx repos/o/r/issues/7/comments "$(stop_at 2026-01-02T00:00:00Z someone)"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "他人の oc-fix-limit マーカーは区切りにしない (6 件 -> stop=true)" $?

echo "== fix-progress.sh check (pushed / answered / none)"
setup bbb '[]' 1
OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > /dev/null
grep -qx 'result=pushed' "$TMP/out"; expect "head が進んだ -> pushed" $?

setup aaa '[]' 1
fx repos/o/r/issues/7/comments '[{"created_at":"2026-01-02T00:00:00Z","user":{"login":"opencode-for-signature-studio[bot]"}}]'
OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > /dev/null
grep -qx 'result=answered' "$TMP/out"; expect "push 無し + bot のコメント -> answered" $?

setup aaa '[]' 1
fx repos/o/r/issues/7/comments '[{"created_at":"2025-12-31T00:00:00Z","user":{"login":"opencode-for-signature-studio[bot]"}},{"created_at":"2026-01-02T00:00:00Z","user":{"login":"someone"}}]'
OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > /dev/null
grep -qx 'result=none' "$TMP/out"; expect "起動前の bot コメント・他人のコメントは数えない -> none" $?

echo "== reopen-pr.sh (close -> reopen。reopen は 3 回まで再試行)"
reset
FAKE_REOPEN_FAILS=1 bash "$SCRIPTS/reopen-pr.sh" > "$TMP/v.out" 2>&1; rc=$?
{ [ $rc = 0 ] && logged 'pr close 7' && [ "$(grep -c 'pr reopen 7' "$LOG")" = 2 ]; }; expect "reopen が 1 回失敗しても再試行で再開する" $?
! logged 'issues/7/labels'; expect "再開できたら oc:stuck を付けない" $?

reset
FAKE_REOPEN_FAILS=99 bash "$SCRIPTS/reopen-pr.sh" > "$TMP/v.out" 2>&1; rc=$?
{ [ $rc = 1 ] && [ "$(grep -c 'pr reopen 7' "$LOG")" = 3 ]; }; expect "reopen が 3 回失敗 -> 非 0 で終わる" $?
{ logged 'issues/7/labels' && logged 'pr comment 7'; }; expect "reopen 失敗時は oc:stuck を付けて PR にコメントする" $?

echo "== fix-progress.sh reopen (旧 workflow との互換)"
reset
run_fix reopen > /dev/null 2>&1; rc=$?
{ [ $rc = 0 ] && logged 'pr close 7' && logged 'pr reopen 7'; }; expect "reopen サブコマンドは reopen-pr.sh に委譲する" $?

echo "== verify-review-verdict.sh"
verify() { GITHUB_EVENT_PATH="${1:-/dev/null}" bash "$SCRIPTS/verify-review-verdict.sh" > "$TMP/v.out" 2>&1; }
vsetup() { # <state of the oc-reviewer review on the head, or NONE>
  reset
  # created_at は「作成直後」(旧実装の Copilot 待ち保留が有効だった条件) にしておく
  fx repos/o/r/pulls/7 "{\"state\":\"open\",\"created_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"head\":{\"sha\":\"hhh\"}}"
  if [ "$1" = NONE ]; then
    fx repos/o/r/pulls/7/reviews '[]'
  else
    fx repos/o/r/pulls/7/reviews "[{\"user\":{\"login\":\"oc-reviewer-for-signature-studio[bot]\"},\"state\":\"$1\",\"commit_id\":\"hhh\",\"body\":\"copilot-pending\"}]"
  fi
  fx repos/o/r/issues/7/comments '[]'
}

vsetup APPROVED; verify; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close'; }; expect "APPROVED -> 何もしない" $?

vsetup CHANGES_REQUESTED; verify; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close'; }; expect "CHANGES_REQUESTED -> 何もしない" $?

vsetup NONE; verify; rc=$?
{ [ $rc = 0 ] && logged 'pr close 7' && logged 'pr reopen 7'; }; expect "verdict 無し -> close -> reopen で再起動" $?

vsetup COMMENTED; verify; rc=$?
{ [ $rc = 0 ] && logged 'pr reopen 7'; }; expect "COMMENT だけ (copilot-pending を含んでも) -> 再起動 (保留は廃止)" $?

vsetup APPROVED
fx repos/o/r/pulls/7/reviews '[{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"APPROVED","commit_id":"hhh"},{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"COMMENTED","commit_id":"hhh"}]'
verify; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close'; }; expect "APPROVED の後に COMMENTED が付いても verdict あり (verdict を持つ最後の review で判定)" $?

vsetup NONE
fx repos/o/r/pulls/7/reviews '[{"user":{"login":"oc-reviewer-evil[bot]"},"state":"APPROVED","commit_id":"hhh"}]'
verify; rc=$?
{ [ $rc = 0 ] && logged 'pr reopen 7'; }; expect "名前が似ているだけの別アカウントの APPROVED は verdict と認めない" $?

vsetup NONE
fx repos/o/r/issues/7/comments '[{"body":"x <!-- review-retry:hhh -->"},{"body":"x <!-- review-retry:hhh -->"},{"body":"x <!-- review-retry:hhh -->"}]'
verify; rc=$?
{ [ $rc = 1 ] && ! logged 'pr reopen' && logged 'pr comment 7'; }; expect "同じ head に 3 回再起動済み -> 警告して失敗、再起動しない" $?

vsetup NONE
printf '%s' '{"pull_request":{"head":{"sha":"old"}}}' > "$TMP/event.json"
verify "$TMP/event.json"; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close'; }; expect "run 中に head が進んだ -> 検証を免除 (新 head の run が担当)" $?

vsetup NONE
fx repos/o/r/pulls/7/reviews '[{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"APPROVED","commit_id":"hhh"},{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"COMMENTED","commit_id":"hhh"}]'
verify; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close'; }; expect "APPROVED の後に COMMENT が付いても verdict は APPROVED のまま (再起動しない)" $?

vsetup NONE
fx repos/o/r/pulls/7 '{"state":"closed","head":{"sha":"hhh"}}'
verify; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close'; }; expect "PR が closed/merged -> 何もしない" $?

vsetup NONE
env -u OC_REPO -u OC_PR_NUMBER GH_TOKEN=x GITHUB_EVENT_PATH=/dev/null RUNNER_TEMP="$TMP" bash "$SCRIPTS/verify-review-verdict.sh" > "$TMP/v.out" 2>&1; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close' && ! logged 'pr reopen' && ! logged 'pr comment'; }; expect "Prepare PR context 失敗で OC_REPO/OC_PR_NUMBER が無い -> 何もせず 0 で終わる (二次失敗しない)" $?

echo "== review-recover.sh (review job が打ち切られたら watchdog を待たず同じ head で再起動 #1950 / CI-38)"
# rrun <annotation> [review-retry マーカー数]: 初期化 -> review job の annotation を仕込んで review-recover.sh を走らせる
rrun() {
  vsetup NONE # vsetup は reset で fixture を消すので、先に呼ぶ
  printf '%s' '{"pull_request":{"number":7,"head":{"sha":"hhh"}}}' > "$TMP/event.json"
  fx repos/o/r/actions/runs/123/jobs '{"jobs":[{"name":"build","id":1},{"name":"review","id":555}]}'
  fx repos/o/r/check-runs/555/annotations "[{\"message\":\"$1\"}]"
  if [ "${2:-0}" -gt 0 ]; then
    local c="[" i
    for ((i = 0; i < $2; i++)); do c="$c{\"body\":\"x <!-- review-retry:hhh -->\"},"; done
    fx repos/o/r/issues/7/comments "${c%,}]"
  fi
  GH_TOKEN=x RUNS_TOKEN=x OC_REPO=o/r GITHUB_RUN_ID=123 GITHUB_EVENT_PATH="$TMP/event.json" \
    bash "$SCRIPTS/review-recover.sh" > "$TMP/v.out" 2>&1; rc=$?
}

rrun "The runner has received a shutdown signal."
{ [ $rc = 0 ] && logged 'pr close 7' && logged 'pr reopen 7'; }; expect "shutdown signal で打ち切られ verdict 無し -> watchdog を待たず同じ head で再起動" $?

rrun "The job has exceeded the maximum execution time of 60 minutes."
{ [ $rc = 0 ] && logged 'pr reopen 7'; }; expect "実行時間超過の打ち切り -> 再起動" $?

rrun "The operation was canceled."
{ [ $rc = 0 ] && ! logged 'pr close' && ! logged 'pr reopen'; }; expect "打ち切り文言が無い (PM の手動 cancel 相当) -> 再起動しない" $?

rrun "The runner has received a shutdown signal." 3
{ [ $rc = 1 ] && ! logged 'pr reopen' && logged 'pr comment 7'; }; expect "同じ head の再起動が上限 3 回に達している -> 再起動せず警告して失敗 (watchdog と上限共有)" $?

rrun "The runner has received a shutdown signal." 2
{ [ $rc = 0 ] && logged 'pr reopen 7'; }; expect "上限未満 (2 回) なら再起動する (上限は review-retry の数で数える)" $?

vsetup NONE
printf '%s' '{"pull_request":{"number":7,"head":{"sha":"hhh"}}}' > "$TMP/event.json"
fx repos/o/r/actions/runs/123/jobs '{"jobs":[{"name":"build","id":1}]}'
GH_TOKEN=x RUNS_TOKEN=x OC_REPO=o/r GITHUB_RUN_ID=123 GITHUB_EVENT_PATH="$TMP/event.json" \
  bash "$SCRIPTS/review-recover.sh" > "$TMP/v.out" 2>&1; rc=$?
{ [ $rc = 0 ] && ! logged 'pr reopen'; }; expect "review job が見つからない -> 何もせず 0 で終わる (watchdog が拾う)" $?

rrun "The runner has received a shutdown signal."
fx repos/o/r/pulls/7 '{"state":"closed","head":{"sha":"hhh"}}'
: > "$LOG"
GH_TOKEN=x RUNS_TOKEN=x OC_REPO=o/r GITHUB_RUN_ID=123 GITHUB_EVENT_PATH="$TMP/event.json" \
  bash "$SCRIPTS/review-recover.sh" > "$TMP/v.out" 2>&1; rc=$?
{ [ $rc = 0 ] && ! logged 'pr reopen'; }; expect "打ち切られた時点で PR が closed/merged -> 再起動しない" $?

echo
printf '%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
