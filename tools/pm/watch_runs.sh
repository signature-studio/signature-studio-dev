#!/bin/bash
# watch_runs.sh — 実行中の Actions run のうち古い順に最大 MAXW 本を追い、いずれか 1 本が
# 完了したら 1 行報告して終了する。終了 = 完了通知 (PM が次の確認をし、直ちに再起動する。
# PM ルール: background の watcher を 0 本にしない)。
#
# API 消費の設計 (2026-10-13: 全 run を 30 秒間隔で並列 watch し core 5000/h を使い切った反省):
#   - `gh run watch` は使わない (1 回の poll で複数 API を叩く)。代わりに actions/runs/<id> を
#     POLL 秒 (既定 120) ごとに 1 リクエストだけ読む。MAXW (既定 3) 本まで。
#   - レート制限 (403 / X-Ratelimit-Remaining: 0) になったら API を叩かず、リセット時刻まで待つ。
#   - 一覧取得は起動時の 1 回 (+ 空の確認 1 回)。失敗しても終了せず待って再試行する。
# 待機は sleep ではなく `timeout N tail -f /dev/null` (sleep 禁止ルール: 指示 86/88)。
set -uo pipefail

REPO="${1:-signature-studio/signature-studio-dev}"
MAXW="${MAXW:-3}"
POLL="${POLL:-120}"
ERR="${TMPDIR:-/tmp}/watch_err.$$.log"

wait_s() { timeout "$1" tail -f /dev/null >/dev/null 2>&1 || true; }

is_limited_err() { grep -qiE "rate limit|HTTP 403" "$1" 2>/dev/null; }

# 403 を受けたら、実際の core の reset を X-Ratelimit-Reset から取る (rate_limit 本文は別カウンタを返すことがある)
reset_wait_from_runs() {
  local reset now
  reset="$(gh api -i "repos/$REPO/actions/runs?per_page=1" 2>/dev/null | tr -d '\r' | sed -n 's/^[Xx]-[Rr]atelimit-[Rr]eset: *//p' | head -1)"
  now="$(date +%s)"
  if [ -n "$reset" ] && [ "$reset" -gt "$now" ] 2>/dev/null; then echo $(( reset - now + 5 )); else echo 120; fi
}

# run が 0 本でも終了しない (watcher を 0 本にしない)。新しい run が現れるまで IDLE 秒ごとに
# 1 リクエストだけ読んで待つ。
IDLE="${IDLE:-60}"
# completed を含む 1 ページ (50 件) では、新しい完了 run に押し出されて未完了 run を取りこぼすため、
# 未完了の status ごとに全ページを取得する (100 件で打ち切らない。古い run が落ちると監視対象から外れる)。
list_active() {
  local s out all=""
  for s in queued in_progress waiting pending requested; do
    out="$(gh api --paginate "repos/$REPO/actions/runs?status=$s&per_page=100" --jq '.workflow_runs[].id' 2>"$ERR")" || return 1
    all="$all$out"$'\n'
  done
  printf '%s' "$all" | sed '/^$/d' | sort -n
}
while true; do
  if ids="$(list_active)"; then
    [ -n "$ids" ] && break
    wait_s "$IDLE"; continue
  fi
  if is_limited_err "$ERR"; then
    w="$(reset_wait_from_runs)"; echo "rate limited; waiting ${w}s until reset" >&2
  else
    w=120; echo "list failed ($(head -c 120 "$ERR" | tr '\n' ' ')); retry in ${w}s" >&2
  fi
  wait_s "$w"
done

# 古い順に MAXW 本を POLL 秒ごとに 1 リクエストで追う。完了 = status == completed。
watch_ids="$(printf '%s\n' $ids | head -n "$MAXW")"
while true; do
  for id in $watch_ids; do
    out="$(gh api "repos/$REPO/actions/runs/$id" --jq '"\(.status)|\(.conclusion)|\(.display_title[0:60])"' 2>"$ERR")" || {
      if is_limited_err "$ERR"; then
        w="$(reset_wait_from_runs)"; echo "rate limited; waiting ${w}s until reset" >&2; wait_s "$w"
      fi
      continue
    }
    case "$out" in
      completed\|*) echo "$id|${out#completed|}"; rm -f "$ERR"; exit 0 ;;
    esac
  done
  wait_s "$POLL"
done
