#!/usr/bin/env bash
# 使い捨て probe リソース (名前が signature-studio-deploy-probe[-x] に厳密一致するもの) だけを削除し、
# snapshot.sh のベースラインと突き合わせて「残存 0・既存無変更」を確認する。本番名 signature-studio には絶対に触れない。
#   bash deploy/probe/probe-cleanup.sh [baseline.json]
set -u
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
cd "$(dirname "$0")/.."
BASE="${1:-work/probe-baseline.json}"
WORKER_RE='^signature-studio-deploy-probe(-[a-z0-9]+)?$'
TOKEN_RE='^signature-studio-deploy-probe(-[a-z0-9]+)?-e2e$'
export WORKER_RE TOKEN_RE

echo "== Access apps"
cf zero-trust access applications list 2>/dev/null | python3 -c "
import sys,json,re,os
for a in json.load(sys.stdin):
    if re.match(os.environ['WORKER_RE'], a['name']): print(a['id'], a['name'])" | while read -r id name; do
  [[ "$name" =~ $WORKER_RE ]] || { echo "REFUSE: $name"; exit 3; }
  cf zero-trust access applications delete "$id" --force >/dev/null 2>&1 && echo "deleted access app $name" || echo "FAILED access app $name"
done
echo "== Access service tokens"
cf zero-trust access service-tokens list 2>/dev/null | python3 -c "
import sys,json,re,os
for a in json.load(sys.stdin):
    if re.match(os.environ['TOKEN_RE'], a['name']): print(a['id'], a['name'])" | while read -r id name; do
  [[ "$name" =~ $TOKEN_RE ]] || { echo "REFUSE: $name"; exit 3; }
  cf zero-trust access service-tokens delete "$id" --force >/dev/null 2>&1 && echo "deleted service token $name" || echo "FAILED service token $name"
done
echo "== Workers"
cf workers scripts search --name signature-studio-deploy-probe --per-page 100 2>/dev/null | python3 -c "
import sys,json,re,os
for s in json.load(sys.stdin):
    if re.match(os.environ['WORKER_RE'], s['script_name']): print(s['script_name'])" | while read -r n; do
  [[ "$n" =~ $WORKER_RE ]] || { echo "REFUSE: $n"; exit 3; }
  (cd "$PWD" && bunx wrangler delete --name "$n" --force >/dev/null 2>&1) && echo "deleted worker $n" || echo "FAILED worker $n"
done
rm -f work/secrets/signature-studio-deploy-probe-*.json work/wrangler.signature-studio-deploy-probe-*.jsonc work/signature-studio-deploy-probe-*.url

echo "== 残存確認 (signature-studio* は 0 件、既存は無変更であること)"
bash probe/snapshot.sh work/probe-after.json >/dev/null
if [ -f "$BASE" ]; then
  if diff <(python3 -m json.tool "$BASE") <(python3 -m json.tool work/probe-after.json) >/dev/null; then echo "BASELINE MATCH: ベースラインと完全一致 (残存 0 / 既存無変更)"; else echo "BASELINE DIFF:"; diff <(python3 -m json.tool "$BASE") <(python3 -m json.tool work/probe-after.json); exit 1; fi
else
  python3 - <<'P'
import json
s=json.load(open('work/probe-after.json'))
print('signature-studio* workers:', [w for w in s['workers'] if w.startswith('signature-studio')])
print('signature-studio* access apps:', [a for a in s['accessApps'] if 'signature-studio' in a])
print('signature-studio* tokens:', [t for t in s['serviceTokens'] if t.startswith('signature-studio')])
P
fi
