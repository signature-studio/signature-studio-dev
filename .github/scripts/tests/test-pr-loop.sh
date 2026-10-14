#!/bin/bash
# test-pr-loop.sh — fix-progress.sh / verify-review-verdict.sh / reopen-pr.sh の分岐を fake gh で検証する (#719, #721)。
# 実行: bash .github/scripts/tests/test-pr-loop.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
# CI: .github/workflows/scripts-test.yaml が .github/scripts/**・.github/actions/**・opencode.yaml の変更ごとに実行する。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/.."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export OC_REPO=o/r OC_PR_NUMBER=7 RUNNER_TEMP="$TMP" OC_REOPEN_WAIT=0 GITHUB_EVENT_PATH=/dev/null

# fake gh: `gh api [--paginate] [-X M] repos/... [--jq E]` は $FIX/<path の / を _ にした名前> を返す。
# `gh pr comment|close|reopen` と POST は $LOG に記録するだけ。
# FAKE_REOPEN_FAILS=N なら、最初の N 回の `gh pr reopen` を失敗させる。FAKE_CLOSE_FAILS=1 なら `gh pr close` を失敗させる。
# FAKE_COMMENT_FAILS=1 なら `gh pr comment` を失敗させる (呼び出しは $LOG に残る)。FAKE_FAIL_PATH=<path> なら、その path の読み取りを失敗させる。
# fixture <名前>.2 があれば、2 回目以降の同じ path の読み取りはそちらを返す (close の間に PR の状態が変わった競合の再現)。
FIX="$TMP/fixtures"
LOG="$TMP/gh.log"
mkdir -p "$FIX" "$TMP/bin"
cat > "$TMP/bin/gh" << 'EOF'
#!/bin/bash
echo "gh $* [GH_TOKEN=${GH_TOKEN:-}]" >> "$FAKE_LOG"
if [ "$1" = pr ]; then
  [ "$2" = close ] && [ -n "${FAKE_CLOSE_FAILS:-}" ] && exit 1
  [ "$2" = comment ] && [ -n "${FAKE_COMMENT_FAILS:-}" ] && exit 1
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
[ -n "${FAKE_FAIL_PATH:-}" ] && [ "$path" = "$FAKE_FAIL_PATH" ] && exit 1
f="$FAKE_FIX/${path//\//_}"
[ -f "$f" ] || { echo "fake gh: no fixture for $path" >&2; exit 1; }
if [ -f "$f.2" ]; then
  n=$(($(cat "$f.reads" 2> /dev/null || echo 0) + 1))
  echo "$n" > "$f.reads"
  [ "$n" -ge 2 ] && f="$f.2"
fi
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
    r="$r{\"user\":{\"login\":\"oc-reviewer-for-signature-studio[bot]\"},\"state\":\"CHANGES_REQUESTED\",\"commit_id\":\"c$i\",\"submitted_at\":\"2026-02-01T00:00:00Z\",\"body\":\"\"},"
  done
  fx repos/o/r/pulls/7/reviews "${r%,}]"
  fx repos/o/r/issues/7/comments '[]'
  fx repos/o/r/issues/comments '[]'
}
reviews() { # <submitted_at> <count> [<submitted_at> <count> ...]: oc-reviewer の CHANGES_REQUESTED review の JSON 配列
  local s="" i
  while [ $# -ge 2 ]; do
    for ((i = 0; i < $2; i++)); do
      s="$s{\"user\":{\"login\":\"oc-reviewer-for-signature-studio[bot]\"},\"state\":\"CHANGES_REQUESTED\",\"commit_id\":\"c\",\"submitted_at\":\"$1\",\"body\":\"\"},"
    done
    shift 2
  done
  printf '[%s]' "${s%,}"
}
stop_at() { # <created_at> [login]: 停止コメント (マーカー付き) の JSON 配列
  printf '[{"created_at":"%s","user":{"login":"%s","type":"Bot"},"body":"上限 <!-- oc-fix-limit -->"}]' "$1" "${2:-github-actions[bot]}"
}
# OC_MARK_TOKEN は workflow が github.token を渡す値 (#2622)。未設定なら既定のテスト値、空なら「無し」として渡す。
run_fix() { GITHUB_ENV="$TMP/env" GITHUB_OUTPUT="$TMP/out" OC_MARK_TOKEN="${OC_MARK_TOKEN-mark-tok}" bash "$SCRIPTS/fix-progress.sh" "$@"; }
# rv <submitted_at> <classes> <body>: oc-reviewer の CHANGES_REQUESTED review (本文末尾に oc-review マーカー)
rv() {
  jq -nc --arg t "$1" --arg c "$2" --arg b "$3" '{user:{login:"oc-reviewer-for-signature-studio[bot]"},state:"CHANGES_REQUESTED",commit_id:"c",submitted_at:$t,body:($b + "\n<!-- oc-review: v=1 round=1 blocking=1 minor=0 classes=" + $c + " -->")}'
}
# seq_rv <classes> <count> <start-day>: 1 日ずつ進む差し戻し (本文は件ごとに語が違う = 繰り返しではない)
SENT=("- 数値Aを修正" "- 関数Bの戻り値" "- 文書Cの節番号" "- 図Dの欠落" "- 引数Eの型" "- 表Fの単位" "- 注釈Gの出典" "- 式Hの係数" "- 用語Iの統一" "- 章Jの見出し" "- 行Kの誤記" "- 項Lの参照" "- 段Mの順序" "- 語Nの表記" "- 例Oの計算")
seq_rv() {
  local i a=()
  for ((i = 0; i < $2; i++)); do
    a+=("$(rv "2026-01-$(printf %02d $(($3 + i)))T00:00:00Z" "$1" "${SENT[$(((($3 + i) - 1) % 15))]}")")
  done
  printf '%s\n' "${a[@]}" | jq -sc .
}
cat_rv() { jq -nc --argjson a "$1" --argjson b "$2" '$a + $b'; }
bot_comment() { # <created_at> <body>: 実装 bot の PR コメント (JSON)
  jq -nc --arg t "$1" --arg b "$2" '{created_at:$t,user:{login:"opencode-for-signature-studio[bot]"},body:$b}'
}

echo "== fix-progress.sh record (往復の上限 5 件・窓の分類 #2323)"
setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 3 1)"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "3 件の差し戻し -> stop=false" $?
grep -qx 'OC_HEAD_BEFORE=aaa' "$TMP/env"; expect "起動時の head を記録する" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 5 1)"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "正例: 5 件すべて doc (本文は別々) -> stop=false" $?
logged 'oc-fix-reset n=1'; expect "正例: 窓を閉じる oc-fix-reset n=1 をコメントする" $?
! logged 'issues/7/labels'; expect "自動再開では oc:stuck を付けない" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(cat_rv "$(seq_rv doc 2 1)" "$(seq_rv code 3 3)")"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ネガ (a): 直近 3 件に code -> stop=true" $?
logged 'oc-pm-intent: stuck pr=7 reason=code'; expect "ネガ (a): 停止理由 reason=code の intent マーカーを残す" $?
logged 'issues/7/labels'; expect "ネガ (a): oc:stuck を付ける" $?

setup aaa '[]' 0
rep1="$(rv 2026-01-05T00:00:00Z doc '- 同じ指摘: 数値を直す')"
rep2="$(rv 2026-01-06T00:00:00Z doc '- 同じ指摘: 数値を直す')"
rep3="$(rv 2026-01-07T00:00:00Z doc '- 同じ指摘: 数値を直す')"
fx repos/o/r/pulls/7/reviews "$(cat_rv "$(seq_rv doc 2 1)" "$(printf '%s\n%s\n%s\n' "$rep1" "$rep2" "$rep3" | jq -sc .)")"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ネガ (b): 同じ指摘が 3 周 -> stop=true" $?
logged 'reason=repeat'; expect "ネガ (b): 停止理由 reason=repeat" $?

setup aaa '[]' 0
cf="$(rv 2026-01-01T00:00:00Z conflict '- 競合を解消')"
cf2="$(rv 2026-01-02T00:00:00Z conflict '- 競合を解消')"
fx repos/o/r/pulls/7/reviews "$(cat_rv "$(printf '%s\n%s\n' "$cf" "$cf2" | jq -sc .)" "$(seq_rv doc 3 3)")"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "ネガ (c): conflict 2 件 + doc 3 件 -> 計数 3 で stop=false" $?
! logged 'oc-fix-reset'; expect "ネガ (c): 計数 3 なので窓を閉じない" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(cat_rv "$(cat_rv "$(seq_rv doc 5 1)" '[]')" "$(seq_rv doc 5 6)")"
fx repos/o/r/issues/7/comments "$(jq -nc '[{created_at:"2026-01-05T12:00:00Z",user:{login:"github-actions[bot]",type:"Bot"},body:"<!-- oc-fix-reset n=1 -->"},{created_at:"2026-01-10T12:00:00Z",user:{login:"github-actions[bot]",type:"Bot"},body:"<!-- oc-fix-reset n=2 -->"}]')"
fx repos/o/r/pulls/7/reviews "$(cat_rv "$(seq_rv doc 15 1)" '[]')"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ネガ (d): 合計 15 件 -> stop=true" $?
logged 'reason=ceiling'; expect "ネガ (d): 停止理由 reason=ceiling" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv "" 5 1)"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "ネガ (e): classes 空 (unknown) の 1 窓目 -> 自動再開" $?
logged 'oc-fix-reset n=1'; expect "ネガ (e): 1 窓目は oc-fix-reset n=1" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(cat_rv "$(seq_rv "" 5 1)" "$(seq_rv "" 5 6)")"
fx repos/o/r/issues/7/comments "$(jq -nc '[{created_at:"2026-01-05T12:00:00Z",user:{login:"github-actions[bot]",type:"Bot"},body:"<!-- oc-fix-reset n=1 -->"}]')"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ネガ (e): classes 空 (unknown) の 2 窓目 -> stop=true" $?
logged 'reason=unknown'; expect "ネガ (e): 停止理由 reason=unknown" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 5 1)"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fx repos/o/r/issues/comments "$(jq -nc --arg t "$now" '[range(0;6)|{created_at:$t,user:{login:"github-actions[bot]",type:"Bot"},body:"<!-- oc-fix-reset n=1 -->"}]')"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ネガ (f): 1 時間に 7 件目の reset -> stop=true" $?
logged 'reason=ceiling'; expect "ネガ (f): 停止理由は reason=ceiling" $?

echo "== fix-progress.sh record (本文はあるがマーカーの無い差し戻しは unknown として数える #2894)"
# nm_seq <start-day> <count>: 本文はあるが oc-review マーカーの無い oc-reviewer の差し戻し (件ごとに本文は別)
nm_seq() {
  local i a=()
  for ((i = 0; i < $2; i++)); do
    a+=("$(jq -nc --arg t "2026-01-$(printf %02d $(($1 + i)))T00:00:00Z" --arg b "${SENT[$(((($1 + i) - 1) % 15))]}" '{user:{login:"oc-reviewer-for-signature-studio[bot]"},state:"CHANGES_REQUESTED",commit_id:"c",submitted_at:$t,body:$b}')")
  done
  printf '%s\n' "${a[@]}" | jq -sc .
}
setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(nm_seq 1 5)"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "マーカー無し (本文あり) の 5 件 -> stop=false (素通りしない)" $?
logged 'oc-fix-reset n=1'; expect "マーカー無しの 1 窓目は oc-fix-reset n=1 で窓を閉じる" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(cat_rv "$(nm_seq 1 5)" "$(nm_seq 6 5)")"
fx repos/o/r/issues/7/comments '[{"created_at":"2026-01-05T12:00:00Z","user":{"login":"github-actions[bot]","type":"Bot"},"body":"<!-- oc-fix-reset n=1 -->"}]'
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "マーカー無しの 2 窓目 -> stop=true" $?
logged 'reason=unknown'; expect "マーカー無しの 2 窓目の停止理由は reason=unknown" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(jq -nc '[range(0;5) as $i | {user:{login:"oc-reviewer-for-signature-studio[bot]"},state:"CHANGES_REQUESTED",commit_id:"c",submitted_at:"2026-01-01T00:00:00Z",body:"- 指摘\($i)\n<!-- oc-review: v=1 round=1 blocking=1 minor=0 -->"}]')"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out" && logged 'oc-fix-reset n=1'; expect "classes= の無いマーカーの 5 件 -> 1 窓目で自動再開 (unknown)" $?

# 停止コメント (oc-fix-limit) より前の差し戻しは数えない: ラベルを外して再開できる
setup aaa '[]' 5
fx repos/o/r/issues/7/comments '[{"created_at":"2026-03-01T00:00:00Z","user":{"login":"github-actions[bot]","type":"Bot"},"body":"stop <!-- oc-fix-limit -->"}]'
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "停止コメントの後に差し戻し 0 件 (ラベルを外した直後) -> stop=false" $?

setup aaa '[]' 5
fx repos/o/r/issues/7/comments '[{"created_at":"2026-03-01T00:00:00Z","user":{"login":"github-actions[bot]","type":"Bot"},"body":"stop <!-- oc-fix-limit -->"}]'
fx repos/o/r/pulls/7/reviews "$(jq -c '. + [{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"CHANGES_REQUESTED","commit_id":"n1","submitted_at":"2026-04-01T00:00:00Z"}]' < "$FIX/repos_o_r_pulls_7_reviews")"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "停止コメントの後の差し戻し 1 件 -> stop=false (数え直し)" $?

setup aaa '[]' 5
fx repos/o/r/issues/7/comments '[{"created_at":"2026-03-01T00:00:00Z","user":{"login":"github-actions[bot]","type":"Bot"},"body":"stop <!-- oc-fix-limit -->"}]'
fx repos/o/r/pulls/7/reviews "$(jq -c '. + [range(0;5)|{"user":{"login":"oc-reviewer-for-signature-studio[bot]"},"state":"CHANGES_REQUESTED","commit_id":"n","submitted_at":"2026-04-01T00:00:00Z","body":""}]' < "$FIX/repos_o_r_pulls_7_reviews")"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "停止コメントの後に再び 5 件 (マーカー無し = unknown の 1 窓目) -> 自動再開" $?
logged 'oc-fix-reset n=1'; expect "停止コメントの後の 1 窓目は oc-fix-reset n=1" $?

# 起動主体は完全一致: 名前が似ているだけの bot の差し戻しは数えない
setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(jq -nc '[range(0;9)|{"user":{"login":"oc-reviewer-evil[bot]"},"state":"CHANGES_REQUESTED","commit_id":"x","submitted_at":"2026-02-01T00:00:00Z"}]')"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "前方一致するだけの別アカウントの差し戻しは数えない" $?

setup aaa '[{"name":"oc:stuck"}]' 0
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ラベル済みなら stop=true" $?
! logged 'pr comment'; expect "ラベル済みなら再コメントしない" $?

echo "== fix-progress.sh record (途中で失敗したら stop=true を残す: retry を起動しない #2638 B3)"
# FAKE_COMMENT_FAILS=1: gh pr comment が失敗する。窓の印 (reset) と停止コメント (ceiling) のどちらでも stop=true を残す
setup aaa '[]' 5
export FAKE_COMMENT_FAILS=1
run_fix record > /dev/null 2>&1
rc=$?
unset FAKE_COMMENT_FAILS
[ "$rc" -ne 0 ] && logged "pr comment 7" && grep -qx 'stop=true' "$TMP/out"
expect "窓の印を投稿できない (reset) ときは rc!=0 かつ stop=true" $?
setup aaa '[]' 15
export FAKE_COMMENT_FAILS=1
run_fix record > /dev/null 2>&1
rc=$?
unset FAKE_COMMENT_FAILS
[ "$rc" -ne 0 ] && logged "pr comment 7" && grep -qx 'stop=true' "$TMP/out"
expect "停止コメントを投稿できない (ceiling) ときは rc!=0 かつ stop=true" $?
setup aaa '[]' 0
run_fix record > /dev/null
[ "$?" = 0 ] && grep -qx 'stop=false' "$TMP/out" && ! grep -q 'stop=true' "$TMP/out"
expect "失敗しなければ stop=false だけを出す (trap は stop=true を足さない)" $?

echo "== fix-progress.sh record (ラベルを取得できないときは止める: 失敗を『ラベル無し』と判定しない #2638 m2)"
setup aaa '[]' 0
rm -f "$FIX/repos_o_r_issues_7"
run_fix record > /dev/null 2>&1
rc=$?
[ "$rc" -ne 0 ] && grep -qx 'stop=true' "$TMP/out" && ! logged 'pr comment'
expect "ラベルの取得に失敗したら rc!=0 かつ stop=true (fix を起動しない)" $?
setup aaa '[]' 0
env -u OC_REPO GITHUB_ENV="$TMP/env" GITHUB_OUTPUT="$TMP/out" bash "$SCRIPTS/fix-progress.sh" record > /dev/null 2>&1
rc=$?
[ "$rc" -ne 0 ] && grep -qx 'stop=true' "$TMP/out"
expect "入力 (OC_REPO) が無くても rc!=0 かつ stop=true を残す (trap は入力検査より前)" $?

echo "== fix-progress.sh record (merge 済み・古い head への差し戻しは agent を起動しない #2601)"
# review_event <review の commit_id>: pull_request_review の event payload (差し戻しの元になった review) を書く
review_event() { jq -nc --arg c "$1" '{action:"submitted",review:{state:"changes_requested",commit_id:$c}}' > "$TMP/event.json"; }
setup aaa '[]' 1
fx repos/o/r/pulls/7 '{"state":"closed","merged":true,"head":{"sha":"aaa"}}'
review_event aaa
GITHUB_EVENT_PATH="$TMP/event.json" run_fix record > "$TMP/rec.out"
grep -qx 'stop=true' "$TMP/out"; expect "merge 済みの PR への差し戻し -> stop=true (agent を起動しない)" $?
grep -q '^::notice::' "$TMP/rec.out"; expect "merge 済みの PR は notice を残す" $?
! logged 'issues/7/labels' && ! logged 'pr comment'; expect "merge 済みの PR は oc:stuck も PR コメントも付けない" $?

setup aaa '[]' 1
fx repos/o/r/pulls/7 '{"state":"closed","merged":false,"head":{"sha":"aaa"}}'
review_event aaa
GITHUB_EVENT_PATH="$TMP/event.json" run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "close 済み (未 merge) の PR への差し戻し -> stop=true" $?

setup aaa '[]' 1
review_event aaa
GITHUB_EVENT_PATH="$TMP/event.json" run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "ネガコン: open の PR で review の commit = head -> stop=false (agent を起動する)" $?

setup aaa '[]' 1
review_event old000
GITHUB_EVENT_PATH="$TMP/event.json" run_fix record > "$TMP/rec.out"
grep -qx 'stop=true' "$TMP/out"; expect "古い head (review=old000, head=aaa) への差し戻し -> stop=true" $?
grep -q '^::notice::' "$TMP/rec.out"; expect "古い head への差し戻しは notice を残す" $?
! logged 'issues/7/labels' && ! logged 'pr comment'; expect "古い head への差し戻しは oc:stuck も PR コメントも付けない" $?

setup aaa '[]' 1
jq -nc '{action:"oc-fix",client_payload:{pr:7,reason:"conflict"}}' > "$TMP/event.json"
GITHUB_EVENT_PATH="$TMP/event.json" run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "repository_dispatch (競合の fix) は差し戻し review を持たないので古い head と見なさない -> stop=false" $?

echo "== fix-progress.sh record (窓は直前の停止コメント以降の差し戻しを数える)"
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
grep -qx 'stop=false' "$TMP/out"; expect "停止コメントの後に 5 件 (unknown の 1 窓目) -> 自動再開 (停止前の 5 件は数えない)" $?
logged 'oc-fix-reset n=1'; expect "1 窓目なので oc-fix-reset n=1" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(reviews 2026-01-01T00:00:00Z 5 2026-01-03T00:00:00Z 1)"
fx repos/o/r/issues/7/comments "$(stop_at 2026-01-02T00:00:00Z someone)"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "他人の oc-fix-limit マーカーは区切りにしない (6 件を窓として数える -> 1 窓目で再開)" $?

echo "== fix-progress.sh record (偽装: 実装 App 名義の窓の印は信じない #2622)"
IMPL="opencode-for-signature-studio[bot]"
setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv code 6 1)"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "ネガ (偽 0): 印なしの code 6 件 -> stop=true" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv code 6 1)"
fx repos/o/r/issues/7/comments "$(jq -nc --arg u "$IMPL" '[{created_at:"2026-02-01T00:00:00Z",user:{login:$u,type:"Bot"},body:"偽 <!-- oc-fix-limit -->"}]')"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "偽装 (停止印): 実装 App 名義の oc-fix-limit では窓を空にできない -> stop=true" $?
logged 'reason=code'; expect "偽装 (停止印): 停止理由は reason=code のまま" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 16 1)"
fx repos/o/r/issues/7/comments "$(jq -nc --arg u "$IMPL" '[{created_at:"2026-01-16T12:00:00Z",user:{login:$u,type:"Bot"},body:"偽 <!-- oc-fix-reset n=1 -->"},{created_at:"2026-01-16T13:00:00Z",user:{login:$u,type:"Bot"},body:"偽 <!-- oc-fix-reset n=2 -->"}]')"
run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "偽装 (再開印): 実装 App 名義の oc-fix-reset で合計の天井を越えられない -> stop=true" $?
logged 'reason=ceiling'; expect "偽装 (再開印): 停止理由 reason=ceiling" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 5 1)"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fx repos/o/r/issues/comments "$(jq -nc --arg t "$now" --arg u "$IMPL" '[range(0;6)|{created_at:$t,user:{login:$u,type:"Bot"},body:"偽 <!-- oc-fix-reset n=1 -->"}]')"
run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "偽装 (1 時間の上限): 実装 App 名義の reset 6 件では正当な自動再開を止めない" $?
logged 'oc-fix-reset n=1'; expect "偽装 (1 時間の上限): 正当な再開は oc-fix-reset n=1 を投稿する" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 5 1)"
OC_MARK_TOKEN=mark-tok run_fix record > /dev/null
grep -qx 'stop=false' "$TMP/out"; expect "正例 (印): OC_MARK_TOKEN があれば 5 件で窓を閉じる" $?
logged 'oc-fix-reset n=1.*GH_TOKEN=mark-tok'; expect "正例 (印): 窓の印は OC_MARK_TOKEN で投稿する" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 5 1)"
OC_MARK_TOKEN= run_fix record > /dev/null
grep -qx 'stop=true' "$TMP/out"; expect "印を投稿できない (OC_MARK_TOKEN 無し) -> 窓を閉じずに stop=true" $?
! logged 'oc-fix-reset'; expect "印を投稿できない -> oc-fix-reset を投稿しない" $?
logged 'reason=ceiling'; expect "印を投稿できない -> 停止理由 reason=ceiling" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv code 5 1)"
OC_MARK_TOKEN=mark-tok run_fix record > /dev/null
logged 'oc-pm-intent: stuck pr=7 reason=code.*GH_TOKEN=mark-tok'; expect "停止印は OC_MARK_TOKEN で投稿する (PM intent の読み手と同じ作者)" $?

echo "== fix-progress.sh record (gh の失敗で止まる: stop=true・reason=record-failed・PR にコメントしない #2869)"
# rf_check: record の失敗の後に check を走らせる (workflow と同じく GITHUB_ENV を読む)。result を出さずに失敗しなければならない
rf_check() { ( while IFS='=' read -r k v; do export "$k=$v"; done < "$TMP/env"; run_fix check ) > /dev/null 2>&1; }
# rf_fail <name>: record が非 0 で終わり、stop=true と reason=record-failed を出し、後続の check が result を出さないこと
rf_fail() {
  local crc
  { [ "$rc" -ne 0 ] && grep -qx 'stop=true' "$TMP/out" && grep -qx 'reason=record-failed' "$TMP/out" && grep -q '::error::fix-progress record failed' "$TMP/rec.out"; }
  expect "$1 -> 非 0・stop=true・reason=record-failed" $?
  { [ "$(grep -c '^::error::' "$TMP/rec.out")" = 1 ] && grep '^::error::' "$TMP/rec.out" | grep -qF 'the fix run is skipped (reason=record-failed)'; }
  expect "$1 -> ::error:: は 1 行で、理由を含む (コマンドに改行があっても行が割れない)" $?
  rf_check; crc=$?
  { [ "$crc" -ne 0 ] && ! grep -q '^result=' "$TMP/out"; }; expect "$1 -> 後続の check は none を出さず失敗する" $?
}
# rf_cmd <name> <text>: ::error:: の行が、失敗したコマンド (<text> を含む) を示すこと (#2869 受入条件 (5))
rf_cmd() { grep '^::error::' "$TMP/rec.out" | grep -qF -- "$2"; expect "$1" $?; }

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 5 1)"
FAKE_COMMENT_FAILS=1 run_fix record > "$TMP/rec.out" 2>&1; rc=$?
rf_fail "(a) 窓を閉じる oc-fix-reset の投稿が失敗"
{ [ "$(grep -c 'pr comment' "$LOG")" = 1 ] && ! logged 'issues/7/labels'; }; expect "(a) 失敗の後に追加の gh pr comment を呼ばない (1 回だけ) ・ラベルも付けない" $?
rf_cmd "(a) ::error:: の行が失敗したコマンド (gh pr comment) を示す" 'gh pr comment'

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv code 5 1)"
FAKE_COMMENT_FAILS=1 run_fix record > "$TMP/rec.out" 2>&1; rc=$?
rf_fail "(b) 停止のコメントが失敗 (ラベルは成功)"
{ logged 'issues/7/labels' && [ "$(grep -c 'pr comment' "$LOG")" = 1 ]; }; expect "(b) ラベルは付いた上で、コメントは 1 回だけ試みて止まる" $?
rf_cmd "(b) ::error:: の行が失敗したコマンド (gh pr comment) を示す" 'gh pr comment'

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 3 1)"
FAKE_FAIL_PATH=repos/o/r/issues/7/comments run_fix record > "$TMP/rec.out" 2>&1; rc=$?
rf_fail "(c) コメント一覧の取得が失敗"
{ ! logged 'pr comment' && ! logged 'issues/7/labels'; }; expect "(c) 取得が失敗したら PR にもラベルにも触らない" $?
rf_cmd "(c) ::error:: の行が失敗したコマンド (コメント一覧の取得) を示す" "issues/\$OC_PR_NUMBER/comments"

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 3 1)"
FAKE_FAIL_PATH=repos/o/r/pulls/7/reviews run_fix record > "$TMP/rec.out" 2>&1; rc=$?
rf_fail "(d) review 一覧の取得が失敗"
rf_cmd "(d) ::error:: の行が失敗したコマンド (review 一覧の取得) を示す" "pulls/\$OC_PR_NUMBER/reviews"

setup aaa '[{"name":"oc:stuck"}]' 0
FAKE_FAIL_PATH=repos/o/r/issues/7 run_fix record > "$TMP/rec.out" 2>&1; rc=$?
rf_fail "(e) ラベルの読み取りが失敗 (旧版はこれを『ラベル無し』と読んで fail open した)"
rf_cmd "(e) ::error:: の行が失敗したコマンド (ラベルの読み取り) を示す" "labels[].name"

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 3 1)"
run_fix record > /dev/null 2>&1; rc=$?
{ [ "$rc" -eq 0 ] && grep -qx 'OC_RECORD_OK=1' "$TMP/env" && grep -qx 'stop=false' "$TMP/out"; }; expect "正例: record が窓の判定まで終えた -> OC_RECORD_OK=1 を残し stop=false" $?

setup aaa '[{"name":"oc:stuck"}]' 0
run_fix record > /dev/null 2>&1
{ grep -qx 'stop=true' "$TMP/out" && ! grep -q OC_RECORD_OK "$TMP/env" && ! grep -q 'reason=record-failed' "$TMP/out"; }; expect "停止の判定で終わった (stop=true) なら OC_RECORD_OK を残さず、record-failed とも出さない" $?

echo "== fix-progress.sh gate / snapshot (窓の判定を agent の無い fixgate job へ分ける #2873)"
# run_gate: fixgate job の gate。$GITHUB_ENV は書かせない (呼び出しの後に空であることを見る)
run_gate() { GITHUB_ENV="$TMP/env" GITHUB_OUTPUT="$TMP/out" OC_MARK_TOKEN="${OC_MARK_TOKEN-mark-tok}" bash "$SCRIPTS/fix-progress.sh" gate; }
# run_snap <gate の stop>: implement job の snapshot (workflow は needs.fixgate.outputs.stop を OC_GATE_STOP で渡す)
run_snap() { GITHUB_ENV="$TMP/env" GITHUB_OUTPUT="$TMP/out" OC_GATE_STOP="$1" bash "$SCRIPTS/fix-progress.sh" snapshot; }

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 3 1)"
run_gate > /dev/null 2>&1; rc=$?
{ [ "$rc" -eq 0 ] && grep -qx 'stop=false' "$TMP/out" && grep -qx 'reason=none' "$TMP/out"; }; expect "gate: 窓が閉じていない -> rc=0・stop=false・reason=none" $?
! grep -q . "$TMP/env"; expect "gate: \$GITHUB_ENV に何も書かない (head も OC_RECORD_OK も残さない)" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 5 1)"
run_gate > /dev/null 2>&1
{ grep -qx 'stop=false' "$TMP/out" && grep -qx 'reason=reset' "$TMP/out"; }; expect "gate: 5 件 (doc) -> stop=false・reason=reset" $?
logged 'oc-fix-reset n=1.*GH_TOKEN=mark-tok'; expect "gate: 窓の印は OC_MARK_TOKEN で投稿する" $?
! logged 'issues/7/labels'; expect "gate: 自動再開では oc:stuck を付けない" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv code 5 1)"
run_gate > /dev/null 2>&1
{ grep -qx 'stop=true' "$TMP/out" && grep -qx 'reason=code' "$TMP/out"; }; expect "gate: 直近 3 件に code -> stop=true・reason=code" $?
logged 'issues/7/labels' && logged 'oc-pm-intent: stuck pr=7 reason=code.*GH_TOKEN=mark-tok'; expect "gate: oc:stuck を付け、停止印を OC_MARK_TOKEN で残す" $?
! grep -q . "$TMP/env"; expect "gate: 停止の判定でも \$GITHUB_ENV は空のまま" $?

setup aaa '[{"name":"oc:stuck"}]' 0
run_gate > /dev/null 2>&1
{ grep -qx 'stop=true' "$TMP/out" && grep -qx 'reason=stuck-label' "$TMP/out" && ! logged 'pr comment'; }; expect "gate: ラベル済みは reason=stuck-label・再コメントしない" $?

setup aaa '[]' 1
fx repos/o/r/pulls/7 '{"state":"closed","merged":true,"head":{"sha":"aaa"}}'
run_gate > /dev/null 2>&1
{ grep -qx 'stop=true' "$TMP/out" && grep -qx 'reason=not-open' "$TMP/out" && ! logged 'pr comment' && ! logged 'issues/7/labels'; }; expect "gate: merge 済みは reason=not-open・何も付けない" $?

setup aaa '[]' 1
review_event old000
GITHUB_EVENT_PATH="$TMP/event.json" run_gate > /dev/null 2>&1
{ grep -qx 'stop=true' "$TMP/out" && grep -qx 'reason=stale-head' "$TMP/out"; }; expect "gate: 古い head への差し戻し -> reason=stale-head" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 5 1)"
FAKE_COMMENT_FAILS=1 run_gate > "$TMP/rec.out" 2>&1; rc=$?
{ [ "$rc" -ne 0 ] && grep -qx 'stop=true' "$TMP/out" && grep -qx 'reason=record-failed' "$TMP/out" && grep -q '::error::fix-progress gate failed' "$TMP/rec.out"; }; expect "gate: 印の投稿に失敗 -> rc!=0・stop=true・reason=record-failed" $?
rf_check; crc=$?
{ [ "$crc" -ne 0 ] && ! grep -q '^result=' "$TMP/out"; }; expect "gate: 失敗の後の check は result を出さない" $?

setup aaa '[]' 0
GITHUB_ENV="$TMP/env" GITHUB_OUTPUT="$TMP/out" OC_PR_NUMBER='7;x' bash "$SCRIPTS/fix-progress.sh" gate > /dev/null 2>&1; rc=$?
{ [ "$rc" -ne 0 ] && grep -qx 'stop=true' "$TMP/out" && [ ! -s "$LOG" ]; }; expect "gate: OC_PR_NUMBER が数字でなければ gh を呼ばず rc!=0・stop=true (fail-closed)" $?

setup bbb '[]' 0
run_snap false > /dev/null 2>&1; rc=$?
{ [ "$rc" -eq 0 ] && grep -qx 'OC_HEAD_BEFORE=bbb' "$TMP/env" && grep -qx 'OC_RECORD_OK=1' "$TMP/env" && grep -q '^OC_START_TS=' "$TMP/env"; }; expect "snapshot: gate が通過 (false) -> OC_HEAD_BEFORE・OC_START_TS・OC_RECORD_OK=1" $?
! grep -q '^stop=' "$TMP/out"; expect "snapshot: stop を出さない" $?

setup bbb '[]' 0
run_snap true > "$TMP/snap.out" 2>&1; rc=$?
{ [ "$rc" -ne 0 ] && ! grep -q 'OC_RECORD_OK' "$TMP/env" && ! grep -q 'OC_HEAD_BEFORE' "$TMP/env" && grep -qx 'stop=true' "$TMP/out" && grep -qx 'reason=record-failed' "$TMP/out"; }; expect "snapshot: gate が止めた (true) -> rc!=0・OC_RECORD_OK を残さず stop=true" $?

setup bbb '[]' 0
run_snap "" > /dev/null 2>&1; rc=$?
{ [ "$rc" -ne 0 ] && ! grep -q 'OC_RECORD_OK' "$TMP/env"; }; expect "snapshot: gate の結果が空なら fail-closed (OC_RECORD_OK を残さない)" $?

setup bbb '[]' 0
GITHUB_ENV="$TMP/env" GITHUB_OUTPUT="$TMP/out" env -u OC_GATE_STOP bash "$SCRIPTS/fix-progress.sh" snapshot > /dev/null 2>&1; rc=$?
{ [ "$rc" -ne 0 ] && ! grep -q 'OC_RECORD_OK' "$TMP/env" && grep -qx 'stop=true' "$TMP/out"; }; expect "snapshot: OC_GATE_STOP が未設定なら rc!=0・stop=true" $?

setup bbb '[]' 0
FAKE_FAIL_PATH=repos/o/r/pulls/7 run_snap false > "$TMP/snap.out" 2>&1; rc=$?
{ [ "$rc" -ne 0 ] && ! grep -q 'OC_RECORD_OK' "$TMP/env" && grep -qx 'stop=true' "$TMP/out"; }; expect "snapshot: head を読めなければ OC_RECORD_OK を残さず stop=true" $?

setup aaa '[]' 0
fx repos/o/r/pulls/7/reviews "$(seq_rv doc 3 1)"
run_gate > /dev/null 2>&1; g="$(sed -n 's/^stop=//p' "$TMP/out")"
run_snap "$g" > /dev/null 2>&1
fx repos/o/r/pulls/7 '{"state":"open","head":{"sha":"bbb"}}'
( while IFS='=' read -r k v; do export "$k=$v"; done < "$TMP/env"; run_fix check > /dev/null 2>&1 )
{ [ "$g" = false ] && grep -qx 'OC_HEAD_BEFORE=aaa' "$TMP/env" && grep -qx 'result=pushed' "$TMP/out"; }; expect "gate -> snapshot -> check: head が進んだ -> pushed (snapshot は gate の後の head を記録する)" $?

echo "== fix-progress.sh check (pushed / answered / none)"
setup bbb '[]' 1
OC_RECORD_OK=1 OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > /dev/null
grep -qx 'result=pushed' "$TMP/out"; expect "head が進んだ -> pushed" $?

setup aaa '[]' 1
fx repos/o/r/issues/7/comments '[{"created_at":"2026-01-02T00:00:00Z","user":{"login":"opencode-for-signature-studio[bot]"}}]'
OC_RECORD_OK=1 OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > /dev/null
grep -qx 'result=answered' "$TMP/out"; expect "push 無し + bot のコメント -> answered" $?

setup aaa '[]' 1
fx repos/o/r/issues/7/comments '[{"created_at":"2025-12-31T00:00:00Z","user":{"login":"opencode-for-signature-studio[bot]"}},{"created_at":"2026-01-02T00:00:00Z","user":{"login":"someone"}}]'
OC_RECORD_OK=1 OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > /dev/null
grep -qx 'result=none' "$TMP/out"; expect "起動前の bot コメント・他人のコメントは数えない -> none" $?

echo "== fix-progress.sh check (PR head を読めない -> result を出さず失敗 #2899)"
setup aaa '[]' 1
fx repos/o/r/issues/7/comments '[{"created_at":"2026-01-02T00:00:00Z","user":{"login":"opencode-for-signature-studio[bot]"}}]'
OC_RECORD_OK=1 FAKE_FAIL_PATH=repos/o/r/pulls/7 OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > "$TMP/v.out" 2>&1; rc=$?
{ [ "$rc" != 0 ] && ! grep -q '^result=' "$TMP/out"; }; expect "head の読み取りが失敗 -> 非 0 で終わり result を出さない (pushed と判定しない)" $?
grep -q 'could not read the head' "$TMP/v.out"; expect "head の読み取りが失敗 -> 失敗理由を error として出す" $?

setup aaa '[]' 1
fx repos/o/r/pulls/7 '{"state":"open","head":{"sha":""}}'
OC_RECORD_OK=1 OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > "$TMP/v.out" 2>&1; rc=$?
{ [ "$rc" != 0 ] && ! grep -q '^result=' "$TMP/out"; }; expect "head が空文字で返った -> 非 0 で終わり result を出さない" $?

setup aaa '[]' 1
OC_HEAD_BEFORE=aaa OC_START_TS=2026-01-01T00:00:00Z run_fix check > /dev/null 2>&1; rc=$?
{ [ "$rc" -ne 0 ] && ! grep -q '^result=' "$TMP/out"; }; expect "record が窓の判定まで終えていない (OC_RECORD_OK 無し) -> none を出さず失敗する" $?

echo "== reopen-pr.sh (close -> reopen。reopen は 3 回まで再試行)"
reset
fx repos/o/r/pulls/7 '{"state":"open","merged_at":null}'
FAKE_REOPEN_FAILS=1 bash "$SCRIPTS/reopen-pr.sh" > "$TMP/v.out" 2>&1; rc=$?
{ [ $rc = 0 ] && logged 'pr close 7' && [ "$(grep -c 'pr reopen 7' "$LOG")" = 2 ]; }; expect "reopen が 1 回失敗しても再試行で再開する" $?
! logged 'issues/7/labels'; expect "再開できたら oc:stuck を付けない" $?

reset
fx repos/o/r/pulls/7 '{"state":"open","merged_at":null}'
FAKE_REOPEN_FAILS=99 bash "$SCRIPTS/reopen-pr.sh" > "$TMP/v.out" 2>&1; rc=$?
{ [ $rc = 1 ] && [ "$(grep -c 'pr reopen 7' "$LOG")" = 3 ]; }; expect "reopen が 3 回失敗 -> 非 0 で終わる" $?
{ logged 'issues/7/labels' && logged 'pr comment 7'; }; expect "reopen 失敗時は oc:stuck を付けて PR にコメントする" $?

echo "== reopen-pr.sh: PR の状態 (#2597。merge 済み・close 済みは想定内で 0、本当のエラーは失敗)"
reopen_run() { bash "$SCRIPTS/reopen-pr.sh" > "$TMP/v.out" 2>&1; }
untouched() { ! logged 'pr close' && ! logged 'pr reopen' && ! logged 'issues/7/labels' && ! logged 'pr comment'; }

reset
fx repos/o/r/pulls/7 '{"state":"closed","merged_at":"2026-01-01T00:00:00Z"}'
reopen_run; rc=$?
{ [ $rc = 0 ] && untouched && grep -q 'already merged' "$TMP/v.out"; }; expect "merge 済みの PR -> close も reopen もせず 0 で終わる (ラベル・コメントも付けない)" $?

reset
fx repos/o/r/pulls/7 '{"state":"closed","merged_at":null}'
reopen_run; rc=$?
{ [ $rc = 0 ] && untouched && grep -q 'not reopened' "$TMP/v.out"; }; expect "close 済み (未 merge) の PR -> 人が閉じたものを reopen せず 0 で終わる" $?

reset
reopen_run; rc=$?
{ [ $rc = 1 ] && untouched && grep -q 'could not read the state' "$TMP/v.out"; }; expect "PR の状態を読めない -> 隠さず失敗する (close しない)" $?

reset
fx repos/o/r/pulls/7 '{"state":"open","merged_at":null}'
FAKE_CLOSE_FAILS=1 reopen_run; rc=$?
{ [ $rc = 1 ] && logged 'pr close 7' && ! logged 'pr reopen' && grep -q 'could not close PR #7' "$TMP/v.out"; }; expect "open のまま close できない (本当のエラー) -> 'could not close PR' で失敗する" $?

reset
fx repos/o/r/pulls/7 '{"state":"open","merged_at":null}'
fx repos/o/r/pulls/7.2 '{"state":"closed","merged_at":"2026-01-01T00:00:00Z"}'
FAKE_CLOSE_FAILS=1 reopen_run; rc=$?
{ [ $rc = 0 ] && logged 'pr close 7' && ! logged 'pr reopen' && ! logged 'issues/7/labels' && grep -q 'merged while it was being closed' "$TMP/v.out"; }; expect "open と読んだ後、close の間に merge された競合 -> 0 で終わる" $?

reset
fx repos/o/r/pulls/7 '{"state":"open","merged_at":null}'
fx repos/o/r/pulls/7.2 '{"state":"closed","merged_at":null}'
FAKE_CLOSE_FAILS=1 reopen_run; rc=$?
{ [ $rc = 0 ] && logged 'pr close 7' && logged 'pr reopen 7'; }; expect "close が失敗したが closed になっている -> PR を closed のまま残さず reopen に進む" $?

echo "== fix-progress.sh reopen (旧 workflow との互換)"
reset
fx repos/o/r/pulls/7 '{"state":"open","merged_at":null}'
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

echo "== verify-review-verdict.sh (差し戻し本文の oc-review マーカーは警告のみ #2320 / CI-42)"
# vrev <body>: head hhh への CHANGES_REQUESTED review (本文 = <body>) を 1 件仕込んで検証する
vrev() {
  vsetup NONE
  fx repos/o/r/pulls/7/reviews "$(jq -nc --arg b "$1" '[{user:{login:"oc-reviewer-for-signature-studio[bot]"},state:"CHANGES_REQUESTED",commit_id:"hhh",body:$b}]')"
  verify; rc=$?
}
warn() { grep -q '::warning::' "$TMP/v.out"; }

vrev "- 指摘 1
<!-- oc-review: v=1 round=1 blocking=1 minor=0 classes=doc,remeasure -->"
{ [ $rc = 0 ] && ! warn && ! logged 'pr reopen'; }; expect "正しいマーカー -> 警告なし・verdict をそのまま採用 (rc 0)" $?

vrev "- 指摘 1"
{ [ $rc = 0 ] && warn && grep -q 'no <!-- oc-review' "$TMP/v.out" && ! logged 'pr reopen'; }; expect "マーカー欠落 -> 警告が出て終了コード 0・再起動しない" $?

vrev "- 指摘 1
<!-- oc-review: v=1 round=1 blocking=1 minor=0 classes=doc,bogus -->"
{ [ $rc = 0 ] && grep -q 'unknown class: bogus' "$TMP/v.out"; }; expect "classes に未知語 -> 警告 (終了コード 0)" $?

vrev "- 指摘 1
<!-- oc-review: v=1 round=1 blocking=1 minor=0 classes=doc -->
追記"
{ [ $rc = 0 ] && grep -q 'not the last line' "$TMP/v.out"; }; expect "マーカーが末尾行でない -> 警告" $?

vrev "- 指摘 1
<!-- oc-review: v=2 round=1 blocking=1 minor=0 classes=doc -->"
{ [ $rc = 0 ] && grep -q 'unsupported version: v=2' "$TMP/v.out"; }; expect "v=1 以外 -> 警告" $?

echo "== reviewer.md の文言 (収束規則・マーカー・PM 判断表。旧文言の再混入を検出 #2320 / CI-42)"
# stale_phrase <file>: 旧文言 (PM に起票を求める) が残っていれば 0 を返す
stale_phrase() { grep -qE '起票を PM に求める|PM に(依頼|求める)する' "$1"; }
REVIEWER_MD="$SCRIPTS/../prompts/reviewer.md"
grep -q '収束規則' "$REVIEWER_MD" && grep -q '<!-- oc-review: v=1 round=<n>' "$REVIEWER_MD" && grep -q 'PM 判断が絡む指摘の扱い' "$REVIEWER_MD"
expect "reviewer.md に収束規則・マーカー書式・PM 判断表がある" $?
! stale_phrase "$REVIEWER_MD"; expect "reviewer.md に旧文言『起票を PM に求める』が無い" $?
# ネガコン: 旧文言を戻した一時コピーでは同じ検査が fail する
printf '%s\n' '(issue が無ければ起票を PM に求める)' > "$TMP/reviewer-neg.md"
stale_phrase "$TMP/reviewer-neg.md"; expect "ネガコン: 旧文言を戻すと検査が検出する" $?

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
