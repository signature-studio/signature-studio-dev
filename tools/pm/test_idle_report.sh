#!/bin/bash
# test_idle_report.sh — idle_report.sh の集計と中断を fake gh で検証する (#2354)。ネットワーク不使用。
# 実行: bash tools/pm/test_idle_report.sh   (全て通れば exit 0、1 件でも落ちれば exit 1)
#
# fake gh は `gh api [-i|--allow-escape-sequences] <endpoint>` だけを受け付ける (GraphQL・他のサブコマンドは exit 99)。
#   - runs 一覧: $FAKE_FIX/runs.jsonl を event・created 範囲・per_page/page で絞って返す (total_count 付き)
#   - jobs: name=watchdog (id = run id * 10 + 1) と skipped の implement を返す
#   - ログ: $FAKE_FIX/log_<run id> をそのまま返す
# X-Ratelimit-Remaining は FAKE_REMAINING (jobs 応答だけ FAKE_REMAINING_JOBS で上書き可)。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/idle_report.sh"
T="$(mktemp -d "${TMPDIR:-/tmp}/idle_report_test.XXXXXX")"
trap 'rm -rf "$T"' EXIT
FIX="$T/fix"
mkdir -p "$FIX" "$T/bin"
export FAKE_FIX="$FIX" FAKE_LOG="$T/gh.log" OC_REPO=o/r

cat > "$T/bin/gh" << 'EOF'
#!/bin/bash
echo "$*" >> "$FAKE_LOG"
[ "${1:-}" = api ] || { echo "fake gh: api 以外のサブコマンド: $*" >&2; exit 99; }
shift
ep=""
for a in "$@"; do
  case "$a" in
    -i | --allow-escape-sequences) ;;
    -*) echo "fake gh: 想定外のフラグ: $a" >&2; exit 99 ;;
    *) ep="$a" ;;
  esac
done
case "$ep" in graphql* | */graphql*) echo "fake gh: GraphQL は禁止" >&2; exit 99 ;; esac
emit() { # emit <remaining>: ヘッダと、標準入力の本文
  printf 'HTTP/2.0 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nX-Ratelimit-Limit: 5000\r\nX-Ratelimit-Remaining: %s\r\nX-Ratelimit-Reset: 1791981843\r\n\r\n' "$1"
  cat
}
case "$ep" in
  repos/o/r/actions/workflows/opencode.yaml/runs\?*)
    event="" created="" pp=100 pg=1
    IFS='&' read -r -a kv <<< "${ep#*\?}"
    for p in "${kv[@]}"; do
      case "$p" in
        event=*) event="${p#event=}" ;;
        created=*) created="${p#created=}" ;;
        per_page=*) pp="${p#per_page=}" ;;
        page=*) pg="${p#page=}" ;;
      esac
    done
    jq -s --arg ev "$event" --arg a "${created%%..*}" --arg b "${created##*..}" --argjson pp "$pp" --argjson pg "$pg" '
      map(select(.event == $ev and .created_at >= $a and .created_at <= $b)) | sort_by(.created_at) | reverse
      | {total_count: (length + (env.FAKE_EXTRA_TOTAL // "0" | tonumber)), workflow_runs: .[($pg - 1) * $pp : $pg * $pp]}' "$FAKE_FIX/runs.jsonl" | emit "${FAKE_REMAINING:-4000}"
    ;;
  repos/o/r/actions/runs/*/jobs\?*)
    id="${ep#repos/o/r/actions/runs/}"
    id="${id%%/*}"
    jq -n --argjson w "$((id * 10 + 1))" --argjson i "$((id * 10 + 2))" --arg c "${FAKE_JOB_CONCLUSION:-success}" '
      {total_count: 2, jobs: [
        {id: $i, name: "implement", status: "completed", conclusion: "skipped", started_at: "2020-01-01T00:00:00Z"},
        {id: $w, name: "watchdog", status: "completed", conclusion: $c, started_at: "2020-01-01T00:00:01Z"}]}' | emit "${FAKE_REMAINING_JOBS:-${FAKE_REMAINING:-4000}}"
    ;;
  repos/o/r/actions/jobs/*/logs)
    jid="${ep#repos/o/r/actions/jobs/}"
    jid="${jid%%/*}"
    f="$FAKE_FIX/log_$(((jid - 1) / 10))"
    [ -f "$f" ] || { echo "fake gh: ログ無し (HTTP 404)" >&2; exit 1; }
    cat "$f"
    ;;
  *) echo "fake gh: 想定外の endpoint: $ep" >&2; exit 99 ;;
esac
EOF
chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH"

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }
check() { # check <名前> <コマンド...>: コマンドが成功なら ok
  local name="$1"
  shift
  if "$@"; then ok "$name"; else ng "$name"; fi
}

BASE="$(date -u -d 2026-10-14T00:00:00Z +%s)"
iso() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ; }
NEXT_ID=1000
reset() {
  rm -rf "$FIX"
  mkdir -p "$FIX"
  : > "$FIX/runs.jsonl"
  : > "$FAKE_LOG"
  rm -f "$T/cache.jsonl"
  unset FAKE_REMAINING FAKE_REMAINING_JOBS FAKE_EXTRA_TOTAL FAKE_JOB_CONCLUSION IDLE_REPORT_PER_PAGE IDLE_REPORT_WINDOW_HOURS IDLE_REPORT_MIN_REMAINING
}
# add_run <event> <title> <基準からの経過分> <idle | text:<ログ全文> | nolog> [status] [STUCK_LABELLED の行数]
add_run() {
  local ev="$1" title="$2" off="$3" idle="$4" status="${5:-completed}" stuck="${6:-0}" id created ts k
  NEXT_ID=$((NEXT_ID + 1))
  id="$NEXT_ID"
  created="$(iso $((BASE + off * 60)))"
  ts="$(iso $((BASE + off * 60 + 20)))"
  jq -cn --argjson id "$id" --arg ev "$ev" --arg t "$title" --arg s "$status" --arg c "$created" \
    '{id: $id, event: $ev, display_title: $t, status: $s, conclusion: "success", created_at: $c}' >> "$FIX/runs.jsonl"
  case "$idle" in
    nolog) ;;
    text:*) printf '%s\n' "${idle#text:}" > "$FIX/log_$id" ;;
    *)
      {
        printf '%s.1000000Z ##[group]Run bash .github/scripts/watchdog.sh\n' "${ts%Z}"
        printf '%s.2000000Z floating-issues=0\n' "${ts%Z}"
        for ((k = 1; k <= stuck; k++)); do
          printf '%s.2500000Z #%s STUCK_LABELLED: oc:stuck is set, waiting for a human decision\n' "${ts%Z}" "$((100 + k))"
        done
        printf '%s.3000000Z stuck=0 stuck-age-max=unknown stuck-age-p50=unknown\n' "${ts%Z}"
        printf '%s.4000000Z open=8 covered(REVIEWING/FIXING)=%s idle=%s acted=0 deferred=0\n' "${ts%Z}" "$((8 - idle))" "$idle"
        printf '%s.5000000Z ##[endgroup]\n' "${ts%Z}"
      } > "$FIX/log_$id"
      ;;
  esac
}
# series <開始分> <間隔分> <idle...>: 5 分おきの watchdog (repository_dispatch) を並べる
series() {
  local off="$1" step="$2" v
  shift 2
  for v in "$@"; do
    add_run repository_dispatch watchdog "$off" "$v"
    off=$((off + step))
  done
}
# report [追加の引数...]: 6 時間の窓で実行し、JSON を $T/out.json、要約を $T/err、終了コードを $RC に入れる
report() {
  bash "$SCRIPT" --since 2026-10-14T00:00:00Z --until 2026-10-14T06:00:00Z "$@" > "$T/out.json" 2> "$T/err"
  RC=$?
}
j() { jq -r "$1" "$T/out.json"; }
eqv() { [ "$(j "$1")" = "$2" ]; } # eqv <jq 式> <期待値>

# (a) idle=0 が続く -> 0 回
reset
series 0 5 0 0 0 0 0 0 0 0 0 0
report
check "a: idle=0 が続く -> rc=0" test "$RC" -eq 0
check "a: idle=0 が続く -> 0 回" eqv .streaks_ge_threshold 0
check "a: 標本 10 件・idle>0 は 0 件" eqv '[.samples.count, .samples.idle_positive] | join(",")' 10,0

# (b) idle>0 が 14 分 -> 0 回 (ネガコン)
reset
series 0 2 3 3 3 3 3 3 3 3 0
report
check "b: idle>0 が 14 分 -> 0 回 (ネガコン)" eqv .streaks_ge_threshold 0
check "b: 区間は記録され 14 分" eqv '.streaks | map(.minutes) | join(",")' 14
check "b: 閾値を 14 分にすると 1 回 (閾値が効いている)" bash -c "bash '$SCRIPT' --since 2026-10-14T00:00:00Z --until 2026-10-14T06:00:00Z --threshold-min 14 --quiet 2> /dev/null | jq -e '.streaks_ge_threshold == 1' > /dev/null"

# (b2) ちょうど 15 分は数える (標本間隔が粗いので実際の担当なし時間は 15 分以上)
reset
series 0 5 2 2 2 2 0
report
check "b2: idle>0 がちょうど 15 分 -> 1 回 (境界)" eqv .streaks_ge_threshold 1

# (c) 16 分 -> 1 回
reset
series 0 2 3 3 3 3 3 3 3 3 3 0
report
check "c: idle>0 が 16 分 -> 1 回" eqv .streaks_ge_threshold 1
check "c: 区間の長さ・標本数・最大 idle" eqv '.streaks[0] | [.minutes, .samples, .max_idle] | join(",")' 16,9,3
check "c: 回数は開始日の窓に帰属する" eqv '.by_bucket[0] | [.bucket, .streaks_ge_threshold] | join(",")' 2026-10-14,1

# (d) idle=0 を挟むと別カウント
reset
series 0 2 3 3 3 3 3 3 3 3 3 0 4 4 4 4 4 4 4 4 4 0
report
check "d: 16 分 + idle=0 + 16 分 -> 2 回 (別カウント)" eqv .streaks_ge_threshold 2
reset
series 0 2 3 3 3 3 3 3 0 4 4 4 4 4 4 0
report
check "d: 10 分 + idle=0 + 10 分 -> 0 回 (合算して 24 分としない)" eqv .streaks_ge_threshold 0
check "d: 区間は 2 つ" eqv '.streaks | length' 2

# (e) 残量 1,499 -> 中断 (終了コード非 0)
reset
series 0 2 3 3 3 3 3 3 3 3 3 0
export FAKE_REMAINING=1499
report
check "e: 残量 1,499 -> 終了コード 3" test "$RC" -eq 3
check "e: 理由 (1499) を標準エラーに出す" grep -q 'X-Ratelimit-Remaining=1499' "$T/err"
check "e: 結果の JSON は出さない" test ! -s "$T/out.json"
export FAKE_REMAINING=1500
report
check "e: 残量 1,500 -> 続行 (境界)" test "$RC" -eq 0
reset
series 0 2 3 3 3 3 3 3 3 3 3 0
export FAKE_REMAINING_JOBS=1499
report
check "e: jobs 応答の残量が 1,499 でも中断 (応答ごとに検査)" test "$RC" -eq 3
unset FAKE_REMAINING_JOBS FAKE_REMAINING

# (f) 全ページ取得と窓の分割 (1 時間の窓・per_page=2 で、窓の境界をまたぐ 20 分の区間を 1 回と数える)
reset
series 50 5 5 5 5 5 5 0
export IDLE_REPORT_PER_PAGE=2 IDLE_REPORT_WINDOW_HOURS=1
report
check "f: 窓・ページを跨いでも標本は欠けず重複しない (6 件)" eqv .samples.count 6
check "f: 境界をまたぐ区間 -> 1 回 (20 分)" eqv '[.streaks_ge_threshold, .streaks[0].minutes] | join(",")' 1,20
check "f: 2 ページ目も取得している" grep -q 'page=2' "$FAKE_LOG"
unset IDLE_REPORT_PER_PAGE IDLE_REPORT_WINDOW_HOURS

# (g) oc-fix の run・未完了の run は標本にしない
reset
series 0 5 0 0
add_run repository_dispatch 'oc-fix #12' 3 9
add_run repository_dispatch watchdog 8 9 in_progress
report
check "g: 標本は watchdog の完了 run だけ (2 件)" eqv .samples.count 2
check "g: oc-fix は数えて除外 (1 件)・未完了 (1 件)" eqv '[.runs.repository_dispatch_not_watchdog, .runs.incomplete] | join(",")' 1,1
check "g: oc-fix の run の jobs は取りに行かない" bash -c "! grep -q 'runs/$((NEXT_ID - 1))/jobs' '$FAKE_LOG'"

# (h) schedule・push の run も標本になる。--events で絞れる
reset
add_run repository_dispatch watchdog 0 2
add_run push 'Merge pull request #1 from x' 6 2
add_run schedule '' 10 2
add_run repository_dispatch watchdog 16 2
add_run push 'Merge pull request #2 from x' 20 0
report
check "h: 3 種類の event を合わせて 16 分の区間 -> 1 回" eqv '[.samples.count, .streaks_ge_threshold] | join(",")' 5,1
report --events repository_dispatch
check "h: --events repository_dispatch だけだと標本 2 件・欠落 1 回 (idle=0 の標本が無いので区間は 16 分)" eqv '[.samples.count, .samples.gaps_over_threshold, .streaks_ge_threshold] | join(",")' 2,1,1
report --events bogus
check "h: 不正な --events は終了コード 2" test "$RC" -eq 2

# (i) 読み取れない run の分類
reset
add_run repository_dispatch watchdog 0 2
add_run repository_dispatch watchdog 5 'text:2026-10-14T00:05:20.1000000Z no idle line here'
add_run repository_dispatch watchdog 10 nolog
add_run repository_dispatch watchdog 15 "text:$(printf '2026-10-14T00:15:20.1000000Z \033[36;1mopen=3 / covered(REVIEWING・FIXING)=1 / idle=2\033[0m')"
report
check "i: ログ無し・idle 行無しは標本にせず理由を数える" eqv '.runs.skipped | [.log_unavailable, .no_idle_line] | join(",")' 1,1
check "i: ANSI 付き・summary 形式の行も読める (標本 2 件・15 分)" eqv '[.samples.count, .streaks_ge_threshold] | join(",")' 2,1
reset
add_run repository_dispatch watchdog 0 2
export FAKE_JOB_CONCLUSION=skipped
report
check "i: watchdog job が skipped の run は標本にしない" eqv '[.samples.count, .runs.skipped.job_skipped] | join(",")' 0,1
check "i: 標本 0 件は警告を出す" grep -q '標本が 0 件' "$T/err"
reset
add_run push 'Merge pull request #3 from x' 0 nolog
export FAKE_JOB_CONCLUSION=cancelled
report --cache "$T/cache.jsonl"
check "i: ログの無い cancelled の job は job_cancelled として数える (log_unavailable にしない)" eqv '.runs.skipped | [.job_cancelled, .log_unavailable // 0] | join(",")' 1,0
unset FAKE_JOB_CONCLUSION

# (j) キャッシュ: 2 回目は jobs・ログを取りに行かず、結果が同じ
reset
series 0 2 3 3 3 3 3 3 3 3 3 0
report --cache "$T/cache.jsonl"
first="$(jq -c '[.streaks_ge_threshold, .samples.count]' "$T/out.json")"
: > "$FAKE_LOG"
report --cache "$T/cache.jsonl"
check "j: キャッシュ有りの 2 回目は同じ結果" test "$(jq -c '[.streaks_ge_threshold, .samples.count]' "$T/out.json")" = "$first"
check "j: 2 回目は jobs・ログを取らない (run 一覧だけ)" bash -c "! grep -qE '/jobs|/logs' '$FAKE_LOG'"
check "j: cache_hits = 10" eqv .runs.cache_hits 10

# (k) 1 窓の run が 1,000 件を超えるなら中断 (黙って取りこぼさない)
reset
series 0 5 0 0
export FAKE_EXTRA_TOTAL=1001
report
check "k: total_count > 1000 -> 終了コード 4" test "$RC" -eq 4
unset FAKE_EXTRA_TOTAL

# (l) 引数の検査
reset
bash "$SCRIPT" --since 2026-10-14T06:00:00Z --until 2026-10-14T00:00:00Z > /dev/null 2>&1
check "l: since >= until は終了コード 2" test "$?" -eq 2
bash "$SCRIPT" --since 2026-10-14T00:00:00Z > /dev/null 2>&1
check "l: --until 無しは終了コード 2" test "$?" -eq 2

# (m) oc:stuck の PR (人の判断待ち) は常に idle に入る。除いた回数も別に出す
reset
for off in 0 5 10 15 20; do add_run repository_dispatch watchdog "$off" 2 completed 2; done
add_run repository_dispatch watchdog 25 0
report
check "m: idle の全てが STUCK_LABELLED -> 全体は 1 回・stuck 除外は 0 回" eqv '[.streaks_ge_threshold, .excluding_stuck_labelled.streaks_ge_threshold] | join(",")' 1,0
reset
for off in 0 5 10 15 20; do add_run repository_dispatch watchdog "$off" 3 completed 2; done
add_run repository_dispatch watchdog 25 0
report
check "m: stuck 以外の idle が残れば stuck 除外でも 1 回 (ネガコン)" eqv '[.streaks_ge_threshold, .excluding_stuck_labelled.streaks_ge_threshold] | join(",")' 1,1

# (n) REST のみ: 呼び出しは全て `api <path>` で、GraphQL を使わない
reset
series 0 5 0 0 3 3
report
check "n: gh の呼び出しは全て api (REST)・graphql 無し" bash -c "! grep -qiE 'graphql' '$FAKE_LOG' && ! grep -vqE '^api ' '$FAKE_LOG'"

echo "idle_report: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
