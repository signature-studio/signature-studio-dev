#!/bin/bash
# test-pr-loop.sh — fix-progress.sh / verify-review-verdict.sh の分岐を fake gh で検証する (#719)。
# 実行: bash .github/scripts/tests/test-pr-loop.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r OC_PR_NUMBER=7 RUNNER_TEMP="$TMP"

# fake gh: `gh api [--paginate] [-X M] repos/... [--jq E]` は $FIX/<path の / を _ にした名前> を返す。
# `gh pr comment|close|reopen` と POST は $LOG に記録するだけ。
FIX="$TMP/fixtures"
LOG="$TMP/gh.log"
mkdir -p "$FIX" "$TMP/bin"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
echo "gh $*" >> "$FAKE_LOG"
if [ "$1" = pr ]; then exit 0; fi
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
    r="$r{\"user\":{\"login\":\"oc-reviewer-for-signature-studio[bot]\"},\"state\":\"CHANGES_REQUESTED\",\"commit_id\":\"c$i\"},"
  done
  fx repos/o/r/pulls/7/reviews "${r%,}]"
  fx repos/o/r/issues/7/comments '[]'
}
run_fix() { GITHUB_ENV="$TMP/env" GITHUB_OUTPUT="$TMP/out" bash "$SCRIPTS/fix-progress.sh" "$@"; }

echo "== fix-progress.sh record (往復の上限)"
setup aaa '[]' 3
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "3 件の差し戻し -> stop=false" $?
grep -qx 'OC_HEAD_BEFORE=aaa' "$TMP/env"; expect "起動時の head を記録する" $?

setup aaa '[]' 10
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "10 件で stop=true" $?
logged 'issues/7/labels'; expect "oc:stuck ラベルを付ける" $?
logged 'pr comment 7'; expect "PR に停止のコメントを残す" $?

setup aaa '[{"name":"oc:stuck"}]' 0
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ラベル済みなら stop=true" $?
! logged 'pr comment'; expect "ラベル済みなら再コメントしない" $?

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

vsetup NONE
fx repos/o/r/issues/7/comments '[{"body":"x <!-- review-retry:hhh -->"},{"body":"x <!-- review-retry:hhh -->"},{"body":"x <!-- review-retry:hhh -->"}]'
verify; rc=$?
{ [ $rc = 1 ] && ! logged 'pr reopen' && logged 'pr comment 7'; }; expect "同じ head に 3 回再起動済み -> 警告して失敗、再起動しない" $?

vsetup NONE
printf '%s' '{"pull_request":{"head":{"sha":"old"}}}' > "$TMP/event.json"
verify "$TMP/event.json"; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close'; }; expect "run 中に head が進んだ -> 検証を免除 (新 head の run が担当)" $?

vsetup NONE
fx repos/o/r/pulls/7 '{"state":"closed","head":{"sha":"hhh"}}'
verify; rc=$?
{ [ $rc = 0 ] && ! logged 'pr close'; }; expect "PR が closed/merged -> 何もしない" $?

echo
printf '%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
