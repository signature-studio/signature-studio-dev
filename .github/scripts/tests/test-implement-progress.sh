#!/bin/bash
# test-implement-progress.sh — implement-progress.sh (implement job 内の無音終了の検知と 1 回だけの再試行・#5727 受入 6) を fake gh で検証する。
# 実行: bash .github/scripts/tests/test-implement-progress.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../implement-progress.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r RUNNER_TEMP="$TMP" GH_TOKEN=x

FIX="$TMP/fixtures"
mkdir -p "$FIX" "$TMP/bin"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
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
[ "$method" = GET ] || exit 0
if [ -n "${FAKE_FAIL:-}" ] && [[ "$path" == *"$FAKE_FAIL"* ]]; then exit 1; fi
f="$FAKE_FIX/${path//\//_}"
[ -f "$f" ] || { echo "fake gh: no fixture for $path" >&2; exit 1; }
if [ -n "$jq_expr" ]; then jq -r "$jq_expr" < "$f"; else cat "$f"; fi
EOF
chmod +x "$TMP/bin/gh"
export PATH="$TMP/bin:$PATH" FAKE_FIX="$FIX"

# 作業用の git repo (HEAD は開始時の sha)
REPO="$TMP/repo"
git init -q "$REPO" && git -C "$REPO" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
START_SHA="$(git -C "$REPO" rev-parse HEAD)"

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }
expect() { if [ "$2" = 0 ]; then ok "$1"; else ng "$1"; fi; }
fx() { printf '%s' "$2" > "$FIX/${1//\//_}"; }
S="2026-10-16T10:00:00Z"
BEFORE="2026-10-16T09:59:00Z"
AFTER="2026-10-16T10:05:00Z"
IMPL='opencode-for-signature-studio[bot]'

# reset: 既定は『何も無い』 (コメント 0 件・ref 0 件・PR 0 件)
reset() {
  rm -rf "$FIX"; mkdir -p "$FIX"
  fx "repos/o/r/issues/42/comments?per_page=100" '[]'
  fx "repos/o/r/git/matching-refs/heads/42-" '[]'
  fx "repos/o/r/pulls?state=all&sort=updated&direction=desc&per_page=100" '[]'
  rm -f "$REPO/leftover.txt" "$TMP/out"
  git -C "$REPO" update-ref HEAD "$START_SHA"
}
# run_check <経過秒の追加> : job 開始を今から (経過 = 0) とした check を走らせ、$TMP/out に出力を残す
run_check() {
  local elapsed="${1:-0}"
  (cd "$REPO" && env OC_ISSUE_NUMBER=42 OC_START_ISO="$S" OC_START_SHA="$START_SHA" \
    OC_JOB_START_EPOCH=$(($(date +%s) - elapsed)) GITHUB_OUTPUT="$TMP/out" \
    bash "$SCRIPT" check) > "$TMP/stderr" 2>&1
  RC=$?
}
get() { sed -n "s/^$1=//p" "$TMP/out" | tail -1; }

# ------------------------------------------------------------------ 副作用の検出
reset
fx "repos/o/r/issues/42/comments?per_page=100" "[{\"user\":{\"login\":\"$IMPL\"},\"created_at\":\"$AFTER\"}]"
run_check
[ "$(get result)" = done ] && [ "$(get reason)" = comment ] && [ "$(get retry)" = false ]
expect "実装 App が run 中に issue へコメントした -> done (再試行しない)" $?

reset
fx "repos/o/r/issues/42/comments?per_page=100" "[{\"user\":{\"login\":\"someone\"},\"created_at\":\"$AFTER\"},{\"user\":{\"login\":\"$IMPL\"},\"created_at\":\"$BEFORE\"}]"
run_check
[ "$(get result)" = none ] && [ "$(get retry)" = true ]
expect "他人のコメントと開始前の App コメントは副作用に数えない -> none (再試行)" $?

reset
fx "repos/o/r/git/matching-refs/heads/42-" '[{"ref":"refs/heads/42-x","object":{"sha":"abc"}}]'
fx "repos/o/r/commits/abc" "{\"commit\":{\"committer\":{\"date\":\"$AFTER\"}}}"
run_check
[ "$(get result)" = done ] && [ "$(get reason)" = push ]
expect "対象ブランチに run 中の commit がある -> done (push)" $?

reset
fx "repos/o/r/git/matching-refs/heads/42-" '[{"ref":"refs/heads/42-x","object":{"sha":"abc"}}]'
fx "repos/o/r/commits/abc" "{\"commit\":{\"committer\":{\"date\":\"$BEFORE\"}}}"
run_check
[ "$(get result)" = none ]
expect "対象ブランチの commit が開始前だけ -> none" $?

reset
fx "repos/o/r/pulls?state=all&sort=updated&direction=desc&per_page=100" "[{\"head\":{\"ref\":\"42-x\"},\"body\":\"\",\"updated_at\":\"$AFTER\"}]"
run_check
[ "$(get result)" = done ] && [ "$(get reason)" = pr ]
expect "run 中に更新された対象 PR がある -> done (pr)" $?

reset
fx "repos/o/r/pulls?state=all&sort=updated&direction=desc&per_page=100" "[{\"head\":{\"ref\":\"7-x\"},\"body\":\"Closes #42\",\"updated_at\":\"$AFTER\"}]"
run_check
[ "$(get result)" = done ]
expect "本文の Closes #42 の PR も対象 (record-run-outcome.sh と同じ判定)" $?

reset
fx "repos/o/r/pulls?state=all&sort=updated&direction=desc&per_page=100" "[{\"head\":{\"ref\":\"420-x\"},\"body\":\"Closes #4200\",\"updated_at\":\"$AFTER\"}]"
run_check
[ "$(get result)" = none ]
expect "#42 と #420・#4200 を取り違えない -> none" $?

# ------------------------------------------------------------------ 無音終了と再試行の可否
reset
run_check
[ "$(get result)" = none ] && [ "$(get reason)" = none ] && [ "$(get retry)" = true ] && [ "$RC" = 0 ]
expect "何も残さず終了し、作業ツリーが clean で時間もある -> none・retry=true" $?

reset
echo dirty > "$REPO/leftover.txt"
run_check
[ "$(get result)" = none ] && [ "$(get retry)" = false ] && [ "$(get reason)" = dirty-worktree ]
expect "未コミットの残骸がある -> 再試行しない (dirty-worktree)" $?
rm -f "$REPO/leftover.txt"

reset
git -C "$REPO" -c user.name=t -c user.email=t@t commit -q --allow-empty -m local
run_check
[ "$(get retry)" = false ] && [ "$(get reason)" = dirty-worktree ]
expect "agent が HEAD を進めた (commit はしたが push 前) -> 再試行しない" $?

reset
run_check 3000
[ "$(get retry)" = false ] && [ "$(get reason)" = no-time-left ]
expect "job の残り時間が足りない (600 秒 < 1080 秒) -> 再試行しない" $?

reset
FAKE_FAIL="comments" run_check
[ "$(get result)" = unknown ] && [ "$(get retry)" = false ] && [ "$(get reason)" = comments-unreadable ]
expect "コメント一覧が読めない -> unknown・再試行しない (推測で none にしない)" $?
unset FAKE_FAIL

reset
fx "repos/o/r/pulls?state=all&sort=updated&direction=desc&per_page=100" "$(jq -cn --arg t "$AFTER" '[range(100) | {head:{ref:"x"},body:"",updated_at:$t}]')"
run_check
[ "$(get result)" = unknown ] && [ "$(get reason)" = pr-overflow ]
expect "PR 一覧が 1 ページを超えて run 中の更新で埋まる -> unknown (判定しない)" $?

# ------------------------------------------------------------------ retry-prompt
printf 'base prompt\n' > "$TMP/prompt.txt"
(OC_PROMPT_SRC="$TMP/prompt.txt" OC_ISSUE_NUMBER=42 RUNNER_TEMP="$TMP" GITHUB_OUTPUT="$TMP/out2" bash "$SCRIPT" retry-prompt) > /dev/null 2>&1
pf="$(sed -n 's/^prompt_file=//p' "$TMP/out2")"
grep -q 'base prompt' "$pf" && grep -q '再試行' "$pf" && grep -q 'Closes #42' "$pf"
expect "retry-prompt は元のプロンプトを残し、再試行の指示 (PR か理由コメント) を足す" $?

# ------------------------------------------------------------------ 不正入力
(cd "$REPO" && env OC_ISSUE_NUMBER='4x' OC_REPO=o/r OC_START_ISO="$S" OC_START_SHA="$START_SHA" OC_JOB_START_EPOCH=1 GITHUB_OUTPUT="$TMP/out3" bash "$SCRIPT" check) > /dev/null 2>&1
[ $? -ne 0 ]
expect "issue 番号が数字でなければ失敗する" $?

bash -n "$SCRIPT"
expect "implement-progress.sh の構文が正しい" $?

# ------------------------------------------------------------------ workflow の配線 (受入 6 のネガコン)
# workflow (.github/workflows/) の変更は GitHub App では push できないため、配線の検査は OC_WORKFLOW_FILE を
# 明示したときだけ走る (既定の CI では skip する。PM が適用版に対して実行する: PR 本文の手順)。
# 修正前の workflow では落ちる (ネガコン)。
if [ -n "${OC_WORKFLOW_FILE:-}" ]; then
  # 抽出は一度だけ行い、grep -q の早期終了による SIGPIPE (pipefail での偽陰性) を避ける
  implement_block() { awk '/^  implement:/{on=1;print;next} /^  [a-z][A-Za-z0-9_-]*:/{on=0} on' "$OC_WORKFLOW_FILE"; }
  BLOCK="$(implement_block)"
  has() { grep -qF -- "$1" <<< "$BLOCK"; }
  has 'implement-progress.sh mark'
  expect "implement job が checkout の直後に mark を取る" $?
  has 'implement-progress.sh check'
  expect "implement job に無音終了の検知 (check) がある" $?
  has 'Run OpenCode (implement run, retry)'
  expect "implement job に job 内の再試行 (1 回) がある" $?
  has 'implement run neither pushed'
  expect "再試行もなお無音なら job を失敗させる" $?
  has "github.event_name == 'issue_comment' && steps.implsha.outcome"
  expect "検知・再試行は issue_comment の run だけ (fix モードは既存の fix-progress 再試行)" $?
else
  echo "skip workflow wiring checks (OC_WORKFLOW_FILE unset)"
fi

echo "pass=$pass fail=$fail"
[ "$fail" = 0 ]
