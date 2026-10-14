#!/bin/bash
# pm_wake.sh — PM の LLM セッションを『必要なときだけ』起こす (heartbeat.sh の置換。#2347, 親 #2319)。
# systemd timer から 1 回ずつ呼ぶ。Worker の /status (公開・集計のみ) を curl で 1 回読み、次のどれかのときだけ固定文を送る:
#   needs_pm      needs_pm > 0
#   worker_stale  fresh=false が 30 分続く (経過は状態ファイルで持つ)
#   stuck_old     stuck_age_max_min > 360 (PM agent が機能していない)
# 上限: 送信の間隔は 3 時間以上、24 時間に 6 回まで (失敗した試行も数える)。
# 文面は kind ごとの固定文だけ。/status の値は文面に入れない。送るのは opencode api post だけ。
# 終了コード: 0 = 判定の結果 (送った・送らなかった) / 1 = PM セッション ID が無い・不正 /
#             2 = /status の取得・解析に失敗 / 3 = 送信に失敗。
# 記録: PM_WAKE_LOG (既定 tools/pm/pm_wake.log)。状態: PM_WAKE_STATE (既定 tools/pm/pm_wake.state.json)。
here="$(cd "$(dirname "$0")" && pwd)"
URL="${PM_WORKER_URL:-}"
if [ -z "$URL" ] && [ -f "$here/worker_url" ]; then
  URL="$(head -n 1 "$here/worker_url" | tr -d '[:space:]')"
fi
STATE="${PM_WAKE_STATE:-$here/pm_wake.state.json}"
LOG="${PM_WAKE_LOG:-$here/pm_wake.log}"
OPENCODE="${OPENCODE_BIN:-opencode}"
now="${PM_WAKE_NOW:-$(date +%s)}"
ts="$(date -u -d "@$now" +%FT%TZ)"
STALE_SEC=1800
STUCK_MIN=360
GAP_SEC=10800
DAY_SEC=86400
DAY_MAX=6

log() { # log <text>: 記録に 1 行足し、500 行に丸める。標準出力にも出す (systemd の journal 用)
  printf '%s %s\n' "$ts" "$*" >> "$LOG"
  tail -n 500 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
  printf '%s %s\n' "$ts" "$*"
}

message_for() { # message_for <kind>: 固定文だけ (/status の値を入れない)
  case "$1" in
    needs_pm) echo '[pm-wake 自動送信 / needs_pm] needs-pm ラベルの issue または PR があります。docs/WORKFLOW.md の PM 手順に従って処理してください。他の作業は止めないでください。' ;;
    worker_stale) echo '[pm-wake 自動送信 / worker_stale] Worker の状態が 30 分以上 fresh=false のままです。infra/pm-worker/README.md の手順で同期の状態を確認してください。' ;;
    stuck_old) echo '[pm-wake 自動送信 / stuck_old] oc:stuck の PR が 6 時間を超えて残っています。PM 手順に従って stuck の PR を処理してください。' ;;
  esac
}

sid="${PM_SESSION_ID:-}"
if [ -z "$sid" ] && [ -n "${PM_SESSION_ID_FILE:-}" ]; then
  sid="$(head -n 1 "$PM_SESSION_ID_FILE" 2>/dev/null | tr -d '[:space:]')"
fi
if ! [[ "$sid" =~ ^[A-Za-z0-9_-]+$ ]]; then
  log "result=no-session reason=PM_SESSION_ID か PM_SESSION_ID_FILE が無い・不正"
  exit 1
fi
if [ -z "$URL" ]; then
  log "result=status-failed reason=URL 未設定 (PM_WORKER_URL / worker_url)"
  exit 2
fi

body="$(curl -fsS -m 10 "$URL/status" 2>/dev/null)"
rc=$?
if [ "$rc" -ne 0 ]; then
  log "result=status-failed curl_rc=$rc"
  exit 2
fi
parsed="$(printf '%s' "$body" | jq -r '
  if (.needs_pm | type) == "number" and (.fresh | type) == "boolean"
     and ((.stuck_age_max_min | type) == "number" or .stuck_age_max_min == null)
  then [.needs_pm, .fresh, ((.stuck_age_max_min // 0) | ceil)] | @tsv
  else error("shape") end' 2>/dev/null)" || parsed=""
if [ -z "$parsed" ]; then
  log "result=status-failed reason=parse"
  exit 2
fi
IFS=$'\t' read -r needs fresh stuck <<< "$parsed"

state='{"attempts":[],"fresh_false_since":null}'
if [ -s "$STATE" ] && jq -e '(.attempts | type) == "array" and ((.fresh_false_since | type) == "number" or .fresh_false_since == null)' "$STATE" > /dev/null 2>&1; then
  state="$(cat "$STATE")"
fi

since="$(jq -r '.fresh_false_since // empty' <<< "$state")"
if [ "$fresh" = false ]; then
  since="${since:-$now}"
else
  since=""
fi
read -r recent last < <(jq -r --argjson c "$((now - DAY_SEC))" \
  '[.attempts[] | select(type == "number" and . > $c)] | "\(length) \(max // 0)"' <<< "$state")

kind=""
if [ "$needs" -gt 0 ]; then
  kind=needs_pm
elif [ -n "$since" ] && [ $((now - since)) -ge "$STALE_SEC" ]; then
  kind=worker_stale
elif [ "$stuck" -gt "$STUCK_MIN" ]; then
  kind=stuck_old
fi

action=none
reason=""
if [ -n "$kind" ]; then
  if [ $((now - last)) -lt "$GAP_SEC" ]; then
    action=skip
    reason="3h 以内の送信がある"
  elif [ "$recent" -ge "$DAY_MAX" ]; then
    action=skip
    reason="24h に $DAY_MAX 回送信済み"
  else
    action=send
  fi
fi

send_rc=0
detail=""
if [ "$action" = send ]; then
  msg="$(message_for "$kind")"
  out="$(timeout 60 "$OPENCODE" api post "/api/session/$sid/prompt" -d "$(jq -cn --arg t "$msg" '{text:$t}')" 2>&1)"
  send_rc=$?
  if [ "$send_rc" -ne 0 ]; then
    detail="$(printf '%s' "$out" | head -n 1 | cut -c 1-160)"
  fi
fi

if ! jq -c --argjson now "$now" --argjson c "$((now - DAY_SEC))" --arg since "$since" \
  --arg kind "$kind" --arg act "$action" --argjson rc "$send_rc" '
    .attempts = [.attempts[] | select(type == "number" and . > $c)]
    | if $act == "send" then .attempts += [$now] | .last = {at: $now, kind: $kind, rc: $rc} else . end
    | .fresh_false_since = (if $since == "" then null else ($since | tonumber) end)
  ' <<< "$state" > "$STATE.tmp"; then
  log "result=state-failed"
  exit 2
fi
mv "$STATE.tmp" "$STATE"

case "$action" in
  send)
    if [ "$send_rc" -eq 0 ]; then
      log "result=sent kind=$kind rc=0"
    else
      log "result=send-failed kind=$kind rc=$send_rc detail=$detail"
      exit 3
    fi ;;
  skip) log "result=skip kind=$kind reason=$reason" ;;
  *) log "result=none needs_pm=$needs fresh=$fresh stuck_min=$stuck" ;;
esac
exit 0
