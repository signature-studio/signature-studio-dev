#!/bin/bash
# idle_report.sh — watchdog の run 履歴から『担当なし (idle>0) の PR が 15 分以上続いた回数』を数える (#2354)。
#
# VM の pm-watchdog.timer を止めてよいかは、全 open PR の担当なし時間が 15 分を超えないことを一定期間
# 実測してから決める。watchdog.sh は点検のたびに `open=N covered(REVIEWING/FIXING)=N idle=N ...` を
# 標準出力に書く (step summary にも同じ値を書く)。この行を run のジョブログから読み、時系列にして数える。
# 新しい計測コードは要らない。
#
#   bash tools/pm/idle_report.sh --since 2026-10-14T00:00:00Z --until 2026-10-14T12:00:00Z
#
# 出力: 標準出力に JSON、標準エラーに人間向けの要約 (--quiet で要約を省く)。
# 終了コード: 0 正常 / 2 引数不正 / 3 レート制限の残量不足で中断 / 4 API 失敗・1 窓の run が多すぎる
#
# 方式 (README.md の idle_report.sh の節も参照):
#   - run 一覧: REST `repos/<R>/actions/workflows/opencode.yaml/runs?event=<E>&created=<A>..<B>` を
#     event ごと・窓 (既定 6 時間) ごとに全ページ取得する。created 付きの検索は 1 検索 1,000 件が上限なので、
#     窓で割り、窓の total_count が 1,000 を超えたら中断する (黙って取りこぼさない)。
#   - repository_dispatch は表題が `watchdog` の run だけを使う (`oc-fix #N` は watchdog job を持たない)。
#     schedule・push の run は watchdog job を持つので使う (push は main への merge のたびに走る)。
#   - 各 run の jobs から name=watchdog の job を選び、そのログの最後の idle 行を読む。標本の時刻はその行の
#     時刻印 (無ければ job の started_at、それも無ければ run の created_at)。完了していない run は使わない。
#   - 標本を時刻順に並べ、idle>0 の標本が途切れずに続く区間を 1 つの連続区間とする。区間の長さは
#     『最初の idle>0 標本から最後の idle>0 標本までの時間』で、閾値 (既定 15 分) 以上なら 1 回と数える (ちょうども数える)。
#     誤差は両方向。両端では標本の間隔ぶん実際より短く測り (過小)、標本の間で idle=0 に戻っても見えず 1 区間に合算する (過大)。
#     下限とは言えない。idle=0 の標本を挟むと別の区間になる。標本の欠落 (間隔が閾値より長い) は区間を切らず、
#     samples.gaps_over_threshold に数えて見えるようにする (欠落を『問題なし』とみなさない)。
#   - 回数は区間の開始時刻の窓 (--bucket day|hour) に帰属させる。期間の外から続く区間は期間の端で切れる。
#   - watchdog.sh の idle は oc:stuck の PR (人の判断待ち。`#N STUCK_LABELLED:` の行) を含む。stuck が残る間は
#     idle が 0 にならないので、同じログの STUCK_LABELLED の行数を引いた idle でも数え、excluding_stuck_labelled に出す。
#   - GraphQL を使わない (REST のみ)。応答ごとに X-Ratelimit-Remaining を見て、IDLE_REPORT_MIN_REMAINING
#     (既定 1500) 未満なら中断して理由を出す。ログ本文は blob へのリダイレクト先から返りヘッダを持たないので、
#     直前の jobs 応答の値で見る。
#   - --cache FILE: 完了した run の読み取り結果 (JSONL) を追記して次回に使う。中断しても続きから再開できる。
#
# 入力 (env): OC_REPO (省略時は git の origin から推定), IDLE_REPORT_MIN_REMAINING (1500),
#             IDLE_REPORT_PER_PAGE (100), IDLE_REPORT_WINDOW_HOURS (6), IDLE_REPORT_WORKFLOW (opencode.yaml)
set -uo pipefail

REPO="${OC_REPO:-}"
SINCE="" UNTIL=""
THRESHOLD_MIN=15
EVENTS="repository_dispatch,schedule,push"
BUCKET=day
CACHE=""
QUIET=0
MIN_REMAINING="${IDLE_REPORT_MIN_REMAINING:-1500}"
PER_PAGE="${IDLE_REPORT_PER_PAGE:-100}"
WINDOW_HOURS="${IDLE_REPORT_WINDOW_HOURS:-6}"
WORKFLOW="${IDLE_REPORT_WORKFLOW:-opencode.yaml}"

usage() {
  cat >&2 << 'EOF'
usage: idle_report.sh --since <ISO> --until <ISO> [--repo OWNER/REPO] [--threshold-min 15]
                      [--events repository_dispatch,schedule,push] [--bucket day|hour]
                      [--cache FILE] [--quiet]
EOF
}
die() { # die <exit code> <message>
  local code="$1"
  shift
  echo "idle_report: $*" >&2
  exit "$code"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --since) SINCE="${2:-}"; shift ;;
    --until) UNTIL="${2:-}"; shift ;;
    --repo) REPO="${2:-}"; shift ;;
    --threshold-min) THRESHOLD_MIN="${2:-}"; shift ;;
    --events) EVENTS="${2:-}"; shift ;;
    --bucket) BUCKET="${2:-}"; shift ;;
    --cache) CACHE="${2:-}"; shift ;;
    --quiet) QUIET=1 ;;
    -h | --help) usage; exit 0 ;;
    *) usage; die 2 "unknown argument: $1" ;;
  esac
  shift
done

[ -n "$SINCE" ] && [ -n "$UNTIL" ] || { usage; die 2 "--since と --until は必須"; }
case "$BUCKET" in day | hour) ;; *) die 2 "--bucket は day か hour" ;; esac
for v in "$THRESHOLD_MIN" "$MIN_REMAINING" "$PER_PAGE" "$WINDOW_HOURS"; do
  [[ "$v" =~ ^[1-9][0-9]*$ ]] || die 2 "数値の指定が正の整数でない: $v"
done
[ "$PER_PAGE" -le 100 ] || die 2 "per_page は 100 以下"
IFS=',' read -r -a EVENT_LIST <<< "$EVENTS"
for ev in "${EVENT_LIST[@]}"; do
  case "$ev" in repository_dispatch | schedule | push) ;; *) die 2 "--events は repository_dispatch,schedule,push の部分集合: $ev" ;; esac
done
if [ -z "$REPO" ]; then
  REPO="$(git config --get remote.origin.url 2> /dev/null | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')"
fi
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die 2 "--repo (または OC_REPO) が OWNER/REPO の形でない: '$REPO'"

SINCE_E="$(date -u -d "$SINCE" +%s 2> /dev/null)" || die 2 "--since を解釈できない: $SINCE"
UNTIL_E="$(date -u -d "$UNTIL" +%s 2> /dev/null)" || die 2 "--until を解釈できない: $UNTIL"
[ "$SINCE_E" -lt "$UNTIL_E" ] || die 2 "--since は --until より前でなければならない"
iso() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ; }

W="$(mktemp -d "${TMPDIR:-/tmp}/idle_report.XXXXXX")"
trap 'rm -rf "$W"' EXIT
ERRF="$W/err"
: > "$W/runs.jsonl"
: > "$W/samples.jsonl"
: > "$W/skips.jsonl"
BODY=""
MIN_SEEN=""
CALLS=0

abort_rate() { # abort_rate <remaining> <reset epoch or empty> <endpoint>
  local reset=""
  [ -n "$2" ] && reset=" (リセット $(iso "$2"))"
  die 3 "中断: X-Ratelimit-Remaining=$1 が下限 $MIN_REMAINING 未満$reset。直前の取得: $3。結果は出さない (--cache があれば取得済みの run は次回に再利用される)"
}

# api_json <endpoint>: 応答の本文を BODY に入れる。X-Ratelimit-Remaining を検査する (無い応答は中断)。
api_json() {
  local out hdr low rem reset
  CALLS=$((CALLS + 1))
  if ! out="$(gh api -i "$1" 2> "$ERRF")"; then
    die 4 "gh api が失敗: $1: $(head -c 300 "$ERRF")"
  fi
  out="${out//$'\r'/}"
  hdr="${out%%$'\n\n'*}"
  BODY="${out#*$'\n\n'}"
  low="$(printf '%s\n' "$hdr" | tr 'A-Z' 'a-z')"
  rem="$(printf '%s\n' "$low" | sed -n 's/^x-ratelimit-remaining: *\([0-9][0-9]*\).*/\1/p' | tail -1)"
  reset="$(printf '%s\n' "$low" | sed -n 's/^x-ratelimit-reset: *\([0-9][0-9]*\).*/\1/p' | tail -1)"
  [ -n "$rem" ] || die 4 "応答に X-Ratelimit-Remaining が無い (残量を確認できないため中断): $1"
  if [ -z "$MIN_SEEN" ] || [ "$rem" -lt "$MIN_SEEN" ]; then MIN_SEEN="$rem"; fi
  [ "$rem" -ge "$MIN_REMAINING" ] || abort_rate "$rem" "$reset" "$1"
}

# gh_log <endpoint> <出力ファイル>: ジョブログ (プレーンテキスト) を取る。失敗は 1 を返す。
# 新しい gh はログの端末制御文字を既定で拒否するので --allow-escape-sequences を付ける (古い gh は付けずに再試行)。
gh_log() {
  CALLS=$((CALLS + 1))
  if gh api --allow-escape-sequences "$1" > "$2" 2> "$ERRF"; then return 0; fi
  if grep -qi 'unknown flag' "$ERRF"; then
    gh api "$1" > "$2" 2> "$ERRF" && return 0
  fi
  return 1
}

# 1. run 一覧 (event × 窓)
for ev in "${EVENT_LIST[@]}"; do
  ws="$SINCE_E"
  while [ "$ws" -le "$UNTIL_E" ]; do
    we=$((ws + WINDOW_HOURS * 3600 - 1))
    [ "$we" -le "$UNTIL_E" ] || we="$UNTIL_E"
    page=1 fetched=0
    while :; do
      api_json "repos/$REPO/actions/workflows/$WORKFLOW/runs?event=$ev&created=$(iso "$ws")..$(iso "$we")&per_page=$PER_PAGE&page=$page"
      total="$(jq -r '.total_count // empty' <<< "$BODY" 2> /dev/null)"
      [[ "$total" =~ ^[0-9]+$ ]] || die 4 "run 一覧の total_count を読めない (event=$ev page=$page)"
      [ "$total" -le 1000 ] || die 4 "窓 $(iso "$ws")..$(iso "$we") (event=$ev) の run が $total 件で、検索の上限 1000 件を超える。IDLE_REPORT_WINDOW_HOURS を小さくする"
      n="$(jq '.workflow_runs | length' <<< "$BODY")"
      jq -c '.workflow_runs[] | {id, event, title: .display_title, status, created_at}' <<< "$BODY" >> "$W/runs.jsonl"
      fetched=$((fetched + n))
      if [ "$n" -eq 0 ] || [ "$fetched" -ge "$total" ]; then break; fi
      page=$((page + 1))
    done
    ws=$((we + 1))
  done
done
jq -s 'unique_by(.id)' "$W/runs.jsonl" > "$W/runs.json"
LISTED="$(jq length "$W/runs.json")"
INCOMPLETE="$(jq '[.[] | select(.status != "completed")] | length' "$W/runs.json")"
NOT_WATCHDOG="$(jq '[.[] | select(.status == "completed" and .event == "repository_dispatch" and .title != "watchdog")] | length' "$W/runs.json")"

# 2. キャッシュの読み込み (id -> JSON 1 行)
declare -A CACHED=()
CACHE_HITS=0
if [ -n "$CACHE" ] && [ -s "$CACHE" ]; then
  while IFS=$'\t' read -r cid cline; do
    [ -n "$cid" ] && CACHED["$cid"]="$cline"
  done < <(jq -r 'select(.run != null) | "\(.run)\t\(tojson)"' "$CACHE" 2> /dev/null)
fi

# record <JSON 1 行> <cache するか 0/1>
record() {
  if jq -e 'has("skip")' <<< "$1" > /dev/null; then printf '%s\n' "$1" >> "$W/skips.jsonl"; else printf '%s\n' "$1" >> "$W/samples.jsonl"; fi
  if [ "$2" = 1 ] && [ -n "$CACHE" ]; then printf '%s\n' "$1" >> "$CACHE"; fi
}

IDLE_RE='open=[0-9]+ (/ )?covered\([^)]*\)=[0-9]+ (/ )?idle=[0-9]+'
ESC=$'\033'

# 3. run ごとに watchdog job のログから idle を読む
while IFS=$'\t' read -r id created; do
  [ -n "$id" ] || continue
  if [ -n "${CACHED[$id]:-}" ]; then
    record "${CACHED[$id]}" 0
    CACHE_HITS=$((CACHE_HITS + 1))
    continue
  fi
  api_json "repos/$REPO/actions/runs/$id/jobs?per_page=100"
  job="$(jq -c '[.jobs[]? | select(.name == "watchdog")][0] // empty' <<< "$BODY")"
  if [ -z "$job" ]; then
    record "$(jq -cn --argjson r "$id" '{run: $r, skip: "no_watchdog_job"}')" 1
    continue
  fi
  if [ "$(jq -r '.conclusion // ""' <<< "$job")" = skipped ]; then
    record "$(jq -cn --argjson r "$id" '{run: $r, skip: "job_skipped"}')" 1
    continue
  fi
  jid="$(jq -r '.id' <<< "$job")"
  jstart="$(jq -r '.started_at // ""' <<< "$job")"
  if ! gh_log "repos/$REPO/actions/jobs/$jid/logs" "$W/log"; then
    if [ "$(jq -r '.conclusion // ""' <<< "$job")" = cancelled ]; then
      record "$(jq -cn --argjson r "$id" '{run: $r, skip: "job_cancelled"}')" 1
    else
      record "$(jq -cn --argjson r "$id" '{run: $r, skip: "log_unavailable"}')" 0
    fi
    continue
  fi
  sed "s/$ESC\[[0-9;]*[A-Za-z]//g" "$W/log" > "$W/log.plain"
  line="$(grep -E "$IDLE_RE" "$W/log.plain" | tail -1)"
  if [ -z "$line" ]; then
    record "$(jq -cn --argjson r "$id" '{run: $r, skip: "no_idle_line"}')" 1
    continue
  fi
  idle="$(sed -nE 's/.*idle=([0-9]+).*/\1/p' <<< "$line")"
  open="$(sed -nE 's/.*open=([0-9]+).*/\1/p' <<< "$line")"
  stuck_lab="$(grep -cE ' #[0-9]+ STUCK_LABELLED:' "$W/log.plain")"
  ts="$(sed -nE 's/^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(\.[0-9]+)?Z .*/\1Z/p' <<< "$line")"
  [ -n "$ts" ] || ts="${jstart:-$created}"
  record "$(jq -cn --argjson r "$id" --arg t "$ts" --argjson idle "$idle" --argjson open "$open" --argjson sl "$stuck_lab" '{run: $r, t: $t, idle: $idle, open: $open, stuck_labelled: $sl}')" 1
done < <(jq -r '.[] | select(.status == "completed" and (.event != "repository_dispatch" or .title == "watchdog")) | "\(.id)\t\(.created_at)"' "$W/runs.json")

# 4. 集計
jq -n \
  --slurpfile samples "$W/samples.jsonl" --slurpfile skips "$W/skips.jsonl" \
  --arg repo "$REPO" --arg since "$(iso "$SINCE_E")" --arg until "$(iso "$UNTIL_E")" \
  --argjson since_e "$SINCE_E" --argjson until_e "$UNTIL_E" \
  --argjson thr "$THRESHOLD_MIN" --arg bucket "$BUCKET" --arg events "$EVENTS" \
  --argjson listed "$LISTED" --argjson incomplete "$INCOMPLETE" --argjson not_watchdog "$NOT_WATCHDOG" \
  --argjson cache_hits "$CACHE_HITS" --argjson calls "$CALLS" --arg min_seen "${MIN_SEEN:-}" '
  def ep: sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601;
  def r2: . * 100 | round / 100;
  ($thr * 60) as $thr_s
  | (if $bucket == "hour" then 3600 else 86400 end) as $step
  | (if $bucket == "hour" then "%Y-%m-%dT%H:00Z" else "%Y-%m-%d" end) as $fmt
  | ($samples | map(. + {e: (.t | ep)}) | sort_by(.e)) as $s
  | def streaks_of($arr):
      reduce $arr[] as $x ({cur: null, out: []};
        if $x.idle > 0 then
          (if .cur == null
           then .cur = {start: $x.e, end: $x.e, samples: 1, max_idle: $x.idle, first_run: $x.run, last_run: $x.run}
           else .cur |= (.end = $x.e | .samples += 1 | .max_idle = ([.max_idle, $x.idle] | max) | .last_run = $x.run) end)
        elif .cur != null then (.out += [.cur] | .cur = null)
        else . end)
      | if .cur != null then .out += [.cur] else . end
      | .out
      | map({start: (.start | todate), end: (.end | todate), minutes: ((.end - .start) / 60 | r2),
             samples, max_idle, first_run, last_run, counted: ((.end - .start) >= $thr_s), bucket: (.start | strftime($fmt))});
    streaks_of($s) as $streaks
  | streaks_of($s | map(.idle = ([.idle - (.stuck_labelled // 0), 0] | max))) as $streaks_ns
  | ([range(1; $s | length)] | map($s[.].e - $s[. - 1].e)) as $gaps
  | ([range($since_e - ($since_e % $step); $until_e + 1; $step)] | map(strftime($fmt)) | unique) as $keys
  | {
      repo: $repo, since: $since, until: $until, threshold_min: $thr, events: ($events | split(",")), bucket: $bucket,
      streaks_ge_threshold: ($streaks | map(select(.counted)) | length),
      excluding_stuck_labelled: {
        streaks_ge_threshold: ($streaks_ns | map(select(.counted)) | length),
        by_bucket: ($keys | map(. as $k | {bucket: $k, streaks_ge_threshold: ($streaks_ns | map(select(.bucket == $k and .counted)) | length)})),
        streaks: $streaks_ns
      },
      by_bucket: ($keys | map(. as $k | {
          bucket: $k,
          streaks_ge_threshold: ($streaks | map(select(.bucket == $k and .counted)) | length),
          longest_idle_min: ($streaks | map(select(.bucket == $k) | .minutes) | max // 0),
          samples: ($s | map(select((.e | strftime($fmt)) == $k)) | length),
          idle_positive_samples: ($s | map(select((.e | strftime($fmt)) == $k and .idle > 0)) | length)
        })),
      samples: {
        count: ($s | length),
        idle_positive: ($s | map(select(.idle > 0)) | length),
        max_idle: ($s | map(.idle) | max // 0),
        longest_gap_min: (($gaps | max // 0) / 60 | r2),
        gaps_over_threshold: ($gaps | map(select(. > $thr_s)) | length)
      },
      runs: {
        listed: $listed, incomplete: $incomplete, repository_dispatch_not_watchdog: $not_watchdog,
        sampled: ($s | length),
        skipped: ($skips | group_by(.skip) | map({key: .[0].skip, value: length}) | from_entries),
        cache_hits: $cache_hits
      },
      api: {calls: $calls, min_ratelimit_remaining: ($min_seen | if . == "" then null else tonumber end)},
      streaks: $streaks
    }' > "$W/report.json" || die 4 "集計に失敗した"

cat "$W/report.json"

if [ "$QUIET" = 0 ]; then
  jq -r '
    "idle_report: \(.repo) \(.since) .. \(.until) (UTC)",
    "  idle>0 が \(.threshold_min) 分以上続いた回数: \(.streaks_ge_threshold) (oc:stuck の PR を除く idle: \(.excluding_stuck_labelled.streaks_ge_threshold))",
    "  標本 \(.samples.count) 件 (idle>0: \(.samples.idle_positive) 件、最大 idle=\(.samples.max_idle))、最長の標本間隔 \(.samples.longest_gap_min) 分、\(.threshold_min) 分超の間隔 \(.samples.gaps_over_threshold) 回",
    "  run: 一覧 \(.runs.listed) 件 / 未完了 \(.runs.incomplete) / oc-fix 等 \(.runs.repository_dispatch_not_watchdog) / 読み取り不能 \(.runs.skipped | to_entries | map("\(.key)=\(.value)") | join(" ") | if . == "" then "なし" else . end) / cache \(.runs.cache_hits)",
    "  API 呼び出し \(.api.calls) 回、X-Ratelimit-Remaining の最小 \(.api.min_ratelimit_remaining // "不明")",
    "  期間ごと (\(.bucket)):",
    (.by_bucket[] | "    \(.bucket)  回数=\(.streaks_ge_threshold)  この窓で始まった idle>0 連続の最長=\(.longest_idle_min) 分  標本=\(.samples) (idle>0: \(.idle_positive_samples))"),
    (.streaks | map(select(.counted)) | if length == 0 then empty else "  閾値以上の区間:" end),
    (.streaks[] | select(.counted) | "    \(.start) .. \(.end)  \(.minutes) 分  標本 \(.samples) 件  最大 idle=\(.max_idle)"),
    (if .samples.count == 0 then "  警告: 標本が 0 件。0 回は『問題なし』を意味しない" else empty end),
    (if .samples.gaps_over_threshold > 0 then "  注意: 標本の欠落 (間隔が閾値超) がある。欠落中の担当なしは数えていない" else empty end)
  ' "$W/report.json" >&2
fi
