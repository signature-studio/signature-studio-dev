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
RECENT_BASE='repos/o/r/pulls?state=all&sort=updated&direction=desc&per_page=100&page='
prs() { fx 'repos/o/r/pulls?state=open&per_page=100' "$1"; fx "${RECENT_BASE}1" "$1"; } # open の PR は all の一覧にも出る
recent() { fx "${RECENT_BASE}1" "$1"; } # run 中に open→merge まで済んだ PR を含む一覧 (state=all, updated 順, 1 ページ目)
# agent の最終回答 (opencode の JSONL。最後の text が回答)
answer() { printf '{"type":"text","part":{"text":"途中経過"}}\n{"type":"step_finish","part":{}}\n' > "$TMP/oc.jsonl"; jq -cn --arg t "$1" '{type:"text",part:{text:$t}}' >> "$TMP/oc.jsonl"; }
ev_issue() { printf '{"issue":{"number":42},"comment":{"body":"x","created_at":"2026-10-14T14:00:00Z"}}' > "$TMP/ev.json"; }
ev_nostart() { printf '{"issue":{"number":42},"comment":{"body":"x"}}' > "$TMP/ev.json"; } # 起動コメントの created_at が無い (run の run_started_at で代用)
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

# 2b. 優先順 artifact > blocked > split > stop (素材名を伴う不足だけが artifact)
reset; ev_issue; issue open '[]'; prs '[]'; answer '素材 fl-win64 が無く、依存 issue もあり、1 run に収まらないので停止します'
outcome
reason_is artifact
expect "priority: artifact (named allowlisted material, missing) wins over blocked/split/stop" $?
reset; ev_issue; issue open '[]'; prs '[]'; answer '素材不足で、依存 issue もあり、1 run に収まらないので停止します'
outcome
reason_is blocked
expect "priority: 素材不足 without an allowlisted name is not artifact -> blocked" $?

# 2c. artifact の判定 (#3184): allowlist の素材名と肯定の不足語が同じ節にあるときだけ。語の一致だけでは数えない
. "$SCRIPTS/run-outcome-reason.sh"
for pair in \
  '素材 fl-win64 が無いため停止します|artifact' \
  'plugins-ott が足りないので着手できません|artifact' \
  '`toolchain-emsdk` が見つからず停止|artifact' \
  '素材 fl-win64 は未展開です|artifact' \
  'fl-win64 は実在しません|artifact' \
  '素材 plugins-massivex・toolchain-retdec が必要です|artifact' \
  '素材不足は無い。依存 issue: #1976|blocked' \
  '素材 fl-win64 は揃っている。停止します|stop' \
  '`oc_artifacts` の追加指定は不要。分割案です|split' \
  'fl-win64 の素材不足は無い|unknown' \
  '素材 plugins-ott は実在します（不足なし）|unknown' \
  '素材 fl-win64 は揃っていて、plugins-ott の不足は無い|unknown' \
  'foo-bar が無い。停止します|stop' \
  'plugins-ott-x が無い|unknown' \
  'fl-win64 の必要はない|unknown' \
  'fl-win64 は使わない方針。影響は無い|unknown' \
  '必要な `oc_artifacts`: `plugins-massivex toolchain-retdec toolchain-emsdk`|unknown' \
  '再起動時に必要な素材: `oc_artifacts: fl-win64` (本文のとおり)|unknown' \
  '素材 fl-win64 が無いため停止します。oc_artifacts に追加してください|artifact'; do
  [ "$(run_outcome_reason "${pair%|*}")" = "${pair#*|}" ]
  expect "reason: '${pair%|*}' -> ${pair#*|}" $?
done
for f in watchdog.sh prepare-event-context.sh; do
  [ "$(sed -n "s/^ARTIFACT_RE='\(.*\)'\$/\1/p" "$SCRIPTS/$f" | head -n1)" = "^$ARTIFACT_NAME\$" ]
  expect "allowlist in run-outcome-reason.sh == $f ARTIFACT_RE" $?
done
# 標本 (#1977・#1804・#2965 の実報告。素材は実在するが、報告は『不足は無い』『必要な oc_artifacts』『実在』を含む) -> artifact にならない
FX3184="$HERE/fixtures"
reset; ev_issue; issue open '[]'; prs '[]'; answer "$(cat "$FX3184/run-outcome-3184-1977-blocked.md")"; outcome
{ [ $RC = 0 ] && reason_is blocked && logged 'labels\[\]=oc:no-pr'; }
expect "sample #1977 report (素材不足は無い・必要な oc_artifacts は次回の指定) -> blocked, not artifact" $?
reset; ev_issue; issue open '[]'; prs '[]'; answer "$(cat "$FX3184/run-outcome-3184-1804-split.md")"; outcome
{ [ $RC = 0 ] && reason_is split; }
expect "sample #1804 report (oc_artifacts の追加指定は不要・分割案) -> split, not artifact" $?
reset; ev_issue; issue open '[]'; prs '[]'; answer "$(cat "$FX3184/run-outcome-3184-2965-blocked.md")"; outcome
{ [ $RC = 0 ] && reason_is blocked; }
expect "sample #2965 report (素材は実在・依存 #3077 未達) -> blocked, not artifact" $?
reset; ev_issue; issue open '[]'; prs '[]'; answer '素材 fl-win64 が無いため停止します。plugins-ott が必要です'; outcome
reason_is artifact
expect "record: named allowlisted material missing -> artifact" $?

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

# 4c. run 中に open→merge まで済んだ PR (open の一覧には出ない。12 秒) -> 着手済み。残っていた oc:no-pr は外す
RUN_PR='{"head":{"ref":"x"},"body":"Refs #42","state":"closed","created_at":"2026-10-14T14:00:05Z","merged_at":"2026-10-14T14:00:17Z","updated_at":"2026-10-14T14:00:17Z"}'
reset; ev_issue; issue open '[]'; prs '[]'; recent "[$RUN_PR]"; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'opened or merged during this run' "$TMP/out"; }
expect "PR opened and merged during the run (open->merge 12 s, Refs #42) -> started, nothing recorded" $?
reset; ev_issue; issue open '[{"name":"oc:no-pr"}]'; prs '[]'; recent "[$RUN_PR]"; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && logged 'api -X DELETE repos/o/r/issues/42/labels/oc%3Ano-pr'; }
expect "... and a stale oc:no-pr label is removed" $?
reset; ev_nostart; issue open '[]'; prs '[]'; recent "[$RUN_PR]"; fx repos/o/r/actions/runs/555 '{"run_started_at":"2026-10-14T14:00:00Z"}'; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST'; }
expect "no created_at on the comment -> run start from run_started_at, PR counted" $?
reset; ev_nostart; issue open '[]'; prs '[]'; recent "[$RUN_PR]"; answer '着手報告のみ'
FAKE_FAIL='actions/runs/555' outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'could not read the run start' "$TMP/out"; }
expect "run start unreadable (no created_at, run API fails) -> no write, exit 0" $?

# 4d. 別 issue の PR・run の開始より前に merge 済みの PR は『着手済み』に数えない
reset; ev_issue; issue open '[]'; prs '[]'; recent '[{"head":{"ref":"421-y"},"body":"Closes #421","state":"closed","created_at":"2026-10-14T14:00:05Z","merged_at":"2026-10-14T14:00:17Z"}]'; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && reason_is unknown && logged 'labels\[\]=oc:no-pr'; }
expect "PR for another issue (#421) merged during the run -> not counted (no-PR marker)" $?
reset; ev_issue; issue open '[]'; prs '[]'; recent '[{"head":{"ref":"42-old"},"body":"Refs #42","state":"closed","created_at":"2026-10-14T13:00:00Z","merged_at":"2026-10-14T13:30:00Z"}]'; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && reason_is unknown && logged 'labels\[\]=oc:no-pr'; }
expect "PR for #42 merged before the run started (13:30 < 14:00) -> not counted (no-PR marker)" $?

# 4e. 一覧 (state=all) の読み取りに失敗したら何も書かない
reset; ev_issue; issue open '[]'; prs '[]'
FAKE_FAIL='state=all' outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && not_logged 'api -X DELETE'; }
expect "recent PR list fails -> no write, exit 0" $?

# 4f. 一覧の 1 ページ目が全部 run の開始より後に更新された -> 次のページも読む。上限 (10 ページ) まで止まらなければ何も書かない
FULL="$(jq -cn '[range(100) | {head:{ref:"o\(.)"},body:"",created_at:"2026-10-14T14:30:00Z",merged_at:null,updated_at:"2026-10-14T14:30:00Z"}]')"
reset; ev_issue; issue open '[]'; prs '[]'; recent "$FULL"; fx "${RECENT_BASE}2" "[$RUN_PR]"; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && logged "pulls?state=all&sort=updated&direction=desc&per_page=100&page=2"; }
expect "100 PRs updated after the run start on page 1 -> page 2 read, PR found -> started" $?
reset; ev_issue; issue open '[]'; prs '[]'; for i in 1 2 3 4 5 6 7 8 9 10; do fx "${RECENT_BASE}$i" "$FULL"; done; answer '着手報告のみ'
outcome
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'more than 1000 PRs' "$TMP/out" && not_logged "page=11"; }
expect "no page reaches the run start within 10 pages -> warn, no write, exit 0" $?

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

# ------------------------------------------------------------------ detect-rate-limit.sh (#2344)
# フィクスチャは opencode 2.0.26 に偽上流 (429 / 503 cooling down) を当てて得た実出力の error 行
echo "== detect-rate-limit.sh"
FX_429="$HERE/fixtures/opencode-2.0.26-rate-limit-429.jsonl"
FX_503="$HERE/fixtures/opencode-2.0.26-rate-limit-503-cooldown.jsonl"
det_reset() { reset; rm -f "$TMP/oc.jsonl"; }
detect() { OC_OUTPUT_FILE="$TMP/oc.jsonl" bash "$SCRIPTS/detect-rate-limit.sh" "$@" > "$TMP/det" 2>&1; RC=$?; }

# a. error 行の率制限 (429) -> annotation + cause=rate_limit。番号を渡すと対象にマーカー 1 件 (本文に /oc 無し)
det_reset; cp "$FX_429" "$TMP/oc.jsonl"; fx repos/o/r/issues/42/comments '[]'
detect 42
{ [ $RC = 0 ] && grep -q '^::error title=oc-rate-limit::' "$TMP/det" && grep -qx 'cause=rate_limit' "$TMP/det" \
  && [ "$(grep -c 'api -X POST repos/o/r/issues/42/comments' "$LOG")" = 1 ] && logged 'cause=rate_limit run=555 -->' \
  && ! grep 'issues/42/comments' "$LOG" | grep -qE '(^|[[:space:]])/(oc|opencode)([[:space:]]|$)'; }
expect "error line rate_limit (429, opencode 2.0.26 output) -> annotation + one marker comment on #42" $?

# a2. 503 + 「credentials are cooling down」(本番の文言に近い形) も error 行で検知する
det_reset; cp "$FX_503" "$TMP/oc.jsonl"
detect
{ [ $RC = 0 ] && grep -qx 'cause=rate_limit' "$TMP/det" && not_logged 'api -X POST'; }
expect "error line 503 'credentials cooling down' rate_limit_error (opencode 2.0.26 output) -> detected (no target: no comment)" $?

# b. ネガコン: error 行でも率制限でない原因 (Argument list too long) -> 検知しない
det_reset; printf '%s\n' '{"type":"error","timestamp":1,"sessionID":"ses_x","error":{"type":"unknown","message":"Argument list too long"}}' > "$TMP/oc.jsonl"
detect 42
{ [ $RC = 0 ] && [ ! -s "$TMP/det" ] && not_logged 'api -X POST'; }
expect "error line for another cause (Argument list too long) -> not detected (negative control)" $?

# c. ネガコン: text 行に rate_limit_error という語が出るだけ -> 検知しない (error 行だけを見る)
det_reset; answer '率制限 rate_limit_error を確認しました。着手します。'
detect 42
{ [ $RC = 0 ] && [ ! -s "$TMP/det" ] && not_logged 'api -X POST'; }
expect "text block mentions rate_limit_error only -> not detected (negative control)" $?

# d. 同じ run で 2 回呼んでもマーカーは 1 件 (2 回目は既存のマーカーを見て付けない)
det_reset; cp "$FX_429" "$TMP/oc.jsonl"; fx repos/o/r/issues/42/comments '[]'
detect 42
fx repos/o/r/issues/42/comments '[{"user":{"type":"Bot"},"body":"[rate-limit] x\n<!-- oc-run-outcome: cause=rate_limit run=555 -->"}]'
detect 42
{ [ $RC = 0 ] && [ "$(grep -c 'api -X POST repos/o/r/issues/42/comments' "$LOG")" = 1 ] && grep -q 'already has' "$TMP/det"; }
expect "same run called twice -> still one marker (idempotent)" $?

# e. 出力ファイルが無い (setup 失敗・cancel) -> 何もせず 0 (gh も呼ばない)
det_reset; rm -f "$TMP/oc.jsonl"
detect 42
{ [ $RC = 0 ] && [ ! -s "$TMP/det" ] && [ ! -s "$LOG" ]; }
expect "no output file -> nothing, exit 0, no gh call" $?

# f. record-run-outcome.sh (implement の経路): PR 無し + 率制限 -> no-pr マーカーに cause=rate_limit、annotation は 1 件、コメントは no-pr の 1 件だけ
reset; ev_issue; issue open '[]'; prs '[]'; answer '着手報告のみ'; cat "$FX_429" >> "$TMP/oc.jsonl"
outcome
{ [ $RC = 0 ] && logged 'labels\[\]=oc:no-pr' && logged 'no-pr reason=unknown cause=rate_limit run=555 -->' \
  && grep -q '^::error title=oc-rate-limit::' "$TMP/out" && [ "$(grep -c 'api -X POST repos/o/r/issues/42/comments' "$LOG")" = 1 ]; }
expect "implement no-PR run with a rate-limit error line -> no-pr marker has cause=rate_limit (one comment)" $?

# f2. ネガコン (record): text だけの率制限の語 -> cause は付かない
reset; ev_issue; issue open '[]'; prs '[]'; answer '率制限 rate_limit_error を確認中。着手しました。'
outcome
{ [ $RC = 0 ] && reason_is unknown && not_logged 'cause=rate_limit' && ! grep -q 'oc-rate-limit' "$TMP/out"; }
expect "implement no-PR run, text mentions rate_limit_error only -> no cause in the marker" $?

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

# ------------------------------------------------------------------ notify-rate-limit.sh (#2346)
echo "== notify-rate-limit.sh"
NT_NOW="$(date -u -d '2026-10-14T12:00:00Z' +%s)"
NT_W30="$(date -u -d "@$((NT_NOW - 1800))" +%Y-%m-%dT%H:%M:%SZ)"
NT_W60="$(date -u -d "@$((NT_NOW - 3600))" +%Y-%m-%dT%H:%M:%SZ)"
NT_AGO() { date -u -d "@$((NT_NOW - $1))" +%Y-%m-%dT%H:%M:%SZ; }
mark() { printf '{"user":{"type":"Bot"},"body":"[rate-limit] x\\n<!-- oc-run-outcome: no-pr reason=unknown cause=rate_limit run=%s -->"}' "$1"; }
noise() { printf '{"user":{"type":"Bot"},"body":"%s"}' "$1"; }
mk_list() { # mk_list <run id>... : 本文に cause=rate_limit のマーカーを持つ bot のコメント
  local s="" i
  for i in "$@"; do s="$s${s:+,}$(mark "$i")"; done
  printf '%s' "$s"
}
cm30() { fx "repos/o/r/issues/comments?since=$NT_W30&per_page=100" "[$1]"; }
runs_total() { fx "repos/o/r/actions/workflows/opencode.yaml/runs?created=%3E%3D$NT_W30&status=completed&per_page=1" "{\"total_count\":$1,\"workflow_runs\":[]}"; }
open_issues() { fx 'repos/o/r/issues?labels=oc%3Arate-limit&state=open&per_page=100' "$1"; }
last_issues() { fx 'repos/o/r/issues?labels=oc%3Arate-limit&state=all&sort=created&direction=desc&per_page=10' "$1"; }
notify() { OC_NOW="$NT_NOW" bash "$SCRIPTS/notify-rate-limit.sh" > "$TMP/nt" 2>&1; RC=$?; }
nt_base() { reset; cm30 "$(mk_list 101 102 103 104)"; runs_total 10; open_issues '[]'; last_issues '[]'; } # この run (555) を含めて 5 件・完了 10 件

# n1. 正例 (閾値ちょうど): 5 件 (他 4 件 + この run)・完了 10 件 (50%)・open な issue 無し -> [CI] 率制限 の起票 1 件 (labels[]=oc:rate-limit)
nt_base
notify
{ [ $RC = 0 ] && logged 'api -X POST repos/o/r/issues -f title=\[CI\] 率制限: 30 分で 5 件の run が失敗' && logged 'labels\[\]=oc:rate-limit' \
  && [ "$(grep -c 'api -X POST repos/o/r/issues -f' "$LOG")" = 1 ]; }
expect "5 runs (threshold, incl. this run) of 10 completed, no open issue -> one [CI] issue with oc:rate-limit" $?

# n1b. 正例 (仕様の例): 30 分に 10 run 中 6 件 (他 5 件 + この run) が rate_limit -> 起票 1 件
reset; cm30 "$(mk_list 101 102 103 104 105)"; runs_total 10; open_issues '[]'; last_issues '[]'
notify
{ [ $RC = 0 ] && logged 'api -X POST repos/o/r/issues -f title=\[CI\] 率制限: 30 分で 6 件の run が失敗' && [ "$(grep -c 'api -X POST repos/o/r/issues -f' "$LOG")" = 1 ]; }
expect "6 of 10 completed runs rate-limited in 30 min -> one [CI] issue" $?

# n2. 起票の中身: @pycabbage・run id のリスト・OC_MODEL_ID を変えない旨。needs-user-input を付けない・repo 変数 API と GraphQL を呼ばない。行頭の /oc が無い
nt_base
notify
{ [ $RC = 0 ] && logged '@pycabbage' && logged 'run id: 101, 102, 103, 104, 555' && logged 'OC_MODEL_ID` は自動では変更されません' \
  && not_logged needs-user-input && not_logged 'actions/variables' && not_logged graphql \
  && ! grep -qE '^/(oc|opencode)([[:space:]]|$)' "$LOG"; }
expect "issue body: @pycabbage, run ids, OC_MODEL_ID unchanged note; no needs-user-input, no variables/graphql call, no /oc line" $?

# n3. ネガコン (件数): 3 件 (他 2 件 + この run、5 件未満) -> 何もしない
reset; cm30 "$(mk_list 101 102)"; runs_total 10; open_issues '[]'; last_issues '[]'
notify
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'rate-limit runs in 30 min: 3 (< 5)' "$TMP/nt"; }
expect "3 runs (< 5) -> no notice (negative control)" $?

# n4. ネガコン (割合): 6 件 / 完了 30 件 = 20% (< 30%) -> 何もしない。境界: 6 件 / 20 件 = 30% -> 起票
reset; cm30 "$(mk_list 101 102 103 104 105)"; runs_total 30; open_issues '[]'; last_issues '[]'
notify
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'rate-limit runs: 6 of 30' "$TMP/nt"; }
expect "6 runs of 30 completed (20%, < 30%) -> no notice (negative control)" $?
reset; cm30 "$(mk_list 101 102 103 104 105)"; runs_total 20; open_issues '[]'; last_issues '[]'
notify
{ [ $RC = 0 ] && logged 'api -X POST repos/o/r/issues -f title=' ; }
expect "6 runs of 20 completed (30%, boundary) -> one issue" $?

# n5. ネガコン (原因): Argument list too long・Prepare PR context の失敗 12 件はマーカーを持たないので数えない (2 件 + この run = 3)
ns=""
for i in $(seq 6); do ns="$ns$(noise 'Argument list too long'),$(noise 'Prepare PR context failed'),"; done
reset; cm30 "$ns$(mk_list 101 102)"; runs_total 10; open_issues '[]'; last_issues '[]'
notify
{ [ $RC = 0 ] && grep -q 'rate-limit runs in 30 min: 3 (< 5)' "$TMP/nt" && not_logged 'api -X POST'; }
expect "12 failures without a rate_limit marker are not counted (negative control)" $?

# n6. open な oc:rate-limit の issue がある (60 分以内の通知なし) -> そこにコメントだけ。新規の起票は 0 件
reset; cm30 "$(mk_list 101 102 103 104)"; runs_total 10
open_issues '[{"number":77,"state":"open","labels":[{"name":"oc:rate-limit"}]}]'
fx "repos/o/r/issues/77/comments?since=$NT_W60&per_page=100" '[]'
notify
{ [ $RC = 0 ] && logged 'api -X POST repos/o/r/issues/77/comments' && logged 'run id: 101, 102, 103, 104, 555' \
  && logged '<!-- oc-rate-limit-notify -->' && [ "$(grep -c 'api -X POST repos/o/r/issues -f' "$LOG")" = 0 ] && not_logged 'repos/o/r/labels'; }
expect "open oc:rate-limit issue -> comment only (run ids + count), no new issue" $?

# n7. ネガコン (60 分): 60 分以内に通知コメントが既にある -> 何も投稿しない
reset; cm30 "$(mk_list 101 102 103 104)"; runs_total 10
open_issues '[{"number":77,"state":"open","labels":[{"name":"oc:rate-limit"}]}]'
fx "repos/o/r/issues/77/comments?since=$NT_W60&per_page=100" '[{"user":{"type":"Bot"},"body":"x\n<!-- oc-rate-limit-notify -->"}]'
notify
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'has a notice within 60 min' "$TMP/nt"; }
expect "a notice within 60 min already on the open issue -> nothing posted (negative control)" $?

# n8. ネガコン (6 時間): 直近の oc:rate-limit の起票が 1 時間前 (open は無い) -> 起票 0 件。7 時間前なら起票 1 件
reset; cm30 "$(mk_list 101 102 103 104)"; runs_total 10; open_issues '[]'
last_issues "[{\"number\":70,\"state\":\"closed\",\"created_at\":\"$(NT_AGO 3600)\",\"pull_request\":null}]"
notify
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'opened within 6 hours' "$TMP/nt"; }
expect "last oc:rate-limit issue opened 1 hour ago -> nothing opened (negative control)" $?
reset; cm30 "$(mk_list 101 102 103 104)"; runs_total 10; open_issues '[]'
last_issues "[{\"number\":70,\"state\":\"closed\",\"created_at\":\"$(NT_AGO 25200)\",\"pull_request\":null}]"
notify
{ [ $RC = 0 ] && logged 'api -X POST repos/o/r/issues -f title=' && [ "$(grep -c 'api -X POST repos/o/r/issues -f' "$LOG")" = 1 ]; }
expect "last oc:rate-limit issue opened 7 hours ago -> one issue opened" $?

# n9. 読めない (comments の取得に失敗・run 数の取得に失敗) -> 0 で終わり、何も投稿しない
reset; cm30 "$(mk_list 101 102 103 104)"; runs_total 10; open_issues '[]'; last_issues '[]'
export FAKE_FAIL='issues/comments'; notify; unset FAKE_FAIL
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'could not read the issue comments' "$TMP/nt"; }
expect "comments unreadable -> exit 0, nothing posted" $?
reset; cm30 "$(mk_list 101 102 103 104)"; open_issues '[]'; last_issues '[]'
export FAKE_FAIL='actions/workflows'; notify; unset FAKE_FAIL
{ [ $RC = 0 ] && not_logged 'api -X POST' && grep -q 'could not count the completed runs' "$TMP/nt"; }
expect "completed-run count unreadable -> exit 0, nothing posted" $?

# n10. repo も token も無い -> 0 で終わり、gh を呼ばない
reset
OC_NOW="$NT_NOW" GH_TOKEN= bash "$SCRIPTS/notify-rate-limit.sh" > "$TMP/nt" 2>&1; RC=$?
{ [ $RC = 0 ] && [ ! -s "$LOG" ]; }
expect "no token -> exit 0, no gh call" $?

# n11. 配線: detect-rate-limit.sh が率制限を検知すると通知まで行う (番号なし = implement の経路)。ただし 429 以外 (Argument list too long) では通知の処理を呼ばない
reset; cp "$FX_429" "$TMP/oc.jsonl"; cm30 "$(mk_list 101 102 103 104)"; runs_total 10; open_issues '[]'; last_issues '[]'
OC_NOW="$NT_NOW" OC_OUTPUT_FILE="$TMP/oc.jsonl" bash "$SCRIPTS/detect-rate-limit.sh" > "$TMP/det" 2>&1; RC=$?
{ [ $RC = 0 ] && grep -qx 'cause=rate_limit' "$TMP/det" && logged 'api -X POST repos/o/r/issues -f title=' && logged 'labels\[\]=oc:rate-limit'; }
expect "detect-rate-limit.sh (429) -> notify-rate-limit.sh is called and opens the issue" $?
reset; printf '%s\n' '{"type":"error","timestamp":1,"sessionID":"ses_x","error":{"type":"unknown","message":"Argument list too long"}}' > "$TMP/oc.jsonl"
OC_NOW="$NT_NOW" OC_OUTPUT_FILE="$TMP/oc.jsonl" bash "$SCRIPTS/detect-rate-limit.sh" 42 > "$TMP/det" 2>&1; RC=$?
{ [ $RC = 0 ] && [ ! -s "$TMP/det" ] && not_logged 'issues/comments'; }
expect "not a rate limit -> notify-rate-limit.sh is not called (negative control)" $?

# n11b. DRY=1 + 429 は書かない: 番号あり (マーカーの計画だけ) も番号なし (通知の計画だけ) も、通知の条件 (5 件・30%) を満たす fixture で POST 0 件
nt_base; fx repos/o/r/issues/42/comments '[]'; cp "$FX_429" "$TMP/oc.jsonl"
DRY=1 OC_NOW="$NT_NOW" OC_OUTPUT_FILE="$TMP/oc.jsonl" bash "$SCRIPTS/detect-rate-limit.sh" 42 > "$TMP/det" 2>&1; RC=$?
{ [ $RC = 0 ] && grep -q 'DRY: comment on #42' "$TMP/det" && not_logged 'api -X POST'; }
expect "DRY=1 + 429 with issue 42 (5 runs, 10 completed) -> plans only: no POST (no marker, no label, no issue)" $?
nt_base; cp "$FX_429" "$TMP/oc.jsonl"
DRY=1 OC_NOW="$NT_NOW" OC_OUTPUT_FILE="$TMP/oc.jsonl" bash "$SCRIPTS/detect-rate-limit.sh" > "$TMP/det" 2>&1; RC=$?
{ [ $RC = 0 ] && grep -qx 'cause=rate_limit' "$TMP/det" && not_logged 'api -X POST'; }
expect "DRY=1 + 429 without number (5 runs, 10 completed) -> notify not called: no POST" $?

# n12. 静的: OC_MODEL_ID の repo 変数 API (actions/variables) を書かない・gh issue/pr のサブコマンド (GraphQL) を使わない・needs-user-input を書かない
{ ! grep -q 'actions/variables' "$SCRIPTS/notify-rate-limit.sh" && ! grep -qE 'gh (issue|pr) ' "$SCRIPTS/notify-rate-limit.sh" \
  && ! grep -q 'needs-user-input' "$SCRIPTS/notify-rate-limit.sh"; }
expect "static: no repo-variable API, no gh issue/pr subcommand (GraphQL), no needs-user-input" $?

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
