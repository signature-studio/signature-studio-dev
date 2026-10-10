#!/usr/bin/env bash
# access-probe.sh create|test|delete — Cloudflare Access (Zero Trust) を既定ホスト名 4 種に掛けられるかを API で確認する
#   a  : Worker 単位 (destination type=worker)           -> workers.dev (本番/プレビュー/将来のカスタムドメイン全部)
#   s  : ホスト名 (type=public) workers.dev
#   p  : ホスト名 (type=public) pages.dev
#   r  : ホスト名 (type=public) r2.dev (自ゾーン外)  -> 期待: 作成不可
# 作成した app の id は work/access-ids.txt に記録し、delete はそこに記録された id のみ消す。
set -u
cd "$(dirname "$0")/.."
SUB=${WORKERS_SUBDOMAIN:-pycabbage}
EMAIL=${ALLOW_EMAIL:-}
R2HOST=${R2HOST:-}
need() { [ -n "$EMAIL" ] && [ -n "$R2HOST" ] || { echo "ALLOW_EMAIL=you@example.com R2HOST=pub-xxxx.r2.dev を指定"; exit 2; }; }
IDS=work/access-ids.txt
mk() { # name destination-json
  local body
  body=$(python3 - "$1" "$2" "$EMAIL" <<'PY'
import json,sys
name,dest,email=sys.argv[1:4]
print(json.dumps({"type":"self_hosted","name":name,"destinations":[json.loads(dest)],"session_duration":"24h",
 "policies":[{"name":name+"-allow","decision":"allow","include":[{"email":{"email":email}}]}]}))
PY
)
  cf zero-trust access applications create --body "$body" 2>&1
}
case "${1:-}" in
create)
  need
  WID=$(cf workers scripts search --name signature-studio-hosting-probe-a 2>/dev/null | python3 -c "import sys,json;print(next(s['id'] for s in json.load(sys.stdin) if s['script_name']=='signature-studio-hosting-probe-a'))")
  for spec in "a|{\"type\":\"worker\",\"worker_id\":\"$WID\"}" \
              "s|{\"type\":\"public\",\"uri\":\"signature-studio-hosting-probe-s.$SUB.workers.dev\"}" \
              "p|{\"type\":\"public\",\"uri\":\"signature-studio-hosting-probe-p.pages.dev\"}" \
              "r|{\"type\":\"public\",\"uri\":\"$R2HOST\"}"; do
    k=${spec%%|*}; dest=${spec#*|}
    out=$(mk "signature-studio-hosting-probe-$k" "$dest")
    id=$(echo "$out" | python3 -c "import sys,json
try: print(json.load(sys.stdin).get('id',''))
except Exception: print('')")
    if [ -n "$id" ]; then echo "$k $id" >> $IDS; echo "[$k] created $id"; else echo "[$k] FAILED: $(echo "$out" | tr '\n' ' ' | cut -c1-600)"; fi
  done ;;
test)
  need
  # hostname 型 Access は作成直後に反映されず 200 のままの時間がある (実測) ため、保護対象は 302 になるまで最大 90 秒ポーリングする
  for u in "https://signature-studio-hosting-probe-a.$SUB.workers.dev/a/" "https://signature-studio-hosting-probe-a.$SUB.workers.dev/d/x.raw" \
           "https://signature-studio-hosting-probe-s.$SUB.workers.dev/s/" "https://signature-studio-hosting-probe-s.$SUB.workers.dev/d/x.raw" \
           "https://signature-studio-hosting-probe-p.pages.dev/s/" "https://$R2HOST/d/x.raw"; do
    t0=$SECONDS
    for i in $(seq 1 30); do
      code=$(curl -s -o /dev/null -w '%{http_code}' "$u")
      [ "$code" = 302 ] && break
      [[ "$u" == *r2.dev* ]] && break
      sleep 3
    done
    printf '%s -> %s (%ss)\n' "$u" "$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$u" | cut -c1-120)" "$((SECONDS-t0))"
  done ;;
delete)
  [ -f $IDS ] || { echo "no ids"; exit 0; }
  rc=0
  while read -r k id; do
    if cf zero-trust access applications delete "$id" --force >/dev/null 2>&1; then echo "[$k] deleted $id"; else echo "[$k] DELETE FAILED $id"; rc=1; fi
  done < $IDS
  [ $rc = 0 ] && rm -f $IDS
  exit $rc ;;
*) echo "usage: $0 create|test|delete"; exit 2 ;;
esac
