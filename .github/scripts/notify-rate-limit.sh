#!/bin/bash
# notify-rate-limit.sh — 率制限の検知と通知 (#2346 / CI-67)。detect-rate-limit.sh が cause=rate_limit を検知した直後に呼ぶ (#2344)。
# 判定: 直近 30 分に cause=rate_limit のマーカーを残した run (bot のコメントの run id を重複なしで数え、呼び出し元の run を加える) が
#       5 件以上、かつ同じ 30 分に作成された opencode の完了 run の 30% 以上。素材不足・依存などは数えない (指示 126)。
# 通知: ラベル oc:rate-limit の open な issue があれば、そこに 60 分に 1 回までコメントを足す (run id のリストと件数だけ)。
#       無ければ `[CI] 率制限: 30 分で <N> 件の run が失敗 (<日付>)` を起票してラベルを付ける (6 時間に 1 件まで)。
# OC_MODEL_ID は変更しない: repo 変数の API は呼ばない。切替は指示 126 の範囲で PM がログを確認して行う。
# 観測用なので、失敗しても run を失敗させない (終了コード 0)。
# 入力 (env): GH_TOKEN (issues:write の App token)・OC_REPO・GITHUB_RUN_ID・GITHUB_SERVER_URL。テスト用: OC_NOW (現在時刻の epoch 秒)。
# コメント・起票本文に agent を起動する語 (行頭の slash + oc 等) を入れない。
set -uo pipefail
export LC_ALL=C.UTF-8

R="${OC_REPO:-}"
if [ -z "$R" ] || [ -z "${GH_TOKEN:-}" ]; then
  echo "::warning::no repo or token: the rate-limit notice is skipped"
  exit 0
fi
LABEL="oc:rate-limit"
RUN="${GITHUB_RUN_ID:-0}"
NOW="${OC_NOW:-$(date -u +%s)}"
iso() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ; }
w30="$(iso $((NOW - 1800)))"

if ! cm="$(gh api --paginate "repos/$R/issues/comments?since=$w30&per_page=100")"; then
  echo "::warning::could not read the issue comments: the rate-limit notice is skipped"
  exit 0
fi
ids="$(jq -cs --arg run "$RUN" '[ .[][] | select(.user.type == "Bot") | .body // "" | scan("cause=rate_limit run=([0-9]+)") | .[0] ] + [$run] | unique' <<< "$cm" 2> /dev/null)" || ids=""
case "$ids" in
  '['*) ;;
  *)
    echo "::warning::could not count the rate-limit markers: the notice is skipped"
    exit 0
    ;;
esac
n="$(jq 'length' <<< "$ids")"
if [ "$n" -lt 5 ]; then
  echo "rate-limit runs in 30 min: $n (< 5): no notice"
  exit 0
fi

total="$(gh api "repos/$R/actions/workflows/opencode.yaml/runs?created=%3E%3D$w30&status=completed&per_page=1" --jq '.total_count' 2> /dev/null)" || total=""
case "$total" in '' | *[!0-9]*)
  echo "::warning::could not count the completed runs: the rate-limit notice is skipped"
  exit 0
  ;;
esac
if [ $((n * 100)) -lt $((total * 30)) ]; then
  echo "rate-limit runs: $n of $total completed runs in 30 min (< 30%): no notice"
  exit 0
fi
runs="$(jq -r 'join(", ")' <<< "$ids")"

if ! open="$(gh api "repos/$R/issues?labels=oc%3Arate-limit&state=open&per_page=100")"; then
  echo "::warning::could not list the open $LABEL issues: the rate-limit notice is skipped"
  exit 0
fi
num="$(jq -r '[.[] | select(.pull_request == null)] | .[0].number // empty' <<< "$open")"
if [ -n "$num" ]; then
  if ! c="$(gh api --paginate "repos/$R/issues/$num/comments?since=$(iso $((NOW - 3600)))&per_page=100")"; then
    echo "::warning::could not read the comments of #$num: the rate-limit notice is skipped"
    exit 0
  fi
  if jq -s -e '[.[][] | select(.user.type == "Bot" and ((.body // "") | contains("<!-- oc-rate-limit-notify -->")))] | length > 0' <<< "$c" > /dev/null; then
    echo "#$num has a notice within 60 min: nothing to post"
    exit 0
  fi
  body="[rate-limit] 直近 30 分で率制限 (rate_limit_error / HTTP 429) により失敗した run が $n 件ありました (同じ 30 分に作成された opencode の完了 run は $total 件)。
run id: $runs
<!-- oc-rate-limit-notify -->"
  gh api -X POST "repos/$R/issues/$num/comments" -f body="$body" > /dev/null || echo "::warning::could not post the rate-limit notice on #$num"
  echo "posted the rate-limit notice on #$num"
  exit 0
fi

if ! last="$(gh api "repos/$R/issues?labels=oc%3Arate-limit&state=all&sort=created&direction=desc&per_page=10" --jq '[.[] | select(.pull_request == null)] | .[0].created_at // empty')"; then
  echo "::warning::could not read the last $LABEL issue: the rate-limit notice is skipped"
  exit 0
fi
last_t=0
[ -n "$last" ] && last_t="$(date -u -d "$last" +%s 2> /dev/null || echo 0)"
if [ "$last_t" -ge $((NOW - 21600)) ]; then
  echo "a $LABEL issue was opened within 6 hours: nothing to open"
  exit 0
fi

day="$(date -u -d "@$NOW" +%Y-%m-%d)"
title="[CI] 率制限: 30 分で $n 件の run が失敗 ($day)"
body="@pycabbage 率制限 (rate_limit_error / HTTP 429) による run の失敗を検知しました。直近 30 分で $n 件、同じ 30 分に作成された opencode の完了 run は $total 件です。

run id: $runs

\`OC_MODEL_ID\` は自動では変更されません。指示 126 の範囲で PM がログを確認して切り替えます。
この issue は自動通知です。6 時間に 1 件までしか起票せず、続報は open な \`$LABEL\` の issue へのコメントで届きます。"
gh api -X POST "repos/$R/labels" -f name="$LABEL" -f color=D93F0B \
  -f description="rate-limit notices from notify-rate-limit.sh (opencode runs failing with rate_limit_error)" > /dev/null 2>&1 || true
if ! gh api -X POST "repos/$R/issues" -f title="$title" -f body="$body" -f "labels[]=$LABEL" > /dev/null; then
  echo "::warning::could not open the rate-limit issue"
  exit 0
fi
echo "opened the rate-limit issue: $title"
exit 0
