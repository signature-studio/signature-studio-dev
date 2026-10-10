#!/usr/bin/env bash
# cleanup.sh — 検証用リソース (名前が signature-studio-hosting-probe[-x] に厳密一致するもの) だけを削除し、残存ゼロを確認する。
# 他用途のリソース (cloudflareos-*, scriba-*, nksf-*, zone cabbagelettuce.com など) には触れない。名前は正規表現で二重に検査してから削除する。
set -u
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
cd "$(dirname "$0")/.."
OK='^signature-studio-hosting-probe(-[a-z]+)?$'
guard() { [[ "$1" =~ $OK ]] || { echo "REFUSE: $1 は検証用リソース名ではない"; exit 3; }; }
BUCKET=signature-studio-hosting-probe

echo "== Access apps"
cf zero-trust access applications list 2>/dev/null | python3 -c "
import sys,json,re
for a in json.load(sys.stdin):
    if re.match(r'$OK', a['name']): print(a['id'], a['name'])" | while read -r id name; do
  guard "$name"; cf zero-trust access applications delete "$id" --force >/dev/null 2>&1 && echo "deleted access app $name" || echo "FAILED access app $name"
done
echo "== Access service tokens"
cf zero-trust access service-tokens list 2>/dev/null | python3 -c "
import sys,json,re
for a in json.load(sys.stdin):
    if re.match(r'$OK', a['name']): print(a['id'], a['name'])" | while read -r id name; do
  guard "$name"; cf zero-trust access service-tokens delete "$id" --force >/dev/null 2>&1 && echo "deleted service token $name" || echo "FAILED service token $name"
done
echo "== Pages project"
if cf pages list 2>/dev/null | python3 -c "
import sys,json,re
sys.exit(0 if any(re.match(r'$OK', p['name']) for p in json.load(sys.stdin)) else 1)"; then
  guard signature-studio-hosting-probe-p; bunx wrangler pages project delete signature-studio-hosting-probe-p --yes >/dev/null 2>&1 && echo "deleted pages project" || echo "FAILED pages project"
fi
echo "== Workers"
for w in a s big over pol; do
  n=signature-studio-hosting-probe-$w; guard "$n"
  if [ -n "$(cf workers scripts search --name "$n" 2>/dev/null | python3 -c "import sys,json;print(''.join(s['script_name'] for s in json.load(sys.stdin) if s['script_name']=='$n'))")" ]; then
    bunx wrangler delete --name "$n" --force >/dev/null 2>&1 && echo "deleted worker $n" || echo "FAILED worker $n"
  fi
done
echo "== R2 bucket"
guard "$BUCKET"
if cf r2 buckets list 2>/dev/null | python3 -c "
import sys,json
sys.exit(0 if any(b['name']=='$BUCKET' for b in json.load(sys.stdin)['buckets']) else 1)"; then
  cf r2 buckets domains managed update "$BUCKET" --enabled=false -f >/dev/null 2>&1
  # 空にする: prefix 削除モード (非空 prefix は '/' 終わり。--body '{}' が CLI 上必須)。このバケットのキーは a/ d/ のみ
  for pre in a/ d/; do cf r2 objects bulk-delete --bucket-name "$BUCKET" --prefix "$pre" --body '{}' -f >/dev/null 2>&1; done
  left=$(cf r2 objects list --bucket-name "$BUCKET" --per-page 5 2>/dev/null | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
  [ "$left" = 0 ] || echo "WARN: bucket に未削除オブジェクトあり (prefix a/ d/ 以外?)"
  cf r2 buckets delete "$BUCKET" -f >/dev/null 2>&1 && echo "deleted bucket $BUCKET" || echo "FAILED bucket $BUCKET"
fi

echo "== 残存確認 (全て 0 件であること)"
{
  cf workers scripts search --name signature-studio 2>/dev/null | python3 -c "import sys,json;print('workers', [s['script_name'] for s in json.load(sys.stdin) if s['script_name'].startswith('signature-studio')])"
  cf pages list 2>/dev/null | python3 -c "import sys,json;print('pages', [p['name'] for p in json.load(sys.stdin) if p['name'].startswith('signature-studio')])"
  cf r2 buckets list 2>/dev/null | python3 -c "import sys,json;print('r2', [b['name'] for b in json.load(sys.stdin)['buckets'] if b['name'].startswith('signature-studio')])"
  cf zero-trust access applications list 2>/dev/null | python3 -c "import sys,json;print('access apps', [a['name'] for a in json.load(sys.stdin) if a['name'].startswith('signature-studio')])"
  cf zero-trust access service-tokens list 2>/dev/null | python3 -c "import sys,json;print('service tokens', [a['name'] for a in json.load(sys.stdin) if a['name'].startswith('signature-studio')])"
}
rm -f work/access-ids.txt work/svc-token.json work/svc-token.id
