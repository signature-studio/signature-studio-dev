#!/bin/bash
# pm_gate.sh <command...> — Worker が primary の間は command を実行せず終了 0 にする (#2341, 親 #2319)。
# primary = Worker の /status が mode=live かつ fresh=true かつ last_tick が MAX_AGE 秒以内。
# それ以外 (取得失敗・dry-run・fresh=false・JSON 不正・URL 未設定) は command を実行する (fail-open)。
# URL は env PM_WORKER_URL、無ければ tools/pm/worker_url の 1 行目。gh / GitHub REST は使わない。
here="$(cd "$(dirname "$0")" && pwd)"
URL="${PM_WORKER_URL:-}"
if [ -z "$URL" ] && [ -f "$here/worker_url" ]; then
  URL="$(head -n 1 "$here/worker_url" | tr -d '[:space:]')"
fi
MAX_AGE="${PM_GATE_MAX_AGE_SEC:-900}"

worker_is_primary() {
  [ -n "$URL" ] || return 1
  local body
  body="$(curl -fsS -m 10 "$URL/status" 2>/dev/null)" || return 1
  printf '%s' "$body" | python3 -c '
import datetime, json, sys
max_age = int(sys.argv[1])
try:
    s = json.load(sys.stdin)
    if s.get("mode") != "live" or s.get("fresh") is not True:
        sys.exit(1)
    t = s.get("last_tick")
    if not isinstance(t, str):
        sys.exit(1)
    last = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
    if last.tzinfo is None:
        sys.exit(1)
    age = (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds()
    sys.exit(0 if -60 <= age <= max_age else 1)
except Exception:
    sys.exit(1)
' "$MAX_AGE"
}

if worker_is_primary; then
  echo "Worker primary: skip ($*)"
  exit 0
fi
exec "$@"
