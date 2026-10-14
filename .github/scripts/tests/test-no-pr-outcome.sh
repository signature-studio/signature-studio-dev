#!/bin/bash
# test-no-pr-outcome.sh — no-pr-outcome.sh の判定と操作を fake gh で検証する (#1950)。
# 実行: bash .github/scripts/tests/test-no-pr-outcome.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/** の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../no-pr-outcome.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r GH_TOKEN=x OC_RUN_ID=999 OC_RUN_START=2026-10-14T08:00:00Z

# fake gh: `gh api [--paginate] repos/... [--jq E]` は $FIX/<path の / を _ にした名前> を返す。
# `gh issue|label ...` と POST は $LOG に記録するだけ。FAKE_FAIL=<部分文字列> で、path に含む `gh api` を失敗させる。
FIX="$TMP/fixtures"
LOG="$TMP/gh.log"
mkdir -p "$FIX" "$TMP/bin"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
echo "gh $*" >> "$FAKE_LOG"
if [ "$1" = issue ] || [ "$1" = label ]; then
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

reset() { rm -rf "$FIX"; mkdir -p "$FIX"; : > "$LOG"; : > "$TMP/out"; unset FAKE_FAIL OC_ISSUE_NUMBER OC_RUN_START OC_RUN_FILE; export OC_RUN_START=2026-10-14T08:00:00Z OC_ISSUE_NUMBER=5; }
fx() { printf '%s' "$2" > "$FIX/${1//\//_}"; } # fx <path> <json>
# issue <labels json> [pull_request 付きか (yes/no)]
issue() {
  local pr=""
  [ "${2:-no}" = yes ] && pr=',"pull_request":{"url":"x"}'
  fx "repos/o/r/issues/5" "{\"number\":5,\"labels\":$1$pr}"
}
# standard: PR 一覧と blocker の既定 (PR 無し・blocker 無し)
standard() {
  fx "repos/o/r/pulls?state=all&per_page=100" "${1:-[]}"
  fx "repos/o/r/issues/5/dependencies/blocked_by" "${2:-[]}"
}
run_it() { # run_it [追加の環境変数の代入...]: $TMP/out に標準出力を残す
  env "$@" bash "$SCRIPT" > "$TMP/out" 2>&1
}
pr() { printf '[{"number":%s,"head":{"ref":"%s"},"created_at":"%s","updated_at":"%s"}]' "$1" "$2" "$3" "$3"; }
TEXT_RUN="$TMP/run.jsonl"
run_text() { printf '{"type":"text","part":{"text":"%s"}}\n' "$1" > "$TEXT_RUN"; }

# 1. 着手報告だけで PR が無い -> oc:no-pr を付け、理由付きマーカーを残す
reset
issue '[]'
standard
run_text "素材不足のため停止します。oc_artifacts を追加してください。"
OC_RUN_FILE="$TEXT_RUN" run_it
logged 'issue edit 5 .*--add-label oc:no-pr' && logged 'issue comment 5 .*oc-run-outcome: no-pr reason=artifact run=999'
expect "no PR and no blocker -> oc:no-pr with reason=artifact and marker" $?

# 2. 理由の語彙: 分割 / ブロック / 停止 / 不明
for c in "split|子 issue を起票しました|split" "blocked|#123 がブロックしています|blocked" "stop|着手できません|stop" "unknown|何も書けませんでした|unknown"; do
  IFS='|' read -r name text want <<< "$c"
  reset
  issue '[]'
  standard
  run_text "$text"
  OC_RUN_FILE="$TEXT_RUN" run_it
  logged "reason=$want" && logged 'issue edit 5 .*--add-label oc:no-pr'
  expect "reason vocabulary: $name -> reason=$want" $?
done

# 3. この run が作った PR (head が 5- で始まり、run 開始以降に作成) があれば no-pr ではない。ラベルは外す
reset
issue '[{"name":"oc:no-pr"}]'
standard "$(pr 77 5-oc-run-outcome 2026-10-14T08:30:00Z)"
run_it
logged 'issue edit 5 .*--remove-label oc:no-pr' && not_logged 'add-label' && not_logged 'issue comment'
expect "PR made by this run -> oc:no-pr removed, nothing added" $?

# 4. 開始より前の PR は数えない (前の run の PR)。no-pr を付ける
reset
issue '[]'
standard "$(pr 77 5-old 2026-10-13T08:00:00Z)"
run_text "停止します"
OC_RUN_FILE="$TEXT_RUN" run_it
logged 'add-label oc:no-pr'
expect "PR older than this run is not counted" $?

# 5. 別の issue の枝 (15-... は 5- で始まらない) は数えない
reset
issue '[]'
standard "$(pr 78 15-other 2026-10-14T08:30:00Z)"
run_it
logged 'add-label oc:no-pr'
expect "branch 15-* is not counted for issue 5" $?

# 6. oc:stuck / needs-user-input は人の判断中なので触らない
for lab in oc:stuck needs-user-input; do
  reset
  issue "[{\"name\":\"$lab\"}]"
  standard
  run_it
  not_logged 'add-label' && not_logged 'remove-label' && not_logged 'issue comment'
  expect "label $lab -> nothing recorded" $?
done

# 7. 開いた blocked_by がある issue は記録しない (ブロックされた issue は『ブロック』で宙に浮かない)
reset
issue '[]'
standard "[]" '[{"number":3,"state":"open"}]'
run_it
not_logged 'add-label' && not_logged 'issue comment'
expect "open blocker -> nothing recorded" $?

# 8. 閉じた blocker だけなら記録する
reset
issue '[]'
standard "[]" '[{"number":3,"state":"closed"}]'
run_it
logged 'add-label oc:no-pr'
expect "closed blocker only -> recorded" $?

# 9. PR (issue JSON に pull_request がある) は対象外
reset
issue '[]' yes
standard
run_it
not_logged 'add-label' && grep -q 'out of scope' "$TMP/out"
expect "pull request is out of scope" $?

# 10. issue 番号が無い run は何もしない
reset
issue '[]'
OC_ISSUE_NUMBER= run_it
not_logged 'issue' && grep -q 'nothing to record' "$TMP/out"
expect "no issue number -> nothing" $?

# 11. 開始時刻が無いと PR の有無を判断できないので何もしない (fail-closed)
reset
issue '[]'
standard
OC_RUN_START= run_it
not_logged 'add-label' && grep -q 'OC_RUN_START is unset' "$TMP/out"
expect "missing run start -> no action (fail-closed)" $?

# 12. issue の読み取りに失敗したら何もしない
reset
issue '[]'
standard
FAKE_FAIL=issues/5 run_it
not_logged 'add-label' && grep -q 'failed to read issue' "$TMP/out"
expect "read failure -> no action" $?

# 13. PR 一覧の読み取りに失敗したら何もしない
reset
issue '[]'
standard
FAKE_FAIL=pulls run_it
not_logged 'add-label' && grep -q 'failed to list PRs' "$TMP/out"
expect "PR list failure -> no action" $?

# 14. 既に oc:no-pr が付いている issue でも、再実行は --add-label を冪等に流す (ラベルは重複しない)
reset
issue '[{"name":"oc:no-pr"}]'
standard
run_it
logged 'add-label oc:no-pr'
expect "already labelled -> idempotent add" $?

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
