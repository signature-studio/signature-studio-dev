#!/bin/bash
# pm_watchdog_ping.sh — GitHub の cron (schedule) が発火しない間の代替 (#749)。
# repository_dispatch (oc-watchdog) を送り、Actions 側の watchdog job を起動する。5 分おきに systemd timer から呼ぶ。
# 認証は gh の keyring。keyring がロックされていると失敗するので、失敗はログに残して終える (推測・平文保存はしない)。
R="${PM_REPO:-signature-studio/signature-studio-dev}"
LOG="${PM_WATCHDOG_LOG:-$(cd "$(dirname "$0")" && pwd)/pm_watchdog_ping.log}"
ts="$(date -u +%FT%TZ)"
if timeout 40 gh api -X POST "repos/$R/dispatches" -f event_type=oc-watchdog > /dev/null 2>"$LOG.err"; then
  echo "$ts ok" >> "$LOG"
else
  echo "$ts FAILED: $(head -c 200 "$LOG.err" | tr '\n' ' ')" >> "$LOG"
fi
tail -n 500 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
exit 0
