#!/usr/bin/env bash
# e2e.sh — 既定ホスト名 (workers.dev / pages.dev / r2.dev) で crossOriginIsolated が成立するかを、使い捨てリソースで一括検証する。
#   bash tools/hosting/probe/e2e.sh                   # 作成 -> 測定 -> 削除 (削除は cleanup.sh、名前厳密一致のみ)
#   KEEP=1 bash tools/hosting/probe/e2e.sh            # 削除しない
#   ALLOW_EMAIL=you@example.com bash ...e2e.sh        # 追加で Access (workers.dev / pages.dev / r2.dev) の掛かり方を検証
#   BIG=1 [BIG_N=2400] bash ...e2e.sh                 # 追加で N x 1MiB (既定 2400 = 2.34GiB) の Static Assets 規模検証
# 前提: `cf auth login` / `wrangler login` 済み、google-chrome、node>=22。作成物は全て signature-studio-hosting-probe* 接頭辞。
set -euo pipefail
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
cd "$(dirname "$0")/.."
H=$PWD
BUCKET=signature-studio-hosting-probe
[ -d node_modules/puppeteer-core ] || npm install --no-audit --no-fund >/dev/null
mkdir -p work/results

cf r2 buckets create-by-name $BUCKET >/dev/null 2>&1 || true   # Worker A の R2 バインディングに先に必要
# workers.dev サブドメインは Worker A の deploy 出力 URL から取得
SUB=$(cd probe/worker-a && bunx wrangler deploy 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -o 'signature-studio-hosting-probe-a\.[a-z0-9-]*\.workers\.dev' | head -1 | cut -d. -f2)
echo "workers.dev subdomain: $SUB"

echo "[1] data + site"
node probe/gen-data.mjs && node probe/build-site.mjs

echo "[2] R2 bucket + objects + CORS + r2.dev"
node probe/r2-upload.mjs $BUCKET
sed "s#pycabbage#$SUB#g" probe/r2-cors.json > work/r2-cors.json
cf r2 buckets cors update $BUCKET --rules @work/r2-cors.json -f >/dev/null
R2HOST=$(cf r2 buckets domains managed update $BUCKET --enabled -f | python3 -c "import sys,json;print(json.load(sys.stdin)['domain'])")
R2=https://$R2HOST
echo "r2.dev: $R2"

echo "[3] deploy A (Worker+R2) / S (Static Assets) / P (Pages)"
(cd probe/worker-a && bunx wrangler deploy >/dev/null 2>&1)
(cd probe/worker-s && bunx wrangler deploy >/dev/null 2>&1)
rm -rf work/dist-p && cp -r work/dist-s work/dist-p
bunx wrangler pages project create signature-studio-hosting-probe-p --production-branch main --force >/dev/null 2>&1 || true
bunx wrangler pages deploy work/dist-p --project-name signature-studio-hosting-probe-p --branch main --commit-dirty=true --force >/dev/null 2>&1
A=https://signature-studio-hosting-probe-a.$SUB.workers.dev
S=https://signature-studio-hosting-probe-s.$SUB.workers.dev
P=https://signature-studio-hosting-probe-p.pages.dev

# 新規 Worker/Pages/_headers/R2 の伝播待ち (最大 3 分)
waitfor() { for i in $(seq 1 60); do eval "$2" >/dev/null 2>&1 && return 0; sleep 3; done; echo "WARN: $1 が反映されない"; }
waitfor "S _headers"  "curl -sI $S/s/ | grep -qi cross-origin-embedder"
waitfor "S manifest"  "curl -sf $S/d/probe-manifest.json | grep -q wasmParts"
waitfor "P _headers"  "curl -sI $P/s/ | grep -qi cross-origin-embedder"
waitfor "P manifest"  "curl -sf $P/d/probe-manifest.json | grep -q wasmParts"
waitfor "A worker"    "curl -sf $A/d/probe-manifest.json | grep -q wasmParts"
waitfor "r2.dev"      "curl -sf $R2/d/probe-manifest.json | grep -q wasmParts"

echo "[4] headless Chrome probes (3 runs each)"
node probe/run-probe.mjs A-worker-r2   "$A/a/?data=/d/&big=big-100m.bin"        --runs 3 >/dev/null
node probe/run-probe.mjs S-static      "$S/s/?data=/d/&big=part-24m.bin"        --runs 3 >/dev/null
node probe/run-probe.mjs B-credentialless "$S/b-cl/?data=$R2/d/&big=big-100m.bin" --runs 3 >/dev/null
node probe/run-probe.mjs B-require-corp   "$S/b-rc/?data=$R2/d/&big=big-100m.bin" --runs 3 >/dev/null
node probe/run-probe.mjs C-pages       "$P/s/?data=/d/&big=part-24m.bin"        --runs 3 >/dev/null
node probe/run-probe.mjs C-pages-r2    "$P/b-rc/?data=$R2/d/&big=big-100m.bin"  --runs 3 >/dev/null
node probe/run-probe.mjs N-plain       "$S/plain/?data=/d/&big=part-24m.bin"    --runs 1 >/dev/null   # 負例: ヘッダ無し => crossOriginIsolated=false
python3 probe/show.py work/results/{A-worker-r2,S-static,B-credentialless,B-require-corp,C-pages,C-pages-r2,N-plain}.json

echo "[5] throughput / rate-limit (Node, 1000 x 1MiB, conc 16)"
for b in $S $A $P $R2; do node probe/stress.mjs $b/d/ 16 1000; done | tee work/results/stress-16.jsonl

if [ -n "${ALLOW_EMAIL:-}" ]; then
  echo "[6] Access"
  ALLOW_EMAIL=$ALLOW_EMAIL R2HOST=$R2HOST WORKERS_SUBDOMAIN=$SUB probe/access-probe.sh create
  ALLOW_EMAIL=$ALLOW_EMAIL R2HOST=$R2HOST WORKERS_SUBDOMAIN=$SUB probe/access-probe.sh test
  WORKERS_SUBDOMAIN=$SUB probe/access-probe.sh delete
fi
if [ "${BIG:-0}" = 1 ]; then
  echo "[7] Static Assets 2400 x 1MiB"
  node probe/gen-big.mjs ${BIG_N:-2400}
  (cd probe/worker-big && time bunx wrangler deploy 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E 'Success|Deployed') || true
  node probe/verify-big.mjs https://signature-studio-hosting-probe-big.$SUB.workers.dev/ 16 0
fi
[ "${KEEP:-0}" = 1 ] || bash probe/cleanup.sh
