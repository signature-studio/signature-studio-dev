#!/usr/bin/env bash
# R2 カスタムドメイン接続。**Access App 作成 (40) と rules 反映 (30) の後**に実行すること
# (先に接続すると、Access 前に bucket が公開される / COOP・COEP 無しで配信される)。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need CF_ZONE CF_HOSTNAME CF_R2_BUCKET

step "カスタムドメイン $CF_HOSTNAME -> $CF_R2_BUCKET"
ZID="$(cf zones list --name "$CF_ZONE" | node -e 'const z=JSON.parse(require("fs").readFileSync(0,"utf8"));const l=Array.isArray(z)?z:z.result??[];console.log(l.find(x=>x.name===process.argv[1])?.id??"")' "$CF_ZONE")"
[[ -n "$ZID" ]] || { echo "zone 解決失敗: $CF_ZONE" >&2; exit 1; }

cf r2 buckets domains custom create "$CF_R2_BUCKET" \
  --domain "$CF_HOSTNAME" --zone-id "$ZID" --enabled true --min-tls 1.2 "${DRYFLAG[@]}"

if [[ "$APPLY" == "1" ]]; then
  echo "接続状態 (Initializing -> Active には数分):"
  cf r2 buckets domains custom get "$CF_HOSTNAME" --bucket-name "$CF_R2_BUCKET" || true
fi
